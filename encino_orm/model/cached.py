import hashlib
import json
import logging

from encino_orm.base import Db

from .cache_backend import CacheBackend
from .model import Model, _set_private

logger = logging.getLogger("encino_orm")


class CachedModel(Model):
    """Modelo cuyo `load` persiste el resultado en un `CacheBackend` inyectable."""

    def __init__(self, db: Db = None, cache: CacheBackend = None, **kwargs):
        super().__init__(db=db, **kwargs)
        _set_private(self, "_cache", cache)

    @classmethod
    def _cache_key_for(cls, keys, values) -> str:
        """Deriva la clave de caché sin instancia (mismo formato que `_cache_key`)."""
        parts = [f"{k}={values[k]}" for k in keys]
        raw = f"{cls._table}:[{'&'.join(parts)}]"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _cache_key(self, keys) -> str:
        values = {k: getattr(self, k) for k in keys}
        return type(self)._cache_key_for(keys, values)

    @classmethod
    async def _delete_cached(cls, cache, key: str) -> None:
        """Borra una clave; fail-open si el backend falla (D-12).

        La escritura ya está commiteada: propagar daría un fallo falso al
        llamador. La lectura obsoleta queda acotada por el TTL.
        """
        try:
            await cache.delete(key)
        except Exception as exc:
            logger.warning("no se pudo invalidar la caché de %s: %r", cls._table, exc)

    async def _invalidate(self, keys=None) -> None:
        """Invalida las claves afectadas; fail-open si el backend falla (D-12).

        Se invalidan DOS dominios de clave: el de las claves de la escritura y el
        de la PK del modelo. `load(keys=...)` es público y cachea bajo claves
        arbitrarias (por defecto la PK), así que un write por una clave NO puede
        asumir que el dominio de lectura coincide: si difieren, la entrada de la
        PK quedaría obsoleta y un `load()` posterior devolvería el valor viejo
        (CR-01).
        """
        cache = self._cache
        if cache is None:
            return
        pk_keys = list(type(self)._pk_fields())
        write_keys = self._normalize_keys(keys, tuple(pk_keys))
        dominios = [write_keys]
        if write_keys != pk_keys:
            dominios.append(pk_keys)
        for dominio in dominios:
            await type(self)._delete_cached(cache, self._cache_key(dominio))

    async def load(self, keys=None, duration: int = 300) -> "CachedModel":
        keys = self._normalize_keys(keys, type(self)._pk_fields())
        cache = self._cache
        if cache is None:
            return await super().load(keys=keys)

        key = self._cache_key(keys)
        raw = await cache.get(key)
        if raw is not None:
            data = json.loads(raw)
            obj = type(self).model_validate(data)
            _set_private(obj, "_db", self._db)
            _set_private(obj, "__exists", True)
            _set_private(obj, "__dirties", [])
            _set_private(obj, "__loading", False)
            _set_private(obj, "_references", {})
            _set_private(obj, "_has_many", {})
            _set_private(obj, "_cache", cache)
            return obj

        obj = await super().load(keys=keys)
        if getattr(obj, "__exists"):
            payload = json.dumps(obj.model_dump(mode="json")).encode("utf-8")
            await cache.set(key, payload, duration)
        _set_private(obj, "_cache", cache)
        return obj

    async def update(self, keys=None, data=None) -> int:
        """Actualiza e invalida la clave afectada tras el commit (D-15)."""
        count = await super().update(keys=keys, data=data)
        await self._invalidate(keys)
        return count

    async def delete(self, keys=None, physical: bool = False) -> bool:
        """Borra (lógico o físico) e invalida la clave afectada (D-15)."""
        result = await super().delete(keys=keys, physical=physical)
        await self._invalidate(keys)
        return result

    async def upsert(self, conflict: list[str] | None = None, values: dict | None = None) -> int:
        """Upsert e invalida la clave del conflicto (D-11/D-15).

        `conflict=None` normaliza a la PK; con `conflict=["rfc"]` se invalida la
        clave derivada de `rfc` — solo la clave afectada, sin namespace.
        """
        count = await super().upsert(conflict=conflict, values=values)
        await self._invalidate(conflict)
        return count

    @classmethod
    async def insert_many(
        cls,
        db=None,
        rows: list[dict] | None = None,
        *,
        chunk: int | None = None,
        cache=None,
    ) -> int:
        """Inserta varias filas e invalida opcionalmente las claves afectadas (D-16).

        Sin `cache=` no se invalida: un INSERT puro no puede dejar obsoleta una
        clave existente sin violar la restricción UNIQUE de la PK. Con `cache=`,
        se invalida la clave de la PK del modelo presente en cada fila — el MISMO
        dominio con el que `load(keys=<PK>)` escribe. Un fallo de invalidación es
        fail-open (warning, no propaga; D-12).
        """
        total = await super().insert_many(db, rows, chunk=chunk)
        if cache is None or not rows:
            return total
        keys = cls._pk_fields()
        for row in rows:
            values = {k: row.get(k) for k in keys}
            if any(values[k] is None for k in keys):
                continue
            await cls._delete_cached(cache, cls._cache_key_for(keys, values))
        return total

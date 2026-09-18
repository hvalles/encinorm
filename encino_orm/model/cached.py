import hashlib
import json
import logging

from encino_orm.base import Db

from .cache_backend import CacheBackend
from .filter import Filter
from .model import Model, _serialize, _set_private
from .scope import current_scope

logger = logging.getLogger("encino_orm")


class CachedModel(Model):
    """Modelo cuyo `load` persiste el resultado en un `CacheBackend` inyectable."""

    def __init__(self, db: Db = None, cache: CacheBackend = None, **kwargs):
        super().__init__(db=db, **kwargs)
        _set_private(self, "_cache", cache)

    @classmethod
    def _cache_key_for(cls, keys, values) -> str:
        """Deriva la clave de caché sin instancia (mismo formato que `_cache_key`).

        El `scope()` activo forma parte de la clave (huella `digest()` del filtro):
        una entrada cacheada bajo un tenant NUNCA casa la clave de otro, así que un
        acierto no puede servir datos de otro tenant ni habilitar una escritura
        cruzada (CR-02). Sin scope la clave es la de siempre (compatibilidad).
        """
        parts = [f"{k}={values[k]}" for k in keys]
        raw = f"{cls._table}:[{'&'.join(parts)}]"
        s = current_scope()
        if s is not None:
            raw = f"{raw}|scope={s.digest()}"
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

    async def _resolve_pk_values(self, keys) -> list[dict] | None:
        """Aprende los valores de la PK REAL de TODAS las filas afectadas (CR-01).

        El dominio de caché es canónico (SOLO la PK), así que una escritura por
        claves no-PK (`update(keys=["grupo"])`, `upsert(conflict=["rfc"])`) necesita
        las PKs reales de las filas para invalidar sus entradas. Si la clave de
        escritura ES la PK se lee de la propia instancia; si no, `Model.update`/
        `delete` afectan a TODAS las filas que casan, así que se resuelven con un
        `SELECT` multi-fila ligado, con `scope` y con `include_deleted=True` (para no
        excluir filas recién soft-borradas). Se reutiliza `Model.search`; no se
        escribe SQL nuevo ni se interpola.

        Devuelve `None` si no hay caché que invalidar, si la fila no se puede
        identificar (alguna clave es `None`), si no hay ninguna fila afectada o si la
        resolución falla: jamás bloquea una escritura ya commiteada (D-12 fail-open,
        WR-02).
        """
        if self._cache is None:
            return None
        pk_keys = list(type(self)._pk_fields())
        try:
            write_keys = self._normalize_keys(keys, tuple(pk_keys))
            if write_keys == pk_keys:
                values = {k: getattr(self, k) for k in pk_keys}
                if any(v is None for v in values.values()):
                    return None
                return [values]
            # La escritura identifica la(s) fila(s) por claves no-PK (p. ej. `rfc`):
            # se reutiliza `Model.search` para heredar los parámetros LIGADOS, el
            # `current_scope()` activo y el filtrado multi-fila.
            if any(getattr(self, k) is None for k in write_keys):
                return None
            cond = None
            for k in write_keys:
                # El DML liga el valor SERIALIZADO (`Model.update` usa `_serialize`),
                # así que la sonda debe ligar el mismo valor: con un `datetime`/
                # `Decimal`/JSON crudo el WHERE de la sonda no casaría ninguna fila y
                # la entrada de la PK sobreviviría obsoleta (CR-R4-01).
                eq = Filter.eq(k, _serialize(getattr(self, k)))
                cond = eq if cond is None else cond & eq
            rows = await self.search(
                filter=cond,
                columns=list(type(self)._pk_cols()),
                include_deleted=True,
            )
            pks = [
                {k: getattr(r, k) for k in pk_keys}
                for r in rows
                if all(getattr(r, k) is not None for k in pk_keys)
            ]
            return pks or None
        except Exception as exc:
            logger.warning(
                "no se pudo resolver la PK de %s para invalidar la caché: %r",
                self._table,
                exc,
            )
            return None

    @staticmethod
    def _union(*lists) -> list[dict]:
        """Une listas de valores de PK deduplicando por una huella hashable.

        Tolerante a `None` (una sonda fallida no aporta candidatos). Acota el TOCTOU
        (WR-02): la unión de la sonda previa y la posterior incluye la fila a la que
        otra transacción pudo mover la clave entre ambas. La huella usa `repr` del
        valor (WR-R3-02): un valor de PK no hashable (`list`/`dict`, que pydantic y
        `_from_db` admiten) rompía el `seen.add` con `TypeError`; `repr` no cambia el
        dedupe de PKs escalares (int/str) porque cada valor tiene un `repr` estable.
        """
        seen = set()
        result = []
        for items in lists:
            if not items:
                continue
            for item in items:
                fingerprint = tuple(sorted((k, repr(v)) for k, v in item.items()))
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                result.append(item)
        return result

    async def _invalidate_after_write(self, *probe_lists) -> None:
        """Invalida la unión de las sondas sin poder fallar una escritura commiteada.

        `_union` puede lanzar (p. ej. un valor no hashable); la escritura ya está
        commiteada, así que propagar daría un fallo falso al llamador (D-12). Si la
        unión falla, se degrada a la concatenación de las sondas: peor dedupe, pero
        nunca una escritura reportada como fallida.
        """
        try:
            pks = self._union(*probe_lists)
        except Exception as exc:
            logger.warning("no se pudo unir las PKs a invalidar de %s: %r", self._table, exc)
            pks = [d for lst in probe_lists if lst for d in lst]
        await self._invalidate_pks(pks)

    async def _invalidate_pks(self, pk_values) -> None:
        """Borra la entrada de CADA fila afectada; fail-open (D-12).

        La clave se deriva del MISMO dominio que `load()` escribe (la PK), así que
        una escritura por cualquier clave elimina las entradas cacheadas de TODAS las
        filas que casan. La derivación va DENTRO del `try` (WR-02).
        """
        if self._cache is None or not pk_values:
            return
        pk_keys = list(type(self)._pk_fields())
        for values in pk_values:
            try:
                if not isinstance(values, dict) or any(v is None for v in values.values()):
                    continue
                key = type(self)._cache_key_for(pk_keys, values)
                await self._cache.delete(key)
            except Exception as exc:
                logger.warning("no se pudo invalidar la caché de %s: %r", self._table, exc)

    async def load(self, keys=None, duration: int = 300) -> "CachedModel":
        """Carga la fila cacheando SIEMPRE bajo la PK (dominio canónico).

        Una lectura por otra clave (`load(keys=["rfc"])`) consulta la BD, aprende
        la PK de la fila devuelta y recachea bajo ella: no acierta en caché y no
        deja entradas bajo claves arbitrarias, de modo que toda escritura puede
        invalidar la entrada de la fila (CR-01). La clave incorpora el `scope()`
        activo, así que un acierto nunca cruza tenants (CR-02).
        """
        read_keys = self._normalize_keys(keys, type(self)._pk_fields())
        cache = self._cache
        if cache is None:
            return await super().load(keys=read_keys)

        pk_keys = list(type(self)._pk_fields())
        if read_keys == pk_keys:
            raw = await cache.get(self._cache_key(read_keys))
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

        obj = await super().load(keys=read_keys)
        if getattr(obj, "__exists"):
            pk_values = {k: getattr(obj, k) for k in pk_keys}
            if all(v is not None for v in pk_values.values()):
                payload = json.dumps(obj.model_dump(mode="json")).encode("utf-8")
                await cache.set(type(self)._cache_key_for(pk_keys, pk_values), payload, duration)
        _set_private(obj, "_cache", cache)
        return obj

    async def update(self, keys=None, data=None) -> int:
        """Actualiza e invalida las entradas de TODAS las filas afectadas (D-15).

        La PK se resuelve ANTES y DESPUÉS de la escritura y se invalida la unión
        (WR-02): si otra transacción mueve la clave a otra fila entre ambas sondas,
        la re-sonda también la captura. Un fallo de resolución/invalidación es
        fail-open (D-12).
        """
        pks = await self._resolve_pk_values(keys)
        count = await super().update(keys=keys, data=data)
        pks_after = await self._resolve_pk_values(keys)
        await self._invalidate_after_write(pks, pks_after)
        return count

    async def delete(self, keys=None, physical: bool = False) -> bool:
        """Borra (lógico o físico) e invalida las entradas de las filas afectadas (D-15).

        La PK se resuelve ANTES del borrado (un borrado físico elimina la fila y la
        sonda posterior ya no la encontraría) y DESPUÉS para acotar el TOCTOU
        (WR-02); se invalida la unión. Fail-open (D-12).
        """
        pks = await self._resolve_pk_values(keys)
        result = await super().delete(keys=keys, physical=physical)
        pks_after = await self._resolve_pk_values(keys)
        await self._invalidate_after_write(pks, pks_after)
        return result

    async def upsert(self, conflict: list[str] | None = None, values: dict | None = None) -> int:
        """Upsert e invalida las entradas de las filas afectadas tras el commit (D-15).

        El caso canónico `upsert(conflict=["rfc"])` desde una instancia con el
        auto-`id` sin asignar resuelve la PK real (puede ser más de una si la clave
        de conflicto no es única) y borra esas entradas (CR-01). Re-sonda
        post-escritura para acotar el TOCTOU (WR-02); fail-open (D-12).
        """
        pks = await self._resolve_pk_values(conflict)
        count = await super().upsert(conflict=conflict, values=values)
        pks_after = await self._resolve_pk_values(conflict)
        await self._invalidate_after_write(pks, pks_after)
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

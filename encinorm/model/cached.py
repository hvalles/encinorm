import hashlib
import json

from encinorm.base import Db

from .cache_backend import CacheBackend
from .model import Model, _set_private


class CachedModel(Model):
    """Modelo cuyo `load` persiste el resultado en un `CacheBackend` inyectable."""

    def __init__(self, db: Db = None, cache: CacheBackend = None, **kwargs):
        super().__init__(db=db, **kwargs)
        _set_private(self, "_cache", cache)

    def _cache_key(self, keys) -> str:
        parts = [f"{k}={getattr(self, k)}" for k in keys]
        raw = f"{self._table}:[{'&'.join(parts)}]"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

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

"""Registro de modelos (nombre -> `Model`) e introspección de modelos."""


class Registry:
    def __init__(self):
        self._models = {}

    def register(self, model_cls) -> None:
        self._models[model_cls._table] = model_cls

    def get(self, name: str):
        return self._models[name]          # KeyError -> 404

    def names(self) -> list[str]:
        return sorted(self._models)


def register_introspection(router, registry: Registry) -> None:
    """Monta los endpoints `/models` y `/models/{name}` sobre `router`."""
    from fastapi import HTTPException

    @router.get("/models")
    async def models():
        return registry.names()

    @router.get("/models/{name}")
    async def model_schema(name: str):
        try:
            cls = registry.get(name)
        except KeyError:
            raise HTTPException(404, detail="modelo no encontrado")
        return cls.model_json_schema()

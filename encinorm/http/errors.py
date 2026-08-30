"""Mapeo de excepciones de encinorm a respuestas HTTP (`install_error_handlers`)."""

from encinorm.exceptions import QueryError
from encinorm.model.exceptions import FailOnUpdate, ValidationError


def install_error_handlers(app) -> None:
    """Registra los handlers globales (a nivel de app) una sola vez."""
    from fastapi.responses import JSONResponse

    @app.exception_handler(ValidationError)
    async def _validation(exc, request):
        # encinorm.ValidationError lleva el dict en `args[0]`
        return JSONResponse(status_code=422, content={"detail": exc.args[0]})

    @app.exception_handler(FailOnUpdate)
    async def _fail_update(exc, request):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(QueryError)
    async def _query_error(exc, request):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

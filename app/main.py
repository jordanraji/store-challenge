import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response

from app.catalog.router import router as catalog_router
from app.core.config import Settings
from app.core.database import make_session_factory
from app.core.errors import DomainError
from app.core.security import SecurityHeadersMiddleware
from app.imports.router import router as imports_router
from app.orders.router import router as orders_router
from app.web.presentation import ROOT, error_response
from app.web.router import router as web_router


def create_app(database_url: str | None = None) -> FastAPI:
    settings = Settings()
    factory = make_session_factory(database_url or settings.database_url)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
        yield
        factory.kw["bind"].dispose()

    application = FastAPI(
        title="Store", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None
    )
    application.state.session_factory = factory
    application.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret or secrets.token_urlsafe(48),
        same_site="lax",
        https_only=settings.secure_cookies,
        max_age=86400,
    )
    application.add_middleware(SecurityHeadersMiddleware)
    application.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")

    @application.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError) -> Response:
        if not request.url.path.startswith("/api/"):
            return error_response(request, exc)
        return JSONResponse(
            status_code=exc.status,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> Response:
        if not request.url.path.startswith("/api/"):
            return error_response(
                request,
                DomainError(422, "invalid_request", "Check the page address and try again."),
            )
        details = [
            {
                "field": ".".join(map(str, error["loc"])),
                "message": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Invalid request",
                    "details": details,
                }
            },
        )

    @application.get("/docs", include_in_schema=False)
    def swagger_docs(request: Request) -> HTMLResponse:
        response = get_swagger_ui_html(
            openapi_url="/openapi.json",
            title="Store - Swagger UI",
            swagger_favicon_url="/static/favicon.svg",
        )
        html = (
            bytes(response.body)
            .decode()
            .replace("<script>", f'<script nonce="{request.state.csp_nonce}">')
        )
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    @application.get("/redoc", include_in_schema=False)
    def redoc_docs(request: Request) -> HTMLResponse:
        return get_redoc_html(
            openapi_url="/openapi.json",
            title="Store - ReDoc",
            redoc_favicon_url="/static/favicon.svg",
            with_google_fonts=False,
        )

    @application.get("/health/live", tags=["health"])
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/health/ready", tags=["health"])
    def ready() -> JSONResponse:
        try:
            with factory() as session:
                session.execute(text("SELECT 1"))
        except OperationalError:
            return JSONResponse(status_code=503, content={"status": "unavailable"})
        return JSONResponse(content={"status": "ok"})

    application.include_router(catalog_router)
    application.include_router(imports_router)
    application.include_router(orders_router)
    application.include_router(web_router)
    return application


app = create_app()

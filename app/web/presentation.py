from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse

from app.core.errors import DomainError
from app.web.security import initialize_session

ROOT = Path(__file__).parent
templates = Jinja2Templates(directory=str(ROOT / "templates"))
templates.env.autoescape = True
templates.env.filters["money"] = lambda value: f"${Decimal(value):,.2f}"


def render(request: Request, template: str, status: int = 200, **context: Any) -> HTMLResponse:
    initialize_session(request)
    return templates.TemplateResponse(
        request=request,
        name=template,
        context={
            "bag_count": sum(request.session["cart"].values()),
            "csrf": request.session["csrf"],
            **context,
        },
        status_code=status,
        headers={"Cache-Control": "no-store", "Vary": "HX-Request, Cookie"},
    )


def error_response(request: Request, error: DomainError) -> HTMLResponse:
    return render(request, "error.html", error.status, error=error)

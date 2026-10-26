import secrets
from uuid import uuid4

from fastapi import Request
from starlette.datastructures import FormData

from app.core.errors import DomainError


def initialize_session(request: Request) -> None:
    if "client_id" not in request.session:
        request.session["client_id"] = str(uuid4())
    if "csrf" not in request.session:
        request.session["csrf"] = secrets.token_urlsafe(32)
    if "cart" not in request.session:
        request.session["cart"] = {}


async def checked_form(request: Request) -> FormData:
    form = await request.form(max_files=1, max_fields=30, max_part_size=2 * 1024 * 1024)
    token = form.get("csrf", "")
    expected = request.session.get("csrf", "")
    if not isinstance(token, str) or not expected or not secrets.compare_digest(token, expected):
        raise DomainError(
            403, "invalid_csrf", "Your session changed. Reload the page and try again."
        )
    return form

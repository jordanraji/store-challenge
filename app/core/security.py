import secrets
from html.parser import HTMLParser

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class MarkupDetector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.found_markup = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.found_markup = True

    def handle_endtag(self, tag: str) -> None:
        self.found_markup = True

    def handle_comment(self, data: str) -> None:
        self.found_markup = True

    def handle_decl(self, decl: str) -> None:
        self.found_markup = True

    def unknown_decl(self, data: str) -> None:
        self.found_markup = True


def validate_plain_text(value: str) -> str:
    if any(
        (ord(character) < 32 and character not in "\t\n\r") or ord(character) == 127
        for character in value
    ):
        raise ValueError("Control characters are not allowed")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("Text must contain valid Unicode characters") from exc
    detector = MarkupDetector()
    try:
        detector.feed(value)
        detector.close()
    except (AssertionError, ValueError) as exc:
        raise ValueError("Use plain text only; malformed HTML markup is not allowed") from exc
    if detector.found_markup:
        raise ValueError("Use plain text only; HTML tags and markup are not allowed")
    return value


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        nonce = secrets.token_urlsafe(24)
        scope.setdefault("state", {})["csp_nonce"] = nonce
        docs = scope["path"] in {"/docs", "/redoc"}
        scripts = f"'self' 'nonce-{nonce}' https://cdn.jsdelivr.net" if docs else "'self'"
        styles = "'self' 'unsafe-inline' https://cdn.jsdelivr.net" if docs else "'self'"
        policy = (
            f"default-src 'none'; script-src {scripts}; script-src-attr 'none'; "
            f"style-src {styles}; img-src 'self' data:; font-src 'self'; connect-src 'self'; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        )

        async def send_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Content-Security-Policy"] = policy
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "same-origin"
            await send(message)

        await self.app(scope, receive, send_headers)

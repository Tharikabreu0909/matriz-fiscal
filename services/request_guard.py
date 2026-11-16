"""Protecao local contra DNS rebinding e CSRF (P0-S1). Sem token: cenario de um operador local."""
import json
import os
from urllib.parse import urlsplit

from services.app_logging import logger

DEFAULT_PORTS = (8141, 8145, 8146)
SAFE_METHODS = {"HEAD", "OPTIONS"}
# Unicos caminhos que aceitam requisicoes cross-site (somente leitura, sem dados).
OPEN_PATHS = {"/", "/static/app.css", "/api/health"}


def allowed_hosts_from_env() -> set[str]:
    """Hosts padrao + CHECKFISCAL_ALLOWED_HOSTS (CSV, aditivo), em minusculas."""
    hosts = {f"{name}:{port}" for name in ("127.0.0.1", "localhost") for port in DEFAULT_PORTS}
    extra = os.environ.get("CHECKFISCAL_ALLOWED_HOSTS", "")
    hosts.update(item.strip().lower() for item in extra.split(",") if item.strip())
    return hosts


def is_guarded(method: str, path: str) -> bool:
    method = method.upper()
    if method in SAFE_METHODS:
        return False
    if method == "GET":  # GETs sob /api/ podem gravar (backup, relatorio, process)
        return path.startswith("/api/") and path not in OPEN_PATHS
    return True


def origin_host(origin: str) -> str | None:
    """'host:porta' de um Origin http; None se for 'null', https ou invalido (o app nao tem TLS)."""
    try:
        parts = urlsplit(origin.strip())
        if parts.scheme != "http" or not parts.hostname or parts.path not in ("", "/"):
            return None
        host = parts.hostname.lower()
        return f"{host}:{parts.port}" if parts.port else host
    except ValueError:
        return None


def check(method: str, path: str, host: str | None, origin: str | None,
          fetch_site: str | None, allowed: set[str]) -> tuple[int, str] | None:
    """None se permitido; senao (status, code)."""
    if (host or "").strip().lower() not in allowed:
        return 400, "HOST_NOT_ALLOWED"
    if not is_guarded(method, path):
        return None
    if origin is not None and origin_host(origin) not in allowed:
        return 403, "CROSS_ORIGIN_BLOCKED"
    if fetch_site is not None and fetch_site.strip().lower() not in ("same-origin", "none"):
        return 403, "CROSS_ORIGIN_BLOCKED"
    return None


class RequestGuardMiddleware:
    """ASGI puro: decide antes do handler e nunca le o corpo."""

    def __init__(self, app, allowed_hosts: set[str] | None = None):
        self.app = app
        self.allowed = allowed_hosts if allowed_hosts is not None else allowed_hosts_from_env()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {}
        for key, value in scope["headers"]:
            headers.setdefault(key.decode("latin-1").lower(), value.decode("latin-1"))
        verdict = check(
            scope["method"], scope["path"], headers.get("host"),
            headers.get("origin"), headers.get("sec-fetch-site"), self.allowed,
        )
        if verdict is None:
            return await self.app(scope, receive, send)
        status, code = verdict
        logger.warning("Bloqueado %s %s: %s", scope["method"], scope["path"], code)
        body = json.dumps({"code": code}).encode()
        await send({"type": "http.response.start", "status": status, "headers": [
            (b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})

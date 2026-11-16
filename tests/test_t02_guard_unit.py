import pytest

from services.request_guard import allowed_hosts_from_env, check, is_guarded, origin_host

ALLOWED = {"127.0.0.1:8141", "localhost:8145"}


@pytest.mark.parametrize("method,path,expected", [
    ("POST", "/api/system/restore", True),
    ("DELETE", "/api/companies/1", True),
    ("POST", "/api/system/restore/", True),
    ("GET", "/api/system/backup", True),
    ("GET", "/api/process/3", True),
    ("GET", "/api/health", False),
    ("GET", "/", False),
    ("PUT", "/api/health", True),
    ("GET", "/static/app.css", False),
    ("HEAD", "/api/system/backup", False),
    ("OPTIONS", "/api/companies", False),
])
def test_is_guarded(method, path, expected):
    assert is_guarded(method, path) is expected


def test_allowed_hosts_defaults_and_additive(monkeypatch):
    monkeypatch.delenv("CHECKFISCAL_ALLOWED_HOSTS", raising=False)
    base = allowed_hosts_from_env()
    assert {"127.0.0.1:8141", "localhost:8146", "localhost:8145"} <= base
    monkeypatch.setenv("CHECKFISCAL_ALLOWED_HOSTS", "TestServer, ,foo:9")
    assert allowed_hosts_from_env() == base | {"testserver", "foo:9"}


@pytest.mark.parametrize("origin,expected", [
    ("http://127.0.0.1:8141", "127.0.0.1:8141"),
    ("http://LOCALHOST:8145/", "localhost:8145"),
    ("https://localhost:8145", None),
    ("null", None),
    ("", None),
    ("ftp://localhost:8145", None),
    ("http://localhost:8145/x", None),
    ("http://localhost:bad", None),
])
def test_origin_host(origin, expected):
    assert origin_host(origin) == expected


def run(method="POST", path="/api/system/restore", host="127.0.0.1:8141", origin=None, site=None):
    return check(method, path, host, origin, site, ALLOWED)


def test_host_rules():
    assert run(host="evil.example") == (400, "HOST_NOT_ALLOWED")
    assert run(host=None) == (400, "HOST_NOT_ALLOWED")
    assert run(host="LOCALHOST:8145") is None
    assert run(method="GET", path="/api/health", host="evil.example")[0] == 400


def test_origin_and_fetch_site_rules():
    assert run() is None  # CLI sem cabecalhos
    assert run(origin="http://127.0.0.1:8141", site="same-origin") is None
    assert run(site="none") is None
    for origin in ("https://evil.example", "null", "http://127.0.0.1:3000"):
        assert run(origin=origin) == (403, "CROSS_ORIGIN_BLOCKED")
    for site in ("cross-site", "same-site", ""):
        assert run(site=site) == (403, "CROSS_ORIGIN_BLOCKED")
    # contradicao: Origin permitido, Sec-Fetch-Site cross-site e o inverso
    assert run(origin="http://127.0.0.1:8141", site="cross-site")[0] == 403
    assert run(origin="https://evil.example", site="same-origin")[0] == 403


def test_open_paths_accept_cross_site():
    assert run(method="GET", path="/api/health", site="cross-site") is None
    assert run(method="GET", path="/", origin="https://evil.example") is None


def _asgi(method, path, headers):
    """Executa o middleware ASGI com cabecalhos crus (repetidos); devolve (status, app_chamado)."""
    import asyncio

    from services.request_guard import RequestGuardMiddleware

    seen = {"called": False, "status": None}

    async def inner(scope, receive, send):
        seen["called"] = True

    async def send(message):
        if message["type"] == "http.response.start":
            seen["status"] = message["status"]

    scope = {"type": "http", "method": method, "path": path,
             "headers": [(k.encode(), v.encode()) for k, v in headers]}
    asyncio.run(RequestGuardMiddleware(inner, ALLOWED)(scope, None, send))
    return seen["status"], seen["called"]


GOOD = ("host", "127.0.0.1:8141")


@pytest.mark.parametrize("method,path", [("POST", "/api/companies"), ("GET", "/api/health"), ("GET", "/")])
@pytest.mark.parametrize("headers", [
    [GOOD, GOOD],  # igual, mas repetido
    [GOOD, ("host", "evil.example")],
    [("host", "evil.example"), GOOD],
])
def test_duplicate_host_is_400_everywhere(method, path, headers):
    assert _asgi(method, path, headers) == (400, False)


@pytest.mark.parametrize("extra", [
    [("origin", "http://127.0.0.1:8141"), ("origin", "http://127.0.0.1:8141")],
    [("origin", "http://127.0.0.1:8141"), ("origin", "https://evil.example")],
    [("sec-fetch-site", "same-origin"), ("sec-fetch-site", "same-origin")],
    [("sec-fetch-site", "same-origin"), ("sec-fetch-site", "cross-site")],
])
def test_duplicate_origin_or_fetch_site_blocked_only_when_guarded(extra):
    assert _asgi("POST", "/api/companies", [GOOD, *extra]) == (403, False)
    assert _asgi("GET", "/api/health", [GOOD, *extra]) == (None, True)


def test_single_headers_still_pass_at_asgi_level():
    headers = [GOOD, ("origin", "http://127.0.0.1:8141"), ("sec-fetch-site", "same-origin")]
    assert _asgi("POST", "/api/companies", headers) == (None, True)

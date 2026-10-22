from app import app


def test_bulk_pgdas_route_is_available():
    paths = {route.path for route in app.routes}
    assert "/api/upload-pgdas-auto" in paths


def test_app_version_is_140():
    assert app.version == "1.45.0"

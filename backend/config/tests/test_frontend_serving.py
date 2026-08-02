"""In DEBUG the backend serves `frontend/` at the site root, so `runserver` alone
puts the whole system on one origin (http://localhost:8000/)."""

import pytest
from django.conf import settings


@pytest.fixture(autouse=True)
def _debug(settings):
    # The frontend catch-all is registered at import time behind `if settings.DEBUG`,
    # and the test settings run with DEBUG off; reload the URLconf with it on.
    settings.DEBUG = True
    from importlib import reload

    from django.urls import clear_url_caches

    import config.urls

    reload(config.urls)
    clear_url_caches()
    yield
    settings.DEBUG = False
    reload(config.urls)
    clear_url_caches()


def test_root_serves_the_landing_page(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/html")


@pytest.mark.parametrize(
    "path",
    ["/login.html", "/account.html", "/rider/index.html", "/css/styles.css"],
)
def test_frontend_files_are_served(client, path):
    assert client.get(path).status_code == 200


def test_directory_paths_resolve_to_index(client):
    """`/rider/` behaves like it would on any static server."""
    assert client.get("/rider/").status_code == 200


def test_operator_portal_is_not_shadowed_by_django_admin(client):
    """Django's admin moved to /django-admin/ so /admin/*.html stays the frontend's."""
    response = client.get("/admin/index.html")

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/html")
    assert client.get("/django-admin/").status_code in (302, 200)


def test_api_routes_win_over_the_catch_all(client):
    response = client.get("/api/public-config/")

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/json")


@pytest.mark.parametrize(
    "path",
    ["/../backend/.env", "/js/../../backend/manage.py", "/nope.html"],
)
def test_traversal_and_missing_files_404(client, path):
    assert client.get(path).status_code == 404


def test_frontend_dir_points_at_the_static_site():
    assert (settings.FRONTEND_DIR / "index.html").is_file()

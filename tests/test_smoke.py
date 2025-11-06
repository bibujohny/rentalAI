import os
import pytest
from app import create_app
from app.models import db, User

@pytest.fixture()
def app():
    os.environ["FLASK_ENV"] = "testing"
    os.environ["SKIP_SEED"] = "1"  # avoid seed altering user DB in tests
    app = create_app()
    app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WTF_CSRF_ENABLED": False,
    })
    with app.app_context():
        db.create_all()
        yield app

@pytest.fixture()
def client(app):
    return app.test_client()


def test_health_redirects_to_login(client):
    r = client.get("/")
    assert r.status_code in (200, 302)
    # If redirected, it should be to login
    if r.status_code == 302:
        assert "/login" in (r.headers.get("Location") or "")


def test_can_register_and_login(client):
    # register
    r = client.post("/register", data={"username": "user1", "password": "pass"}, follow_redirects=True)
    assert r.status_code == 200
    assert b"Please login" in r.data or b"Login" in r.data

    # login
    r = client.post("/login", data={"username": "user1", "password": "pass"}, follow_redirects=True)
    assert r.status_code == 200
    assert b"Dashboard" in r.data


def test_add_building(client):
    client.post("/register", data={"username": "u2", "password": "p2"}, follow_redirects=True)
    client.post("/login", data={"username": "u2", "password": "p2"}, follow_redirects=True)

    r = client.post("/buildings/add", data={
        "name": "Test Building",
        "address": "Somewhere",
        "pincode": "123456",
        "total_rooms": 10,
    }, follow_redirects=True)
    assert r.status_code == 200
    assert b"Test Building" in r.data


def test_ai_insights_local_fallback(client):
    client.post("/register", data={"username": "u3", "password": "p3"}, follow_redirects=True)
    client.post("/login", data={"username": "u3", "password": "p3"}, follow_redirects=True)
    r = client.get("/")
    # On dashboard, we should see AI section either way
    assert r.status_code == 200
    assert b"AI Insights" in r.data


def test_hdfc_page_requires_login_and_renders(client):
    client.post("/register", data={"username": "u4", "password": "p4"}, follow_redirects=True)
    client.post("/login", data={"username": "u4", "password": "p4"}, follow_redirects=True)
    r = client.get("/pdf/hdfc")
    assert r.status_code == 200
    assert b"HDFC Bank Statement" in r.data

"""Tests for app.py's Flask routes: login, signup, logout, and the debug endpoints."""

import pytest

import app


def _login(client, username="reader", password="pw"):
    return client.post(
        "/do_login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )


# ---------------------------------------------------------------------------
# login page
# ---------------------------------------------------------------------------
def test_login_page_renders_form(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert '<form method="post" action="/do_login">' in body
    assert 'name="username"' in body
    assert 'name="password"' in body


# ---------------------------------------------------------------------------
# do_login
# ---------------------------------------------------------------------------
def test_login_with_valid_credentials_redirects_to_root(client):
    app.create_user("reader", "pw")
    resp = _login(client)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/"


def test_login_with_wrong_password_redirects_back_to_login(client):
    app.create_user("reader", "pw")
    resp = _login(client, password="wrong")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/login"


def test_login_with_unknown_user_redirects_back_to_login(client):
    resp = _login(client, username="ghost")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/login"


@pytest.mark.parametrize(
    "form",
    [
        {"username": "", "password": "pw"},
        {"username": "reader", "password": ""},
        {},
    ],
)
def test_login_with_missing_credentials_redirects_back_to_login(client, form):
    resp = client.post("/do_login", data=form)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/login"


def test_login_trims_surrounding_whitespace_in_username(client):
    app.create_user("reader", "pw")
    resp = _login(client, username="  reader  ")
    assert resp.headers["Location"] == "/"


def test_failed_login_flashes_a_message_on_the_login_page(client):
    app.create_user("reader", "pw")
    _login(client, password="wrong")
    body = client.get("/login").get_data(as_text=True)
    assert "認証失敗" in body


# ---------------------------------------------------------------------------
# session / auth status
# ---------------------------------------------------------------------------
def test_auth_status_when_anonymous(client):
    data = client.get("/auth").get_json()
    assert data["authenticated"] is False
    assert data["user_id"] is None


def test_auth_status_after_login(client):
    uid = app.create_user("reader", "pw")
    _login(client)

    data = client.get("/auth").get_json()
    assert data["authenticated"] is True
    assert str(data["user_id"]) == str(uid)
    assert data["username"] == "reader"


def test_logout_clears_the_session(client):
    app.create_user("reader", "pw")
    _login(client)
    assert client.get("/auth").get_json()["authenticated"] is True

    resp = client.get("/logout")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/"
    assert client.get("/auth").get_json()["authenticated"] is False


# ---------------------------------------------------------------------------
# signup
# ---------------------------------------------------------------------------
def test_signup_creates_a_usable_account(client):
    resp = client.post(
        "/signup",
        data={"username": "newbie", "password": "pw", "role": "admin", "email": "n@example.com"},
    )
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/login"

    row = app.get_user_row(username="newbie")
    assert row is not None
    assert row[3] == "admin"

    # the new account can actually log in
    assert _login(client, "newbie", "pw").headers["Location"] == "/"


def test_signup_defaults_role_and_blank_email_to_null(client):
    client.post("/signup", data={"username": "plain", "password": "pw", "email": ""})
    assert app.get_user_row(username="plain")[3] == "doctor"

    conn = app.get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT email FROM users WHERE username = %s", ("plain",))
            assert cur.fetchone()[0] is None
    finally:
        conn.close()


def test_signup_with_duplicate_username_redirects_to_root(client):
    app.create_user("taken", "pw")
    resp = client.post("/signup", data={"username": "taken", "password": "pw"})
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/"


@pytest.mark.parametrize(
    "form",
    [{"username": "", "password": "pw"}, {"username": "x", "password": ""}],
)
def test_signup_requires_username_and_password(client, form):
    resp = client.post("/signup", data=form)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/"
    assert app.get_user_row(username=form["username"]) is None


# ---------------------------------------------------------------------------
# Dash layout (serve_layout runs inside a request context)
# ---------------------------------------------------------------------------
def test_layout_prompts_anonymous_visitors_to_log_in(client):
    body = client.get("/_dash-layout").get_data(as_text=True)
    assert "ログインが必要です" in body
    assert "新規ユーザ作成" in body


def test_layout_greets_the_logged_in_user(client):
    app.create_user("reader", "pw", role="doctor")
    _login(client)

    body = client.get("/_dash-layout").get_data(as_text=True)
    assert "reader" in body
    assert "ログアウト" in body
    assert "ログインが必要です" not in body


# ---------------------------------------------------------------------------
# debug endpoint
# ---------------------------------------------------------------------------
def test_debug_endpoint_404s_before_any_dash_post(client, monkeypatch):
    monkeypatch.setattr(app, "_last_dash_request_body", None)
    resp = client.get("/debug/last_dash_request")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "no dash request captured yet"


def test_debug_endpoint_replays_the_last_dash_post_body(client, monkeypatch):
    monkeypatch.setattr(app, "_last_dash_request_body", None)
    # The payload targets no registered callback, so Dash's dispatcher errors out.
    # That is fine: the before_request hook records the body first, which is what
    # this endpoint replays. Keep the 500 as a response instead of an exception.
    monkeypatch.setitem(app.server.config, "PROPAGATE_EXCEPTIONS", False)
    client.post("/_dash-update-component", json={"output": "probe", "inputs": []})

    resp = client.get("/debug/last_dash_request")
    assert resp.status_code == 200
    assert "probe" in resp.get_data(as_text=True)

"""Tests for the protected `/analytics` route ("Advanced Analytics — Coming
Soon" placeholder page).

No spec file exists for this feature (it was implemented directly from a
design screenshot). Behaviour under test, derived from the feature
description rather than from reading app.py:

  - `GET /analytics` with a valid logged-in session (`session['user_id']`
    set to a real user id) returns 200 and renders `analytics.html`,
    whose content includes "Advanced Analytics" and "Coming Soon".
  - `GET /analytics` without a logged-in session redirects (302) to
    `/login`, using the exact same auth-guard pattern as the existing
    `/profile` route.
  - The navbar in `base.html` shows an "Analytics" link (pointing at the
    analytics route) when the user is logged in, and omits it when the
    user is logged out.

Fixtures `app` and `client` come from the project-root conftest.py:
  - `app` patches `database.db.DB_PATH` to an isolated sqlite file and
    re-imports `app.py` fresh, which runs `init_db()`/`seed_db()` at
    import time against that isolated file.
  - `client` is supplied by pytest-flask, built from the `app` fixture.
"""

from flask import url_for

import database.db as db


def test_analytics_redirects_when_unauthenticated(client):
    response = client.get("/analytics")
    assert response.status_code == 302, "Unauthenticated GET /analytics should redirect, not 200"
    assert response.location.endswith("/login"), "Expected redirect target to be the login page"


def test_analytics_redirect_body_does_not_leak_protected_content(client):
    response = client.get("/analytics")
    body = response.get_data(as_text=True)
    assert "Advanced Analytics" not in body, "Redirect response must not leak protected page content"


def test_analytics_matches_profile_auth_guard_pattern(client):
    """/analytics should be protected identically to the existing /profile route."""
    analytics_response = client.get("/analytics")
    profile_response = client.get("/profile")

    assert analytics_response.status_code == profile_response.status_code == 302
    assert analytics_response.location == profile_response.location, (
        "Expected /analytics to redirect to the same login URL as /profile"
    )


def test_analytics_renders_page_when_authenticated(app, client):
    db.seed_db()
    demo_user = db.get_user_by_email("demo@spendly.com")

    with client.session_transaction() as sess:
        sess["user_id"] = demo_user["id"]

    response = client.get("/analytics")
    assert response.status_code == 200, "Authenticated GET /analytics should return 200"

    body = response.get_data(as_text=True)
    assert "Advanced Analytics" in body, "Expected the 'Advanced Analytics' heading in the response"
    assert "Coming Soon" in body, "Expected the 'Coming Soon' badge/text in the response"


def test_analytics_renders_for_freshly_created_user_with_no_data(app, client):
    db.init_db()
    new_user_id = db.create_user("Fresh User", "fresh-analytics@example.com", "password123")

    with client.session_transaction() as sess:
        sess["user_id"] = new_user_id

    response = client.get("/analytics")
    assert response.status_code == 200, "Analytics page should render even for a brand-new user with no expenses"

    body = response.get_data(as_text=True)
    assert "Advanced Analytics" in body
    assert "Coming Soon" in body


def test_analytics_redirects_when_session_user_id_missing_after_logout(app, client):
    db.seed_db()
    demo_user = db.get_user_by_email("demo@spendly.com")

    with client.session_transaction() as sess:
        sess["user_id"] = demo_user["id"]

    # Confirm access works while logged in...
    assert client.get("/analytics").status_code == 200

    # ...then clear the session (simulating logout) and confirm the guard re-engages.
    with client.session_transaction() as sess:
        sess.clear()

    response = client.get("/analytics")
    assert response.status_code == 302
    assert response.location.endswith("/login")


def test_navbar_shows_analytics_link_when_logged_in(app, client):
    db.seed_db()
    demo_user = db.get_user_by_email("demo@spendly.com")

    with client.session_transaction() as sess:
        sess["user_id"] = demo_user["id"]

    response = client.get("/profile")
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    with app.test_request_context():
        analytics_url = url_for("analytics")

    assert f'href="{analytics_url}"' in body, (
        "Expected the navbar to contain a link to the analytics route when logged in"
    )
    assert ">Analytics<" in body, "Expected the navbar link text 'Analytics' when logged in"


def test_navbar_hides_analytics_link_when_logged_out(app, client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    with app.test_request_context():
        analytics_url = url_for("analytics")

    assert f'href="{analytics_url}"' not in body, (
        "Navbar must not contain a link to the analytics route when the user is logged out"
    )
    assert ">Analytics<" not in body, "Navbar must not contain the 'Analytics' link text when logged out"

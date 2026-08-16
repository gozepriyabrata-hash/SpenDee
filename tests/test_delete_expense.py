"""Tests for the "Delete Expense" feature (Step 9): `POST /expenses/<id>/delete`
and the new `database/db.py` helper it depends on.

Derived from the authoritative spec at `.claude/specs/09-delete-expense.md`, not
from reading `app.py`'s implementation. Behaviour under test:

  - `remove_expense(expense_id, user_id)` issues a parameterised
    `DELETE FROM expenses WHERE id = ? AND user_id = ?`: it removes the row
    when the caller owns the expense, and silently affects zero rows (no
    exception) when the `user_id` doesn't match the expense's owner or when
    the `expense_id` doesn't exist.
  - `POST /expenses/<id>/edit`-style auth guard: `POST /expenses/<id>/delete`
    requires an authenticated session, following the same pattern as
    `/expenses/add` and `/expenses/<id>/edit`.
  - `POST /expenses/<id>/delete` for the logged-in user's own expense deletes
    the row and redirects (302) to `/profile`.
  - `POST /expenses/<id>/delete` for another user's expense, or for a
    non-existent id, returns 404 and leaves the DB unchanged.
  - `GET /expenses/<id>/delete` is not allowed — the route is POST-only, so a
    bare GET must return 405, regardless of auth state.

Fixtures `app` and `client` come from the project-root conftest.py:
  - `app` patches `database.db.DB_PATH` to an isolated sqlite file and
    re-imports `app.py` fresh, which runs `init_db()`/`seed_db()` at import
    time against that isolated file.
  - `client` is supplied by pytest-flask, built from the `app` fixture.
  - `temp_db` (also from conftest.py) gives pure `database/db.py` unit tests
    an isolated DB without going through Flask at all.
"""

from datetime import date

import database.db as db

PROFILE_URL = "/profile"


def _delete_url(expense_id):
    return f"/expenses/{expense_id}/delete"


def _login_as(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def _fresh_user(name="Fresh User", email="fresh-delete-expense@example.com"):
    db.init_db()
    return db.create_user(name, email, "password123")


def _fresh_expense(user_id, **overrides):
    """Create an expense row via `db.create_expense` to have something to delete."""
    defaults = {
        "amount": 25.00,
        "category": "Food",
        "expense_date": date.today().isoformat(),
        "description": "Original description",
    }
    defaults.update(overrides)
    return db.create_expense(
        user_id,
        defaults["amount"],
        defaults["category"],
        defaults["expense_date"],
        defaults["description"],
    )


# ---------------------------------------------------------------------------
# Unit tests: remove_expense
# ---------------------------------------------------------------------------


def test_delete_expense_removes_row_for_correct_user(temp_db):
    user_id = temp_db.create_user("Owner", "owner-delete@example.com", "password123")
    expense_id = _fresh_expense(user_id)

    db.remove_expense(expense_id, user_id)

    row = db.get_expense_by_id(expense_id, user_id)
    assert row is None, "Expected the row to be removed from the DB after remove_expense"


def test_delete_expense_wrong_user_leaves_row_and_raises_no_error(temp_db):
    owner_id = temp_db.create_user("Owner", "owner-delete-guard@example.com", "password123")
    other_id = temp_db.create_user("Other", "other-delete-guard@example.com", "password123")
    expense_id = _fresh_expense(owner_id, amount=10.00, category="Food", description="Original")

    # Calling with the wrong user_id must not raise, and must affect 0 rows.
    db.remove_expense(expense_id, other_id)

    row = db.get_expense_by_id(expense_id, owner_id)
    assert row is not None, "Row must remain in the DB when remove_expense is called with the wrong user_id"
    assert float(row["amount"]) == 10.00
    assert row["category"] == "Food"
    assert row["description"] == "Original"


def test_delete_expense_nonexistent_id_raises_no_error_and_db_unchanged(temp_db):
    user_id = temp_db.create_user("Owner", "owner-delete-missing@example.com", "password123")
    expense_id = _fresh_expense(user_id)

    # Deleting a non-existent id must not raise.
    db.remove_expense(999999, user_id)

    # The real row must be untouched.
    row = db.get_expense_by_id(expense_id, user_id)
    assert row is not None, "remove_expense on a non-existent id must not affect unrelated rows"


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------


def test_post_delete_expense_redirects_when_unauthenticated(app, client):
    user_id = _fresh_user()
    expense_id = _fresh_expense(user_id)

    response = client.post(_delete_url(expense_id))

    assert response.status_code == 302, "Unauthenticated POST /expenses/<id>/delete should redirect, not delete"
    assert response.location.endswith("/login"), "Expected redirect target to be the login page"


def test_post_delete_expense_unauthenticated_does_not_delete_row(app, client):
    user_id = _fresh_user()
    expense_id = _fresh_expense(user_id)

    client.post(_delete_url(expense_id))

    row = db.get_expense_by_id(expense_id, user_id)
    assert row is not None, "Unauthenticated POST must not delete the expense"


# ---------------------------------------------------------------------------
# POST happy path
# ---------------------------------------------------------------------------


def test_post_delete_expense_own_expense_redirects_to_profile(app, client):
    user_id = _fresh_user()
    expense_id = _fresh_expense(user_id)
    _login_as(client, user_id)

    response = client.post(_delete_url(expense_id))

    assert response.status_code == 302, "Valid POST /expenses/<id>/delete should redirect"
    assert response.location.endswith(PROFILE_URL), "Expected redirect to /profile after deleting an expense"


def test_post_delete_expense_own_expense_removes_row_from_db(app, client):
    user_id = _fresh_user()
    expense_id = _fresh_expense(user_id)
    _login_as(client, user_id)

    client.post(_delete_url(expense_id))

    row = db.get_expense_by_id(expense_id, user_id)
    assert row is None, "Expected the expense row to no longer exist after deletion"


def test_post_delete_expense_does_not_remove_other_users_expenses(app, client):
    user_id = _fresh_user()
    other_expense_owner = _fresh_user(name="Other Owner", email="other-owner-delete@example.com")
    own_expense_id = _fresh_expense(user_id)
    other_expense_id = _fresh_expense(other_expense_owner)
    _login_as(client, user_id)

    client.post(_delete_url(own_expense_id))

    other_row = db.get_expense_by_id(other_expense_id, other_expense_owner)
    assert other_row is not None, "Deleting one expense must not affect another user's expenses"


# ---------------------------------------------------------------------------
# Ownership guard (404s)
# ---------------------------------------------------------------------------


def test_post_delete_expense_other_users_expense_returns_404(app, client):
    owner_id = _fresh_user(name="Owner", email="owner-post404-delete@example.com")
    other_id = _fresh_user(name="Other", email="other-post404-delete@example.com")
    expense_id = _fresh_expense(owner_id, amount=10.00, category="Food", description="Original")
    _login_as(client, other_id)

    response = client.post(_delete_url(expense_id))

    assert response.status_code == 404, "POST to delete another user's expense must return 404"


def test_post_delete_expense_other_users_expense_row_still_exists(app, client):
    owner_id = _fresh_user(name="Owner", email="owner-post404-delete-row@example.com")
    other_id = _fresh_user(name="Other", email="other-post404-delete-row@example.com")
    expense_id = _fresh_expense(owner_id, amount=10.00, category="Food", description="Original")
    _login_as(client, other_id)

    client.post(_delete_url(expense_id))

    row = db.get_expense_by_id(expense_id, owner_id)
    assert row is not None, "Expense must remain in the DB when a non-owner attempts to delete it"
    assert float(row["amount"]) == 10.00
    assert row["category"] == "Food"
    assert row["description"] == "Original"


def test_post_delete_expense_nonexistent_id_returns_404(app, client):
    user_id = _fresh_user()
    _login_as(client, user_id)

    response = client.post(_delete_url(999999))

    assert response.status_code == 404, "POST to delete a non-existent expense id must return 404"


# ---------------------------------------------------------------------------
# Method not allowed
# ---------------------------------------------------------------------------


def test_get_delete_expense_returns_405_when_unauthenticated(app, client):
    user_id = _fresh_user()
    expense_id = _fresh_expense(user_id)

    response = client.get(_delete_url(expense_id))

    assert response.status_code == 405, "GET /expenses/<id>/delete must return 405, not be routed at all"


def test_get_delete_expense_returns_405_when_authenticated(app, client):
    user_id = _fresh_user()
    expense_id = _fresh_expense(user_id)
    _login_as(client, user_id)

    response = client.get(_delete_url(expense_id))

    assert response.status_code == 405, "GET /expenses/<id>/delete must return 405 even for an authenticated owner"

    # A 405 must not have deleted anything.
    row = db.get_expense_by_id(expense_id, user_id)
    assert row is not None, "A disallowed GET request must not delete the expense"

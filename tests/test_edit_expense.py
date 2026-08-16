"""Tests for the "Edit Expense" feature (Step 8): `GET`/`POST /expenses/<id>/edit`
and the two new `database/db.py` helpers it depends on.

Derived from the authoritative spec at `.claude/specs/08-edit-expense.md`, not
from reading `app.py`'s implementation. Behaviour under test:

  - `get_expense_by_id(expense_id, user_id)` returns the matching row only
    when the expense both exists and belongs to the given user; otherwise it
    returns `None`.
  - `update_expense(expense_id, user_id, amount, category, date, description)`
    is scoped to `id = ? AND user_id = ?`: it updates the row when the caller
    owns the expense, and silently affects zero rows (no exception) when the
    `user_id` doesn't match the expense's owner.
  - `GET /expenses/<id>/edit` and `POST /expenses/<id>/edit` both require an
    authenticated session, following the same auth-guard pattern as
    `/expenses/add` and `/profile`.
  - `GET /expenses/<id>/edit` for the logged-in user's own expense returns
    200 and renders a form pre-filled with that expense's current amount,
    category (pre-selected in the `<select>`), date, and description.
  - `GET`/`POST /expenses/<id>/edit` for another user's expense, or for a
    non-existent id, returns 404.
  - `POST /expenses/<id>/edit` with valid data updates the row in place and
    redirects (302) to `/profile`.
  - Invalid amount (missing, zero, non-numeric), invalid category, and
    invalid date are all rejected: the form re-renders (200, not a redirect)
    with an error message, and the DB row is left unchanged.
  - Omitting the description on an otherwise valid submission succeeds and
    stores `NULL`.

Fixtures `app` and `client` come from the project-root conftest.py:
  - `app` patches `database.db.DB_PATH` to an isolated sqlite file and
    re-imports `app.py` fresh, which runs `init_db()`/`seed_db()` at import
    time against that isolated file.
  - `client` is supplied by pytest-flask, built from the `app` fixture.
  - `temp_db` (also from conftest.py) gives pure `database/db.py` unit tests
    an isolated DB without going through Flask at all.
"""

import re
from datetime import date

import pytest

import database.db as db

FIXED_CATEGORIES = [
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
]

PROFILE_URL = "/profile"


def _edit_url(expense_id):
    return f"/expenses/{expense_id}/edit"


def _login_as(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def _fresh_user(name="Fresh User", email="fresh-edit-expense@example.com"):
    db.init_db()
    return db.create_user(name, email, "password123")


def _fresh_expense(user_id, **overrides):
    """Create an expense row via `db.create_expense` to have something to edit."""
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


def _valid_payload(**overrides):
    payload = {
        "amount": "60.00",
        "category": "Transport",
        "date": date.today().isoformat(),
        "description": "Updated expense",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Unit tests: get_expense_by_id
# ---------------------------------------------------------------------------


def test_get_expense_by_id_returns_row_for_correct_user(temp_db):
    user_id = temp_db.create_user("Owner", "owner-get@example.com", "password123")
    expense_id = _fresh_expense(user_id, amount=55.25, category="Bills", description="Electric bill")

    row = db.get_expense_by_id(expense_id, user_id)

    assert row is not None, "Expected a row for a valid id + correct user_id"
    assert row["id"] == expense_id
    assert float(row["amount"]) == 55.25, "Amount on the fetched row does not match what was created"
    assert row["category"] == "Bills"
    assert row["description"] == "Electric bill"


def test_get_expense_by_id_returns_none_for_wrong_user(temp_db):
    owner_id = temp_db.create_user("Owner", "owner-wrong-user@example.com", "password123")
    other_id = temp_db.create_user("Other", "other-wrong-user@example.com", "password123")
    expense_id = _fresh_expense(owner_id)

    row = db.get_expense_by_id(expense_id, other_id)

    assert row is None, "get_expense_by_id must return None when the expense belongs to a different user"


def test_get_expense_by_id_returns_none_for_nonexistent_id(temp_db):
    user_id = temp_db.create_user("Owner", "owner-missing-id@example.com", "password123")

    row = db.get_expense_by_id(999999, user_id)

    assert row is None, "get_expense_by_id must return None for a non-existent expense id"


# ---------------------------------------------------------------------------
# Unit tests: update_expense
# ---------------------------------------------------------------------------


def test_update_expense_updates_row_for_correct_user(temp_db):
    user_id = temp_db.create_user("Owner", "owner-update@example.com", "password123")
    expense_id = _fresh_expense(user_id, amount=10.00, category="Food", description="Original")

    db.update_expense(expense_id, user_id, 99.0, "Shopping", date.today().isoformat(), "Updated desc")

    row = db.get_expense_by_id(expense_id, user_id)
    assert row is not None
    assert float(row["amount"]) == 99.0, "Expected the DB row's amount to reflect the update"
    assert row["category"] == "Shopping", "Expected the DB row's category to reflect the update"
    assert row["description"] == "Updated desc", "Expected the DB row's description to reflect the update"


def test_update_expense_wrong_user_leaves_row_unchanged_and_raises_no_error(temp_db):
    owner_id = temp_db.create_user("Owner", "owner-guard@example.com", "password123")
    other_id = temp_db.create_user("Other", "other-guard@example.com", "password123")
    expense_id = _fresh_expense(owner_id, amount=10.00, category="Food", description="Original")

    # Calling with the wrong user_id must not raise, and must affect 0 rows.
    db.update_expense(expense_id, other_id, 999.0, "Shopping", date.today().isoformat(), "Hacked")

    row = db.get_expense_by_id(expense_id, owner_id)
    assert row is not None
    assert float(row["amount"]) == 10.00, "Row must remain unchanged when update_expense is called with the wrong user_id"
    assert row["category"] == "Food"
    assert row["description"] == "Original"


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------


def test_get_edit_expense_redirects_when_unauthenticated(app, client):
    user_id = _fresh_user()
    expense_id = _fresh_expense(user_id)

    response = client.get(_edit_url(expense_id))

    assert response.status_code == 302, "Unauthenticated GET /expenses/<id>/edit should redirect, not 200"
    assert response.location.endswith("/login"), "Expected redirect target to be the login page"


def test_post_edit_expense_redirects_when_unauthenticated(app, client):
    user_id = _fresh_user()
    expense_id = _fresh_expense(user_id)

    response = client.post(_edit_url(expense_id), data=_valid_payload())

    assert response.status_code == 302, "Unauthenticated POST /expenses/<id>/edit should redirect, not update"
    assert response.location.endswith("/login"), "Expected redirect target to be the login page"


def test_post_edit_expense_unauthenticated_does_not_update_db(app, client):
    user_id = _fresh_user()
    expense_id = _fresh_expense(user_id, amount=10.00, category="Food", description="Original")

    client.post(_edit_url(expense_id), data=_valid_payload(amount="500.00"))

    row = db.get_expense_by_id(expense_id, user_id)
    assert float(row["amount"]) == 10.00, "Unauthenticated POST must not modify the expense"


# ---------------------------------------------------------------------------
# GET renders the pre-filled form
# ---------------------------------------------------------------------------


def test_get_edit_expense_own_expense_returns_200_with_prefilled_values(app, client):
    user_id = _fresh_user()
    expense_id = _fresh_expense(
        user_id, amount=45.50, category="Health", expense_date="2026-01-15", description="Doctor visit"
    )
    _login_as(client, user_id)

    response = client.get(_edit_url(expense_id))
    assert response.status_code == 200, "Authenticated GET of own expense should return 200"

    body = response.get_data(as_text=True)
    assert 'name="amount"' in body, "Expected an amount field in the edit-expense form"
    assert 'name="category"' in body, "Expected a category field in the edit-expense form"
    assert 'name="date"' in body, "Expected a date field in the edit-expense form"
    assert 'name="description"' in body, "Expected a description field in the edit-expense form"

    assert "45.5" in body, "Expected the current amount to be pre-filled"
    assert "2026-01-15" in body, "Expected the current date to be pre-filled"
    assert "Doctor visit" in body, "Expected the current description to be pre-filled"


def test_get_edit_expense_preselects_correct_category(app, client):
    user_id = _fresh_user()
    expense_id = _fresh_expense(user_id, category="Entertainment")
    _login_as(client, user_id)

    response = client.get(_edit_url(expense_id))
    body = response.get_data(as_text=True)

    match = re.search(r"<option([^>]*)>\s*Entertainment\s*</option>", body)
    assert match is not None, "Expected an <option> for 'Entertainment' in the category <select>"
    assert "selected" in match.group(1), "Expected the 'Entertainment' option to be pre-selected"


def test_get_edit_expense_form_includes_all_fixed_categories(app, client):
    user_id = _fresh_user()
    expense_id = _fresh_expense(user_id, category="Food")
    _login_as(client, user_id)

    response = client.get(_edit_url(expense_id))
    body = response.get_data(as_text=True)

    for category in FIXED_CATEGORIES:
        assert category in body, f"Expected category '{category}' to be an option in the edit-expense form"


def test_get_edit_expense_other_users_expense_returns_404(app, client):
    owner_id = _fresh_user(name="Owner", email="owner-get404@example.com")
    other_id = _fresh_user(name="Other", email="other-get404@example.com")
    expense_id = _fresh_expense(owner_id)
    _login_as(client, other_id)

    response = client.get(_edit_url(expense_id))

    assert response.status_code == 404, "GET of another user's expense must return 404"


def test_get_edit_expense_nonexistent_id_returns_404(app, client):
    user_id = _fresh_user()
    _login_as(client, user_id)

    response = client.get(_edit_url(999999))

    assert response.status_code == 404, "GET of a non-existent expense id must return 404"


# ---------------------------------------------------------------------------
# POST happy path
# ---------------------------------------------------------------------------


def test_post_edit_expense_valid_data_redirects_to_profile(app, client):
    user_id = _fresh_user()
    expense_id = _fresh_expense(user_id)
    _login_as(client, user_id)

    response = client.post(_edit_url(expense_id), data=_valid_payload())

    assert response.status_code == 302, "Valid POST /expenses/<id>/edit should redirect"
    assert response.location.endswith(PROFILE_URL), "Expected redirect to /profile after editing an expense"


def test_post_edit_expense_valid_data_updates_db_row(app, client):
    user_id = _fresh_user()
    expense_id = _fresh_expense(user_id, amount=10.00, category="Food", description="Original")
    _login_as(client, user_id)

    updated_date = date.today().isoformat()
    client.post(
        _edit_url(expense_id),
        data=_valid_payload(amount="123.45", category="Bills", date=updated_date, description="Rent payment"),
    )

    row = db.get_expense_by_id(expense_id, user_id)
    assert row is not None, "Expected the expense row to still exist after the update"
    assert float(row["amount"]) == 123.45, "Expected the updated amount to be persisted"
    assert row["category"] == "Bills", "Expected the updated category to be persisted"
    assert row["date"] == updated_date, "Expected the updated date to be persisted"
    assert row["description"] == "Rent payment", "Expected the updated description to be persisted"


def test_post_edit_expense_other_users_expense_returns_404(app, client):
    owner_id = _fresh_user(name="Owner", email="owner-post404@example.com")
    other_id = _fresh_user(name="Other", email="other-post404@example.com")
    expense_id = _fresh_expense(owner_id, amount=10.00, category="Food", description="Original")
    _login_as(client, other_id)

    response = client.post(_edit_url(expense_id), data=_valid_payload(amount="999.00"))

    assert response.status_code == 404, "POST to another user's expense must return 404"

    row = db.get_expense_by_id(expense_id, owner_id)
    assert float(row["amount"]) == 10.00, "Expense must remain unchanged when edited by a non-owner"


# ---------------------------------------------------------------------------
# Amount validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "invalid_amount",
    ["0", "-5", "abc", ""],
    ids=["zero", "negative", "non_numeric", "blank"],
)
def test_post_edit_expense_invalid_amount_rejected(app, client, invalid_amount):
    user_id = _fresh_user(email=f"edit-amt-{hash(invalid_amount) & 0xffff}@example.com")
    expense_id = _fresh_expense(user_id, amount=10.00, category="Food", description="Original")
    _login_as(client, user_id)

    response = client.post(_edit_url(expense_id), data=_valid_payload(amount=invalid_amount))

    assert response.status_code == 200, (
        f"Invalid amount {invalid_amount!r} should re-render the form (200), not redirect"
    )
    body = response.get_data(as_text=True).lower()
    assert "error" in body, f"Expected an error message for invalid amount {invalid_amount!r}"

    row = db.get_expense_by_id(expense_id, user_id)
    assert float(row["amount"]) == 10.00, f"DB must remain unchanged for invalid amount {invalid_amount!r}"


def test_post_edit_expense_missing_amount_field_rejected(app, client):
    user_id = _fresh_user()
    expense_id = _fresh_expense(user_id, amount=10.00, category="Food", description="Original")
    _login_as(client, user_id)

    payload = _valid_payload()
    del payload["amount"]

    response = client.post(_edit_url(expense_id), data=payload)

    assert response.status_code == 200, "Missing amount field should re-render the form, not raise a 500"
    body = response.get_data(as_text=True).lower()
    assert "error" in body, "Expected an error message when the amount field is missing"

    row = db.get_expense_by_id(expense_id, user_id)
    assert float(row["amount"]) == 10.00, "DB must remain unchanged when the amount field is missing"


# ---------------------------------------------------------------------------
# Category validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "invalid_category",
    ["NotACategory", "food", ""],
    ids=["unknown_value", "lowercase", "blank"],
)
def test_post_edit_expense_invalid_category_rejected(app, client, invalid_category):
    user_id = _fresh_user(email=f"edit-cat-{hash(invalid_category) & 0xffff}@example.com")
    expense_id = _fresh_expense(user_id, amount=10.00, category="Food", description="Original")
    _login_as(client, user_id)

    response = client.post(_edit_url(expense_id), data=_valid_payload(category=invalid_category))

    assert response.status_code == 200, (
        f"Invalid category {invalid_category!r} should re-render the form, not redirect"
    )
    body = response.get_data(as_text=True).lower()
    assert "error" in body, f"Expected an error message for invalid category {invalid_category!r}"

    row = db.get_expense_by_id(expense_id, user_id)
    assert row["category"] == "Food", f"DB must remain unchanged for invalid category {invalid_category!r}"


# ---------------------------------------------------------------------------
# Date validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "invalid_date",
    ["", "not-a-date", "2026-13-40"],
    ids=["blank", "garbage", "invalid_month_day"],
)
def test_post_edit_expense_invalid_date_rejected(app, client, invalid_date):
    user_id = _fresh_user(email=f"edit-date-{hash(invalid_date) & 0xffff}@example.com")
    expense_id = _fresh_expense(user_id, amount=10.00, category="Food", expense_date="2026-01-01", description="Original")
    _login_as(client, user_id)

    response = client.post(_edit_url(expense_id), data=_valid_payload(date=invalid_date))

    assert response.status_code == 200, (
        f"Invalid date {invalid_date!r} should re-render the form, not redirect"
    )
    body = response.get_data(as_text=True).lower()
    assert "error" in body, f"Expected an error message for invalid date {invalid_date!r}"

    row = db.get_expense_by_id(expense_id, user_id)
    assert row["date"] == "2026-01-01", f"DB must remain unchanged for invalid date {invalid_date!r}"


# ---------------------------------------------------------------------------
# Error re-rendering preserves the submitted (not original) values
# ---------------------------------------------------------------------------


def test_post_edit_expense_validation_error_preserves_submitted_values(app, client):
    user_id = _fresh_user()
    expense_id = _fresh_expense(
        user_id, amount=10.00, category="Food", expense_date="2026-01-01", description="Original"
    )
    _login_as(client, user_id)

    submitted_date = date.today().isoformat()
    response = client.post(
        _edit_url(expense_id),
        data=_valid_payload(amount="-5", category="Bills", date=submitted_date, description="Submitted desc"),
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)

    assert "Submitted desc" in body, "Expected the submitted (not original) description to be preserved"
    assert submitted_date in body, "Expected the submitted (not original) date to be preserved"
    assert "Bills" in body, "Expected the submitted (not original) category to be preserved"


# ---------------------------------------------------------------------------
# Optional description
# ---------------------------------------------------------------------------


def test_post_edit_expense_no_description_redirects_and_saves_null(app, client):
    user_id = _fresh_user()
    expense_id = _fresh_expense(user_id, amount=10.00, category="Food", description="Original")
    _login_as(client, user_id)

    response = client.post(_edit_url(expense_id), data=_valid_payload(description=""))

    assert response.status_code == 302, "Description is optional; omitting it should still succeed"
    assert response.location.endswith(PROFILE_URL), "Expected redirect to /profile after editing an expense"

    row = db.get_expense_by_id(expense_id, user_id)
    assert row["description"] is None, "Expected description to be stored as NULL when omitted"

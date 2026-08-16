"""Tests for the "Add Expense" feature (Step 7): `GET`/`POST /expenses/add`.

Derived from the authoritative spec at `.claude/specs/07-add-expense.md`,
not from reading `app.py`'s implementation. Behaviour under test:

  - `GET /expenses/add` while logged out redirects (302) to `/login`,
    following the exact same auth-guard pattern as `/profile` and
    `/analytics`.
  - `GET /expenses/add` while logged in returns 200 and renders a form
    with `amount`, `category`, `date`, and `description` fields. The
    `category` field is a `<select>` populated from the fixed 7-value
    list: Food, Transport, Bills, Health, Entertainment, Shopping,
    Other.
  - `POST /expenses/add` with a valid amount, category, date, and
    optional description creates a new row in `expenses` for the
    current session user and redirects (302) to `/profile`.
  - The newly created expense shows up in `/profile`'s recent
    transactions list and category breakdown.
  - Invalid amount (blank, zero, negative, non-numeric), invalid/absent
    category (outside the fixed list), and invalid/missing date are all
    rejected: the form re-renders (200, not a redirect) with an error
    and no row is written to `expenses`.
  - Previously submitted field values (category, date, description) are
    preserved in the re-rendered form after a validation error.
  - `POST /expenses/add` while logged out also requires login: it
    redirects instead of creating an expense.

Fixtures `app` and `client` come from the project-root conftest.py:
  - `app` patches `database.db.DB_PATH` to an isolated sqlite file and
    re-imports `app.py` fresh, which runs `init_db()`/`seed_db()` at
    import time against that isolated file.
  - `client` is supplied by pytest-flask, built from the `app` fixture.
"""

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

ADD_EXPENSE_URL = "/expenses/add"
PROFILE_URL = "/profile"


def _login_as(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def _fresh_user(name="Fresh User", email="fresh-add-expense@example.com"):
    db.init_db()
    return db.create_user(name, email, "password123")


def _count_expenses_for_user(user_id):
    conn = db.get_db()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row["n"]
    finally:
        conn.close()


def _valid_payload(**overrides):
    payload = {
        "amount": "42.50",
        "category": "Food",
        "date": date.today().isoformat(),
        "description": "Test expense",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------


def test_get_add_expense_redirects_when_unauthenticated(client):
    response = client.get(ADD_EXPENSE_URL)
    assert response.status_code == 302, "Unauthenticated GET /expenses/add should redirect, not 200"
    assert response.location.endswith("/login"), "Expected redirect target to be the login page"


def test_get_add_expense_redirect_matches_profile_auth_guard_pattern(client):
    add_expense_response = client.get(ADD_EXPENSE_URL)
    profile_response = client.get(PROFILE_URL)

    assert add_expense_response.status_code == profile_response.status_code == 302
    assert add_expense_response.location == profile_response.location, (
        "Expected /expenses/add to redirect to the same login URL as /profile"
    )


def test_get_add_expense_redirect_body_does_not_leak_form(client):
    response = client.get(ADD_EXPENSE_URL)
    body = response.get_data(as_text=True)
    assert "amount" not in body.lower() or response.status_code == 302, (
        "Redirect response should not leak the protected add-expense form"
    )


def test_post_add_expense_redirects_when_unauthenticated(client):
    response = client.post(ADD_EXPENSE_URL, data=_valid_payload())
    assert response.status_code == 302, "Unauthenticated POST /expenses/add should redirect, not create an expense"
    assert response.location.endswith("/login"), "Expected redirect target to be the login page"


def test_post_add_expense_unauthenticated_does_not_create_expense(app, client):
    user_id = _fresh_user()
    before = _count_expenses_for_user(user_id)

    client.post(ADD_EXPENSE_URL, data=_valid_payload())

    after = _count_expenses_for_user(user_id)
    assert after == before, "No expense should be created when the POST is unauthenticated"


# ---------------------------------------------------------------------------
# GET renders the form
# ---------------------------------------------------------------------------


def test_get_add_expense_renders_form_when_authenticated(app, client):
    user_id = _fresh_user()
    _login_as(client, user_id)

    response = client.get(ADD_EXPENSE_URL)
    assert response.status_code == 200, "Authenticated GET /expenses/add should return 200"

    body = response.get_data(as_text=True)
    assert 'name="amount"' in body, "Expected an amount field in the add-expense form"
    assert 'name="category"' in body, "Expected a category field in the add-expense form"
    assert 'name="date"' in body, "Expected a date field in the add-expense form"
    assert 'name="description"' in body, "Expected a description field in the add-expense form"


def test_get_add_expense_form_includes_all_fixed_categories(app, client):
    user_id = _fresh_user()
    _login_as(client, user_id)

    response = client.get(ADD_EXPENSE_URL)
    body = response.get_data(as_text=True)

    for category in FIXED_CATEGORIES:
        assert category in body, f"Expected category '{category}' to be an option in the add-expense form"


def test_get_add_expense_date_defaults_to_today(app, client):
    user_id = _fresh_user()
    _login_as(client, user_id)

    response = client.get(ADD_EXPENSE_URL)
    body = response.get_data(as_text=True)

    today_iso = date.today().isoformat()
    assert today_iso in body, "Expected the date field to default to today's date"


# ---------------------------------------------------------------------------
# POST happy path
# ---------------------------------------------------------------------------


def test_post_add_expense_valid_data_redirects_to_profile(app, client):
    user_id = _fresh_user()
    _login_as(client, user_id)

    response = client.post(ADD_EXPENSE_URL, data=_valid_payload())

    assert response.status_code == 302, "Valid POST /expenses/add should redirect"
    assert response.location.endswith(PROFILE_URL), "Expected redirect to /profile after adding an expense"


def test_post_add_expense_valid_data_creates_db_row(app, client):
    user_id = _fresh_user()
    before = _count_expenses_for_user(user_id)
    _login_as(client, user_id)

    client.post(
        ADD_EXPENSE_URL,
        data=_valid_payload(amount="42.50", category="Food", description="Groceries"),
    )

    after = _count_expenses_for_user(user_id)
    assert after == before + 1, "Expected exactly one new expense row to be created for the current user"

    conn = db.get_db()
    try:
        row = conn.execute(
            "SELECT amount, category, date, description, user_id FROM expenses WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None, "Expected the new expense row to exist"
    assert row["user_id"] == user_id, "New expense must belong to the logged-in user"
    assert float(row["amount"]) == 42.50, "Expense amount was not stored correctly"
    assert row["category"] == "Food", "Expense category was not stored correctly"
    assert row["description"] == "Groceries", "Expense description was not stored correctly"


def test_post_add_expense_without_description_succeeds(app, client):
    user_id = _fresh_user()
    _login_as(client, user_id)

    response = client.post(
        ADD_EXPENSE_URL,
        data=_valid_payload(description=""),
    )

    assert response.status_code == 302, "Description is optional; omitting it should still succeed"
    assert _count_expenses_for_user(user_id) == 1, "Expected the expense to be created without a description"


@pytest.mark.parametrize("category", FIXED_CATEGORIES)
def test_post_add_expense_accepts_every_fixed_category(app, client, category):
    user_id = _fresh_user(email=f"cat-{category.lower()}@example.com")
    _login_as(client, user_id)

    response = client.post(ADD_EXPENSE_URL, data=_valid_payload(category=category))

    assert response.status_code == 302, f"Category '{category}' from the fixed list should be accepted"
    assert _count_expenses_for_user(user_id) == 1


def test_post_add_expense_creates_expense_only_for_current_user(app, client):
    other_user_id = _fresh_user(name="Other User", email="other-add-expense@example.com")
    current_user_id = _fresh_user(name="Current User", email="current-add-expense@example.com")
    _login_as(client, current_user_id)

    client.post(ADD_EXPENSE_URL, data=_valid_payload())

    assert _count_expenses_for_user(current_user_id) == 1, "Expense should be attributed to the logged-in user"
    assert _count_expenses_for_user(other_user_id) == 0, "Expense must not leak to another user's account"


# ---------------------------------------------------------------------------
# New expense appears on /profile
# ---------------------------------------------------------------------------


def test_new_expense_appears_in_profile_recent_transactions(app, client):
    user_id = _fresh_user()
    _login_as(client, user_id)

    client.post(
        ADD_EXPENSE_URL,
        data=_valid_payload(amount="77.25", category="Entertainment", description="Concert tickets"),
    )

    response = client.get(PROFILE_URL)
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    assert "Concert tickets" in body, "Expected the new expense's description in profile's recent transactions"
    assert "Entertainment" in body, "Expected the new expense's category in profile's recent transactions"


def test_new_expense_appears_in_profile_category_breakdown(app, client):
    user_id = _fresh_user()
    _login_as(client, user_id)

    client.post(
        ADD_EXPENSE_URL,
        data=_valid_payload(amount="100.00", category="Shopping", description="New shoes"),
    )

    response = client.get(PROFILE_URL)
    body = response.get_data(as_text=True)

    assert "Shopping" in body, "Expected the new expense's category to appear in the category breakdown"

    breakdown = db.get_category_breakdown(user_id)
    categories = [entry["name"] for entry in breakdown]
    assert "Shopping" in categories, "Expected 'Shopping' to appear in the DB-level category breakdown"


# ---------------------------------------------------------------------------
# Amount validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "invalid_amount",
    ["", "0", "-5", "-0.01", "abc", "twenty"],
    ids=["blank", "zero", "negative", "negative_decimal", "non_numeric", "words"],
)
def test_post_add_expense_invalid_amount_rejected(app, client, invalid_amount):
    user_id = _fresh_user(email=f"amt-{hash(invalid_amount) & 0xffff}@example.com")
    _login_as(client, user_id)

    response = client.post(ADD_EXPENSE_URL, data=_valid_payload(amount=invalid_amount))

    assert response.status_code == 200, (
        f"Invalid amount {invalid_amount!r} should re-render the form (200), not redirect"
    )
    assert _count_expenses_for_user(user_id) == 0, (
        f"No expense row should be created for invalid amount {invalid_amount!r}"
    )


def test_post_add_expense_missing_amount_field_rejected(app, client):
    user_id = _fresh_user()
    _login_as(client, user_id)

    payload = _valid_payload()
    del payload["amount"]

    response = client.post(ADD_EXPENSE_URL, data=payload)

    assert response.status_code == 200, "Missing amount field should re-render the form, not raise a 500"
    assert _count_expenses_for_user(user_id) == 0


# ---------------------------------------------------------------------------
# Category validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "invalid_category",
    ["Groceries", "food", "FOOD", "", "Miscellaneous", "<script>alert(1)</script>"],
    ids=["unknown_value", "lowercase", "uppercase", "blank", "not_in_list", "xss_attempt"],
)
def test_post_add_expense_invalid_category_rejected(app, client, invalid_category):
    user_id = _fresh_user(email=f"cat-invalid-{hash(invalid_category) & 0xffff}@example.com")
    _login_as(client, user_id)

    response = client.post(ADD_EXPENSE_URL, data=_valid_payload(category=invalid_category))

    assert response.status_code == 200, (
        f"Category {invalid_category!r} outside the fixed list should re-render the form, not redirect"
    )
    assert _count_expenses_for_user(user_id) == 0, (
        f"No expense row should be created for invalid category {invalid_category!r}"
    )


def test_post_add_expense_missing_category_field_rejected(app, client):
    user_id = _fresh_user()
    _login_as(client, user_id)

    payload = _valid_payload()
    del payload["category"]

    response = client.post(ADD_EXPENSE_URL, data=payload)

    assert response.status_code == 200, "Missing category field should re-render the form, not raise a 500"
    assert _count_expenses_for_user(user_id) == 0


# ---------------------------------------------------------------------------
# Date validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "invalid_date",
    ["", "not-a-date", "13/25/2026", "2026-13-40", "2026/08/16"],
    ids=["blank", "garbage", "us_slash_format", "invalid_month_day", "wrong_separator"],
)
def test_post_add_expense_invalid_date_rejected(app, client, invalid_date):
    user_id = _fresh_user(email=f"date-{hash(invalid_date) & 0xffff}@example.com")
    _login_as(client, user_id)

    response = client.post(ADD_EXPENSE_URL, data=_valid_payload(date=invalid_date))

    assert response.status_code == 200, (
        f"Invalid date {invalid_date!r} should re-render the form, not redirect"
    )
    assert _count_expenses_for_user(user_id) == 0, (
        f"No expense row should be created for invalid date {invalid_date!r}"
    )


def test_post_add_expense_missing_date_field_rejected(app, client):
    user_id = _fresh_user()
    _login_as(client, user_id)

    payload = _valid_payload()
    del payload["date"]

    response = client.post(ADD_EXPENSE_URL, data=payload)

    assert response.status_code == 200, "Missing date field should re-render the form, not raise a 500"
    assert _count_expenses_for_user(user_id) == 0


# ---------------------------------------------------------------------------
# Error re-rendering & value preservation
# ---------------------------------------------------------------------------


def test_post_add_expense_invalid_amount_preserves_other_fields(app, client):
    user_id = _fresh_user()
    _login_as(client, user_id)

    submitted_date = date.today().isoformat()
    response = client.post(
        ADD_EXPENSE_URL,
        data=_valid_payload(
            amount="-5",
            category="Bills",
            date=submitted_date,
            description="Preserve me please",
        ),
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)

    assert "Preserve me please" in body, "Expected the submitted description to be preserved after a validation error"
    assert submitted_date in body, "Expected the submitted date to be preserved after a validation error"
    assert "Bills" in body, "Expected the submitted category to be preserved after a validation error"


def test_post_add_expense_invalid_category_preserves_other_fields(app, client):
    user_id = _fresh_user()
    _login_as(client, user_id)

    submitted_date = date.today().isoformat()
    response = client.post(
        ADD_EXPENSE_URL,
        data=_valid_payload(
            amount="15.75",
            category="NotARealCategory",
            date=submitted_date,
            description="Also preserve me",
        ),
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)

    assert "Also preserve me" in body, "Expected the submitted description to be preserved after a validation error"
    assert submitted_date in body, "Expected the submitted date to be preserved after a validation error"
    assert "15.75" in body, "Expected the submitted amount to be preserved after a validation error"


def test_post_add_expense_invalid_date_preserves_other_fields(app, client):
    user_id = _fresh_user()
    _login_as(client, user_id)

    response = client.post(
        ADD_EXPENSE_URL,
        data=_valid_payload(
            amount="22.00",
            category="Health",
            date="not-a-date",
            description="Keep this text",
        ),
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)

    assert "Keep this text" in body, "Expected the submitted description to be preserved after a validation error"
    assert "Health" in body, "Expected the submitted category to be preserved after a validation error"
    assert "22.00" in body or "22" in body, "Expected the submitted amount to be preserved after a validation error"


def test_post_add_expense_validation_error_shows_error_message(app, client):
    user_id = _fresh_user()
    _login_as(client, user_id)

    response = client.post(ADD_EXPENSE_URL, data=_valid_payload(amount="0"))

    assert response.status_code == 200
    body = response.get_data(as_text=True).lower()
    assert "error" in body, "Expected some error indication to be rendered on validation failure"

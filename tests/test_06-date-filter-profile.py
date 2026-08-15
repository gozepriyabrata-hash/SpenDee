"""Tests for Step 6 — Date-range filter on the Profile page.

Spec: .claude/specs/06-date-filter-profile.md

Contract under test (from the spec, not from reading app.py's internals):
  - `GET /profile` gains optional `start_date` / `end_date` query params
    (`YYYY-MM-DD`) that scope the summary stats, transaction list, and
    category breakdown to that range.
  - No params -> identical to the pre-Step-6 all-time behaviour.
  - The route stays login-only; query params must never bypass the guard.
  - `start_date`/`end_date` are validated server-side: malformed dates and
    `start_date > end_date` must be *silently ignored*, falling back to
    all-time data rather than erroring.
  - `database/db.py`'s `get_summary_stats`, `get_recent_transactions`, and
    `get_category_breakdown` accept optional `start_date`/`end_date` and
    add a `date BETWEEN ? AND ?` clause "when both are present" — i.e.
    supplying only one of the two must not filter anything.
  - A zero-match range must render cleanly: ₹0.00 total, 0 transactions,
    empty transaction list, empty category breakdown, no errors.
  - The filtered URL must be directly reloadable (bookmarkable/shareable)
    and yield the same filtered results.
  - Currency must always render with ₹, never $ or £.

Fixtures `app`, `client`, and `temp_db` come from the project-root
conftest.py:
  - `temp_db` patches `database.db.DB_PATH` to an isolated sqlite file for
    calling the db-layer functions directly (no Flask involved).
  - `app` patches `database.db.DB_PATH` to its own isolated sqlite file and
    re-imports `app.py` fresh, which runs `init_db()`/`seed_db()` at import
    time against that isolated file.
  - `client` is supplied by pytest-flask, built from the `app` fixture.

Expected numbers are derived from `database/db.seed_db()`'s seeding recipe,
replicated below using the same day-of-month formula, so the tests stay
correct regardless of what calendar day/month they run on.
"""

from datetime import date, timedelta
from urllib.parse import quote

import pytest

import database.db as db


# Mirrors `sample_expenses` in database/db.py's seed_db():
# (amount, category, day_of_month, description)
SEED_EXPENSES = [
    (12.50, "Food", 2, "Groceries at local market"),
    (45.00, "Transport", 4, "Monthly bus pass top-up"),
    (89.99, "Bills", 6, "Electricity bill"),
    (25.00, "Health", 9, "Pharmacy - over-the-counter meds"),
    (60.00, "Entertainment", 11, "Movie night with friends"),
    (150.00, "Shopping", 14, "New running shoes"),
    (8.75, "Other", 17, "Miscellaneous stationery"),
    (32.40, "Food", 20, "Dinner at a restaurant"),
]

ALL_TIME_TOTAL = sum(row[0] for row in SEED_EXPENSES)  # 423.64
ALL_TIME_COUNT = len(SEED_EXPENSES)  # 8


def _seed_date(day_of_month):
    """Reproduce seed_db()'s `first_of_month + timedelta(day_of_month - 1)`."""
    first_of_month = date.today().replace(day=1)
    return (first_of_month + timedelta(days=day_of_month - 1)).isoformat()


# A partial range covering day_of_month 4..14 inclusive: Transport, Bills,
# Health, Entertainment, Shopping. Excludes the two Food rows and Other.
RANGE_START = _seed_date(4)
RANGE_END = _seed_date(14)
RANGE_MATCHES = [row for row in SEED_EXPENSES if 4 <= row[2] <= 14]
RANGE_TOTAL = sum(row[0] for row in RANGE_MATCHES)  # 369.99
RANGE_COUNT = len(RANGE_MATCHES)  # 5
RANGE_CATEGORIES = {row[1] for row in RANGE_MATCHES}
RANGE_DESCRIPTIONS = {row[3] for row in RANGE_MATCHES}
EXCLUDED_DESCRIPTIONS = {row[3] for row in SEED_EXPENSES} - RANGE_DESCRIPTIONS
EXCLUDED_CATEGORIES = {row[1] for row in SEED_EXPENSES} - RANGE_CATEGORIES

# A single-day boundary: day 14 has exactly one expense (Shopping, 150.00).
SINGLE_DAY = _seed_date(14)
SINGLE_DAY_AMOUNT = 150.00
SINGLE_DAY_DESCRIPTION = "New running shoes"

# A window strictly after the last seeded expense (day 20) -> zero matches.
# Days 23-26 are safe in every calendar month (all months have >= 28 days).
ZERO_START = _seed_date(23)
ZERO_END = _seed_date(26)


def _login_as_demo_user(client):
    """Log the test client in as the seeded demo user via session injection.

    Mirrors how login already works in this app (session["user_id"] set on
    successful POST /login) without needing to know the login form's field
    names beyond what app.py's login route already documents.
    """
    db.seed_db()
    demo_user = db.get_user_by_email("demo@spendly.com")
    with client.session_transaction() as sess:
        sess["user_id"] = demo_user["id"]
    return demo_user


def _no_currency_leak(body):
    return "$" not in body and "£" not in body


# ------------------------------------------------------------------------- #
# Auth guard — query params must never bypass the login requirement
# ------------------------------------------------------------------------- #


class TestProfileFilterAuthGuard:
    def test_unauthenticated_no_params_redirects_to_login(self, client):
        response = client.get("/profile")

        assert response.status_code == 302
        assert response.location.endswith("/login")

    @pytest.mark.parametrize(
        "query_string",
        [
            f"start_date={RANGE_START}&end_date={RANGE_END}",
            f"start_date={RANGE_START}",
            f"end_date={RANGE_END}",
            "start_date=not-a-date&end_date=also-not-a-date",
            f"start_date={RANGE_END}&end_date={RANGE_START}",  # inverted range
        ],
    )
    def test_unauthenticated_with_query_params_still_redirects_to_login(
        self, client, query_string
    ):
        response = client.get(f"/profile?{query_string}")

        assert response.status_code == 302, (
            "A filtered request from a logged-out user must not be treated "
            "differently from a plain /profile request"
        )
        assert response.location.endswith("/login"), (
            "Query params must not bypass the auth guard on /profile"
        )


# ------------------------------------------------------------------------- #
# Happy path — no filter behaves as before; a valid filter narrows results
# ------------------------------------------------------------------------- #


class TestProfileFilterHappyPath:
    def test_no_query_params_shows_all_time_data(self, app, client):
        _login_as_demo_user(client)

        response = client.get("/profile")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert f"₹{ALL_TIME_TOTAL:.2f}" in body, (
            "With no filter, the total must match the full, unfiltered sum"
        )
        assert str(ALL_TIME_COUNT) in body
        assert "Showing" not in body, (
            "The active-range indicator must not appear when no filter is applied"
        )

    def test_valid_range_narrows_total_count_and_currency(self, app, client):
        _login_as_demo_user(client)

        response = client.get(
            f"/profile?start_date={RANGE_START}&end_date={RANGE_END}"
        )

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert f"₹{RANGE_TOTAL:.2f}" in body, "Filtered total must be scoped to the range"
        assert str(RANGE_COUNT) in body
        assert _no_currency_leak(body), "Only ₹ may be used for currency, never $ or £"

    def test_valid_range_narrows_transaction_list(self, app, client):
        _login_as_demo_user(client)

        response = client.get(
            f"/profile?start_date={RANGE_START}&end_date={RANGE_END}"
        )
        body = response.get_data(as_text=True)

        for description in RANGE_DESCRIPTIONS:
            assert description in body, f"Expected in-range expense missing: {description}"
        for description in EXCLUDED_DESCRIPTIONS:
            assert description not in body, (
                f"Out-of-range expense leaked into the filtered view: {description}"
            )

    def test_valid_range_narrows_category_breakdown(self, app, client):
        _login_as_demo_user(client)

        response = client.get(
            f"/profile?start_date={RANGE_START}&end_date={RANGE_END}"
        )
        body = response.get_data(as_text=True)

        for category in RANGE_CATEGORIES:
            assert category in body
        for category in EXCLUDED_CATEGORIES:
            assert category not in body, (
                f"Category with no expenses in range should not appear: {category}"
            )

    def test_valid_range_shows_active_range_and_clear_link(self, app, client):
        _login_as_demo_user(client)

        response = client.get(
            f"/profile?start_date={RANGE_START}&end_date={RANGE_END}"
        )
        body = response.get_data(as_text=True)

        assert "Showing" in body, "Active filter must show the 'Showing:' range indicator"
        assert "Clear" in body, "Active filter must show a 'Clear' link/control"

    def test_single_day_range_start_equals_end_matches_only_that_day(self, app, client):
        _login_as_demo_user(client)

        response = client.get(
            f"/profile?start_date={SINGLE_DAY}&end_date={SINGLE_DAY}"
        )

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert f"₹{SINGLE_DAY_AMOUNT:.2f}" in body
        assert SINGLE_DAY_DESCRIPTION in body
        for _, _, _, description in SEED_EXPENSES:
            if description != SINGLE_DAY_DESCRIPTION:
                assert description not in body, (
                    f"Only the single matching day's expense should appear, "
                    f"found unexpected: {description}"
                )

    def test_filtered_url_is_directly_reloadable_with_same_result(self, app, client):
        """A filtered URL must be bookmarkable: reloading it fresh (a brand
        new GET, simulating opening the link directly) reproduces the same
        filtered data."""
        _login_as_demo_user(client)
        url = f"/profile?start_date={RANGE_START}&end_date={RANGE_END}"

        first = client.get(url)
        second = client.get(url)

        assert first.status_code == 200
        assert second.status_code == 200
        first_body = first.get_data(as_text=True)
        second_body = second.get_data(as_text=True)
        assert f"₹{RANGE_TOTAL:.2f}" in first_body
        assert f"₹{RANGE_TOTAL:.2f}" in second_body

    def test_clear_returns_to_plain_profile_with_all_time_data(self, app, client):
        """Simulates following the 'Clear' link: a plain GET with no params
        after having previously applied a filter."""
        _login_as_demo_user(client)
        client.get(f"/profile?start_date={RANGE_START}&end_date={RANGE_END}")

        response = client.get("/profile")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert f"₹{ALL_TIME_TOTAL:.2f}" in body
        assert "Showing" not in body, "Clearing the filter must remove the active-range note"


# ------------------------------------------------------------------------- #
# Edge cases — zero matches, single-sided params
# ------------------------------------------------------------------------- #


class TestProfileFilterEdgeCases:
    def test_zero_match_range_shows_zero_total_and_zero_count(self, app, client):
        _login_as_demo_user(client)

        response = client.get(f"/profile?start_date={ZERO_START}&end_date={ZERO_END}")

        assert response.status_code == 200, "A zero-match range must never error"
        body = response.get_data(as_text=True)
        assert "₹0.00" in body, "Total spent must display as ₹0.00 for a zero-match range"

    def test_zero_match_range_shows_empty_transaction_list(self, app, client):
        _login_as_demo_user(client)

        response = client.get(f"/profile?start_date={ZERO_START}&end_date={ZERO_END}")
        body = response.get_data(as_text=True)

        for _, _, _, description in SEED_EXPENSES:
            assert description not in body, (
                f"No seeded expense should appear in a zero-match window: {description}"
            )

    def test_zero_match_range_shows_empty_category_breakdown(self, app, client):
        _login_as_demo_user(client)

        response = client.get(f"/profile?start_date={ZERO_START}&end_date={ZERO_END}")
        body = response.get_data(as_text=True)

        distinct_categories = {row[1] for row in SEED_EXPENSES}
        for category in distinct_categories:
            assert category not in body, (
                f"Category breakdown must be empty for a zero-match range, "
                f"but found: {category}"
            )

    def test_zero_match_range_still_displays_rupee_symbol(self, app, client):
        _login_as_demo_user(client)

        response = client.get(f"/profile?start_date={ZERO_START}&end_date={ZERO_END}")
        body = response.get_data(as_text=True)

        assert "₹" in body
        assert _no_currency_leak(body)

    def test_only_start_date_supplied_falls_back_to_all_time(self, app, client):
        _login_as_demo_user(client)

        response = client.get(f"/profile?start_date={RANGE_START}")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert f"₹{ALL_TIME_TOTAL:.2f}" in body, (
            "A lone start_date (no end_date) must not filter anything"
        )
        assert "Showing" not in body

    def test_only_end_date_supplied_falls_back_to_all_time(self, app, client):
        _login_as_demo_user(client)

        response = client.get(f"/profile?end_date={RANGE_END}")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert f"₹{ALL_TIME_TOTAL:.2f}" in body, (
            "A lone end_date (no start_date) must not filter anything"
        )
        assert "Showing" not in body

    def test_empty_string_params_fall_back_to_all_time(self, app, client):
        _login_as_demo_user(client)

        response = client.get("/profile?start_date=&end_date=")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert f"₹{ALL_TIME_TOTAL:.2f}" in body
        assert "Showing" not in body


# ------------------------------------------------------------------------- #
# Validation errors — must degrade silently to all-time data, never error
# ------------------------------------------------------------------------- #


class TestProfileFilterValidation:
    def test_start_after_end_falls_back_to_all_time(self, app, client):
        _login_as_demo_user(client)

        response = client.get(
            f"/profile?start_date={RANGE_END}&end_date={RANGE_START}"
        )

        assert response.status_code == 200, (
            "start_date > end_date must never raise/500"
        )
        body = response.get_data(as_text=True)
        assert f"₹{ALL_TIME_TOTAL:.2f}" in body, (
            "An inverted range must be ignored, not applied or errored on"
        )
        assert "Showing" not in body, "An inverted/invalid range is not an 'active' filter"

    @pytest.mark.parametrize(
        "start_date,end_date",
        [
            ("not-a-date", RANGE_END),
            (RANGE_START, "also-not-a-date"),
            ("2026-13-40", RANGE_END),  # invalid month/day
            ("2026/08/04", "2026/08/14"),  # wrong separator
            ("08-04-2026", "08-14-2026"),  # wrong field order
            ("", RANGE_END),
        ],
    )
    def test_malformed_dates_fall_back_to_all_time(
        self, app, client, start_date, end_date
    ):
        _login_as_demo_user(client)

        response = client.get(f"/profile?start_date={start_date}&end_date={end_date}")

        assert response.status_code == 200, "Malformed dates must never cause a 500"
        body = response.get_data(as_text=True)
        assert f"₹{ALL_TIME_TOTAL:.2f}" in body
        assert "Showing" not in body

    def test_sql_injection_like_value_is_rejected_safely(self, app, client):
        """A malformed value shaped like an injection attempt must be
        treated the same as any other malformed date: silently ignored,
        never executed, never causing an error, and never corrupting data."""
        _login_as_demo_user(client)
        malicious = "2026-08-01'; DROP TABLE expenses;--"

        response = client.get(
            f"/profile?start_date={quote(malicious)}&end_date={RANGE_END}"
        )

        assert response.status_code == 200, "Must not error out on a malformed value"
        body = response.get_data(as_text=True)
        assert f"₹{ALL_TIME_TOTAL:.2f}" in body, "Invalid value must fall back to all-time data"

        # Confirm the expenses table survived intact for a subsequent request.
        follow_up = client.get("/profile")
        assert follow_up.status_code == 200
        assert f"₹{ALL_TIME_TOTAL:.2f}" in follow_up.get_data(as_text=True)

    def test_very_long_garbage_value_does_not_error(self, app, client):
        _login_as_demo_user(client)
        garbage = "2026-08-01" + ("x" * 500)

        response = client.get(f"/profile?start_date={garbage}&end_date={RANGE_END}")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert f"₹{ALL_TIME_TOTAL:.2f}" in body


# ------------------------------------------------------------------------- #
# DB-level side effects — db.py helpers correctly scope to the date range
# ------------------------------------------------------------------------- #


class TestSummaryStatsDbLayer:
    def test_range_narrows_total_and_count(self, temp_db):
        temp_db.seed_db()
        user_id = temp_db.get_user_by_email("demo@spendly.com")["id"]

        stats = temp_db.get_summary_stats(
            user_id, start_date=RANGE_START, end_date=RANGE_END
        )

        assert stats["total_spent"] == pytest.approx(RANGE_TOTAL)
        assert stats["transaction_count"] == RANGE_COUNT

    def test_zero_match_range_returns_zero(self, temp_db):
        temp_db.seed_db()
        user_id = temp_db.get_user_by_email("demo@spendly.com")["id"]

        stats = temp_db.get_summary_stats(
            user_id, start_date=ZERO_START, end_date=ZERO_END
        )

        assert stats["total_spent"] == 0
        assert stats["transaction_count"] == 0

    def test_only_start_date_is_ignored(self, temp_db):
        temp_db.seed_db()
        user_id = temp_db.get_user_by_email("demo@spendly.com")["id"]

        stats = temp_db.get_summary_stats(user_id, start_date=RANGE_START)

        assert stats["total_spent"] == pytest.approx(ALL_TIME_TOTAL)
        assert stats["transaction_count"] == ALL_TIME_COUNT

    def test_only_end_date_is_ignored(self, temp_db):
        temp_db.seed_db()
        user_id = temp_db.get_user_by_email("demo@spendly.com")["id"]

        stats = temp_db.get_summary_stats(user_id, end_date=RANGE_END)

        assert stats["total_spent"] == pytest.approx(ALL_TIME_TOTAL)
        assert stats["transaction_count"] == ALL_TIME_COUNT

    def test_no_args_still_returns_all_time_data(self, temp_db):
        """Regression guard: pre-Step-6 callers passing only user_id must
        be completely unaffected."""
        temp_db.seed_db()
        user_id = temp_db.get_user_by_email("demo@spendly.com")["id"]

        stats = temp_db.get_summary_stats(user_id)

        assert stats["total_spent"] == pytest.approx(ALL_TIME_TOTAL)
        assert stats["transaction_count"] == ALL_TIME_COUNT


class TestRecentTransactionsDbLayer:
    def test_range_returns_only_matching_transactions(self, temp_db):
        temp_db.seed_db()
        user_id = temp_db.get_user_by_email("demo@spendly.com")["id"]

        result = temp_db.get_recent_transactions(
            user_id, start_date=RANGE_START, end_date=RANGE_END
        )

        assert len(result) == RANGE_COUNT
        descriptions = {row["description"] for row in result}
        assert descriptions == RANGE_DESCRIPTIONS
        for excluded in EXCLUDED_DESCRIPTIONS:
            assert excluded not in descriptions

    def test_range_keeps_newest_first_ordering(self, temp_db):
        temp_db.seed_db()
        user_id = temp_db.get_user_by_email("demo@spendly.com")["id"]

        result = temp_db.get_recent_transactions(
            user_id, start_date=RANGE_START, end_date=RANGE_END
        )

        dates = [row["date"] for row in result]
        assert dates == sorted(dates, reverse=True), "Filtered results must stay newest-first"

    def test_zero_match_range_returns_empty_list(self, temp_db):
        temp_db.seed_db()
        user_id = temp_db.get_user_by_email("demo@spendly.com")["id"]

        result = temp_db.get_recent_transactions(
            user_id, start_date=ZERO_START, end_date=ZERO_END
        )

        assert result == []

    def test_missing_end_date_is_ignored(self, temp_db):
        temp_db.seed_db()
        user_id = temp_db.get_user_by_email("demo@spendly.com")["id"]

        result = temp_db.get_recent_transactions(user_id, start_date=RANGE_START)

        assert len(result) == ALL_TIME_COUNT

    def test_limit_still_respected_alongside_date_filter(self, temp_db):
        """Pre-existing `limit=` behaviour must be unaffected by the new
        date params."""
        temp_db.seed_db()
        user_id = temp_db.get_user_by_email("demo@spendly.com")["id"]

        result = temp_db.get_recent_transactions(
            user_id, limit=2, start_date=RANGE_START, end_date=RANGE_END
        )

        assert len(result) == 2


class TestCategoryBreakdownDbLayer:
    def test_range_only_includes_matching_categories(self, temp_db):
        temp_db.seed_db()
        user_id = temp_db.get_user_by_email("demo@spendly.com")["id"]

        result = temp_db.get_category_breakdown(
            user_id, start_date=RANGE_START, end_date=RANGE_END
        )

        names = {row["name"] for row in result}
        assert names == RANGE_CATEGORIES
        for excluded in EXCLUDED_CATEGORIES:
            assert excluded not in names

        assert sum(row["total"] for row in result) == pytest.approx(RANGE_TOTAL)
        assert sum(row["percent"] for row in result) == 100, (
            "Percentages within the filtered range must still sum to 100"
        )

    def test_zero_match_range_returns_empty_list(self, temp_db):
        temp_db.seed_db()
        user_id = temp_db.get_user_by_email("demo@spendly.com")["id"]

        result = temp_db.get_category_breakdown(
            user_id, start_date=ZERO_START, end_date=ZERO_END
        )

        assert result == []

    def test_missing_start_date_is_ignored(self, temp_db):
        temp_db.seed_db()
        user_id = temp_db.get_user_by_email("demo@spendly.com")["id"]

        result = temp_db.get_category_breakdown(user_id, end_date=RANGE_END)

        distinct_seeded_categories = {row[1] for row in SEED_EXPENSES}
        assert len(result) == len(distinct_seeded_categories), (
            "A lone end_date must not filter the category breakdown"
        )

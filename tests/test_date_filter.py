"""Tests for the Step 6 date-range filter on GET /profile.

Spec: .claude/specs/06-date-filter-profile.md

Covers two layers of the contract:
  1. database/db.py — get_summary_stats / get_recent_transactions /
     get_category_breakdown accept optional start_date/end_date and narrow
     results to `date BETWEEN start_date AND end_date` when *both* are
     given. If either is missing, these functions fall back to all-time
     data (that's a plain truthiness check in db.py, not validation).
  2. app.py's GET /profile route — owns the *validation* contract: it must
     silently ignore malformed dates and start_date > end_date, falling
     back to all-time data with no error, and echo the active range back
     to the template only when a filter is genuinely applied.

Expected numbers are derived from database/db.seed_db()'s seeding logic
(not hardcoded from memory): each seeded expense lands on
`date.today().replace(day=1) + timedelta(days=day_of_month - 1)`, i.e. the
`day_of_month`-th day of the current month, so a helper below replicates
that formula to stay correct regardless of what day tests are run on.
"""

from datetime import date, timedelta

import pytest

import database.db as db


# Mirrors the `sample_expenses` list in database/db.py's seed_db():
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


def _expense_date(day_of_month):
    """Reproduce seed_db()'s date formula for a given `day_of_month`."""
    first_of_month = date.today().replace(day=1)
    return (first_of_month + timedelta(days=day_of_month - 1)).isoformat()


# A range covering day_of_month 4..14 inclusive: Transport, Bills, Health,
# Entertainment, Shopping (excludes the two Food entries and Other).
PARTIAL_START = _expense_date(4)
PARTIAL_END = _expense_date(14)
PARTIAL_MATCHES = [row for row in SEED_EXPENSES if 4 <= row[2] <= 14]
PARTIAL_TOTAL = sum(row[0] for row in PARTIAL_MATCHES)  # 369.99
PARTIAL_COUNT = len(PARTIAL_MATCHES)  # 5
PARTIAL_CATEGORIES = {row[1] for row in PARTIAL_MATCHES}
EXCLUDED_CATEGORIES = {row[1] for row in SEED_EXPENSES} - PARTIAL_CATEGORIES
EXCLUDED_DESCRIPTIONS = [row[3] for row in SEED_EXPENSES if not (4 <= row[2] <= 14)]
INCLUDED_DESCRIPTIONS = [row[3] for row in PARTIAL_MATCHES]

# A range after the last seeded expense (day 20) — guaranteed zero matches.
# Day 22-25 is safe in every calendar month (all months have >= 28 days).
ZERO_MATCH_START = _expense_date(22)
ZERO_MATCH_END = _expense_date(25)


# --------------------------------------------------------------------- #
# Unit tests: database/db.py functions with start_date/end_date directly
# --------------------------------------------------------------------- #


class TestGetSummaryStatsDateFilter:
    def test_partial_range_narrows_total_count_and_top_category(self, temp_db):
        temp_db.seed_db()
        user_id = temp_db.get_user_by_email("demo@spendly.com")["id"]

        stats = temp_db.get_summary_stats(
            user_id, start_date=PARTIAL_START, end_date=PARTIAL_END
        )

        assert stats["total_spent"] == pytest.approx(PARTIAL_TOTAL), (
            "Total should only sum expenses inside the date range"
        )
        assert stats["transaction_count"] == PARTIAL_COUNT
        assert stats["top_category"] == "Shopping"

    def test_zero_match_range_returns_zero_without_error(self, temp_db):
        temp_db.seed_db()
        user_id = temp_db.get_user_by_email("demo@spendly.com")["id"]

        stats = temp_db.get_summary_stats(
            user_id, start_date=ZERO_MATCH_START, end_date=ZERO_MATCH_END
        )

        assert stats["total_spent"] == 0
        assert stats["transaction_count"] == 0
        assert stats["top_category"] == "—"

    def test_only_start_date_given_is_ignored_shows_all_time(self, temp_db):
        temp_db.seed_db()
        user_id = temp_db.get_user_by_email("demo@spendly.com")["id"]

        stats = temp_db.get_summary_stats(user_id, start_date=PARTIAL_START)

        assert stats["total_spent"] == pytest.approx(ALL_TIME_TOTAL)
        assert stats["transaction_count"] == ALL_TIME_COUNT

    def test_only_end_date_given_is_ignored_shows_all_time(self, temp_db):
        temp_db.seed_db()
        user_id = temp_db.get_user_by_email("demo@spendly.com")["id"]

        stats = temp_db.get_summary_stats(user_id, end_date=PARTIAL_END)

        assert stats["total_spent"] == pytest.approx(ALL_TIME_TOTAL)
        assert stats["transaction_count"] == ALL_TIME_COUNT

    def test_existing_no_arg_call_still_returns_all_time_data(self, temp_db):
        """Regression guard: callers passing only user_id must be unaffected."""
        temp_db.seed_db()
        user_id = temp_db.get_user_by_email("demo@spendly.com")["id"]

        stats = temp_db.get_summary_stats(user_id)

        assert stats["total_spent"] == pytest.approx(ALL_TIME_TOTAL)
        assert stats["transaction_count"] == ALL_TIME_COUNT
        assert stats["top_category"] == "Shopping"


class TestGetRecentTransactionsDateFilter:
    def test_partial_range_returns_only_matching_transactions(self, temp_db):
        temp_db.seed_db()
        user_id = temp_db.get_user_by_email("demo@spendly.com")["id"]

        result = temp_db.get_recent_transactions(
            user_id, start_date=PARTIAL_START, end_date=PARTIAL_END
        )

        assert len(result) == PARTIAL_COUNT
        descriptions = {row["description"] for row in result}
        assert descriptions == set(INCLUDED_DESCRIPTIONS)
        for excluded in EXCLUDED_DESCRIPTIONS:
            assert excluded not in descriptions

    def test_partial_range_keeps_newest_first_ordering(self, temp_db):
        temp_db.seed_db()
        user_id = temp_db.get_user_by_email("demo@spendly.com")["id"]

        result = temp_db.get_recent_transactions(
            user_id, start_date=PARTIAL_START, end_date=PARTIAL_END
        )

        dates = [row["date"] for row in result]
        assert dates == sorted(dates, reverse=True), (
            "Filtered transactions must still be newest-first"
        )
        assert result[0]["description"] == "New running shoes"  # day 14, newest
        assert result[-1]["description"] == "Monthly bus pass top-up"  # day 4, oldest

    def test_zero_match_range_returns_empty_list(self, temp_db):
        temp_db.seed_db()
        user_id = temp_db.get_user_by_email("demo@spendly.com")["id"]

        result = temp_db.get_recent_transactions(
            user_id, start_date=ZERO_MATCH_START, end_date=ZERO_MATCH_END
        )

        assert result == []

    def test_missing_end_date_is_ignored_shows_all_time(self, temp_db):
        temp_db.seed_db()
        user_id = temp_db.get_user_by_email("demo@spendly.com")["id"]

        result = temp_db.get_recent_transactions(user_id, start_date=PARTIAL_START)

        assert len(result) == ALL_TIME_COUNT

    def test_limit_still_respected_alongside_date_filter(self, temp_db):
        """Existing `limit=` callers must be unaffected by the new params."""
        temp_db.seed_db()
        user_id = temp_db.get_user_by_email("demo@spendly.com")["id"]

        result = temp_db.get_recent_transactions(
            user_id, limit=2, start_date=PARTIAL_START, end_date=PARTIAL_END
        )

        assert len(result) == 2


class TestGetCategoryBreakdownDateFilter:
    def test_partial_range_only_includes_matching_categories(self, temp_db):
        temp_db.seed_db()
        user_id = temp_db.get_user_by_email("demo@spendly.com")["id"]

        result = temp_db.get_category_breakdown(
            user_id, start_date=PARTIAL_START, end_date=PARTIAL_END
        )

        names = {row["name"] for row in result}
        assert names == PARTIAL_CATEGORIES
        for excluded in EXCLUDED_CATEGORIES:
            assert excluded not in names

        assert sum(row["total"] for row in result) == pytest.approx(PARTIAL_TOTAL)
        assert sum(row["percent"] for row in result) == 100

    def test_zero_match_range_returns_empty_list(self, temp_db):
        temp_db.seed_db()
        user_id = temp_db.get_user_by_email("demo@spendly.com")["id"]

        result = temp_db.get_category_breakdown(
            user_id, start_date=ZERO_MATCH_START, end_date=ZERO_MATCH_END
        )

        assert result == []

    def test_missing_start_date_is_ignored_shows_all_time(self, temp_db):
        temp_db.seed_db()
        user_id = temp_db.get_user_by_email("demo@spendly.com")["id"]

        result = temp_db.get_category_breakdown(user_id, end_date=PARTIAL_END)

        assert len(result) == 7  # all seven seeded categories, unfiltered


# --------------------------------------------------------------------- #
# Route-level tests: GET /profile?start_date=...&end_date=...
# --------------------------------------------------------------------- #


def _login_as_demo_user(client, db_module):
    db_module.seed_db()
    demo_user = db_module.get_user_by_email("demo@spendly.com")
    with client.session_transaction() as sess:
        sess["user_id"] = demo_user["id"]
    return demo_user


class TestProfileDateFilterRoute:
    def test_filter_requires_login(self, client):
        response = client.get(
            f"/profile?start_date={PARTIAL_START}&end_date={PARTIAL_END}"
        )
        assert response.status_code == 302
        assert response.location.endswith("/login"), (
            "Query params must not bypass the auth guard on /profile"
        )

    def test_no_query_params_shows_all_time_data(self, app, client):
        _login_as_demo_user(client, db)

        response = client.get("/profile")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert f"{ALL_TIME_TOTAL:.2f}" in body
        assert "Showing" not in body, "No 'Showing' note when no filter is applied"

    def test_valid_partial_range_narrows_all_three_sections(self, app, client):
        _login_as_demo_user(client, db)

        response = client.get(
            f"/profile?start_date={PARTIAL_START}&end_date={PARTIAL_END}"
        )

        assert response.status_code == 200
        body = response.get_data(as_text=True)

        assert f"₹{PARTIAL_TOTAL:.2f}" in body, "Filtered total must display with ₹"
        assert str(PARTIAL_COUNT) in body

        for description in INCLUDED_DESCRIPTIONS:
            assert description in body
        for description in EXCLUDED_DESCRIPTIONS:
            assert description not in body

        for category in PARTIAL_CATEGORIES:
            assert category in body

        assert "Showing" in body, "Active filter must show a 'Showing:' note"
        assert "Clear" in body, "Active filter must show a 'Clear' link"

    def test_url_is_directly_reloadable_with_same_filtered_result(self, app, client):
        """A filtered URL must be bookmarkable — reloading it directly
        (a fresh GET, same as the one above) yields the same filtered data."""
        _login_as_demo_user(client, db)
        url = f"/profile?start_date={PARTIAL_START}&end_date={PARTIAL_END}"

        first = client.get(url).get_data(as_text=True)
        second = client.get(url).get_data(as_text=True)

        assert f"₹{PARTIAL_TOTAL:.2f}" in first
        assert f"₹{PARTIAL_TOTAL:.2f}" in second

    def test_zero_match_range_shows_zero_without_error(self, app, client):
        _login_as_demo_user(client, db)

        response = client.get(
            f"/profile?start_date={ZERO_MATCH_START}&end_date={ZERO_MATCH_END}"
        )

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "₹0.00" in body
        for _, _, _, description in SEED_EXPENSES:
            assert description not in body
        assert "₹" in body

    def test_start_after_end_falls_back_to_all_time(self, app, client):
        _login_as_demo_user(client, db)

        response = client.get(
            f"/profile?start_date={PARTIAL_END}&end_date={PARTIAL_START}"
        )

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert f"₹{ALL_TIME_TOTAL:.2f}" in body, (
            "start_date > end_date must be silently ignored, not erroring"
        )
        assert "Showing" not in body, "Invalid range must not be treated as active"

    @pytest.mark.parametrize(
        "start_date,end_date",
        [
            ("not-a-date", PARTIAL_END),
            (PARTIAL_START, "also-not-a-date"),
            ("2026-13-40", PARTIAL_END),
            ("2026/08/04", "2026/08/14"),
        ],
    )
    def test_malformed_dates_fall_back_to_all_time(
        self, app, client, start_date, end_date
    ):
        _login_as_demo_user(client, db)

        response = client.get(
            f"/profile?start_date={start_date}&end_date={end_date}"
        )

        assert response.status_code == 200, "Malformed dates must never 500"
        body = response.get_data(as_text=True)
        assert f"₹{ALL_TIME_TOTAL:.2f}" in body
        assert "Showing" not in body

    def test_only_start_date_param_falls_back_to_all_time(self, app, client):
        _login_as_demo_user(client, db)

        response = client.get(f"/profile?start_date={PARTIAL_START}")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert f"₹{ALL_TIME_TOTAL:.2f}" in body
        assert "Showing" not in body

    def test_only_end_date_param_falls_back_to_all_time(self, app, client):
        _login_as_demo_user(client, db)

        response = client.get(f"/profile?end_date={PARTIAL_END}")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert f"₹{ALL_TIME_TOTAL:.2f}" in body
        assert "Showing" not in body

    def test_empty_string_params_fall_back_to_all_time(self, app, client):
        _login_as_demo_user(client, db)

        response = client.get("/profile?start_date=&end_date=")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert f"₹{ALL_TIME_TOTAL:.2f}" in body
        assert "Showing" not in body

    def test_clear_link_target_has_no_query_params(self, app, client):
        """Clicking Clear returns to plain /profile with all-time data."""
        _login_as_demo_user(client, db)

        # Simulates following the "Clear" link: a plain GET with no params.
        response = client.get("/profile")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert f"₹{ALL_TIME_TOTAL:.2f}" in body
        assert "Showing" not in body

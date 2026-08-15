import pytest


def test_summary_stats_with_expenses(temp_db):
    temp_db.seed_db()
    user_id = temp_db.get_user_by_email("demo@spendly.com")["id"]

    stats = temp_db.get_summary_stats(user_id)

    assert stats["total_spent"] == pytest.approx(423.64)
    assert stats["transaction_count"] == 8
    assert stats["top_category"] == "Shopping"


def test_summary_stats_zero_expenses(temp_db):
    new_id = temp_db.create_user("New User", "new@example.com", "password123")

    stats = temp_db.get_summary_stats(new_id)

    assert stats == {"total_spent": 0, "transaction_count": 0, "top_category": "—"}

def test_returns_seeded_expenses_newest_first(temp_db):
    temp_db.seed_db()
    user_id = temp_db.get_user_by_email("demo@spendly.com")["id"]

    result = temp_db.get_recent_transactions(user_id)

    assert len(result) == 8
    assert result[0]["description"] == "Dinner at a restaurant"
    assert result[0]["amount"] == 32.40
    assert result[-1]["description"] == "Groceries at local market"
    assert result[-1]["amount"] == 12.50
    for item in result:
        assert set(item.keys()) == {"id", "date", "description", "category", "amount"}


def test_respects_limit(temp_db):
    temp_db.seed_db()
    user_id = temp_db.get_user_by_email("demo@spendly.com")["id"]

    result = temp_db.get_recent_transactions(user_id, limit=3)

    assert len(result) == 3


def test_empty_for_user_with_no_expenses(temp_db):
    new_user_id = temp_db.create_user("New User", "new@spendly.com", "password123")

    result = temp_db.get_recent_transactions(new_user_id)

    assert result == []

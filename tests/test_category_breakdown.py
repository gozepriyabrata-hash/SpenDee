def test_category_breakdown_with_expenses(temp_db):
    temp_db.seed_db()
    user_id = temp_db.get_user_by_email("demo@spendly.com")["id"]

    result = temp_db.get_category_breakdown(user_id)

    assert len(result) == 7
    assert [row["total"] for row in result] == sorted(
        (row["total"] for row in result), reverse=True
    )

    top = result[0]
    assert top["name"] == "Shopping"
    assert top["total"] == 150.00
    assert top["percent"] == 35

    assert sum(row["percent"] for row in result) == 100
    for row in result:
        assert isinstance(row["percent"], int)
        assert 0 <= row["percent"] <= 100


def test_category_breakdown_with_no_expenses(temp_db):
    new_user_id = temp_db.create_user("Fresh User", "fresh@spendly.com", "password123")

    result = temp_db.get_category_breakdown(new_user_id)

    assert result == []

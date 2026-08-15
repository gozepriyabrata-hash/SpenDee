import database.db as db


def test_profile_redirects_when_unauthenticated(client):
    response = client.get("/profile")
    assert response.status_code == 302
    assert response.location.endswith("/login")


def test_profile_shows_real_seeded_data(app, client):
    db.seed_db()
    demo_user = db.get_user_by_email("demo@spendly.com")

    with client.session_transaction() as sess:
        sess["user_id"] = demo_user["id"]

    response = client.get("/profile")
    assert response.status_code == 200

    body = response.get_data(as_text=True)
    assert "Demo User" in body
    assert "demo@spendly.com" in body
    assert "₹" in body
    assert "423.64" in body
    assert "Shopping" in body

    newest_idx = body.find("Dinner at a restaurant")
    oldest_idx = body.find("Groceries at local market")
    assert newest_idx != -1 and oldest_idx != -1
    assert newest_idx < oldest_idx

    for category in [
        "Food",
        "Transport",
        "Bills",
        "Health",
        "Entertainment",
        "Shopping",
        "Other",
    ]:
        assert category in body


def test_profile_handles_new_user_with_no_expenses(app, client):
    db.init_db()
    new_user_id = db.create_user("Fresh User", "fresh@example.com", "password123")

    with client.session_transaction() as sess:
        sess["user_id"] = new_user_id

    response = client.get("/profile")
    assert response.status_code == 200

    body = response.get_data(as_text=True)
    assert "Fresh User" in body
    assert "0.00" in body

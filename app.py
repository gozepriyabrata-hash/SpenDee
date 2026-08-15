from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database.db import (
    create_user,
    email_exists,
    get_db,
    get_user_by_email,
    init_db,
    seed_db,
)

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-in-production"

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not name:
            error = "Full name is required."
        elif not email or "@" not in email:
            error = "Enter a valid email address."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif email_exists(email):
            error = "An account with this email already exists."
        else:
            create_user(name, email, password)
            return redirect(url_for("login"))

        return render_template("register.html", error=error, name=name, email=email)

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        user = get_user_by_email(email)
        if user is None or not check_password_hash(user["password_hash"], password):
            error = "Invalid email or password."
            return render_template("login.html", error=error)

        session["user_id"] = user["id"]
        session["user_name"] = user["name"]
        return redirect(url_for("profile"))

    return render_template("login.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user = {
        "name": "Demo User",
        "email": "demo@spendly.com",
        "initials": "DU",
        "member_since": "March 2025",
    }

    summary = {
        "total_spent": 423.64,
        "transaction_count": 8,
        "top_category": "Shopping",
    }

    expenses = [
        {"date": "2026-08-14", "description": "Dinner at a restaurant", "category": "Food", "amount": 32.40},
        {"date": "2026-08-11", "description": "New running shoes", "category": "Shopping", "amount": 150.00},
        {"date": "2026-08-08", "description": "Movie night with friends", "category": "Entertainment", "amount": 60.00},
        {"date": "2026-08-06", "description": "Electricity bill", "category": "Bills", "amount": 89.99},
        {"date": "2026-08-04", "description": "Monthly bus pass top-up", "category": "Transport", "amount": 45.00},
        {"date": "2026-08-02", "description": "Groceries at local market", "category": "Food", "amount": 12.50},
    ]

    categories = [
        {"name": "Food", "total": 44.90, "percent": 60},
        {"name": "Shopping", "total": 150.00, "percent": 100},
        {"name": "Bills", "total": 89.99, "percent": 60},
        {"name": "Entertainment", "total": 60.00, "percent": 40},
        {"name": "Transport", "total": 45.00, "percent": 30},
    ]

    return render_template(
        "profile.html",
        user=user,
        summary=summary,
        expenses=expenses,
        categories=categories,
    )


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)

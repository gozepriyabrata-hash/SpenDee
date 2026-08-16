from datetime import date, datetime

from flask import Flask, abort, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database.db import (
    create_expense,
    create_user,
    email_exists,
    get_category_breakdown,
    get_db,
    get_expense_by_id,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_email,
    get_user_by_id,
    init_db,
    seed_db,
    update_expense,
)

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-in-production"

EXPENSE_CATEGORIES = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]
DESCRIPTION_MAX_LENGTH = 500

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


def _compute_initials(name):
    parts = [p for p in name.split() if p]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0][0].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _format_member_since(created_at):
    dt = datetime.strptime(created_at.split(" ")[0], "%Y-%m-%d")
    return dt.strftime("%B %Y")


def _parse_date_filter(query_params):
    start_date = query_params.get("start_date", "").strip()
    end_date = query_params.get("end_date", "").strip()

    if not start_date or not end_date:
        return None, None

    try:
        start_dt = date.fromisoformat(start_date)
        end_dt = date.fromisoformat(end_date)
    except ValueError:
        return None, None

    if start_dt > end_dt:
        return None, None

    return start_date, end_date


def _format_display_date(iso_date):
    dt = date.fromisoformat(iso_date)
    return f"{dt.day} {dt.strftime('%b %Y')}"


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]
    user_row = get_user_by_id(user_id)
    if user_row is None:
        session.clear()
        return redirect(url_for("login"))

    user = {
        "name": user_row["name"],
        "email": user_row["email"],
        "initials": _compute_initials(user_row["name"]),
        "member_since": _format_member_since(user_row["created_at"]),
    }

    start_date, end_date = _parse_date_filter(request.args)

    summary = get_summary_stats(user_id, start_date, end_date)
    expenses = get_recent_transactions(user_id, start_date=start_date, end_date=end_date)
    categories = get_category_breakdown(user_id, start_date, end_date)

    return render_template(
        "profile.html",
        user=user,
        summary=summary,
        expenses=expenses,
        categories=categories,
        start_date=start_date,
        end_date=end_date,
        start_date_display=_format_display_date(start_date) if start_date else None,
        end_date_display=_format_display_date(end_date) if end_date else None,
    )


@app.route("/analytics")
def analytics():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    return render_template("analytics.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

def _validate_expense_form(form):
    """Returns (amount, fields, error). fields are the cleaned/submitted
    values for re-rendering the form; error is None if valid."""
    amount_raw = form.get("amount", "").strip()
    category = form.get("category", "").strip()
    expense_date = form.get("date", "").strip()
    description = form.get("description", "").strip()

    try:
        amount = float(amount_raw)
    except ValueError:
        amount = None

    error = None
    if amount is None or not (0 < amount < 1_000_000_000):
        error = "Enter a valid amount greater than zero."
    elif category not in EXPENSE_CATEGORIES:
        error = "Select a valid category."
    elif not expense_date:
        error = "Date is required."
    elif len(description) > DESCRIPTION_MAX_LENGTH:
        error = f"Description is too long (max {DESCRIPTION_MAX_LENGTH} characters)."
    else:
        try:
            date.fromisoformat(expense_date)
        except ValueError:
            error = "Enter a valid date."

    fields = {
        "amount": amount_raw,
        "category": category,
        "date_value": expense_date,
        "description": description,
    }
    return amount, fields, error


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    if request.method == "POST":
        amount, fields, error = _validate_expense_form(request.form)

        if error:
            return render_template(
                "add_expense.html",
                error=error,
                categories=EXPENSE_CATEGORIES,
                **fields,
            )

        create_expense(
            session["user_id"],
            round(amount, 2),
            fields["category"],
            fields["date_value"],
            fields["description"] or None,
        )
        return redirect(url_for("profile"))

    return render_template(
        "add_expense.html",
        categories=EXPENSE_CATEGORIES,
        date_value=date.today().isoformat(),
    )


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
def edit_expense(id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    expense = get_expense_by_id(id, session["user_id"])
    if expense is None:
        abort(404)

    if request.method == "POST":
        amount, fields, error = _validate_expense_form(request.form)

        if error:
            return render_template(
                "edit_expense.html",
                error=error,
                categories=EXPENSE_CATEGORIES,
                expense_id=id,
                **fields,
            )

        update_expense(
            id,
            session["user_id"],
            round(amount, 2),
            fields["category"],
            fields["date_value"],
            fields["description"] or None,
        )
        return redirect(url_for("profile"))

    return render_template(
        "edit_expense.html",
        categories=EXPENSE_CATEGORIES,
        expense_id=id,
        amount=expense["amount"],
        category=expense["category"],
        date_value=expense["date"],
        description=expense["description"],
    )


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)

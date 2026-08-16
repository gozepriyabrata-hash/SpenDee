# Spec: Add Expense

## Overview
This feature implements Step 7 of the Spendly roadmap: letting a logged-in
user record a new expense. It replaces the raw-string stub at
`GET /expenses/add` in `app.py` with a real form page, adds a `POST`
handler that validates input and writes the expense to SQLite, and adds
the missing `create_expense()` helper to `database/db.py`. The
`profile.html` page already links to this route via
`url_for('add_expense')`, so this is the next piece needed to make that
link functional. Editing and deleting expenses (Steps 8 and 9) are out of
scope.

## Depends on
- Step 1 (`database/db.py` — `get_db()`, `init_db()`, schema)
- Step 3 (login/session — `session["user_id"]`)
- Step 5/6 (profile page already links to this route)

## Routes
- `GET /expenses/add` — renders the add-expense form — logged-in only
- `POST /expenses/add` — validates input, inserts the expense, redirects
  to `/profile` on success; re-renders the form with an error and the
  submitted values on failure — logged-in only

Both methods are handled by the existing `add_expense()` view function in
`app.py` (add `methods=["GET", "POST"]` to the route decorator, matching
the pattern already used by `register()` and `login()`).

Login-required check follows the exact pattern used in `/profile` and
`/analytics`:
```python
if not session.get("user_id"):
    return redirect(url_for("login"))
```

## Database changes
No schema changes — the `expenses` table (`database/db.py`, `init_db()`)
already has the required columns: `user_id`, `amount`, `category`,
`date`, `description`.

Add one new helper to `database/db.py`:
- `create_expense(user_id, amount, category, date, description)` —
  inserts a row into `expenses` using a parameterized `INSERT` (`?`
  placeholders), returns nothing or the new row id. Follows the same
  connection/commit/close pattern as `create_user()`.

The category value must be validated in `app.py` against the fixed
7-value list already used by `seed_db()`: `Food, Transport, Bills,
Health, Entertainment, Shopping, Other`. Define this list once (e.g. a
module-level constant in `app.py`) and reuse it for both validation and
rendering the `<select>` options.

## Templates
- **Create:** `templates/add_expense.html` — extends `base.html`, uses
  the same form structure/classes as `login.html` / `register.html`
  (`auth-section` / `auth-container` / `auth-card`, `form-group`,
  `form-input`, `btn-submit`, `auth-error` div for a top-level error).
  Fields: amount (number, step 0.01, min > 0), category (`<select>` from
  the fixed list), date (date input, default to today), description
  (optional text input). On validation failure, re-render this same
  template with `error` and the previously submitted field values
  preserved (mirrors `register.html`'s `value="{{ name or '' }}"`
  pattern) — no exceptions, no raw string responses.
- **Modify:** none required. `templates/profile.html` already contains
  `<a href="{{ url_for('add_expense') }}" class="btn-primary">+ Add
  expense</a>` (profile.html:15) — no change needed there.

## Files to change
- `app.py` — replace the `add_expense()` stub with a real `GET`/`POST`
  view; add the category-list constant.
- `database/db.py` — add `create_expense()`.

## Files to create
- `templates/add_expense.html`
- `static/css/add-expense.css` — page-specific styles, loaded via the
  `{% block head %}` pattern (see `profile.html`'s
  `<link rel="stylesheet" href="{{ url_for('static',
  filename='css/profile.css') }}">`). Must reuse the existing CSS custom
  properties in `static/css/style.css` (`--ink`, `--paper-card`,
  `--accent`, `--border`, `--radius-md`, etc.) — no hardcoded hex values.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` via `database/db.py` only
- Parameterised queries only — `?` placeholders, never f-strings in SQL
- All DB logic lives in `database/db.py`, never inline in `app.py`
- Use CSS variables — never hardcode hex values
- The template must extend `base.html`
- Never use raw string returns — always render a template, including on
  validation errors
- Never hardcode URLs — always `url_for()`
- Validate `amount` (numeric, > 0), `category` (must be in the fixed
  list), and `date` (non-empty, valid `YYYY-MM-DD`) server-side; on
  failure re-render the form with an `error` message — do not raise an
  unhandled exception or 500
- `description` is optional and may be empty/omitted
- Currency is displayed with the ₹ symbol, consistent with `profile.html`
- Match the existing login-required pattern used by `/profile` and
  `/analytics` exactly

## Definition of done
- [ ] Visiting `/expenses/add` while logged out redirects to `/login`
- [ ] Visiting `/expenses/add` while logged in renders a form with
      amount, category, date, and description fields
- [ ] Submitting the form with a valid amount, category, date, and
      optional description creates a new row in `expenses` for the
      current user and redirects to `/profile`
- [ ] The newly added expense appears in `/profile`'s recent
      transactions and category breakdown
- [ ] Submitting with a missing/invalid amount (blank, zero, negative,
      non-numeric) re-renders the form with an error and no DB write
      occurs
- [ ] Submitting with a category outside the fixed 7-value list is
      rejected with an error and no DB write occurs
- [ ] Submitting with a missing/invalid date is rejected with an error
      and no DB write occurs
- [ ] Previously entered field values are preserved in the form after a
      validation error
- [ ] The "+ Add expense" button on `/profile` navigates to a working
      page (no more raw string stub)
- [ ] `pytest` passes for all new tests covering the above

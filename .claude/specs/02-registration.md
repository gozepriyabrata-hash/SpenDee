# Spec: Registration

## Overview
This feature implements account creation for Spendly. It replaces the current
static `GET /register` stub with a working `POST /register` handler that
validates user input, hashes the password, and inserts a new row into the
`users` table. This is the first authentication-related feature built on top
of the database layer from Step 1, and it unblocks Login (session handling),
Logout (Step 3), and Profile (Step 4), all of which depend on real user
records existing in the database.

## Depends on
- Step 1 — Database setup (`database/db.py`: `get_db()`, `init_db()`, `users`
  table schema). Must already be complete.

## Routes
- `GET /register` — renders the registration form — public (already
  implemented, unchanged)
- `POST /register` — validates input, creates the user, redirects to
  `/login` on success or re-renders the form with an error on failure —
  public

## Database changes
No database changes. The existing `users` table
(`id`, `name`, `email`, `password_hash`, `created_at`) already supports
registration. No new tables, columns, or constraints are needed.

## Templates
- **Create:** none
- **Modify:**
  - `templates/register.html` — change the form `action` from the hardcoded
    `/register` string to `{{ url_for('register') }}`; no structural changes
    needed since the `{% if error %}` block already exists for validation
    messages

## Files to change
- `app.py` — change `@app.route("/register")` to accept `["GET", "POST"]`;
  on `POST`, validate input and call the new `db.py` helper to create the
  user, then redirect to `/login`; on validation failure, re-render
  `register.html` with an `error` message and the previously entered
  `name`/`email` values
- `database/db.py` — add a `create_user(name, email, password)` helper that
  hashes the password with `werkzeug.security.generate_password_hash` and
  inserts the row using a parameterized query; add an `email_exists(email)`
  (or equivalent) helper so `app.py` never queries the `users` table
  directly
- `templates/register.html` — use `url_for('register')` for the form action

## Files to create
None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never f-strings in SQL
- Passwords hashed with werkzeug (`generate_password_hash`) before storage —
  never store plaintext passwords
- All DB logic lives in `database/db.py` — `app.py` route functions only
  fetch data, validate, and render/redirect
- Use CSS variables — never hardcode hex values (no new styles expected,
  but if any are added they must follow this rule)
- All templates extend `base.html`
- Never hardcode URLs in templates — always use `url_for()`
- Validate on the server even though HTML5 `required`/`type="email"`
  attributes exist client-side: name non-empty, email non-empty and
  contains `@`, password at least 8 characters, email not already
  registered
- Duplicate-email and validation failures must re-render `register.html`
  with a clear `error` message — never a bare string response
- Do not implement session/login logic in this step — successful
  registration redirects to `/login`, it does not log the user in

## Definition of done
- [x] Submitting the registration form with valid, unique data creates a
      new row in `users` with a hashed (not plaintext) password, and
      redirects to `/login`
- [x] Submitting with an email that already exists re-renders
      `register.html` with an error and does not create a duplicate row
- [x] Submitting with a password under 8 characters re-renders
      `register.html` with an error and does not create a row
- [x] Submitting with a missing name or email re-renders `register.html`
      with an error and does not create a row
- [x] `GET /register` still renders the form unchanged
- [x] No new pip packages were added to `requirements.txt`
- [x] All new DB access goes through `database/db.py`, none inline in
      `app.py`

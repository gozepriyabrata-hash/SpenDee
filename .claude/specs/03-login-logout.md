# Spec: Login and Logout

## Overview
This feature completes Spendly's authentication flow by wiring up real credential checking on `/login` and implementing `/logout`. Step 2 (Registration) already creates users with hashed passwords but redirects to `/login` without logging anyone in, and `/login` currently only renders the form on `GET` — there is no session concept anywhere in the app yet. This step introduces Flask's server-side session as the single source of truth for "who is logged in," verifies credentials against the `users` table, and replaces the `/logout` bare-string stub with real session teardown. Future steps (profile, expense CRUD) depend on this session mechanism to identify the current user.

## Depends on
- **Step 1 — Database setup**: `users` table (`id`, `name`, `email`, `password_hash`, `created_at`) and `get_db()` with `PRAGMA foreign_keys = ON`.
- **Step 2 — Registration**: `create_user()`, `email_exists()`, and password hashing via `werkzeug.security.generate_password_hash` in `database/db.py`.

## Routes
- `POST /login` — validate submitted email/password against the `users` table, create a session on success and redirect to `/profile`, or re-render `login.html` with an error on failure — public
- `GET /logout` — clear the session and redirect to `/login` — public (safe to call whether or not a session exists)

`GET /login` (already implemented) is unchanged — it continues to just render `login.html`.

## Database changes
No database changes. The `users` table already has every column needed (`email`, `password_hash`) to verify credentials.

`database/db.py` needs one new helper (not a schema change) to support the login route:
- `get_user_by_email(email)` — `SELECT id, name, email, password_hash FROM users WHERE email = ?`, returns the row or `None`.

## Templates
- **Modify:** `templates/login.html` — change the form's hardcoded `action="/login"` to `action="{{ url_for('login') }}"` for consistency with `register.html`. The `{% if error %}` block already exists and can be reused as-is for invalid-credential messages.
- **Modify:** `templates/base.html` — the navbar (`nav-links`) is currently hardcoded to always show "Sign in" / "Get started". Add a conditional block driven by `session.get('user_id')`: when logged in, show the user's name and a "Log out" link (`url_for('logout')`); when logged out, show the existing "Sign in" / "Get started" links.

## Files to change
- `app.py` — add `methods=["GET", "POST"]` to the `/login` route with credential validation (fetch user via `get_user_by_email`, verify with `check_password_hash`, store `session['user_id']` and `session['user_name']` on success); implement `/logout` to `session.clear()` and redirect to `url_for('login')`; set `app.secret_key` (required for Flask sessions to work).
- `database/db.py` — add `get_user_by_email(email)`.
- `templates/login.html` — fix form `action` to use `url_for('login')`.
- `templates/base.html` — add session-aware navbar block.
- `CLAUDE.md` — update the "Implemented vs stub routes" table: mark `GET /logout` as Implemented, and add a row for `POST /login` (Implemented) alongside the existing `GET /login` row.

## Files to create
None.

## New dependencies
No new dependencies. `check_password_hash` ships with the same `werkzeug.security` module already used for `generate_password_hash` — no `requirements.txt` change needed.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never f-strings in SQL
- Passwords verified with `werkzeug.security.check_password_hash` against the existing `password_hash` column
- Use CSS variables — never hardcode hex values (reuse the existing `.auth-*` classes and `--danger`/`--ink`/`--paper` variables in `style.css`)
- All templates extend `base.html`
- Store only `user_id` (and optionally `user_name` for display) in the session — never store the password or password hash
- `/logout` must not error when called with no active session; it should simply redirect to `/login`
- Do not touch `/profile` or the `/expenses/*` stub routes — they are out of scope for this step

## Definition of done
- [ ] Submitting the login form with valid credentials (e.g. `demo@spendly.com` / `demo123`) creates a session and redirects away from `/login`
- [ ] Submitting the login form with an invalid email or wrong password re-renders `login.html` with an error message and does not create a session
- [ ] Visiting `/logout` while logged in clears the session and redirects to `/login`
- [ ] Visiting `/logout` while logged out does not raise an error and redirects to `/login`
- [ ] After logging in, reloading any page keeps the session active (no re-login required)
- [ ] `base.html`'s navbar shows a logged-in state (name + "Log out") after login, and the original "Sign in"/"Get started" state after logout
- [ ] `login.html`'s form posts via `url_for('login')` instead of a hardcoded `"/login"` string
- [ ] No new hex colors introduced — all new nav/error styling reuses existing CSS variables

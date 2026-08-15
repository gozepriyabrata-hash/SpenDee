# Spec: Date Filter for Profile Page

## Overview
Step 6 adds a date-range filter to the Profile page so users can narrow the
transactions, summary stats, and category breakdown down to a specific time
window instead of always seeing all-time data. The filter is a plain HTML
form (start date + end date, plus quick presets like "This month" / "This
year" / "All time") submitted via `GET` to `/profile`, so the existing
server-rendered route stays the single source of truth and no JS framework
or client-side state is required. This builds directly on Step 5, which
wired `/profile` to live database queries.

## Depends on
- Step 1: Database setup (`expenses` table with a `date` column)
- Step 3: Login / Logout (`session["user_id"]` is set on login)
- Step 5: Profile backend routes (`/profile` already queries live data via
  `get_summary_stats`, `get_recent_transactions`, `get_category_breakdown`)

## Routes
- `GET /profile` — modified — accepts optional `start_date` and `end_date`
  query parameters (`YYYY-MM-DD`) and filters all profile data to that
  range — logged-in only

If no `start_date`/`end_date` are supplied, `/profile` behaves exactly as it
does today (all-time data). No other new routes.

## Database changes
No database changes. The `expenses.date` column (`TEXT`, ISO `YYYY-MM-DD`)
already supports range comparisons with `BETWEEN` / `>=` / `<=` in SQLite.

## Templates
- **Modify:** `templates/profile.html`
  - Add a date-filter form above "Recent transactions" with two `<input
    type="date">` fields (`start_date`, `end_date`), a "Filter" submit
    button, and a "Clear" link back to `/profile` with no query params.
  - Form uses `method="GET"` and `action="{{ url_for('profile') }}"` so the
    filtered view is a normal, bookmarkable/shareable URL.
  - When a filter is active, show the active range back to the user (e.g.
    "Showing: 1 Aug 2026 – 15 Aug 2026") next to the "Clear" link.
  - No structural changes to the stats, transaction table, or category
    breakdown sections — they keep consuming the same variable names, just
    now scoped to the filtered range.

## Files to change
- `app.py` — `profile()` reads `start_date`/`end_date` from `request.args`,
  validates them, and passes them through to the three query helpers
- `database/db.py` — `get_summary_stats`, `get_recent_transactions`,
  `get_category_breakdown` accept optional `start_date`/`end_date`
  parameters and add a `date BETWEEN ? AND ?` clause when both are present
- `templates/profile.html` — add the filter form and active-range indicator

## Files to create
No new files.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format values into SQL
- Passwords hashed with werkzeug (unaffected by this step, kept for
  consistency with existing rules)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline `<style>` tags — filter styling goes in `static/css/profile.css`
- Vanilla JS only if any JS is added — no frameworks, no npm packages
- `start_date`/`end_date` must be validated server-side: reject malformed
  dates and `start_date > end_date` by ignoring the filter and falling back
  to all-time data, rather than raising an exception
- Currency must always display as ₹ — never £ or $
- Filtering must be entirely server-side; the page must work correctly with
  JavaScript disabled

## Definition of done
- [ ] Visiting `/profile` with no query params shows all-time data, exactly
      as before this step
- [ ] Submitting the filter form with a start/end date range updates the
      total spent, transaction count, top category, transaction list, and
      category breakdown to reflect only expenses within that range
- [ ] The filtered URL (e.g. `/profile?start_date=2026-08-01&end_date=2026-08-15`)
      can be reloaded directly and shows the same filtered results
- [ ] Selecting a range with zero matching expenses shows ₹0.00 total,
      0 transactions, and an empty transaction list/category breakdown
      without errors
- [ ] Submitting `start_date` after `end_date` falls back to all-time data
      instead of erroring
- [ ] Clicking "Clear" returns to `/profile` with no query params and
      all-time data restored
- [ ] All amounts on the filtered view still display the ₹ symbol

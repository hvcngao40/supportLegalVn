# Plan: Fix Campaign Creation Datetime Validation

## Goal
Fix the validation error when creating a campaign:
`"detail": "invalid input for query argument $3: '2026-01-01T00:00:00Z' (expected a datetime.date or datetime.datetime instance, got 'str')"`

## Root Cause Analysis
1. In `api/v1/gamification.py`, the `CampaignCreateRequest` Pydantic model defines the `starts_at` and `ends_at` fields as `str | None`.
2. When a request is received, the string value (e.g., `'2026-01-01T00:00:00Z'`) is passed down as a string into the payload dictionary.
3. In `core/gamification/postgres_store.py`, `PostgresGamificationStore.create_campaign()` runs an `INSERT` statement via `self.pool.fetchrow()`, passing the string directly.
4. Because the corresponding columns are `timestamptz`, `asyncpg` intercepts the query execution and expects Python `datetime` (or `date`) objects for these arguments, raising an error when it encounters a `str`.

## Proposed Solution
1. **Pydantic Validation Update:**
   Update `CampaignCreateRequest` in [gamification.py](file:///c:/Users/hvcng/PycharmProjects/supportLegalVn/api/v1/gamification.py) to declare `starts_at` and `ends_at` as `datetime | None = None`. This will automatically parse ISO-8601 strings into Python `datetime` objects and return standard HTTP 422 Validation Errors if invalid string values are provided, instead of a database 500 error.
2. **Store Robustness:**
   In [postgres_store.py](file:///c:/Users/hvcng/PycharmProjects/supportLegalVn/core/gamification/postgres_store.py), import `datetime` and ensure that if `starts_at` or `ends_at` are passed as strings, we parse them to `datetime` objects. This provides safety if the method is called directly with raw string values.

## Verification Plan
1. Run local tests:
   ```bash
   .venv\Scripts\python -m pytest tests/test_gamification_api.py tests/test_gamification_full_flow.py tests/test_gamification_rules.py tests/test_gamification_worker.py
   ```
2. Write a new unit/integration test reproducing the issue (passing string date/times to campaign creation) and verifying it works correctly.

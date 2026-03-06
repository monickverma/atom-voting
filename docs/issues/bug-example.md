# Bug Report Example

> Use this as a reference when writing a bug report issue.
> Copy the structure below into your GitHub issue.

---

## Title

`fix(api): 500 error when vote is cast on closed poll`

## Labels

`type: bug` · `priority: high` · `difficulty: intermediate`

---

## Description

The API returns `HTTP 500 Internal Server Error` when a user attempts to vote on a poll that has already closed. The expected behaviour is a `422 Unprocessable Entity` with error code `POLL_CLOSED`.

## Steps to Reproduce

```bash
# 1. Create a poll that closes in the past
curl -X POST http://localhost:8000/api/v1/polls \
  -H "Content-Type: application/json" \
  -d '{"title": "Test", "options": ["A", "B"], "closes_at": "2020-01-01T00:00:00Z"}'

# 2. Attempt to vote
curl -X POST http://localhost:8000/api/v1/polls/{poll_id}/vote \
  -H "Content-Type: application/json" \
  -d '{"choice": "A"}'
```

## Expected Behaviour

```json
HTTP 422 Unprocessable Entity
{
  "error": {
    "code": "POLL_CLOSED",
    "message": "Voting period has ended."
  }
}
```

## Actual Behaviour

```
HTTP 500 Internal Server Error
```

## Environment

- Python: 3.12.2
- FastAPI: 0.110.0
- OS: Ubuntu 22.04

## Possible Cause

The `cast_vote` function in `src/core/voting.py` does not check `closes_at` before processing.

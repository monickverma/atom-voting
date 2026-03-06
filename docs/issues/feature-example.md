# Feature Request Example

> Use this as a reference when writing a feature request issue.
> Copy the structure below into your GitHub issue.

---

## Title

`feat: Add batch voting endpoint`

## Labels

`type: feature` · `priority: medium` · `difficulty: good first issue`

---

## Problem

Currently, voters must submit one HTTP request per vote. For bulk testing or integration scenarios, this is inefficient.

## Proposed Solution

Add `POST /api/v1/polls/{id}/votes/batch` that accepts an array of choices and processes them in a single transaction.

**Example request:**
```json
{
  "votes": [
    { "voter_id": "user_001", "choice": "Python" },
    { "voter_id": "user_002", "choice": "Rust" }
  ]
}
```

## Alternatives Considered

- Client-side batching: puts the burden on every client, doesn't help with transaction safety
- GraphQL mutations: out of scope for current API design

## Acceptance Criteria

- [ ] Endpoint accepts an array of up to 100 votes
- [ ] Entire batch succeeds or fails atomically
- [ ] Returns per-vote result in response
- [ ] Unit tests added for batch logic
- [ ] `docs/api.md` updated

## Additional Context

Related to issue #10 (rate limiting) — both endpoints should share the same rate limiting layer.

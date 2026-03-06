# API Reference

All endpoints are versioned under `/api/v1/`. All responses use a consistent envelope.

## Response Envelope

**Success**
```json
{
  "data": { ... }
}
```

**Error**
```json
{
  "error": {
    "code": "VOTE_ALREADY_CAST",
    "message": "You have already voted in this poll."
  }
}
```

---

## Polls

### Create a Poll

```
POST /api/v1/polls
```

**Request body**
```json
{
  "title": "Best programming language?",
  "options": ["Python", "Rust", "Go"],
  "closes_at": "2026-03-10T00:00:00Z"
}
```

**Response** `201 Created`
```json
{
  "data": {
    "id": "poll_abc123",
    "title": "Best programming language?",
    "options": ["Python", "Rust", "Go"],
    "closes_at": "2026-03-10T00:00:00Z",
    "created_at": "2026-03-06T11:00:00Z"
  }
}
```

---

### Get a Poll

```
GET /api/v1/polls/{poll_id}
```

**Response** `200 OK`
```json
{
  "data": {
    "id": "poll_abc123",
    "title": "Best programming language?",
    "options": ["Python", "Rust", "Go"],
    "status": "open"
  }
}
```

---

## Votes

### Cast a Vote

```
POST /api/v1/polls/{poll_id}/vote
```

**Request body**
```json
{
  "choice": "Python"
}
```

**Response** `200 OK`
```json
{
  "data": {
    "poll_id": "poll_abc123",
    "choice": "Python",
    "voter_id": "user_xyz",
    "cast_at": "2026-03-06T11:05:00Z"
  }
}
```

**Error — already voted** `409 Conflict`
```json
{
  "error": {
    "code": "VOTE_ALREADY_CAST",
    "message": "You have already voted in this poll."
  }
}
```

---

### Get Results

```
GET /api/v1/polls/{poll_id}/results
```

**Response** `200 OK`
```json
{
  "data": {
    "poll_id": "poll_abc123",
    "total_votes": 42,
    "results": [
      { "option": "Python", "votes": 25, "percentage": 59.5 },
      { "option": "Rust",   "votes": 12, "percentage": 28.6 },
      { "option": "Go",     "votes": 5,  "percentage": 11.9 }
    ]
  }
}
```

---

## Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `POLL_NOT_FOUND` | 404 | Poll ID does not exist |
| `POLL_CLOSED` | 422 | Voting period has ended |
| `INVALID_CHOICE` | 422 | Choice not in poll options |
| `VOTE_ALREADY_CAST` | 409 | Voter has already submitted a vote |
| `RATE_LIMITED` | 429 | Too many requests |
| `UNAUTHORIZED` | 401 | Missing or invalid auth token |

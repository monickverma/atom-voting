# Roadmap

This roadmap outlines the development direction of Atom Voting. It is a living document — community input shapes what gets prioritised.

---

## v1.0 — Hackathon Release ✅ (Current)

- [x] Core voting domain logic (`src/core/voting.py`)
- [x] REST API with versioned endpoints (`/api/v1/`)
- [x] Create poll, cast vote, retrieve results endpoints
- [x] Modular architecture (core / services / api / models)
- [x] Docker Compose local development
- [x] CI pipeline (lint + type check + tests)
- [x] Full contributor documentation

---

## v1.1 — Contributions Welcome 🙌

> These are confirmed next steps. Great contribution opportunities.

- [ ] Add rate limiting to prevent vote spam (#15) — `difficulty: intermediate`
- [ ] Add batch voting endpoint for bulk submissions (#12) — `difficulty: good first issue`
- [ ] Write integration tests for API endpoints (#18) — `difficulty: good first issue`
- [ ] Add Dependabot for dependency updates (#22) — `difficulty: good first issue`
- [ ] Add pagination to results endpoint (#25) — `difficulty: intermediate`

---

## v2.0 — Community Input Needed 💬

> These are ideas under active discussion. Open a Discussion to share your thoughts.

- [ ] WebSocket support for real-time vote results
- [ ] Plugin system for custom tallying strategies (ranked choice, quadratic, etc.)
- [ ] Web dashboard UI
- [ ] Webhook integration for vote event notifications
- [ ] Multi-language support

---

## Ideas Under Consideration 💡

These are not committed but welcome PRs:

- Slack / Discord bot integration
- Public audit log export (CSV, JSON)
- Anonymous voting mode
- Multi-tenant support

---

## How to Influence the Roadmap

1. Open a [GitHub Discussion](https://github.com/monickverma/atom-voting/discussions) under **Ideas**
2. Upvote existing feature requests in Issues
3. Submit a PR — working code drives prioritisation faster than anything else

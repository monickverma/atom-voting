# ADR-001: Use PostgreSQL as the Primary Database

**Status**: Accepted
**Date**: 2026-03-06
**Deciders**: @monickverma

---

## Context

Atom Voting needs a persistent data store for polls and votes. The key requirements are:

- ACID compliance — a vote that is committed must never be lost
- Relational queries — retrieving vote counts and joining poll data
- Concurrent writes — multiple voters submitting simultaneously without corruption
- Well-understood tooling — contributors should not need to learn an exotic database

---

## Decision

We will use **PostgreSQL 15** as the primary database, accessed via **SQLAlchemy 2.0** ORM with async support (`asyncpg` driver).

---

## Alternatives Considered

| Option | Reason Not Chosen |
|--------|------------------|
| **SQLite** | No concurrent writes; not suitable for multi-user production workload |
| **MongoDB** | Document model is a poor fit for the relational poll/vote/result schema; ACID guarantees require extra configuration |
| **MySQL** | PostgreSQL has better JSONB support, better concurrency model, and is more common in our contributors' experience |

---

## Consequences

**Positive**:
- Full ACID guarantees — no partial votes
- Rich query capabilities for analytics and result aggregation
- SQLAlchemy abstracts the database layer — swapping to SQLite for tests is trivial

**Negative**:
- Contributors must have Docker installed to run PostgreSQL locally (mitigated by `docker-compose.yml`)
- Slightly more complex setup than SQLite — mitigated by `make dev`

---

## Review

Revisit if: vote volumes grow to millions of writes/second, at which point a time-series database or event-sourcing approach may be warranted.

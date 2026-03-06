# Developer Onboarding Guide

Welcome to Atom Voting! This guide will walk you through setting up a complete local development environment from scratch.

> This guide is tested on macOS, Linux, and Windows (WSL2). Run through it on a clean machine and open an issue if anything is unclear.

---

## Prerequisites

Install these tools before starting:

| Tool | Minimum Version | Install |
|------|----------------|---------|
| Python | 3.12+ | [python.org](https://www.python.org/downloads/) |
| Docker Desktop | 24+ | [docker.com](https://www.docker.com/get-started/) |
| Git | 2.40+ | [git-scm.com](https://git-scm.com/) |

Verify your setup:
```bash
python --version   # should show 3.12.x
docker --version   # should show 24.x or higher
git --version
```

---

## Step-by-Step Setup

### 1. Fork and clone

```bash
# Fork via GitHub UI, then:
git clone https://github.com/<your-username>/atom-voting
cd atom-voting
```

### 2. Set up remote tracking

```bash
git remote add upstream https://github.com/monickverma/atom-voting
git fetch upstream
```

### 3. Configure environment

```bash
cp .env.example .env
# Open .env and set any required values (DATABASE_URL is pre-set for Docker)
```

### 4. Install dependencies and hooks

```bash
make install
# This installs Python deps + activates pre-commit hooks
```

### 5. Start services

```bash
make dev
# Starts PostgreSQL and Redis via Docker, then the API with hot reload
```

### 6. Verify it's working

```bash
curl http://localhost:8000/health
# Expected: {"status": "ok"}
```

---

## Running the Test Suite

```bash
make test
# All tests should pass with coverage report
```

**What "passing" looks like:**
```
========================= 14 passed in 0.43s ==========================
TOTAL                      coverage: 87%
```

---

## Making Your First Change

1. Create your branch:
   ```bash
   git checkout develop
   git pull upstream develop
   git checkout -b feat/my-feature
   ```

2. Make your changes and run checks:
   ```bash
   make lint     # no errors
   make test     # all pass
   ```

3. Commit following [Conventional Commits](../CONTRIBUTING.md#commit-convention):
   ```bash
   git add .
   git commit -m "feat(api): add my feature"
   ```

4. Push and open a PR targeting `develop`.

---

## Common Setup Errors

### `port 5432 already in use`
You have a local PostgreSQL running. Either stop it or change the port in `docker-compose.yml` and `.env`.

### `ModuleNotFoundError: No module named 'src'`
Run commands from the project root, not from inside `src/`.

### Pre-commit hook fails on first commit
Run `make format` and `make lint` to fix auto-fixable issues, then re-commit.

---

## Project Structure Quick Reference

```
src/
├── api/          HTTP layer — routes only, no business logic
├── services/     Use case orchestration — calls core logic
├── core/         Pure domain logic — no framework imports
├── models/       Pydantic schemas and domain types
└── utils/        Shared helpers
```

---

## Getting Help

- **GitHub Discussions** — Q&A and general questions
- **GitHub Issues** — bugs and feature requests (check existing issues first)
- Tag your issue with `type: docs` if something in this guide needs improvement

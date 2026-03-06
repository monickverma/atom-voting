# Contributing to Atom Voting

Thank you for your interest in contributing! This document covers everything you need to go from zero to a merged pull request.

---

## Table of Contents

1. [Development Setup](#development-setup)
2. [Branch Strategy](#branch-strategy)
3. [Commit Convention](#commit-convention)
4. [Pull Request Process](#pull-request-process)
5. [Code Review](#code-review)
6. [Issue Labels](#issue-labels)
7. [Getting Help](#getting-help)

---

## Development Setup

### Prerequisites

- Python 3.12+
- Docker 24+ and Docker Compose
- Git

### Steps

```bash
# 1. Fork and clone the repository
git clone https://github.com/<your-username>/atom-voting
cd atom-voting

# 2. Copy and configure environment variables
cp .env.example .env

# 3. Install all dependencies and pre-commit hooks
make install

# 4. Start the local development environment
make dev
```

The API will be running at `http://localhost:8000`.

### Verify your setup

```bash
make test    # all tests should pass
make lint    # no lint errors should appear
```

---

## Branch Strategy

We use **Simplified GitFlow**:

| Branch | Purpose |
|---|---|
| `main` | Always stable and deployable. Protected. Receives merges from `develop` only. |
| `develop` | Integration branch. All feature branches merge here. CI must pass. |
| `feat/<name>` | A single feature or work item. Short-lived. |
| `fix/<name>` | Bug fixes. Same lifecycle as feature branches. |
| `docs/<name>` | Documentation-only changes. |
| `refactor/<name>` | Code restructuring with no behavior change. |
| `hotfix/<name>` | Emergency production fixes. Merges into `main` and `develop`. |

```
feat/login
      \
feat/vote ----> develop ----> main
      /
fix/tally
```

**Never commit directly to `main` or `develop`.**

---

## Commit Convention

We follow [Conventional Commits](https://www.conventionalcommits.org/).

```
<type>(optional scope): <short description>
```

### Types

| Type | When to use |
|---|---|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `test` | Adding or updating tests |
| `refactor` | Code change with no feature or fix |
| `chore` | Dependency updates, config, tooling |
| `perf` | Performance improvement |
| `ci` | CI/CD pipeline changes |
| `style` | Formatting, whitespace (no logic change) |

### Examples

```
feat(api): add vote casting endpoint
fix(core): handle duplicate vote edge case
docs(readme): update quick start instructions
test(core): add unit tests for tally logic
refactor(models): extract VoteResult into separate module
chore(deps): upgrade fastapi to 0.110.0
```

### Breaking changes

```
feat(api)!: change vote response envelope from result to data

BREAKING CHANGE: all API responses now wrap data in the `data` key
instead of `result`. Update all clients accordingly.
```

---

## Pull Request Process

1. **Create a branch** from `develop`:
   ```bash
   git checkout develop
   git pull origin develop
   git checkout -b feat/your-feature-name
   ```

2. **Make your changes** following the code style (automated via pre-commit).

3. **Write or update tests** for your changes.

4. **Update documentation** if you've changed behaviour or added a feature.

5. **Submit the PR** targeting the `develop` branch.

6. **Fill in the PR template** — incomplete templates will be sent back.

---

## Code Review

- Maintainers aim to review PRs within **48 hours**.
- PRs must have CI passing before review.
- Address review comments in new commits (don't force-push during review).
- Once approved, maintainers will merge using **Squash and Merge**.

---

## Issue Labels

### Type
| Label | Meaning |
|---|---|
| `type: bug` | Something is broken |
| `type: feature` | New capability |
| `type: docs` | Documentation improvement |
| `type: refactor` | Code quality improvement |
| `type: performance` | Speed or memory improvement |

### Priority
| Label | Meaning |
|---|---|
| `priority: high` | Blocking or urgent |
| `priority: medium` | Should be done soon |
| `priority: low` | Nice to have |

### Difficulty
| Label | Meaning |
|---|---|
| `difficulty: good first issue` | Suitable for newcomers |
| `difficulty: intermediate` | Some familiarity with codebase needed |
| `difficulty: advanced` | Deep knowledge required |

---

## Getting Help

- **GitHub Discussions** — general questions and ideas
- **GitHub Issues** — bug reports and feature requests
- Open an issue and tag it `type: docs` if something in this guide is unclear

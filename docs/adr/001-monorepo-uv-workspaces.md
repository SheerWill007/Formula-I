# ADR 001: Monorepo with uv Workspaces

**Date:** 2026-03-01
**Status:** Accepted

## Context

Pitwaal has multiple Python services (backend, ml, ingestion, stream) that share
types and utilities but are deployed independently. We need a dependency management
strategy that is reproducible, fast, and industry-standard.

`requirements.txt` is excluded from consideration: it has no lock file with hashes,
no dev/prod separation, no dependency resolution, and no workspace concept.

## Decision

Use a **uv workspace** (monorepo). Each Python service has its own `pyproject.toml`
declaring its own dependencies. A single `uv.lock` at the repo root pins every
transitive dependency with a cryptographic hash.

The `uv.lock` file is **committed to git**. This is non-negotiable.

## Consequences

- `uv sync` installs all dependencies across all services in seconds
- Every developer and CI pipeline runs byte-identical dependency versions
- `pyproject.toml` replaces requirements.txt, setup.py, setup.cfg, and MANIFEST.in
- Dev dependencies (`pytest`, `ruff`, `mypy`) are declared separately under `[project.optional-dependencies]`
- Adding a dependency: `uv add flask` (updates pyproject.toml + uv.lock atomically)

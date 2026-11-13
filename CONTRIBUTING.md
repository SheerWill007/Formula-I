# Contributing

Thanks for helping improve BoxUp. Start with the root [README](README.md)
and [repository guide](docs/repository.md) for setup and project layout.

## Development setup

Install dependencies and start the local services:

```bash
make install
make up
make migrate
make seed       # optional sample sessions
```

Run `make backend` and `make frontend` in separate terminals. Keep local
development and tests pointed at local Postgres; do not use production
credentials for routine development.

## Checks

Run the checks relevant to your changes:

```bash
make lint
make test
cd apps/frontend && pnpm tsc --noEmit && pnpm test
```

Backend tests use the configured `DATABASE_URL`; set it to the local database
before running them. CI also runs backend tests, Ruff, the agent golden eval,
frontend type checking, and a frontend build.

## Change guidelines

- Keep database access parameterized and agent tools read-only.
- Keep API and agent tool inputs and outputs explicit and validated.
- Do not commit secrets, local environment files, generated models, or caches.
- Add or update focused tests when changing behavior.
- Update one of the five project docs only when the change affects its subject.

## Pull requests

Use a short branch name such as `feat/telemetry-filter` or
`fix/agent-timeout`. Open a PR against `main`, explain the user-visible change,
and include the checks you ran. Use Conventional Commit prefixes such as
`feat:`, `fix:`, `docs:`, `test:`, or `chore:`.

Keep discussion respectful and focused on the work. Report conduct concerns to
the maintainers through the repository's GitHub contact options.

## Security reports

Do not post vulnerabilities in a public issue. Use GitHub's private
vulnerability reporting (Security tab, "Report a vulnerability") with the impact
and, if possible, reproduction steps and affected files or routes. Never commit `.env` files, credentials,
private API tokens, or sensitive database dumps.

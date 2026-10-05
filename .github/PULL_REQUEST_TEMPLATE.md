## Summary

<!-- What changed, and why. Link related issues: Fixes #123 -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor / tech debt
- [ ] Documentation
- [ ] CI / tooling

## Test plan

<!-- CI runs the same gates. Tick what you ran locally. -->

- [ ] Backend gates: `ruff check . --target-version py312`, `ruff format --check .`, `mypy agent api shared`
- [ ] Backend tests: `pytest tests/ --ignore=tests/test_integration.py` (CI also runs integration + eval suites)
- [ ] Frontend gates: `npm run build`, `npm run lint`, `npm run test`
- [ ] New endpoints and settings are documented (README table + `docs/`)
- [ ] `CHANGELOG.md` `[Unreleased]` entry added
- [ ] Database migrations included (or PR states "no migration") — `alembic heads` stays a single head
- [ ] No secrets, API keys, or `.env` files committed

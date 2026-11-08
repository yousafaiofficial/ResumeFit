# Contributing to ResumeFit

Thank you for contributing! We adhere to professional software engineering workflows and strict version control practices.

---

## 1. Branching Strategy

- **`main` must always be green and deployable.** Direct commits to `main` are prohibited.
- For all work, branch from `main`:
  - `feature/<short-name>` for new features (e.g. `feature/redis-queue`)
  - `fix/<short-name>` for bug fixes (e.g. `fix/pdf-page-boundary`)
  - `test/<short-name>` for test additions or benchmark suites
  - `docs/<short-name>` for documentation updates
- Submit a Pull Request targeting `main`.

---

## 2. Commit Message Conventions

We enforce [Conventional Commits](https://www.conventionalcommits.org/):
- `feat:` A new feature or capability
- `fix:` A bug fix
- `refactor:` Code restructuring without behavior changes
- `test:` Adding or updating tests
- `chore:` Tooling, dependencies, or configuration changes
- `docs:` Documentation improvements

**Rules:**
- Keep commits focused on a single logical change.
- Never commit secrets, credentials, API keys, or personal PDFs.
- Verify tests pass locally before committing.

---

## 3. Quality Gates & Pre-commit

Before committing, ensure your code passes linting, formatting, type checking, and secret detection:

```bash
# Run pre-commit hooks
pre-commit run --all-files

# Run automated test suite
python -m pytest -v
```

All Pull Requests trigger the GitHub Actions CI pipeline running Ruff and Pytest.

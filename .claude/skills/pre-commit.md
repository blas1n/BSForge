# Pre-commit Skill

Run this skill before creating a git commit to ensure all requirements are met.

## Pre-commit Checklist

### 1. Code Quality (Required)

```bash
# Linting - must pass with 0 errors
/home/vscode/.local/bin/uv run ruff check app/

# Type checking - must pass with 0 errors
/home/vscode/.local/bin/uv run mypy app/

# Tests - all must pass
/home/vscode/.local/bin/uv run pytest tests/
```

### 2. Code Review

- [ ] All new functions have type hints
- [ ] All new functions have Google-style docstrings
- [ ] No hardcoded prompts (use `app/prompts/templates/`)
- [ ] No hardcoded patterns (use config)
- [ ] No `# type: ignore` or `# noqa` comments
- [ ] No secrets in code (.env, API keys, credentials)

### 3. Documentation

- [ ] Updated relevant CLAUDE.md if conventions changed
- [ ] Architecture docs updated if design changed

### 4. Security Check

Files that should NEVER be committed:
- `.env` files
- `config/channels/` (real channel configs)
- `config/sources/` (crawl targets)
- `data/` directory
- `datasets/` directory
- `outputs/` directory
- Any file containing API keys or credentials

### 5. Git Commit Format

Use conventional commits:

```
<type>: <description>

[optional body]
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `refactor`: Code refactoring
- `docs`: Documentation
- `test`: Adding tests
- `chore`: Maintenance

Example:
```
feat: Add BGM support to video pipeline

- Integrate Freesound API for music sourcing
- Add audio mixing with configurable volume
```

## Auto-fix Commands

```bash
# Fix import order and simple issues
/home/vscode/.local/bin/uv run ruff check app/ --fix

# Format code
/home/vscode/.local/bin/uv run ruff format app/
```

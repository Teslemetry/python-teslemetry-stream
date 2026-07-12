# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- Add durable project-specific notes here as they are discovered through real work.
- CI runs on push/PR: `.github/workflows/ci.yml`. Uses `uv` (see `uv.lock`).
- `tests/` files are plain scripts (`if __name__ == "__main__"`), not pytest-based - pytest would collect zero tests here. Run each directly, e.g. `uv run python tests/test_field_type_coercion.py`.
- `pyproject.toml` has a `[tool.mypy]` config but no dev-dependency group declares mypy, so `uv sync` alone won't install it. CI installs it ephemerally via `uv run --with mypy mypy teslemetry_stream`.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.

# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- Add durable project-specific notes here as they are discovered through real work.
- CI runs on push/PR: `.github/workflows/ci.yml`. Uses `uv` (see `uv.lock`).
- `tests/` files are plain scripts (`if __name__ == "__main__"`), not pytest-based - pytest would collect zero tests here. Run each directly, e.g. `uv run python tests/test_field_type_coercion.py`.
- `pyproject.toml` has a `[tool.mypy]` config but no dev-dependency group declares mypy, so `uv sync` alone won't install it. CI installs it ephemerally via `uv run --with mypy mypy teslemetry_stream`.
- `Signal` in `const.py` tracks <https://api.teslemetry.com/fields.json>; the config route rejects names it does not know with `fst_err_validation`. Fields the API has retired are not rejected - it accepts the request and names them in a top-level `ignoredFields` list - so the library can lag the published list without breaking.
- Config responses are shaped inconsistently: success is flat, `{"updated_vehicles": n}` plus `ignoredFields` when some were dropped, while errors are wrapped, `{"response": null, "error": ...}`. Do not look for `updated_vehicles` under `response`; that lookup silently never matches.
- `update_config` funnels every caller through one per-vehicle single-flight flush (`TeslemetryStreamVehicle._flush`): the first caller starts it, later callers merge into the same pending config and await it rather than starting their own PATCH. This exists because a batch of listeners scheduled at once (e.g. HA integration setup) must produce one PATCH, not one per listener - see `tests/test_batch_retry_storm.py`. A body-shaped error (`{"error": ...}`) is terminal for that batch: it is not replayed, but the pending config is kept for the next explicit `update_config` call. A transport-level failure (`aiohttp.ClientError`/timeout) gets one bounded retry inside the same flush. `tests/test_config_update.py` covers the response-shape handling.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.

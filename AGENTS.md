# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- Add durable project-specific notes here as they are discovered through real work.

## Maintainer scripts (`scripts/`)

`scripts/` holds prod-touching maintainer tooling that is deliberately kept
out of the `teslemetry_stream` package and out of CI - it needs an
authenticated NATS context with prod access, which CI does not have and
should never be given.

- `scripts/tesla_cache_validate.py` validates Tesla field semantics (tri-state
  vs true-or-absent, observed value domains, presence rates) against the live
  `na_cache`/`eu_cache` NATS KV buckets - vehicle REST snapshots, streamed
  Fleet Telemetry signals, and energy `live_status`/`site_info`. Read-only,
  run by hand by a maintainer. See `scripts/README.md` for usage and the
  reliability guards (most importantly: reads MUST go through
  `nats stream get --last-for ... -j`, never `nats kv get`, which silently
  reads empty on these buckets).
- Its pure logic (field extraction, presence classification, sanitization)
  is unit-tested offline in `tests/test_cache_validate_logic.py` - safe to
  run in CI. The script itself is not exercised by any automated test suite
  because doing so would require prod NATS access.
- This is phase 1 of a longer roadmap (declarative field registry + golden
  fixtures, described in the originating design report) - phases 2+
  (fixtures module, `Field`/`Presence` registry) are intentionally not
  implemented yet.

# Project agent memory

Project-intrinsic knowledge that should travel with the code: build, test, release, architecture, and sharp edges. Add durable notes here as real work uncovers them.

## Build, test, release

- CI (`.github/workflows/ci.yml`) runs `lint` (ruff + mypy), `test` (Python 3.9-3.13 matrix), `build` (`uv build` + `twine check`). Ruff, mypy and twine are deliberately not dev dependencies - `uv sync` won't install them; CI runs each ephemerally via `uv run --with <tool> <tool> ...`. Do the same locally.
- `tests/` files are plain scripts (`if __name__ == "__main__"`), not pytest-based - pytest would collect zero tests. Run each directly: `uv run python tests/test_config_events.py`.
- The `test` job fails outright when `tests/test_*.py` matches nothing. Do not reintroduce a silent-skip fallback.
- Releases go through `.github/workflows/release.yml` on a `v*.*.*` tag: lint + the full test matrix must pass on the release SHA before build, then trusted-publishing OIDC publishes to PyPI and a GitHub release is cut. It carries `workflow_dispatch` so a run that failed before publish can be re-run without tag surgery.
  - It **must stay a top-level workflow**, never a `workflow_call` reusable one: PyPI's trusted publisher is bound to the `release.yml` + `pypi` environment identity, and a reusable workflow signs PEP 740 attestations under the *caller's* identity, which that publisher rejects.
  - `jobs.<id>.environment.name`/`.url` **cannot reference the `env` context** (only `github`, `inputs`, `vars`, `needs`, `secrets`, `strategy`, `matrix` resolve there). Doing so is a workflow-file parse error that fails the whole file at startup, before trigger filtering - every push, zero jobs, no logs. Use literals or `vars.*`.

## Fields and enums (`const.py`)

- `Signal` tracks <https://api.teslemetry.com/fields.json>. The config route rejects unknown names with `fst_err_validation`, but *retired* names are accepted and returned in a top-level `ignoredFields` list - so the library can lag the published list without breaking.
- The `TeslemetryEnum` value tables are hand-maintained against the `tesla-protocol` PyPI package's proto enum descriptors, not derived at runtime: that package pulls in `protobuf` + `googleapis-common-protos`, disproportionate for ~40 static string lists in a library whose only dependency is `aiohttp` and whose consumers (Home Assistant integrations) are sensitive to protobuf pinning. `ChargeState` is the one table that does not match the proto at all (deprecated field, commented in place). `tests/test_enum_tables.py` pins the drift-prone tables as a manual re-check aid, not a live comparison.
- **Adding a streamable field**: give it a `Signal` entry in `const.py` in alphabetical order by constant name, but *append* its `listen_<Field>` method to the **end** of `TeslemetryStreamVehicle` in `vehicle.py` - that method order is chronological-by-addition, not sorted. Pick `make_int`/`make_float`/`make_bool`/`make_dict` by matching the closest existing field of the same shape; there is no per-field firmware-version metadata anywhere in the library, so omit it.

## Stream lifecycle (`stream.py`)

- `TeslemetryStream` has no `__aenter__`/`__aexit__` - do not reintroduce `async with TeslemetryStream(...)` in the README or examples. Lifecycle is listener-driven: `async_add_listener` connects on the first public listener, disconnects on the last one removed; `connect()`/`close()`/`listen()` are for callers managing it themselves.
- Exactly one `_listen_task` is owned. A second concurrent `listen()` joins the owner via `await existing_task` rather than racing it; `connect()` serializes the GET behind `_connect_lock` and re-checks `active` after both the lock and the response, discarding a response that arrived after a stop.
- Internal reconnect paths (EOF, `ClientError`, unexpected exceptions) call `_close_response()`, **never** `close()` - `close()` additionally flips `active=False` and cancels the owned task, i.e. a real stop. `listen()`'s `finally` calls `_close_response()` unconditionally so cancellation still releases the connection.
- Dispatch iterates a **sorted snapshot** of `_listeners.values()` with internal listeners first, never the live dict: a callback adding a listener mid-dispatch (e.g. `get_vehicle()` for an uncached VIN) must not raise `RuntimeError: dictionary changed size during iteration`, and a public callback must not mutate the event before an internal bookkeeping listener has cached from it. `_update_connection_listeners()` has the same mutation hazard and iterates a plain `list(...)` snapshot (no ordering requirement - connection listeners share no mutable event).
- `__anext__` treats `ClientResponseError` with status 401/403 as terminal: sets `active = False` and raises `TeslemetryStreamAuthenticationError`. Every other `aiohttp.ClientError` keeps backoff-and-reconnect.
- `async_add_listener(..., internal=True)` marks a bookkeeping-only listener (the vehicle config-sync listener is the only user). Its `schedule_refresh` gate is unconditionally false, which is what makes construction-time registration safe outside a running event loop. Both the "first listener starts the task" and "last listener removed auto-closes" checks count only public listeners, so an internal listener can neither pin the connection open nor block a later public listener's zero-to-one restart. **Any stream stand-in (test doubles included) must implement `async_add_listener(callback, filters, internal=False)` and `async_add_connection_listener(callback)`.**
- `topics=` is an optional exact SSE wire-event allowlist sent as the connection's `topics` query param. `SseTopic` is the closed server-recognized set; `SSE_VEHICLE_TOPICS`/`SSE_ENERGY_TOPICS`/`SSE_ALL_TOPICS` are client-side presets, flat per-product-kind lists deliberately not split by whether a topic has a connect-time snapshot (server behavior, not something this library encodes). Omitting it (`None`) is legacy-all forever. An explicitly empty iterable raises `ValueError` at construction - "no topics" must not mean "all topics", mirroring the server's 400. A bare `str`/`SseTopic` is accepted as a single topic, not iterated character-by-character; `topics: str | Iterable[str] | None` exists precisely because a lone string also satisfies `Iterable[str]`.
- `ingest()` (and `TeslemetryStreamVehicle.ingest()`, same call with the VIN filled in) is the entry point for an observation not read off the SSE connection - a Bluetooth broadcast, today. It builds the native wire event (`vin`/`data`/`createdAt`) plus an open-ended `metadata` dict (`Metadata.SOURCE`/`Metadata.RAW`) and hands it to the same `_dispatch` `listen()` uses, so existing `listen_*` callbacks receive both sources with no translation and no second subscription. Dispatch is arrival-ordered and the stream holds no per-field value: **nothing is deduplicated, reordered, or dropped, and there is deliberately no source ranking or precedence** - which report to believe is the consumer's decision, made on `metadata`. Ingesting neither requires nor opens a connection. Neither library depends on the other: the BLE-side shim shaping a broadcast into this format lives in `tesla-fleet-api` and the consumer wires the two.

## Vehicle config (`vehicle.py`)

- Config responses are shaped inconsistently: success is flat (`{"updated_vehicles": n}`, plus `ignoredFields` when some were dropped), errors are wrapped (`{"response": null, "error": ...}`). Do not look for `updated_vehicles` under `response` - that lookup silently never matches.
- `update_config` funnels every caller through one per-vehicle single-flight flush (`_flush`): the first caller starts it, later callers merge into the same pending config and await it. This is why a batch of listeners scheduled at once (e.g. HA integration setup) produces one PATCH, not one per listener. A body-shaped error (`{"error": ...}`) is terminal for that batch - not replayed, but the pending config survives for the next explicit `update_config`. A transport-level failure (`ClientError`/timeout) gets one bounded retry inside the same flush.
- `fields` is kept fresh against *server-side* changes (another client, the console, a Teslemetry migration), not just this client's own history. `__init__` registers `_on_config_event` as an internal listener unconditionally at construction - not lazily - so no connection can predate it and miss an event. A well-typed `fields` piece replaces the record (every nested entry must itself be a dict; one bad entry rejects the whole piece rather than leaving something `add_field` would crash on); a missing piece is left untouched; a malformed piece is logged and skipped without touching pending `_config`. The stored dict and each nested per-field dict are **copied, never aliased** to the event handed to public listeners.
- prefer_typed is server-side default now (no per-vehicle toggle exists), but it is a default, not a guarantee: some vehicles still stream string-encoded numerics/booleans, so `make_int`/`make_float`/`make_bool` must keep coercing a `str` payload.
- `add_field` gates its no-op skip on `_populated`, not on connection/topic state. An unpopulated vehicle awaits `_ensure_populated()` - a single-flight `get_config()` GET that concurrent callers join - before deciding; a populated one trusts `fields` with no network call. `_populated` is set by a successful `get_config()` (200 **or** 404 - both authoritative; 404 also clears `fields`, since "no config exists" is itself the answer) and by every `_on_config_event`, and cleared by `_on_connection_event` on disconnect, so a field-config call landing in a reconnect window re-fetches instead of trusting pre-disconnect data. A *failed* fetch is not authoritative: `_ensure_populated()` catches, logs, and leaves the vehicle unpopulated rather than propagating - every `listen_*` reaches `add_field()` through `_enable_field()`'s fire-and-forget `create_task()`, where an uncaught exception would silently abandon the field request.

## Energy sites (`energysite.py`)

- Energy events are shaped unlike vehicle signals: `live_status`/`site_info` are flat top-level envelopes (`{createdAt, site_id, isCache?, live_status|site_info}`), not nested under `data`, and carry a full opaque document rather than a field delta. There is no per-field config to enable - the server auto-polls subscribed sites.
- `energy_totals` differs again: the site id rides `id`, **not** `site_id` - filter on `id` and `totals`. It carries a compact cumulative `totals` object (`EnergyHistoryTotals`), not a document. Wire payload is `id`/`createdAt`/`totals`, plus `isCache` only when true.
- `site_info` does **not** carry `tariff_content`/`tariff_content_v2`. The V2 tariff is its own event/listener (`listen_TariffContentV2`), same envelope shape, with a `None` body meaning explicit server-side removal rather than "not received yet".
- All of these share a silence-means-no-change contract: the server sends a connect-time snapshot and then fires only on change. Freshness lives in REST, never in event cadence.
- There is deliberately no helper recombining `site_info` and `tariff_content_v2` - it would only ever cover V2 (legacy V1 `tariff_content` has no SSE topic and stays REST-only). A consumer wanting both tariffs uses the REST site_info endpoint.

## Test map

| Area | Test |
| --- | --- |
| Config record merge, nested-entry validation | `test_config_events.py` |
| Config listener registration, auto-close exclusion, populated gating | `test_config_listener_lifecycle.py` |
| Config response-shape handling | `test_config_update.py` |
| One-PATCH-per-batch coalescing | `test_batch_retry_storm.py` |
| Reconnect-window re-fetch race | `test_reconnect_config_window.py` |
| Listen task ownership, dispatch snapshots/order, close races | `test_stream_lifecycle.py` |
| 401/403 terminal vs transient retry | `test_auth_failure.py` |
| `str` payload coercion against real telemetry | `test_field_type_coercion.py` |
| `topics` URL construction, empty/bare-string handling, tariff listener | `test_sse_topics.py` |
| Native-event regression, source indistinguishability, no-dedup contract | `test_external_ingest.py` |
| Energy event fixtures | `test_energysite_events.py` |
| Enum tables vs proto names | `test_enum_tables.py` |

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.

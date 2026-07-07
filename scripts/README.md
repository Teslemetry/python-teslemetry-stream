# Maintainer scripts

## `tesla_cache_validate.py` - validate Tesla field semantics against prod

Answers, with evidence instead of guesswork, the questions that keep coming
up when a client library or an HA integration has to decide how to treat a
Tesla field:

- Is this field a genuine **tri-state** (explicit `true`/`false`/`null`), or
  does it follow a **true-or-absent** shape (present when true, simply
  omitted otherwise)?
- What is the **observed value domain** - every distinct value Tesla actually
  sends for this field?
- What is the **presence rate** across the fleet, and does absence correlate
  with some other field (asleep state, a sensor's own "invalid" reading,
  location scope, etc.)?

It queries the production `na_cache`/`eu_cache` NATS KV buckets (read-only)
that Teslemetry's backend already populates from real vehicle/energy
traffic. This promotes the one-off recipe from
`data/chargeport-null-validate-v4/report.md` (the report that settled
`charge_state.charge_port_door_open` as a genuine tri-state, n=723) into a
reusable, committed tool.

### Why this matters

Every one of these was, at some point, a guess that turned out wrong:

- `charge_state.charge_port_door_open`: assumed "null means closed" -
  refuted by 431/723 vehicles reporting explicit `false`.
- Commit `b72b9a9` in this repo: six streamed fields were silently mistyped
  until someone hand-checked na_cache against real telemetry.
- Several Home Assistant integration bugs (`TypeError`/`IndexError` on
  present-null or out-of-range values) trace back to a field whose
  nullability or value domain was never actually confirmed.

This tool exists so that confirmation is a five-minute command instead of a
one-off archaeology project.

### Prerequisites

- The `nats` CLI, with an authenticated context already configured
  (`nats context select` / `nats context info` to confirm). This script
  never hardcodes a context, server URL, or credential - pass `--context`
  if you don't want to rely on whatever context is currently selected.
- Read access to the `na_cache`/`eu_cache` KV buckets. Nothing here needs
  write access; the script never calls `nats kv put`, `nats pub`, or any
  other write path.

This is an **offline, maintainer-run** tool. CI does not have prod NATS
access and should never be given it - CI's job (a later phase) is to check
committed fixtures against a schema, not to touch prod. Run this by hand,
commit what it finds.

### The three record shapes it understands

The cache holds three distinct shapes; pick the matching `--kind`:

| `--kind` | KV key shape | Record body |
|---|---|---|
| `vehicle_data` | `<VIN>.vehicle_data` | Full REST `vehicle_data` snapshot (nested dict: `charge_state`, `climate_state`, `drive_state`, `vehicle_state`, ...) |
| `signal` | `<VIN>.data.<SignalName>` | One streamed Fleet Telemetry signal - the whole record body IS the value (a bare scalar) |
| `energy_live_status` | `energy_sites.<SITE_ID>.live_status` | REST energy `live_status`, wrapped as `{"statusCode":200,"json":{"response":{...}}}` (auto-unwrapped) |
| `energy_site_info` | `energy_sites.<SITE_ID>.site_info` | REST energy `site_info`, same envelope (auto-unwrapped) |

`--field` is a dotted path within the (unwrapped) record for the three REST
kinds, e.g. `charge_state.charge_port_door_open` or `grid_status`. For
`signal` it is the bare `Signal` name as it appears in `const.py`, e.g.
`ChargePortDoorOpen` - no dots, since the KV key already names the field.

### Examples

```bash
# Settle a tri-state-vs-true-or-absent question on a vehicle REST field,
# cross-tabbed against a related field, both regions, every cached record:
python3 scripts/tesla_cache_validate.py \
    --kind vehicle_data \
    --field charge_state.charge_port_door_open \
    --cross-tab charge_state.charge_port_latch \
    --out-md /tmp/charge_port_door_open.md

# The same question for a streamed Fleet Telemetry signal (na region only,
# capped so it doesn't have to walk the entire fleet):
python3 scripts/tesla_cache_validate.py \
    --kind signal --field ChargePortDoorOpen --buckets na --sample 500

# An energy field, both regions:
python3 scripts/tesla_cache_validate.py \
    --kind energy_live_status --field grid_status

# Save sanitized copies of every record touched, to seed phase-2 fixtures:
python3 scripts/tesla_cache_validate.py \
    --kind energy_site_info --field components.battery \
    --save-raw /tmp/tesla-fixture-seed
```

### Reliability guards (do not remove these)

These are the difference between evidence and a fabricated conclusion - see
the original recipe report for how each one was discovered the hard way:

1. **Never uses `nats kv get`.** It reliably times out or silently reads
   empty against these buckets. The only read path used is
   `nats stream get KV_<bucket> --last-for '$KV.<bucket>.<key>' -j`, decoding
   the JSON envelope's base64 `data` field.
2. **Has-key semantics, never truthiness.** Presence is classified as
   `explicit_value` / `present_null` / `key_absent` / `parent_absent` by
   walking the dotted path and checking key membership at each level - an
   explicit `false`/`0`/`null` is never mistaken for "absent".
3. **The non-empty-read guard.** Before any "this field is absent" or
   "this field is always X" conclusion is trustworthy, the tool must have
   actually read at least one non-empty record. If every fetch in a run
   failed or decoded empty, it prints `GUARD TRIPPED` and exits non-zero
   instead of emitting a report - this is exactly the silent-empty failure
   mode that made the original recipe insist on proving reads first.
4. **Read-only, always.** No write path exists in this script. It is safe
   to run repeatedly against prod at any time.
5. **Fetch errors are never counted as absent.** A `nats stream get` that
   times out or returns "no message found" is a `fetch_error`, tallied and
   reported separately from `key_absent`. This matters most for
   `energy_live_status`/`energy_site_info`: those cache entries carry a
   short NATS message TTL (refreshed roughly every 30s), so a nontrivial
   fetch-error rate on energy kinds is expected background noise, not a
   tool bug - it means the entry expired between listing and reading, not
   that the field was absent.

### Output

Markdown (human-readable) and/or JSON (machine-readable) reports include:
presence classification counts and percentages, the observed value domain,
an optional cross-tab against a second field, and an inferred presence shape
(`ALWAYS` / `NULLABLE` / `TRUE_OR_ABSENT` / `CONDITIONALLY_PRESENT` /
`ALWAYS_ABSENT` / `MIXED` / `INSUFFICIENT_DATA`) with a one-line rationale.
Each report ends with a `provenance` line
(`validated na_cache+eu_cache kind=... field=... n=... shape=...`) meant to
be pasted directly into a field's `provenance` string once the phase-3
`Field`/`Presence` registry exists (see
`api-tesla-schema-fixtures-n6/report.md` for that roadmap). This tool
deliberately stops at producing evidence - it does not implement the
registry or the fixtures module itself.

### Sanitization

`--save-raw DIR` writes one sanitized JSON file per record touched. Real
customer values may appear in the statistical report (value domains,
presence counts) since those aren't personally identifying, but full raw
records are redacted before being saved or displayed unless they belong to
the configured reference vehicle/site (`--preferred-vin`/`--preferred-site`,
defaulting to the maintainer's own vehicle and energy site). Redaction
replaces sensitive fields (VIN, id, tokens, precise geo-coordinates, wall
connector VIN/din, email, site name) with a same-typed placeholder rather
than deleting the key, so "is this field present" stays checkable.

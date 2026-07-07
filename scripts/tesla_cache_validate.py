#!/usr/bin/env python3
"""Validate Tesla field semantics against the live prod NATS KV caches.

Read-only maintainer tool. It answers per-field questions that are otherwise
guessed at or re-derived by every consumer: is this field a genuine tri-state
(explicit true/false/null), does it follow a true-or-absent shape (present
when true, omitted rather than false), what value domain is actually
observed, and how often is it present across the fleet?

It queries the `na_cache`/`eu_cache` NATS KV buckets, which hold three record
shapes:

  vehicle_data          <VIN>.vehicle_data           REST vehicle_data snapshot (nested dict)
  signal                <VIN>.data.<SignalName>      one streamed Fleet Telemetry signal (scalar)
  energy_live_status    energy_sites.<SITE>.live_status   REST energy live_status (wrapped)
  energy_site_info      energy_sites.<SITE>.site_info     REST energy site_info (wrapped)

Reliability guards baked in (see data/chargeport-null-validate-v4/report.md,
the recipe this script promotes to a committed tool):

  * `nats kv get` reliably times out / silently reads empty against these
    buckets. This tool ONLY reads via
    `nats stream get KV_<bucket> --last-for '$KV.<bucket>.<key>' -j` and
    base64-decodes the envelope `data` field. Never uses `nats kv get`.
  * Presence is classified with has-key semantics, never truthiness, so an
    explicit `false`/`0`/`null` is never confused with "absent".
  * Before trusting ANY "field is absent" conclusion, the tool proves the
    scan actually read at least one non-empty record. If every fetch in a
    run failed or decoded empty, it refuses to emit a report and exits
    non-zero instead of fabricating an "absent" finding.
  * Read-only: this tool never writes to NATS (no `kv put`, no `pub`). It is
    meant to run on a maintainer box against an authenticated `nats` CLI
    context; no endpoint or credentials are hardcoded here. CI never runs
    this script (it has no prod access and none should be granted).

Usage examples:

    # Vehicle REST snapshot field, both regions, all cached records
    python3 scripts/tesla_cache_validate.py \\
        --kind vehicle_data \\
        --field charge_state.charge_port_door_open \\
        --cross-tab charge_state.charge_port_latch \\
        --out-md /tmp/charge_port_door_open.md

    # One streamed Fleet Telemetry signal, na region only, capped sample
    python3 scripts/tesla_cache_validate.py \\
        --kind signal --field ChargePortDoorOpen --buckets na --sample 200

    # Energy live_status field across both regions
    python3 scripts/tesla_cache_validate.py \\
        --kind energy_live_status --field grid_status

    # Use a non-default nats CLI context (never hardcode one here)
    python3 scripts/tesla_cache_validate.py --context my-prod-context \\
        --kind energy_site_info --field components.battery

See scripts/README.md for the full recipe and rationale.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any

# The maintainer's own reference vehicle/site (captain's ruling, 2026-07-07):
# real customer values may appear in outputs, but should default to this
# vehicle/site where possible; other customers' records are sanitized.
DEFAULT_PREFERRED_VIN = "LRW3F7EK4NC716336"
DEFAULT_PREFERRED_SITE = "2533979794926773"

REGION_BUCKETS = {"na": "na_cache", "eu": "eu_cache"}

# Keys redacted (case-insensitive, anywhere in the record) before a record is
# saved to --save-raw or printed as a --show-samples example, unless the
# record belongs to the configured preferred VIN/site.
SENSITIVE_KEYS = {
    "vin", "id", "id_s", "vehicle_id", "user_id", "tokens", "token",
    "backseat_token", "backseat_token_updated_at", "access_token",
    "refresh_token", "email", "site_name", "din", "latitude", "longitude",
    "native_latitude", "native_longitude", "address",
}


class RecordKind:
    VEHICLE_DATA = "vehicle_data"
    SIGNAL = "signal"
    ENERGY_LIVE_STATUS = "energy_live_status"
    ENERGY_SITE_INFO = "energy_site_info"

    ALL = (VEHICLE_DATA, SIGNAL, ENERGY_LIVE_STATUS, ENERGY_SITE_INFO)


# ---------------------------------------------------------------------------
# nats CLI plumbing (read-only)
# ---------------------------------------------------------------------------


class FetchError(Exception):
    """A read against NATS failed (timeout, no message, bad decode)."""


def _nats_base_args(context: str | None, timeout: str) -> list[str]:
    args = ["nats", f"--timeout={timeout}"]
    if context:
        args.append(f"--context={context}")
    return args


def nats_kv_ls(bucket: str, context: str | None, timeout: str) -> list[str]:
    """List every key in a KV bucket. Read-only (`nats kv ls`)."""
    cmd = _nats_base_args(context, timeout) + ["kv", "ls", bucket]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise FetchError(f"kv ls {bucket} failed: {proc.stderr.strip()}")
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def nats_stream_get_raw(
    bucket: str, key: str, context: str | None, timeout: str
) -> bytes:
    """Read the current value for one KV key via the reliable path.

    Uses `nats stream get KV_<bucket> --last-for '$KV.<bucket>.<key>' -j`
    and base64-decodes the envelope's `data` field. Deliberately never uses
    `nats kv get`, which reliably times out / silently reads empty on these
    buckets (see module docstring).
    """
    subject = f"$KV.{bucket}.{key}"
    cmd = _nats_base_args(context, timeout) + [
        "stream", "get", f"KV_{bucket}", f"--last-for={subject}", "-j",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise FetchError(proc.stderr.strip() or "nats stream get failed")
    try:
        envelope = json.loads(proc.stdout)
        return base64.b64decode(envelope["data"])
    except Exception as exc:  # noqa: BLE001 - surfaced as FetchError below
        raise FetchError(f"could not decode envelope for {key}: {exc}") from exc


# ---------------------------------------------------------------------------
# Record-kind specific key discovery + field extraction
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RecordRef:
    """One KV key that holds a record we want to inspect for a given kind."""

    bucket: str
    key: str
    identifier: str  # VIN or energy site id, used for sanitization + cross-tab labels


def discover_records(
    kind: str, bucket: str, field: str, keys: list[str]
) -> list[RecordRef]:
    if kind == RecordKind.VEHICLE_DATA:
        pattern = re.compile(r"^(?P<id>[^.]+)\.vehicle_data$")
    elif kind == RecordKind.ENERGY_LIVE_STATUS:
        pattern = re.compile(r"^energy_sites\.(?P<id>[^.]+)\.live_status$")
    elif kind == RecordKind.ENERGY_SITE_INFO:
        pattern = re.compile(r"^energy_sites\.(?P<id>[^.]+)\.site_info$")
    elif kind == RecordKind.SIGNAL:
        pattern = re.compile(r"^(?P<id>[^.]+)\.data\." + re.escape(field) + r"$")
    else:
        raise ValueError(f"unknown kind: {kind}")

    refs = []
    for key in keys:
        match = pattern.match(key)
        if match:
            refs.append(RecordRef(bucket=bucket, key=key, identifier=match.group("id")))
    return refs


def discover_signal_universe(bucket: str, keys: list[str]) -> list[str]:
    """VINs known to this bucket, used as the presence-rate denominator for
    the `signal` kind (a `.data.<Signal>` key simply won't exist for a VIN
    that never streamed that signal, so absence is a listing fact, not a
    fetch)."""
    pattern = re.compile(r"^(?P<vin>[^.]+)\.state$")
    vins = []
    for key in keys:
        match = pattern.match(key)
        if match:
            vins.append(match.group("vin"))
    return vins


ENERGY_ENVELOPE_PREFIX = ("json", "response")


def unwrap_energy_envelope(record: Any) -> Any:
    """Energy live_status/site_info records are cached as
    `{"statusCode": 200, "json": {"response": {...actual fields...}}}`.
    Unwrap to the actual field dict; fall back to the raw record if the
    envelope shape doesn't match (so a shape change surfaces as ABSENT
    fields rather than a crash)."""
    node = record
    for key in ENERGY_ENVELOPE_PREFIX:
        if isinstance(node, dict) and key in node:
            node = node[key]
        else:
            return record
    return node


class Presence:
    EXPLICIT_VALUE = "explicit_value"
    PRESENT_NULL = "present_null"
    KEY_ABSENT = "key_absent"
    PARENT_ABSENT = "parent_absent"  # absent because a containing object is missing entirely
    FETCH_ERROR = "fetch_error"


@dataclass
class ClassifiedField:
    identifier: str
    bucket: str
    presence: str
    value: Any = None
    cross_tab_value: Any = None
    error: str | None = None


def extract_dotted(record: Any, path: str) -> tuple[str, Any]:
    """Walk a dotted path with has-key semantics (never truthiness).

    Returns (presence, value). `value` is only meaningful for EXPLICIT_VALUE.
    """
    node = record
    parts = path.split(".")
    for i, part in enumerate(parts):
        is_last = i == len(parts) - 1
        if not isinstance(node, dict) or part not in node:
            # A missing leaf key means its container exists but doesn't
            # carry this field; a missing intermediate segment means some
            # ancestor object (e.g. drive_state on an asleep-vehicle
            # payload) is absent entirely - worth telling apart when
            # diagnosing conditionally-present fields.
            return (Presence.KEY_ABSENT if is_last else Presence.PARENT_ABSENT), None
        node = node[part]
    if node is None:
        return Presence.PRESENT_NULL, None
    return Presence.EXPLICIT_VALUE, node


# ---------------------------------------------------------------------------
# Sanitization (captain's ruling, 2026-07-07): real values may appear in
# outputs, prefer the maintainer's own vehicle/site; other customers'
# records must be sanitized but stay shape-valid.
# ---------------------------------------------------------------------------


def sanitize_record(record: Any, preferred: bool) -> Any:
    if preferred:
        return record
    if isinstance(record, dict):
        out = {}
        for k, v in record.items():
            if k.lower() in SENSITIVE_KEYS:
                out[k] = _redact_shape_valid(v)
            else:
                out[k] = sanitize_record(v, preferred)
        return out
    if isinstance(record, list):
        return [sanitize_record(v, preferred) for v in record]
    return record


def _redact_shape_valid(value: Any) -> Any:
    """Replace a sensitive leaf with a shape-valid placeholder (same type,
    fixed value) rather than deleting the key, so consumers validating
    "field is present" still see it."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return type(value)(0)
    if isinstance(value, str):
        return "REDACTED"
    if value is None:
        return None
    return "REDACTED"


# ---------------------------------------------------------------------------
# Presence-shape inference (labels a finding with the report's taxonomy;
# does NOT build the Field/Presence registry itself - that is phase 3)
# ---------------------------------------------------------------------------


def infer_presence_shape(counts: Counter[str], value_domain: Counter[str]) -> tuple[str, str]:
    explicit = counts[Presence.EXPLICIT_VALUE]
    null = counts[Presence.PRESENT_NULL]
    absent = counts[Presence.KEY_ABSENT] + counts[Presence.PARENT_ABSENT]
    total_conclusive = explicit + null + absent

    if total_conclusive == 0:
        return "INSUFFICIENT_DATA", "no records were successfully classified"

    if absent == 0 and null == 0:
        return "ALWAYS", "never null or absent in this sample"

    if null > 0 and explicit > 0:
        return (
            "NULLABLE",
            f"present-null in {null}/{total_conclusive} records alongside "
            f"{explicit} explicit non-null value(s) - genuine tri-state candidate",
        )

    if absent > 0 and null == 0 and explicit > 0:
        distinct = len(value_domain)
        if distinct == 1:
            return (
                "TRUE_OR_ABSENT",
                f"only one distinct explicit value observed ({next(iter(value_domain))!r}), "
                f"omitted in {absent}/{total_conclusive} - matches the true-or-absent hypothesis",
            )
        return (
            "CONDITIONALLY_PRESENT",
            f"absent in {absent}/{total_conclusive} with {distinct} distinct explicit "
            "values observed when present - confirm the gating condition (scope/sleep/etc.) "
            "before assuming true-or-absent",
        )

    if absent > 0 and explicit == 0 and null == 0:
        return "ALWAYS_ABSENT", "field never observed present in this sample - check the field path"

    return "MIXED", "does not cleanly match one shape - inspect the raw counts"


# ---------------------------------------------------------------------------
# Scan orchestration
# ---------------------------------------------------------------------------


@dataclass
class ScanResult:
    kind: str
    field: str
    cross_tab: str | None
    buckets: list[str]
    sampled: int
    counts: Counter[str] = dc_field(default_factory=Counter)
    value_domain: Counter[str] = dc_field(default_factory=Counter)
    cross_tab_table: dict[tuple[str, str], int] = dc_field(default_factory=dict)
    fetch_errors: list[str] = dc_field(default_factory=list)
    non_empty_reads: int = 0
    saved_raw: int = 0


def _fetch_and_classify(
    ref: RecordRef,
    kind: str,
    field: str,
    cross_tab: str | None,
    context: str | None,
    timeout: str,
) -> tuple[ClassifiedField, Any]:
    try:
        raw = nats_stream_get_raw(ref.bucket, ref.key, context, timeout)
    except FetchError as exc:
        return ClassifiedField(ref.identifier, ref.bucket, Presence.FETCH_ERROR, error=str(exc)), None

    if kind == RecordKind.SIGNAL:
        # The whole decoded body IS the field's value (a bare scalar).
        text = raw.decode("utf-8", errors="replace").strip()
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            value = text
        presence = Presence.PRESENT_NULL if value is None else Presence.EXPLICIT_VALUE
        return ClassifiedField(ref.identifier, ref.bucket, presence, value=value), {field: value}

    try:
        record = json.loads(raw)
    except json.JSONDecodeError as exc:
        return ClassifiedField(
            ref.identifier, ref.bucket, Presence.FETCH_ERROR, error=f"non-JSON body: {exc}"
        ), None

    if kind in (RecordKind.ENERGY_LIVE_STATUS, RecordKind.ENERGY_SITE_INFO):
        record = unwrap_energy_envelope(record)

    presence, value = extract_dotted(record, field)
    cross_val = None
    if cross_tab:
        cross_presence, cross_val = extract_dotted(record, cross_tab)
        if cross_presence != Presence.EXPLICIT_VALUE:
            cross_val = f"<{cross_presence}>"

    classified = ClassifiedField(ref.identifier, ref.bucket, presence, value=value, cross_tab_value=cross_val)
    return classified, record


def run_scan(
    kind: str,
    field: str,
    regions: list[str],
    context: str | None,
    timeout: str,
    sample: int | None,
    concurrency: int,
    cross_tab: str | None,
    preferred_vin: str,
    preferred_site: str,
    save_raw_dir: Path | None,
) -> ScanResult:
    result = ScanResult(kind=kind, field=field, cross_tab=cross_tab, buckets=[], sampled=0)

    all_refs: list[RecordRef] = []
    for region in regions:
        bucket = REGION_BUCKETS[region]
        result.buckets.append(bucket)
        keys = nats_kv_ls(bucket, context, timeout)

        if kind == RecordKind.SIGNAL:
            # Cap the fleet universe itself (not just the present-record
            # fetch), so KEY_ABSENT is always counted against the same
            # denominator as EXPLICIT_VALUE/PRESENT_NULL. Capping only the
            # present-record fetch while leaving KEY_ABSENT computed against
            # the full uncapped universe would silently skew every
            # percentage once --sample is smaller than the true universe.
            universe = discover_signal_universe(bucket, keys)
            if sample is not None and sample > 0:
                universe = universe[:sample]
            universe_set = set(universe)
            present_refs = [
                ref
                for ref in discover_records(kind, bucket, field, keys)
                if ref.identifier in universe_set
            ]
            present_vins = {ref.identifier for ref in present_refs}
            result.counts[Presence.KEY_ABSENT] += len(universe_set) - len(present_vins)
            all_refs.extend(present_refs)
        else:
            refs = discover_records(kind, bucket, field, keys)
            if sample is not None and sample > 0:
                refs = refs[:sample]
            all_refs.extend(refs)

    result.sampled = len(all_refs)

    if save_raw_dir:
        save_raw_dir.mkdir(parents=True, exist_ok=True)

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [
            pool.submit(_fetch_and_classify, ref, kind, field, cross_tab, context, timeout)
            for ref in all_refs
        ]
        for ref, future in zip(all_refs, futures):
            classified, raw_record = future.result()
            result.counts[classified.presence] += 1
            if classified.presence == Presence.FETCH_ERROR:
                result.fetch_errors.append(f"{ref.bucket}:{ref.key}: {classified.error}")
                continue

            result.non_empty_reads += 1

            if classified.presence == Presence.EXPLICIT_VALUE:
                result.value_domain[repr(classified.value)] += 1

            if cross_tab and classified.presence == Presence.EXPLICIT_VALUE:
                key = (repr(classified.value), repr(classified.cross_tab_value))
                result.cross_tab_table[key] = result.cross_tab_table.get(key, 0) + 1

            if save_raw_dir and raw_record is not None:
                is_preferred = ref.identifier in (preferred_vin, preferred_site)
                sanitized = sanitize_record(raw_record, is_preferred)
                out_path = save_raw_dir / f"{ref.bucket}.{ref.identifier}.{kind}.json"
                out_path.write_text(json.dumps(sanitized, indent=2, sort_keys=True))
                result.saved_raw += 1

    return result


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def render_markdown(result: ScanResult) -> str:
    shape, shape_note = infer_presence_shape(result.counts, result.value_domain)
    total = sum(result.counts.values())
    lines = [
        f"# Field validation: `{result.field}` ({result.kind})",
        "",
        f"**Buckets scanned:** {', '.join(result.buckets)}  ",
        f"**Records fetched over the network:** {result.sampled}  ",
        f"**Records classified (fetched + known-absent-from-listing):** {total}  ",
        f"**Non-empty reads:** {result.non_empty_reads}  ",
        f"**Fetch errors:** {len(result.fetch_errors)}",
        "",
    ]
    if result.kind == RecordKind.SIGNAL:
        lines.insert(
            3,
            "_For `signal`, absence is known for free from the key listing "
            "(no fetch needed), so `classified` can exceed `fetched`._  ",
        )

    if result.non_empty_reads == 0:
        lines += [
            "## GUARD TRIPPED - no absence conclusion is trustworthy",
            "",
            "Every read in this scan failed or decoded empty. This matches the "
            "known silent-empty failure mode (see module docstring) - do NOT "
            "treat any KEY_ABSENT count below as evidence the field is absent. "
            "Fix connectivity/context/timeout and re-run.",
            "",
        ]

    lines += [
        f"**Inferred presence shape:** `{shape}`  ",
        f"_{shape_note}_",
        "",
        "## Presence classification",
        "",
        "| Classification | Count | % of total |",
        "|---|---|---|",
    ]
    for presence in (
        Presence.EXPLICIT_VALUE,
        Presence.PRESENT_NULL,
        Presence.KEY_ABSENT,
        Presence.PARENT_ABSENT,
        Presence.FETCH_ERROR,
    ):
        count = result.counts.get(presence, 0)
        pct = (count / total * 100) if total else 0.0
        lines.append(f"| {presence} | {count} | {pct:.1f}% |")

    lines += ["", "## Observed value domain", "", "| Value | Count |", "|---|---|"]
    for value, count in result.value_domain.most_common(30):
        lines.append(f"| `{value}` | {count} |")
    if len(result.value_domain) > 30:
        lines.append(f"| ... {len(result.value_domain) - 30} more distinct values | |")

    if result.cross_tab:
        lines += [
            "",
            f"## Cross-tab: `{result.field}` vs `{result.cross_tab}`",
            "",
            f"| {result.field} | {result.cross_tab} | Count |",
            "|---|---|---|",
        ]
        for (value, cross_val), count in sorted(
            result.cross_tab_table.items(), key=lambda kv: -kv[1]
        ):
            lines.append(f"| `{value}` | `{cross_val}` | {count} |")

    if result.fetch_errors:
        lines += ["", "## Fetch errors (excluded from presence counts)", ""]
        for err in result.fetch_errors[:20]:
            lines.append(f"- `{err}`")
        if len(result.fetch_errors) > 20:
            lines.append(f"- ... {len(result.fetch_errors) - 20} more")

    lines += [
        "",
        "## Provenance",
        "",
        "```",
        f"validated {'+'.join(result.buckets)} "
        f"kind={result.kind} field={result.field} "
        f"n={result.sampled} non_empty={result.non_empty_reads} "
        f"shape={shape}",
        "```",
        "",
        "Paste the line above into a field's `provenance` string once the "
        "phase-3 registry exists.",
    ]
    return "\n".join(lines)


def render_json(result: ScanResult) -> dict[str, Any]:
    shape, shape_note = infer_presence_shape(result.counts, result.value_domain)
    return {
        "kind": result.kind,
        "field": result.field,
        "cross_tab": result.cross_tab,
        "buckets": result.buckets,
        "sampled": result.sampled,
        "non_empty_reads": result.non_empty_reads,
        "counts": dict(result.counts),
        "value_domain": dict(result.value_domain),
        "cross_tab_table": {f"{k[0]}|{k[1]}": v for k, v in result.cross_tab_table.items()},
        "fetch_errors": result.fetch_errors,
        "saved_raw": result.saved_raw,
        "inferred_shape": shape,
        "inferred_shape_note": shape_note,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--kind", required=True, choices=RecordKind.ALL)
    parser.add_argument(
        "--field",
        required=True,
        help="Dotted path within the record (vehicle_data/energy kinds), or the "
        "bare Signal name (signal kind), e.g. charge_state.charge_port_door_open "
        "or ChargePortDoorOpen.",
    )
    parser.add_argument(
        "--cross-tab",
        default=None,
        help="Optional second dotted path to cross-tabulate against (same record). "
        "Not supported for --kind signal.",
    )
    parser.add_argument(
        "--buckets",
        default="na,eu",
        help="Comma-separated regions to scan: na, eu, or na,eu (default).",
    )
    parser.add_argument(
        "--context",
        default=None,
        help="nats CLI context name to use. Defaults to whatever context is "
        "currently selected (`nats context select`) - never hardcode a "
        "context, endpoint, or credential here.",
    )
    parser.add_argument("--timeout", default="20s", help="Per-read nats timeout (default 20s).")
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="Cap the number of records fetched (default: fetch every discovered key).",
    )
    parser.add_argument("--concurrency", type=int, default=10, help="Parallel fetches (default 10).")
    parser.add_argument("--out-json", type=Path, default=None, help="Write the JSON report here.")
    parser.add_argument("--out-md", type=Path, default=None, help="Write the Markdown report here.")
    parser.add_argument(
        "--save-raw",
        type=Path,
        default=None,
        help="Directory to save sanitized per-record JSON, seeding phase-2 fixtures. "
        "Off by default.",
    )
    parser.add_argument("--preferred-vin", default=DEFAULT_PREFERRED_VIN)
    parser.add_argument("--preferred-site", default=DEFAULT_PREFERRED_SITE)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    regions = [r.strip() for r in args.buckets.split(",") if r.strip()]
    for region in regions:
        if region not in REGION_BUCKETS:
            print(f"error: unknown region {region!r}, expected one of {list(REGION_BUCKETS)}", file=sys.stderr)
            return 2

    if args.kind == RecordKind.SIGNAL and args.cross_tab:
        print("error: --cross-tab is not supported for --kind signal", file=sys.stderr)
        return 2

    try:
        result = run_scan(
            kind=args.kind,
            field=args.field,
            regions=regions,
            context=args.context,
            timeout=args.timeout,
            sample=args.sample,
            concurrency=args.concurrency,
            cross_tab=args.cross_tab,
            preferred_vin=args.preferred_vin,
            preferred_site=args.preferred_site,
            save_raw_dir=args.save_raw,
        )
    except FetchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if result.non_empty_reads == 0:
        print(
            "GUARD TRIPPED: every read failed or decoded empty - refusing to "
            "report an absence conclusion. See --out-md/--out-json for details "
            "if you still want the raw counts, or fix connectivity and re-run.",
            file=sys.stderr,
        )

    markdown = render_markdown(result)
    if args.out_md:
        args.out_md.write_text(markdown)
    else:
        print(markdown)

    if args.out_json:
        args.out_json.write_text(json.dumps(render_json(result), indent=2, sort_keys=True))

    return 0 if result.non_empty_reads > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

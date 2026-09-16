"""The api tells string-only clients from numeric-capable ones solely by the
`X-Library` header value: the legacy value `python teslemetry-stream` (no
suffix) means string-only, anything with a `/<version>` suffix means this
client accepts numeric energy-site ids. These tests pin that contract.
"""
from __future__ import annotations

import asyncio
from importlib.metadata import version

from teslemetry_stream.stream import TeslemetryStream


def make_stream() -> TeslemetryStream:
    return TeslemetryStream(session=None, access_token="test-token", manual=True)  # type: ignore[arg-type]


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"{label:<64} {'PASS' if ok else 'FAIL'}{'  ' + detail if detail else ''}")
    return ok


def main() -> None:
    results = []

    headers = asyncio.run(make_stream().headers())
    library_header = headers["X-Library"]
    installed_version = version("teslemetry-stream")

    results.append(
        check(
            "X-Library carries the installed package version",
            library_header == f"python teslemetry-stream/{installed_version}",
            f"got {library_header!r}",
        )
    )
    results.append(
        check(
            "X-Library is not the bare legacy (string-only) value",
            library_header != "python teslemetry-stream",
            f"got {library_header!r}",
        )
    )

    print("-" * 72)
    print("ALL PASS" if all(results) else "FAILURES PRESENT")
    if not all(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

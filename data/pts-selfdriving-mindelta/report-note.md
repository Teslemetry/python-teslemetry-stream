# self_driving_miles_since_reset minimum_delta claim — verification

## Claim
An automated HA-domain reviewer claimed `self_driving_miles_since_reset` never receives
data unless its field config carries `minimum_delta >= 1`, and asked for that to be set,
by precedent with how `odometer` is configured.

## Verification

This library's field configuration surface was inspected directly:

- `TeslemetryStreamVehicle.add_field()` (`teslemetry_stream/vehicle.py:320-339`) builds the
  PATCH body for a field as `{"interval_seconds": interval}` (or `None`) — that is the
  *entire* per-field config shape this library ever sends. There is no `minimum_delta` key,
  parameter, or concept anywhere in `add_field`, `update_config`, `patch_config`,
  `post_config`, or any `listen_*` method.
- Every `listen_*` method (e.g. `listen_Odometer`, `listen_SelfDrivingMilesSinceReset`) goes
  through the same `_enable_field()` → `add_field(field)` path with no interval/delta
  argument exposed to callers.
- `Signal.ODOMETER` and `Signal.SELF_DRIVING_MILES_SINCE_RESET` (`const.py:199,237`) are
  plain enum members like every other signal — neither carries or implies any delta/interval
  default, and there is no per-field default table in this codebase at all.
- A repo-wide grep for `minimum_delta`/`delta` turns up zero references to any such config
  key in `teslemetry_stream/`, `tests/`, or the example scripts — only unrelated hits
  (`energysite.py`'s "field delta" doc comment, `timedelta` import).

## Verdict: no change

The claim doesn't describe anything this library controls. `minimum_delta` is not a field
config option this library ever sends to the Teslemetry server — the only configurable knob
is `interval_seconds`, and it is not set differently for `odometer` than for any other
field (no per-field precedent exists to match). If the underlying server-side field
emission behavior genuinely requires a `minimum_delta` setting, that would need to be a
Teslemetry API/server-side capability this library doesn't yet expose at all — i.e. a new
feature (a new `add_field`/`update_config` parameter plumbed through to the PATCH body),
not a one-line fix to an existing config value. That's out of scope for this "small
verified fix" task and needs its own scoped design (what the parameter should be called,
whether it belongs on `add_field` or as a stream-wide default, etc.) rather than a
speculative field-specific tweak based on an unverifiable external claim.

No code changes made.

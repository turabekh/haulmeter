"""AI-CONTEXT: the ±3-minute validation, and the circularity it refuses (M14-FR2).

E2-FR2's validation is *"an arrival/departure pair derived from a real fleet's ELD feed
matches the facility's gate reality within the F3 ±3-minute target on ≥10 stops."* The
phrase that carries the weight is **the facility's gate reality** — not our own record of
it.

**MOTIVE MAY NOT VALIDATE MOTIVE, and this is enforced rather than asked for.** A ground
truth sourced from the provider proves only that the poller copies faithfully, which is
the one thing already covered by unit tests. `GroundTruth.source` is required and a
provider-derived source is REFUSED at construction — a check a human can forget at 11pm
on a pilot call is not a check.

The permitted sources are the three a fleet can actually produce: a gate log the facility
keeps, a receiver's signed sheet, and the driver's own word. The last is the weakest and
is labelled as such in the report rather than quietly averaged in with the others —
§11.7's discipline pointed at our own evidence for once.

STORED NOWHERE. This is a measuring instrument, not a feature: the report is computed and
printed. Persisting ground truth would make it a second source of arrival times inside a
product whose whole argument is that there is one.
"""

from dataclasses import dataclass
from datetime import datetime

# a source that IS the provider proves nothing — see the module docstring
FORBIDDEN_SOURCES = ("motive", "samsara", "eld", "telematics", "provider", "gomotive")

# the three a fleet can actually produce, weakest last and labelled as such
SOURCE_KINDS = {
    "gate_log": "facility gate log",
    "receiver_sheet": "receiver's signed sheet",
    "driver": "driver's own word (weakest)",
}

TARGET_MINUTES = 3.0
REQUIRED_STOPS = 10


class CircularGroundTruth(Exception):
    """The ground truth came from the thing being validated."""


@dataclass(frozen=True)
class GroundTruth:
    """One stop's independently-observed arrival and departure.

    `source` is REQUIRED and validated. A default would be the whole defect: the field
    exists to make circularity impossible, and a field with a default is a field people
    stop filling in.
    """

    stop_ref: str
    arrived_at: datetime
    departed_at: datetime | None
    source: str
    note: str = ""

    def __post_init__(self) -> None:
        key = (self.source or "").strip().lower()
        if not key:
            raise CircularGroundTruth("a ground truth with no source is not a ground truth")
        if any(bad in key for bad in FORBIDDEN_SOURCES):
            raise CircularGroundTruth(
                f"source '{self.source}' is the provider being validated — "
                "Motive validating Motive proves only that the poller copies faithfully. "
                f"Use one of: {', '.join(SOURCE_KINDS)}"
            )
        if key not in SOURCE_KINDS:
            raise CircularGroundTruth(
                f"unknown source '{self.source}' — use one of: {', '.join(SOURCE_KINDS)}"
            )


def _delta_minutes(a: datetime | None, b: datetime | None) -> float | None:
    if a is None or b is None:
        return None
    return abs((a - b).total_seconds()) / 60.0


@dataclass
class StopComparison:
    stop_ref: str
    source: str
    arrival_delta_min: float | None
    departure_delta_min: float | None
    note: str = ""

    @property
    def worst(self) -> float | None:
        deltas = [d for d in (self.arrival_delta_min, self.departure_delta_min) if d is not None]
        return max(deltas) if deltas else None

    @property
    def passed(self) -> bool | None:
        """None means UNMEASURABLE, which is not a pass. A stop where the ELD never saw
        an arrival cannot be within three minutes of anything, and counting it either way
        would make the headline number a fiction."""
        worst = self.worst
        return None if worst is None else worst <= TARGET_MINUTES


def compare(truth: GroundTruth, eld_arrival, eld_departure) -> StopComparison:
    return StopComparison(
        stop_ref=truth.stop_ref,
        source=truth.source,
        arrival_delta_min=_delta_minutes(eld_arrival, truth.arrived_at),
        departure_delta_min=_delta_minutes(eld_departure, truth.departed_at),
        note=truth.note,
    )


def report(comparisons: list[StopComparison]) -> str:
    """Formatted to paste straight into `docs/validation/m14-slice1.md`.

    Counts UNMEASURABLE separately from failed, because they need different answers: a
    failure means the geofence is wrong, and an unmeasurable stop means the truck was
    never seen at all — usually an unmapped vehicle, which is a mapping problem and not a
    measurement one.
    """
    lines = [
        "| stop | source | arrival Δ | departure Δ | within ±3 min |",
        "|---|---|---|---|---|",
    ]
    passed = failed = unmeasurable = 0
    for c in comparisons:
        if c.passed is True:
            passed += 1
            verdict = "yes"
        elif c.passed is False:
            failed += 1
            verdict = "**NO**"
        else:
            unmeasurable += 1
            verdict = "unmeasurable"
        arr = f"{c.arrival_delta_min:.1f} min" if c.arrival_delta_min is not None else "—"
        dep = f"{c.departure_delta_min:.1f} min" if c.departure_delta_min is not None else "—"
        lines.append(
            f"| `{c.stop_ref[:8]}` | {SOURCE_KINDS[c.source]} "
            f"| {arr} | {dep} | {verdict} |"
        )

    measured = passed + failed
    lines += [
        "",
        f"**{passed} of {measured} measured stops within ±{TARGET_MINUTES:.0f} min** "
        f"· {unmeasurable} unmeasurable · {passed}/{REQUIRED_STOPS} toward the E2-FR2 target.",
    ]
    if unmeasurable:
        lines.append(
            f"> {unmeasurable} stop(s) produced no ELD arrival at all. That is usually an "
            "unmapped vehicle rather than a bad geofence — check the mapping before "
            "reading anything into it."
        )
    weakest = [c for c in comparisons if c.source == "driver"]
    if weakest:
        lines.append(
            f"> {len(weakest)} stop(s) rest on the driver's own word, which is the weakest "
            "of the three sources. Named here rather than averaged in silently."
        )
    if passed >= REQUIRED_STOPS and failed == 0:
        lines.append("")
        lines.append("**E2-FR2's ±3-minute validation is MET.** Record it in the validation log.")
    return "\n".join(lines)

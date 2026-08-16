"""AI-CONTEXT: bands, the provisional label, and the calibration gate (M15-FR4, Q-8).

E3 NAMES THE BANDS AND NOT THE THRESHOLDS, and that gap is handled rather than filled in.
FR4 says "Readiness bands Green/Yellow/Red" — so the vocabulary is the owner's, and this
also settles the question Session A parked when it left `session.band` a String rather than
invent an enum. What no document states is which score becomes which band, and that is a
product judgement about **what a driver is told they are**, not a schema detail.

So the numbers are F13 CONFIG KEYS with stated defaults, on the pattern
`m09.contingency_fee_basis_points` and `m05.arrival_lead_minutes` already use: tunable on a
live box without a deploy, visible in the admin console, and changed by the owner rather
than by a session. The defaults below are a starting position and are recorded in the
handoff as an owner question — composing from an existing mechanism, and parking the actual
figures, rather than hardcoding a number that decides how a driver sees themselves.

Q-8 IS ENFORCED AT THE ONLY PLACE THAT CANNOT BE FORGOTTEN. Until rolling human agreement
clears the gate, **every** band renders "provisional". That is not a flag a caller passes:
`band_for` returns a `BandVerdict` whose `provisional` is computed from the database, and
there is no way to obtain a band without it. A caller who wants to render a bare colour has
to go out of their way, and the test asserts they cannot do it by accident.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.foundation.f13_flags import public as flags

from .models import ReviewSample

# --- the tunable numbers (defaults, owner-confirmable without a deploy) ---------------

CONFIG_BAND_GREEN_MIN = "m15.band_green_min"
CONFIG_BAND_YELLOW_MIN = "m15.band_yellow_min"
CONFIG_CALIBRATION_MIN_AGREEMENT = "m15.calibration_min_agreement_pct"
CONFIG_CALIBRATION_MIN_SAMPLES = "m15.calibration_min_samples"

DEFAULT_GREEN_MIN = 80
DEFAULT_YELLOW_MIN = 55
# E3 §E3.1.10 Q-8 states this one: "rolling human agreement >= 85%".
DEFAULT_MIN_AGREEMENT_PCT = 85
# AI-CONTEXT: a floor on the SAMPLE, not just the rate. Three reviews that happen to agree
# are 100% agreement and prove nothing — without this, the gate would open on the first
# lucky handful and every band would silently drop the word "provisional".
DEFAULT_MIN_SAMPLES = 30


class Band(enum.Enum):
    """E3 §E3.1.4 names these three. There is no fourth and no numeric alternative."""

    green = "green"
    yellow = "yellow"
    red = "red"


@dataclass(frozen=True)
class BandVerdict:
    """A band and whether it may be shown without the provisional label.

    AI-CONTEXT: the two travel together ON PURPOSE. Returning a bare `Band` would let a
    caller render a colour with no qualifier, which is the exact failure Q-8 exists to
    prevent — a driver, or worse a carrier, reading "Green" as a settled judgement from a
    scorer nobody has checked against a human yet.
    """

    band: Band
    provisional: bool
    score: int
    sample_size: int
    agreement_pct: float | None

    @property
    def label_key(self) -> str:
        """The i18n key a surface renders. Provisional has its OWN key, not a suffix.

        A caller cannot render the plain key by accident, because the plain key is only
        ever returned when the gate is met.
        """
        return f"roadside.band.{self.band.value}" + ("_provisional" if self.provisional else "")


def register_config(db: Session) -> None:
    """Declare the tunables at boot, so an operator can find them before they need them."""
    flags.register_config(
        db,
        CONFIG_BAND_GREEN_MIN,
        DEFAULT_GREEN_MIN,
        description=(
            "M15: minimum overall score for a GREEN readiness band (0-100). A product "
            "judgement about what a driver is told they are — owner-tunable."
        ),
        scope="m15",
    )
    flags.register_config(
        db,
        CONFIG_BAND_YELLOW_MIN,
        DEFAULT_YELLOW_MIN,
        description="M15: minimum overall score for a YELLOW band; below this is RED.",
        scope="m15",
    )
    flags.register_config(
        db,
        CONFIG_CALIBRATION_MIN_AGREEMENT,
        DEFAULT_MIN_AGREEMENT_PCT,
        description=(
            "M15 Q-8: rolling human-agreement percent required before bands stop "
            "rendering 'provisional'. E3 states 85."
        ),
        scope="m15",
    )
    flags.register_config(
        db,
        CONFIG_CALIBRATION_MIN_SAMPLES,
        DEFAULT_MIN_SAMPLES,
        description=(
            "M15 Q-8: minimum reviewed turns before the agreement rate means anything. "
            "Three reviews that agree are 100 percent and prove nothing."
        ),
        scope="m15",
    )


# --- the rolling agreement metric ------------------------------------------------------


def rolling_agreement(db: Session, *, window: int = 200) -> tuple[int, float | None]:
    """(sample size, agreement %) over the most recent reviewed turns.

    Returns `None` for the rate when nothing has been reviewed — deliberately not 0.0. A
    zero would read as "the scorer agrees with humans 0% of the time", which is a much
    worse claim than "no human has looked yet", and it is the kind of zero this project
    has a trap about.
    """
    rows = list(
        db.scalars(
            select(ReviewSample)
            .where(ReviewSample.agree.is_not(None))
            .order_by(ReviewSample.created_at.desc())
            .limit(window)
        )
    )
    if not rows:
        return 0, None
    agreed = sum(1 for r in rows if r.agree)
    return len(rows), round(100.0 * agreed / len(rows), 1)


def is_calibrated(db: Session) -> bool:
    """Has the scorer earned the right to drop the word 'provisional'?

    BOTH conditions, and the sample floor is the one that matters in practice: a gate on
    the rate alone opens on the first lucky handful.
    """
    min_pct = float(
        flags.get_config(db, CONFIG_CALIBRATION_MIN_AGREEMENT, DEFAULT_MIN_AGREEMENT_PCT)
    )
    min_samples = int(
        flags.get_config(db, CONFIG_CALIBRATION_MIN_SAMPLES, DEFAULT_MIN_SAMPLES)
    )
    size, pct = rolling_agreement(db)
    if pct is None or size < min_samples:
        return False
    return pct >= min_pct


# --- bands ------------------------------------------------------------------------------


def overall_score(turn_scores: list[dict[str, int]]) -> int:
    """The mean across every scored dimension of every scored turn.

    AI-CONTEXT: turns carrying NO scores are excluded rather than counted as zero, which is
    Q-2 reaching the band. A session where the recogniser failed three times must not
    produce a lower band than one where it did not — the driver said the same things.
    """
    values = [v for scores in turn_scores if scores for v in scores.values()]
    if not values:
        return 0
    return round(sum(values) / len(values))


def band_for(db: Session, turn_scores: list[dict[str, int]]) -> BandVerdict:
    """The only way to get a band, and it always carries its provisional state."""
    green_min = int(flags.get_config(db, CONFIG_BAND_GREEN_MIN, DEFAULT_GREEN_MIN))
    yellow_min = int(flags.get_config(db, CONFIG_BAND_YELLOW_MIN, DEFAULT_YELLOW_MIN))

    score = overall_score(turn_scores)
    if score >= green_min:
        band = Band.green
    elif score >= yellow_min:
        band = Band.yellow
    else:
        band = Band.red

    size, pct = rolling_agreement(db)
    return BandVerdict(
        band=band,
        provisional=not is_calibrated(db),
        score=score,
        sample_size=size,
        agreement_pct=pct,
    )


def record_review(
    db: Session,
    *,
    turn_id,
    ai_band: str,
    human_band: str,
    reviewer: str,
    notes: str | None = None,
) -> ReviewSample:
    """A human's verdict beside the machine's. `agree` is DERIVED, never passed in.

    AI-CONTEXT: letting a caller supply `agree` would let the calibration metric be fed a
    boolean nobody computed from the two bands — and this is the number that decides
    whether a driver's band still says "provisional". It is derived here so the metric
    cannot be told a story.
    """
    sample = ReviewSample(
        turn_id=turn_id,
        ai_band=ai_band,
        human_band=human_band,
        reviewer=reviewer,
        agree=(ai_band == human_band),
        notes=notes,
    )
    db.add(sample)
    db.flush()
    return sample

import enum


class Confidence(enum.Enum):
    """Basis transparency (M8-FR5): confidence is a function of sample size, never
    a fabricated number. Below the low threshold a prediction is a heuristic."""

    heuristic = "heuristic"  # no per-facility samples yet — public/heuristic basis
    low = "low"  # 1–2 tracked stops
    medium = "medium"  # 3–9 tracked stops
    high = "high"  # 10+ tracked stops


LOW_MIN = 1
MEDIUM_MIN = 3
HIGH_MIN = 10


def confidence_for(sample_size: int) -> Confidence:
    if sample_size >= HIGH_MIN:
        return Confidence.high
    if sample_size >= MEDIUM_MIN:
        return Confidence.medium
    if sample_size >= LOW_MIN:
        return Confidence.low
    return Confidence.heuristic

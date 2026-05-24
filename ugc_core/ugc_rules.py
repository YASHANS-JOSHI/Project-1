"""UGC / DEB calculation rules from content development flow."""

from dataclasses import dataclass


@dataclass
class UnitMetrics:
    credits: int
    unit_count: int
    total_learning_hours: float
    hours_per_unit: float
    minutes_per_unit: int
    target_slides: int
    slm_total_words: int
    slm_words_per_unit: int
    pages_estimate: int


def compute_unit_metrics(
    credits: int,
    unit_count: int,
    *,
    slides_per_hour: int = 12,
    delivery_minutes: int = 80,
) -> UnitMetrics:
    """
    Flow doc:
    - Total learning hours (course) = Credit × 30
    - SLM words ≈ Credit × (12000–15000), split per unit
    - e-Tutorial delivery ≈ 80 min/unit (section 4)
    - PPT slides ≈ delivery_hours × (10–15), default 12/hour → ~16 slides/unit
    """
    units = max(1, unit_count)
    total_hours = credits * 30
    hours_per_unit = total_hours / units  # SLM / course planning share

    delivery_hours = delivery_minutes / 60
    target_slides = int(round(delivery_hours * slides_per_hour))
    target_slides = max(12, min(25, target_slides))

    slm_total = credits * 13_500
    slm_per_unit = slm_total // units
    pages = credits * 70
    minutes = delivery_minutes

    return UnitMetrics(
        credits=credits,
        unit_count=units,
        total_learning_hours=total_hours,
        hours_per_unit=hours_per_unit,
        minutes_per_unit=minutes,
        target_slides=target_slides,
        slm_total_words=slm_total,
        slm_words_per_unit=slm_per_unit,
        pages_estimate=pages,
    )

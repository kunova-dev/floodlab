"""Generic time-window selection; event evidence is supplied by the peril application."""

from datetime import date

from .pairs import candidate_pairs


def select_event_pair(observations, aoi, event):
    bounds = {
        k: date.fromisoformat(event[k])
        for k in ("before_start", "before_end", "during_start", "during_end")
    }
    if (
        not bounds["before_start"]
        <= bounds["before_end"]
        < bounds["during_start"]
        <= bounds["during_end"]
    ):
        raise ValueError("Event observation windows must be ordered and non-overlapping")
    eligible = []
    for a, b, assessment in candidate_pairs(observations, aoi, bands=("VV",)):
        da, db = date.fromisoformat(a.datetime[:10]), date.fromisoformat(b.datetime[:10])
        if (
            bounds["before_start"] <= da <= bounds["before_end"]
            and bounds["during_start"] <= db <= bounds["during_end"]
        ):
            rank = (
                -assessment.coverage["common"],
                a.platform != b.platform,
                (db - bounds["during_start"]).days,
                -da.toordinal(),
                a.id,
                b.id,
            )
            eligible.append((rank, a, b, assessment))
    if not eligible:
        raise ValueError(
            "No scientifically compatible observations in the evidence-based event windows"
        )
    _, a, b, assessment = min(eligible, key=lambda item: item[0])
    return (
        a,
        b,
        {
            "policy": event["selection_policy"],
            "eligible_pairs": len(eligible),
            "assessment": assessment.to_dict(),
            "before": a.to_dict(),
            "during": b.to_dict(),
            "interpretation": event["interpretation"],
        },
    )

"""Engine insights — win/loss reasons, conversion, weaknesses, progress.

Placeholder only; the web app fills it lazily via /api/conversion (engine-backed,
over all games of the chosen format).
"""
from ...registry import metric
from ... import widgets as W


@metric("player", title="Engine insights", order=60, category="Insights")
def conversion_stages(ctx):
    return W.conversion()

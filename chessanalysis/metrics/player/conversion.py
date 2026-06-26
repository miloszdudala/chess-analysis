"""Conversion & stage analysis — where you perform well/poorly.

Placeholder only; the web app fills it lazily via /api/conversion (engine-backed,
over all games of the chosen format).
"""
from ...registry import metric
from ... import widgets as W


@metric("player", title="Conversion & stages", order=65)
def conversion_stages(ctx):
    return W.conversion()

"""Recent games — an engine-analysed, clickable list.

This metric only emits a placeholder; the web app fills it lazily via
/api/recent (with a 5/10/20/All selector) so the rest of the report stays fast.
"""
from ...registry import metric
from ... import widgets as W


@metric("player", title="Recent games", order=60)
def recent_games(ctx):
    return W.recent()

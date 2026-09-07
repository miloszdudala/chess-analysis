"""Brackets mode: the ladder — every stat, band by band."""
from __future__ import annotations

from . import mode, run_metrics
from .. import corpus
from ..contexts import CohortContext
from ..document import Document


@mode("brackets")
def brackets(username: str = "", depth: int | None = None) -> Document:
    depth = depth or corpus.DEPTH
    bands = corpus.ladder(depth)
    if not bands:
        raise SystemExit("The corpus is empty — use Expand database to fill it.")
    me = corpus.mine(username, depth) if username else None
    t = corpus.totals(depth)
    ctx = CohortContext(user=username, depth=depth, me=me, bands=bands, totals=t)
    doc = Document(
        mode="brackets", title="Rating brackets",
        subtitle=f"{t['games']} games from {t['players']} players · "
                 f"{t['samples']} samples · depth {depth}",
        meta={"depth": depth, **t})
    run_metrics("brackets", ctx, doc)
    return doc

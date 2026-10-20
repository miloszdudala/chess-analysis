"""Guide mode: what every number in the app means (see `glossary`)."""
from __future__ import annotations

from . import mode
from .. import book, corpus, glossary
from ..document import Document


@mode("guide")
def guide() -> Document:
    t = corpus.totals(corpus.DEPTH)
    facts = {"games": t.get("games"), "players": t.get("players"),
             "time_control": corpus.TIME_CONTROL, "depth": corpus.DEPTH}
    sections = glossary.guide_sections(facts, book.facts())
    doc = Document(mode="guide", title="How to read the numbers",
                   subtitle="Every unit the app uses, with examples computed from "
                            "the same formulas the statistics use.",
                   meta={"ids": [sid for sid, _, _ in sections]})
    for _, title, widgets in sections:
        doc.add(title, widgets)
    return doc

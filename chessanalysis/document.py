"""The Document — a mode's output: ordered widgets + metadata.

This is the serialization boundary. `to_dict()` is what a JS frontend would
fetch as JSON; render_html.py turns the same structure into a static page.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class Section:
    title: str | None
    widgets: list[dict]


@dataclass
class Document:
    mode: str
    title: str
    subtitle: str = ""
    meta: dict = field(default_factory=dict)
    sections: list[Section] = field(default_factory=list)

    def add(self, title, widgets) -> None:
        if not widgets:
            return
        if isinstance(widgets, dict):
            widgets = [widgets]
        widgets = [w for w in widgets if w]
        if widgets:
            self.sections.append(Section(title=title, widgets=widgets))

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "title": self.title,
            "subtitle": self.subtitle,
            "meta": self.meta,
            "sections": [
                {"title": s.title, "widgets": s.widgets} for s in self.sections
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

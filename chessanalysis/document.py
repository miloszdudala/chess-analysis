"""The Document — a mode's output: ordered widgets + metadata.

This is the serialization boundary: `to_dict()` is the JSON the web app's
frontend renders (frontend/js/widgets.js), and what the CLI writes to disk.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class Section:
    title: str | None
    widgets: list[dict]
    category: str | None = None   # UI grouping label (e.g. "Openings")


@dataclass
class Document:
    mode: str
    title: str
    subtitle: str = ""
    meta: dict = field(default_factory=dict)
    sections: list[Section] = field(default_factory=list)

    def add(self, title, widgets, category=None) -> None:
        if not widgets:
            return
        if isinstance(widgets, dict):
            widgets = [widgets]
        widgets = [w for w in widgets if w]
        if widgets:
            self.sections.append(
                Section(title=title, widgets=widgets, category=category))

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "title": self.title,
            "subtitle": self.subtitle,
            "meta": self.meta,
            "sections": [
                {"title": s.title, "widgets": s.widgets, "category": s.category}
                for s in self.sections
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

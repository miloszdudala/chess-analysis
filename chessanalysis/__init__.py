"""Chess game analysis toolkit.

Pluggable architecture:
  * model.py     — PGN parsing into rich, perspective-bound Game objects
  * registry.py  — @register decorator; stats self-register
  * util.py      — aggregation helpers (tally, WDL)
  * render.py    — HTML widgets (cards, tables, bars, sparklines, page shell)
  * stats/       — one file per stat block; auto-discovered at import

To add a new stat: drop a file in stats/ with a @register(...) function that
takes a list[Game] and returns an HTML string. Nothing else to wire up.
"""

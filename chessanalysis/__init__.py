"""Chess game analysis toolkit — pluggable along three axes.

Layers:
  * model.py        PGN -> perspective-bound Game objects (+ parsed moves/clocks)
  * contexts.py     per-mode input shapes (PlayerContext, GameContext, ...)
  * enrich/         derived data (Stockfish engine analysis), cached to disk
  * registry.py     @metric decorator; metrics self-register, tagged by scope
  * metrics/        compute-only units returning widget data — auto-discovered
  * widgets.py      the widget vocabulary (the backend<->frontend data contract)
  * document.py     a mode's output: ordered widgets + metadata (-> JSON)
  * modes/          build a context, run its scope's metrics, assemble a Document
  * render_html.py  default renderer: Document -> static HTML (JSON works too)

Three independent extension axes — each is "drop one file":
  1. New stat   -> add a metrics/<scope>/ file (@metric), pick an existing widget
  2. New mode   -> add a modes/ file (@mode) + a Context; reuses that scope's metrics
  3. New chart  -> add a widgets.py builder + a render_html handler (+ frontend later)

The discipline: metrics compute (never render); modes shape data (never compute);
renderers render (never compute).
"""

"""Chess game analysis toolkit — pluggable along three axes.

Layers:
  * store.py        one SQLite file: games, engine analyses, corpus, training
  * model.py        PGN -> perspective-bound Game objects (+ parsed moves/clocks)
  * phases.py       the opening / middlegame / endgame split, by position
  * enrich/         Stockfish per-move analysis, kept in the store
  * contexts.py     per-mode input shapes (PlayerContext, GameContext, ...)
  * registry.py     @metric decorator; metrics self-register, tagged by scope
  * metrics/        compute-only units returning widget data — auto-discovered
  * widgets.py      the widget vocabulary (the backend<->frontend data contract)
  * document.py     a mode's output: ordered widgets + metadata (-> JSON)
  * modes/          build a context, run its scope's metrics, assemble a Document
  * coach.py        you against rating-matched corpus players, with a control
  * training.py     positions from your games, judged and scheduled
  * explorer.py     the opening explorer over your games, your band, the book

Three independent extension axes — each is "drop one file":
  1. New stat   -> add a metrics/<scope>/ file (@metric), pick an existing widget
  2. New mode   -> add a modes/ file (@mode) + a Context; reuses that scope's metrics
  3. New chart  -> add a widgets.py builder + a renderer in frontend/js/widgets.js

The discipline: metrics compute (never render); modes shape data (never compute);
renderers render (never compute).
"""

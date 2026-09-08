# TODO

Things worth doing, with enough context to pick up cold.

## 1. Compare is still scaffolding

`modes/comparison.py` and `metrics/compare/basics.py` are close to the stub they
started as: one card row (win rate, peak Elo) and little else. The architecture
is there — `CompareContext` carries both cohorts plus their head-to-head games,
and any `@metric("compare")` file is picked up automatically — but almost
nothing uses it.

What it should probably become, now that the Brackets work exists: the same
two-column shape, pointed at a named opponent instead of a rating band. Most of
that machinery already exists and is not compare-specific —
`metrics/brackets/compare.py` tallies two populations through the report's own
classifiers and prints a gap column. Worth reusing rather than rewriting.

Open questions before building:
- Compare syncs and analyses the other player's whole history. At review depth
  that is ~30s a game. It needs the corpus-depth path (`corpus.analyse_own`
  generalised to any account) and a progress UI, or it will just hang.
- Head-to-head is usually a handful of games. Decide what is honestly sayable
  from five games, and what has to fall back to comparing the two full
  histories instead.

## 2. Blunder anatomy, revisited

Removed in the commit that added this file — see the comment left in
`weaknesses.py` where it used to live. It grouped blunders by the tactic the
engine's refutation exploited, and measured against static exchange evaluation
its largest bucket ("Lost material to a capture") was **45% wrong**: it asked
only whether the captured square was defended, never whether the capture won
anything, so an even trade and a won piece looked identical to it.

A rebuild got the material claims right — exchange evaluation, played out
cheapest-attacker-first, so "hung a piece" means the refutation nets a minor
piece or more, and a fork has to *win* on two squares rather than merely attack
them. That part is sound and is worth recovering from git history
(`git log -S _see -- chessanalysis/weaknesses.py`).

What stopped it being shippable is the rest of the taxonomy. Pins, discovered
attacks, deflection, an overloaded defender, a king that has quietly become
unsafe — these are the motifs actually worth naming to a player, and none of
them follow from the position by any arrangement of if-statements. Roughly 43%
of blunders landed in "positional / other", which is honest but not useful.

Ideas, in rough order of appeal:
- Ship only what is provable — mate, material by exchange evaluation, check —
  and name the remainder plainly ("the evaluation collapsed, no immediate
  tactic") rather than implying a taxonomy that is not there.
- Ask the engine instead of a rule: the refutation's principal variation says
  what happens next, and a pin or a deflection is visible in the line even when
  it is invisible in the position. Needs the PV stored, not just the first move.
- Accept that motif naming is a model's job, not a rule's.

Whatever the approach: the audit that caught this is the deliverable. Classify a
sample, then check each label against something independent (exchange evaluation
for material claims), and report the disagreement rate. A classifier nobody has
measured is a classifier nobody should trust.

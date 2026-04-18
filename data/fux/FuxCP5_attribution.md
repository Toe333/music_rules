# FuxCP5 — reference implementation attribution

The Fux portion of `rules_combined.json` and the checker functions in
`src/music_rules/core/fux/` are a Python re-implementation of the species
counterpoint rule set formalized by **FuxCP5**:

- **Repository**: <https://github.com/TomLaiUCL/FuxCP5>
- **Author**: Tom Lai
- **Institution**: UCLouvain (Université catholique de Louvain), Belgium
- **Context**: MSc thesis on constraint-based species counterpoint generation
- **Original implementation**: C++ + Common Lisp, using the Gecode
  constraint-programming library
- **Original license**: GPL (consult upstream `LICENSE` for the exact terms
  in force at the time you read this)

## What we did

We **read** the FuxCP5 source — primarily:

- `FuxCP/c++/headers/constraints.hpp` — declarations and per-constraint docstrings
- `FuxCP/c++/src/constraints.cpp` — implementations
- `FuxCP/lisp/` — high-level orchestration and species selection logic

— and **re-expressed** each rule in our own JSON corpus (with rule IDs,
scopes, exception clauses, soft/hard tiers, and `input_shape` signatures)
and then **re-implemented** the checks in idiomatic Python.

## What we did *not* do

- We did **not** copy any C++ or Common Lisp source files into this
  repository.
- We did **not** translate FuxCP5 functions line-for-line; the Python
  implementations are independently written from the rule descriptions.
- We did **not** include FuxCP5 as a dependency, build artifact, or
  vendored library.

This re-implementation is therefore considered an independent work guided
by, and acknowledging, the prior art. If a downstream user requires GPL
compliance because they consider the rule-text formalization a derivative
work, they should consult upstream FuxCP5 directly.

## When you extend the Fux rule set

If you add a new Fux rule that has a clear analogue in FuxCP5, please:

1. Quote the relevant FuxCP5 constraint name (e.g. `cp_no_chromatic_step`)
   in the rule's `source` field.
2. Re-derive the Python implementation from the rule's description, not by
   transliterating the C++.
3. If you find yourself copying more than a few characters, stop and
   re-read the rule from the perspective of the input shape.

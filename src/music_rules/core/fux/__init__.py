"""Fux species-counterpoint checkers.

Each module in this subpackage implements one or more checker functions
matching the ``input_shape`` signatures declared in
``rules_combined.json``. Phase 3 ships:

* ``melodic`` — ``check_melodic_interval``, ``check_melodic_triple``.
* ``motion``  — ``check_motion_pair``.
* ``harmonic``— ``check_vertical_chord``, ``check_first_interval``,
  ``check_final_interval``.
* ``species`` — orchestration (Phase 4 wires this into ``evaluate_passage``).

Every checker returns the standard report dict::

    {
        "ok": bool,
        "violations": [{"rule_id": str, "msg": str}, ...],
        "soft_costs":  [{"rule_id": str, "cost": float, "msg": str}, ...],
    }
"""

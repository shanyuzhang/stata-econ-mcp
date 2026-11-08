# Stata Econ playbook — index

Read `workflow` first for any analysis task, then the topic guides that apply.

| topic | when |
|---|---|
| workflow | always: project layout, do-file template, order of work, how to report back |
| econ_standards | what a referee/advisor expects: identification, inference, robustness, magnitudes |
| panel_fe | panel data, two-way / high-dimensional FE, clustering, IV with FE, PPML |
| did | difference-in-differences: 2x2, staggered adoption, modern estimators, pre-trends |
| ddd | triple differences: specification, fixed effects, interpretation, pitfalls |
| event_study | dynamic DiD / event-study specs and plots (TWFE and robust estimators) |
| latex_tables | publication tables (stata_table / esttab), descriptive Table 1, figure export |
| stata_gotchas | Stata language traps that silently produce wrong numbers |

Quick decision guide
- Treatment switches on at one date for all treated units → classic DiD (`did`), event study for pre-trends.
- Treatment timing varies across units (staggered) → TWFE as benchmark only; report a heterogeneity-robust
  estimator (csdid / did_imputation / eventstudyinteract / did_multiplegt_dyn) — see `did`.
- Policy hits a subgroup inside treated regions → triple differences (`ddd`).
- No policy shock, just within-unit variation → panel FE (`panel_fe`); be explicit that FE ≠ causal identification.

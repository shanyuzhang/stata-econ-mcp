# Difference-in-differences

## Variables to construct first
```stata
* first_treat: year the unit is first treated; missing (or 0 for csdid) if never treated
bysort id: egen first_treat = min(cond(D == 1, year, .))
gen byte treated = !missing(first_treat)              // ever-treated group
gen byte post    = year >= first_treat & treated       // treated AND after adoption
gen gvar = cond(missing(first_treat), 0, first_treat)  // csdid convention: 0 = never treated
gen rel  = year - first_treat                          // event time (missing for never-treated)
* Check: is treatment absorbing (never switches off)? If not, see did_multiplegt_dyn.
bysort id (year): assert D >= D[_n-1] if _n > 1
```

## Canonical DiD (single adoption date)
```stata
reghdfe y post, absorb(id year) vce(cluster id)        // "post" = treated × after
```
β = ATT under parallel trends. Cluster at the level of treatment assignment.

## Staggered adoption: TWFE is not enough
With treatment timing that varies across units and effects that vary over time/cohorts, the TWFE
coefficient is a weighted average that uses already-treated units as controls and can even carry negative
weights (Goodman-Bacon 2021; de Chaisemartin & D'Haultfœuille 2020; Sun & Abraham 2021;
Callaway & Sant'Anna 2021; Borusyak, Jaravel & Spiess 2024). Standard practice:
1. Report TWFE as the familiar benchmark.
2. Diagnose: `bacondecomp y post, ddetail` (needs a balanced panel, single treatment variable) — how much
   weight comes from "late vs early (already treated)" comparisons.
3. Report at least one heterogeneity-robust estimator and show the estimates are similar (or explain why not).

### Callaway & Sant'Anna — csdid
```stata
csdid y, ivar(id) time(year) gvar(gvar) method(dripw)            // never-treated as controls
csdid y, ivar(id) time(year) gvar(gvar) notyet method(dripw)     // not-yet-treated as controls
estat simple          // overall ATT
estat event, window(-5 5)    // dynamic effects
estat group           // by cohort
csdid_plot            // after estat event
```
- Covariates enter as **baseline (pre-treatment) values**; time-varying controls are not appropriate.
- Default pre-period estimates are "short gaps" (period-to-period); use `long2` option for long differences
  comparable to a TWFE event study.
- Needs never-treated units or the `notyet` option. Units treated in the first period are dropped.
- For repeated cross-sections omit `ivar()`.

### Borusyak–Jaravel–Spiess imputation — did_imputation (ssc install did_imputation)
```stata
gen Ei = first_treat          // missing for never-treated
did_imputation y id year Ei, fe(id year) cluster(id) horizons(0/5) pretrends(5) minn(0)
```

### Sun & Abraham — eventstudyinteract (ssc install eventstudyinteract)
```stata
gen never = missing(first_treat)
* rel_* lead/lag dummies built as in the event_study guide (omit -1)
eventstudyinteract y lead_* lag_*, cohort(first_treat) control_cohort(never) absorb(id year) vce(cluster id)
```

### Others
- `did_multiplegt_dyn` (de Chaisemartin & D'Haultfœuille): non-absorbing / on-off or continuous treatments.
- `jwdid` (Wooldridge extended TWFE / Mundlak): `jwdid y, ivar(id) tvar(year) gvar(gvar)`; then `estat event`.

## Parallel trends evidence
- Event-study pre-period coefficients (see `event_study`), joint F-test of leads = 0.
- Raw trends plot: mean outcome by year for treated vs control (or by cohort).
- Pre-trends tests have low power; if leads are noisy or trending, show HonestDiD sensitivity
  (`honestdid`, Rambachan & Roth 2023) rather than claiming "no pre-trends".

## Standard robustness for DiD
- Not-yet-treated vs never-treated controls; drop always-treated / first-period-treated units.
- Region×year FE; unit-specific linear trends (as a check).
- Placebo timing: pretend treatment happened k years earlier, using only pre-period data.
- Permutation inference: randomly reassign treatment dates/groups many times, compare β with the placebo
  distribution (`permute` or a loop with `set seed`).
- Exclude units affected by concurrent policies; check for anticipation (shift treatment date by −1).
- Spillovers: drop controls adjacent to treated units.

## Continuous / intensity treatment
`reghdfe y c.intensity#c.post_period, absorb(id year)` identifies an average of slopes only under strong
assumptions (Callaway, Goodman-Bacon & Sant'Anna 2024). Present the binary (any exposure) version too,
and show dose-response by intensity bins.

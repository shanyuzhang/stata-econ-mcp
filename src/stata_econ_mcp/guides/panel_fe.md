# Panel fixed effects

## Setup and audit
```stata
isid id year                 // panel must be unique by unit-time; fix before anything else
xtset id year
xtdescribe                   // balance, gaps
bysort id: gen byte _first = _n == 1
count if _first              // number of units
```

## Default estimator: reghdfe
```stata
* Two-way FE, SEs clustered by unit
reghdfe y x1 x2, absorb(id year) vce(cluster id)

* High-dimensional FE: industry-by-year and province-by-year shocks
reghdfe y x1 x2, absorb(id ind#year prov#year) vce(cluster id)

* Two-way clustering
reghdfe y x1 x2, absorb(id year) vce(cluster id year)
```
- `reghdfe` drops singleton groups by default (correct: they bias SEs). Report how many were dropped.
- Variables that are constant within an absorbed FE are not identified (e.g. region dummies with unit FE).
- Report **within R²** (`e(r2_within)`), not the inflated overall R².
- `xtreg y x, fe vce(cluster id)` gives the same β as `reghdfe ..., absorb(id)`; SE small-sample
  adjustments can differ slightly. Prefer reghdfe for >1 FE.
- Store estimates and the dependent-variable mean right after each model:
```stata
reghdfe y x1 x2, absorb(id year) vce(cluster id)
quietly summarize y if e(sample)
estadd scalar ymean = r(mean)
estimates store m1
```

## Choosing FE and clusters
- Unit FE + time FE is the baseline. Add region×time or industry×time FE to absorb local/sectoral shocks;
  check how much identifying variation is left (the coefficient is identified only from within-cell variation).
- Cluster at the level where treatment varies/is assigned, at least at the unit level. If the regressor of
  interest varies at the province level, cluster by province.
- FE vs RE: in applied econ FE is the default. If asked, use a robust Hausman (Mundlak/CRE approach or
  `xtoverid`), not the classic `hausman` which assumes homoskedasticity.

## Dynamic panels
- Lagged dependent variable + unit FE ⇒ Nickell bias when T is small. Use Arellano–Bond / system GMM
  (`xtabond2`) only with care (instrument count ≤ number of groups; report AR(2) and Hansen tests), or
  argue T is large enough.

## IV with fixed effects
```stata
ivreghdfe y (x = z) w1 w2, absorb(id year) cluster(id) first
```
- Report first stage (coefficient on z, F). Use Kleibergen–Paap rk Wald F (`e(widstat)`) with clustered SEs;
  F < 10 is a red flag; consider Anderson–Rubin weak-IV-robust CIs (`weakiv`, or `ivreghdfe ..., first`
  and AR test). State the exclusion restriction in words.

## Count / non-negative outcomes with many zeros
```stata
ppmlhdfe y x1 x2, absorb(id year) vce(cluster id)   // coefficients are semi-elasticities
```

## Heterogeneity
- Interactions: `reghdfe y c.x##i.group, absorb(id year) vce(cluster id)`; report the interaction and the
  implied effect for each group (`lincom x + 1.group#c.x`).
- Split-sample + test of equality: prefer the pooled interaction model (same FE, one test).

## Standard table pattern
Columns progressively add FE/controls: (1) unit+year FE; (2) + controls; (3) + region×year FE;
(4) + industry×year FE. Use `stata_table` with fe_rows {"Unit FE", "Year FE", "Region × Year FE", ...}
and stats ["N","r2_within","ymean","N_clust"].

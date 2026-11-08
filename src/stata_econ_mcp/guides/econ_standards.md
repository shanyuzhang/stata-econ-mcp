# Applied-micro standards (what a referee will check)

## 1. Identification first
- State the estimand (ATT? ATE? elasticity?) and the identifying assumption in one sentence
  (e.g. "absent the policy, treated and control counties would have followed parallel trends in log employment").
- Fixed effects remove time-invariant unit heterogeneity and common shocks; they do NOT by themselves make a
  correlation causal. Say so when the design is pure panel FE.
- Name the main threats: confounding policies at the same time, anticipation, selection into treatment,
  spillovers to controls (SUTVA), compositional change, measurement/reclassification at the cutoff date.

## 2. Inference
- Cluster at the level of treatment assignment (policy at province level → cluster by province), or higher.
  Unit-level clustering when treatment is assigned at a higher level understates SEs.
- Few clusters (roughly < 40–50) or few treated clusters → wild cluster bootstrap (`boottest` after
  `reghdfe`, e.g. `boottest treat_post, cluster(prov) reps(9999) weight(webb)`) and/or randomization
  inference (permute treatment across units/dates).
- Two-way clustering (`vce(cluster id year)`) when errors correlate within time periods across units.
- Report the number of clusters. Never report non-robust SEs in panel settings.
- Many outcomes/subgroups → mention multiple testing (sharpened q-values, Romano–Wolf `rwolf`).

## 3. Specification discipline
- Controls must be pre-determined (measured before treatment) — post-treatment "bad controls" bias the estimate.
  With DiD, interact baseline covariates with time FE instead of adding time-varying controls.
- Keep the sample constant across columns where possible (`e(sample)` from the fullest model), or report N.
- Logs of variables with zeros: `ln(1+y)` is not scale-invariant; prefer PPML (`ppmlhdfe`) or report
  extensive and intensive margins separately. asinh has the same scale problem.
- Winsorize/trim outliers only as robustness (e.g. 1/99), and say so.
- Weighting: say whether regressions are population-weighted and why.

## 4. Robustness menu (pick what fits; FE/DiD papers usually show several)
- Alternative FE (region×year, industry×year), unit-specific linear trends (as a check, not a fix).
- Alternative clustering levels; wild bootstrap.
- Drop early/late cohorts, drop outlier units/regions, balanced panel only.
- Alternative outcome definitions / scaling.
- Placebo: fake treatment dates (shift k years earlier), fake treated groups (permutation), placebo outcomes.
- Heterogeneity-robust DiD estimators when timing is staggered.
- Controlling for concurrent policies; excluding units exposed to them.
- Sensitivity to parallel-trends violations (HonestDiD, Rambachan & Roth 2023) if pre-trends are borderline.

## 5. Magnitudes and interpretation
- Always translate β into economics: % change, effect relative to mean, in SD units, implied elasticity,
  or aggregate effect (β × treated units). Compare with literature benchmarks if the user provides them.
- Distinguish statistical from economic significance; discuss a null with its confidence interval
  (what effect sizes can be ruled out).

## 6. Presentation
- Table 1 (summary statistics), main table, event-study figure, robustness table(s), heterogeneity table.
- Every table note states: SE type and clustering level, FE included, sample, stars convention.
- Coefficient labels in words, not variable names. Same decimals within a table (usually 3).

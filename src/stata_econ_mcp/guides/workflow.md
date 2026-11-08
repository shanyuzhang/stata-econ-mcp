# Workflow

## Tool usage
- `stata_run`: quick checks (describe, tab, one regression to look at). Top-level locals persist between calls.
- `stata_do`: the real analysis. Each do-file must run top-to-bottom on its own (load data itself,
  define its own locals). Numbered files: `01_clean`, `02_describe`, `03_main`, `04_robust`,
  `05_heterogeneity`, `06_mechanism`, `07_figures`.
- `stata_results`: read coefficients/SEs/N exactly — never retype numbers from text output by eye.
- `stata_table`: LaTeX tables from stored estimates. `stata_graph`: export + show figures.
- Long jobs (bootstrap, csdid with many cohorts): if STATUS is RUNNING, call `stata_wait`.
- Never use `!`/`shell`, never delete or overwrite the user's raw data. Save derived data under a new name
  (e.g. `stata_output/data/panel_clean.dta`). Ask before `ssc install`.

## Do-file header template
```stata
*==============================================================
* 03_main.do — baseline DiD estimates
* Input : stata_output/data/panel_clean.dta
* Output: tables/did_main.tex
*==============================================================
version 18
clear all
set more off
set seed 20261108          // only matters for bootstrap/permutation, but always set it
use "stata_output/data/panel_clean.dta", clear
xtset id year
```

## Order of work (do not skip the audit)
1. **Clarify the design** with the user if unclear: unit of observation, time unit, outcome(s), treatment
   definition and timing, treated vs control groups, level at which treatment is assigned (→ clustering).
2. **Data audit**: `isid id year` (panel uniqueness), `duplicates report id year`, `xtdescribe` (balance,
   gaps), `misstable summarize`, `summarize, detail` on outcomes (outliers, zeros, units), check treatment
   timing per unit is consistent (`bysort id: assert first_treat == first_treat[1]`).
3. **Descriptives**: Table 1 by treated/control, pre-period means, raw trends plot of treated vs control.
4. **Baseline**: the cleanest specification first, then add controls/FE progressively across columns.
5. **Identification checks**: event study / pre-trends, placebo, robust estimators (see `did`, `ddd`).
6. **Robustness**, **heterogeneity**, **mechanisms**.
7. **Tables & figures** in LaTeX/PDF.

## Reporting back to the user (every time)
- Specification in words: outcome, treatment, FE, controls, sample, SE clustering level.
- Point estimate, SE, significance, N, clusters — read via `stata_results`.
- **Economic magnitude**: relative to the dependent-variable mean or SD; log outcome ⇒ ≈100·β % (use
  100·(e^β−1) when |β|>0.1); log-log ⇒ elasticity.
- Caveats: singletons dropped, sample changes across columns, few clusters, failed pre-trends.
- Paths of saved do-files, logs, tables and figures.
- Report every specification you ran, not only the significant ones.

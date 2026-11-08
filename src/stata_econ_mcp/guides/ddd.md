# Triple differences (DDD)

## Setup
Three dimensions: region/state r (treated vs control), group g (affected vs unaffected population within
a region), time t (pre vs post). DDD = [DiD between treated & control regions for the affected group]
− [same DiD for the unaffected group]. It differences out shocks specific to treated regions that hit both
groups (region×time) and shocks specific to the affected group nationally (group×time).

Identifying assumption (Olden & Møen 2022): only ONE parallel trend is needed — the *gap* in trends between
affected and unaffected groups would have evolved the same in treated and control regions. The two
underlying DiDs may each be biased, as long as the bias is equal.

## Fully saturated specification
Every lower-order term must be present (absorbed by FE or included explicitly). Missing a two-way
interaction is the most common DDD error.
```stata
* treatR = region is treated; affG = group is affected; post = after policy
gen byte ddd = treatR * affG * post

* Individual/group-level data with region-group-time cells:
reghdfe y ddd, absorb(region#year  group#year  region#group) vce(cluster region)
```
- `region#year` absorbs treatR×post (and post, region FE); `group#year` absorbs affG×post;
  `region#group` absorbs treatR×affG. So only the triple term remains.
- With unit FE (unit nested in region×group): `absorb(id region#year group#year)`.
- Without FE you must include all of: treatR affG post treatR#affG treatR#post affG#post treatR#affG#post:
  `reghdfe y i.treatR##i.affG##i.post, noabsorb vce(cluster region)` → coefficient on `1.treatR#1.affG#1.post`.
- Cluster at the level of policy variation (region), not the individual.

## Report alongside the DDD estimate
- The two DiDs separately (affected group; unaffected group) — the unaffected-group DiD is itself a placebo.
- A DDD event study: interact event-time dummies with affG (within treated vs control regions):
```stata
* rel = year - policy_year (single adoption); omit rel == -1
forvalues k = 2/5 {
    gen byte lead`k' = (rel == -`k') * treatR * affG
}
forvalues k = 0/5 {
    gen byte lag`k'  = (rel ==  `k') * treatR * affG
}
reghdfe y lead* lag*, absorb(region#year group#year region#group) vce(cluster region)
```
  (Bin endpoints if the window is wider than the data support — see `event_study`.)

## Staggered DDD
TWFE-DDD inherits the staggered-timing problems of DiD. A transparent robust approach: build the
within-region gap `y_aff − y_unaff` at the region×year level, then run a robust DiD estimator (csdid /
did_imputation) on that gap, using region as the unit. Present this alongside the pooled DDD.

## Interpretation and pitfalls
- β_DDD is the differential effect on the affected group relative to the unaffected group within treated
  regions. If the policy also affects the "unaffected" group (spillovers), β understates the total effect.
- Check composition: the affected/unaffected classification must be pre-determined (not changed by policy).
- Show group sizes per cell; tiny cells make the DDD noisy.

# Event studies

## TWFE event study with binned endpoints (reference period −1)
```stata
* first_treat missing for never-treated; rel = year - first_treat
gen rel = year - first_treat
local L = 5    // leads shown
local K = 5    // lags shown
* never-treated units: all event dummies = 0 (they act as controls)
gen byte lead_bin = !missing(rel) & rel <= -(`L'+1)          // binned far leads
forvalues k = `L'(-1)2 {
    gen byte lead`k' = (rel == -`k')
}
forvalues k = 0/`K' {
    gen byte lag`k' = (rel == `k')
}
gen byte lag_bin = !missing(rel) & rel >= (`K'+1)            // binned far lags
* rel == -1 omitted (reference)
reghdfe y lead_bin lead`L'-lead2 lag0-lag`K' lag_bin, absorb(id year) vce(cluster id)
estimates store es_twfe
test lead`L' lead4 lead3 lead2         // joint pre-trend test (adjust list to L)
```
- Always omit one pre-period (−1). With no never-treated units, also omit a second (e.g. the far bin)
  to avoid collinearity with time FE.
- Report binned endpoints in the table but usually not in the plot.
- With staggered timing, TWFE leads/lags are contaminated by other periods' effects (Sun & Abraham 2021):
  show a robust version too.

## Plot (coefplot)
```stata
coefplot es_twfe, keep(lead* lag*) drop(lead_bin lag_bin) vertical  ///
    order(lead5 lead4 lead3 lead2 lag0 lag1 lag2 lag3 lag4 lag5)       ///
    coeflabels(lead5="-5" lead4="-4" lead3="-3" lead2="-2"             ///
               lag0="0" lag1="1" lag2="2" lag3="3" lag4="4" lag5="5")  ///
    yline(0, lcolor(gs8)) xline(4.5, lpattern(dash) lcolor(gs8))       ///
    ciopts(recast(rcap) lcolor(navy)) mcolor(navy) msymbol(O)          ///
    xtitle("Years relative to treatment") ytitle("Effect on y")        ///
    graphregion(color(white)) plotregion(margin(small))
```
Then `stata_graph("event_study_twfe")` (PNG shown + PDF for LaTeX). Add the omitted −1 at zero if desired
by plotting from a matrix, or note "t = −1 is the reference period" in the caption.

## Robust event studies
```stata
* Callaway & Sant'Anna
csdid y, ivar(id) time(year) gvar(gvar) notyet long2
estat event, window(-5 5)
csdid_plot, title("") xtitle("Years relative to treatment")

* Borusyak–Jaravel–Spiess
did_imputation y id year first_treat, fe(id year) cluster(id) horizons(0/5) pretrends(5) minn(0)
event_plot, default_look graph_opt(xtitle("Years relative to treatment") ytitle("Effect"))
```
(`event_plot` is `ssc install event_plot`; it also plots several estimators together for comparison —
a common figure: TWFE vs CS vs BJS vs SA on one graph.)

## What to say about the figure
- Pre-period coefficients: size and joint test, not just "insignificant". Mention power.
- Dynamics: immediate vs gradual effects, persistence/fade-out.
- Composition: with unbalanced event windows, far leads/lags are identified from fewer cohorts.

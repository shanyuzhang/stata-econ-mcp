# LaTeX tables and figures

## Regression table via stata_table
1. After each model: add the dependent-variable mean and store.
```stata
reghdfe y post, absorb(id year) vce(cluster id)
quietly summarize y if e(sample)
estadd scalar ymean = r(mean)
estimates store m1
```
2. Call the tool, e.g.
```
stata_table(models=["m1","m2","m3"], filename="did_main",
  title="Effect of the policy on log employment",
  mtitles=["Baseline","+ Controls","+ Prov.×Year FE"],
  keep="post", coeflabels={"post": "Treat $\\times$ Post"},
  fe_rows={"County FE": ["Yes","Yes","Yes"], "Year FE": ["Yes","Yes","--"], "Province $\\times$ Year FE": ["No","No","Yes"]},
  stats=["N","r2_within","ymean","N_clust"],
  se_note="Standard errors clustered at the county level in parentheses.")
```
Output: `stata_output/tables/did_main.tex` (booktabs, stars * 0.10 ** 0.05 *** 0.01, SEs in parentheses).
Preamble needs `\usepackage{booktabs}`. Use `fragment=True` to get only the rows (for custom wrappers,
e.g. multi-panel tables with `\input{}`).

## Conventions
- Labels in words; same decimals (3) for b and SE; Observations with thousands separator.
- FE rows "Yes/No" (or "--" when absorbed by a finer FE); clustering stated in the note.
- Dependent-variable name in the caption or a `mgroups`/header row; column titles describe specification.
- Use `label` (variable labels) — set good labels in the do-file: `label variable post "Treat × Post"`.

## Multi-panel table (Panel A / Panel B) by hand
```stata
esttab a1 a2 a3 using "stata_output/tables/tab_panelA.tex", fragment booktabs replace ///
    b(3) se(3) star(* 0.10 ** 0.05 *** 0.01) keep(post) label nomtitles nonumbers nolines
esttab b1 b2 b3 using "stata_output/tables/tab_panelB.tex", fragment booktabs replace ///
    b(3) se(3) star(* 0.10 ** 0.05 *** 0.01) keep(post) label nomtitles nonumbers nolines
```
then a wrapper .tex with `\midrule \multicolumn{4}{l}{\textit{Panel A: ...}}\\ \input{tab_panelA}` etc.

## Table 1: summary statistics
```stata
estpost summarize y x1 x2 treated
esttab using "stata_output/tables/sumstats.tex", replace booktabs label nonumbers noobs ///
    cells("count(fmt(%9.0fc)) mean(fmt(3)) sd(fmt(3)) min(fmt(3)) max(fmt(3))") ///
    collabels("N" "Mean" "SD" "Min" "Max")

* Balance / by group with difference test
estpost ttest y x1 x2, by(treated)
esttab using "stata_output/tables/balance.tex", replace booktabs label nonumbers noobs ///
    cells("mu_1(fmt(3)) mu_2(fmt(3)) b(fmt(3) star) se(par fmt(3))") ///
    collabels("Control" "Treated" "Diff." "SE")
```

## Figures
- Build the graph in Stata, then `stata_graph("name")` → PNG (shown in chat) + PDF (for LaTeX).
- Clean style: `graphregion(color(white))`, gray reference lines, no titles inside the graph (caption in LaTeX).
- LaTeX: `\includegraphics[width=\linewidth]{figures/name.pdf}`.

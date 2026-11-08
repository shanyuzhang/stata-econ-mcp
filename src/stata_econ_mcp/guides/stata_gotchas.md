# Stata traps that silently give wrong numbers

- **Missing = +∞.** `gen big = x > 100` sets big=1 for missing x. Write `x > 100 & !missing(x)`.
  Same for `keep if x > c`, `replace ... if x >= c`.
- `=` assigns, `==` compares (`if x == 1`).
- `by` needs sorted data → use `bysort id (year):`. `x[_n-1]` within `bysort id (year)` is the previous
  year only if there are no gaps — prefer time-series operators `L.x` after `xtset` (gaps → missing, correct).
- `generate` fails if the variable exists; `replace` to modify; `capture drop v` before re-creating.
- `merge`: always `merge 1:1`/`m:1` explicitly and inspect `tab _merge`, then `assert` the expected pattern
  and `drop _merge`. Never `merge m:m`.
- `egen` (group functions: `mean()`, `total()`, `group()`, `tag()`) vs `gen` (row-wise).
  `egen total()` treats missing as 0.
- Factor variables: `i.` for categories, `c.` for continuous in interactions (`c.x#i.g`); `##` adds main effects.
- Precision: default float has ~7 digits. IDs > 16,777,216 lose precision as float — store as `long`/`double`
  or string. (`set type double` is applied by this server.)
- Strings: comparisons are case-sensitive; trim with `strtrim()`; `destring, replace` fails silently with
  `force` → check what became missing.
- Dates: `date("2020-01-31","YMD")` gives daily dates; use `%td` format; `year()`, `mofd()`, `qofd()` to convert.
- `capture` swallows errors — check `_rc` afterwards or use `capture noisily`.
- Each estimation command overwrites `e()` → `estimates store` immediately; `estadd` before `estimates store`
  (or `estadd ... : name` afterwards).
- `collapse` destroys the data in memory → `preserve` / `restore`, or save to a tempfile.
- Sorting ties are random → `sort id year, stable` and `set seed` when results depend on order.
- `reghdfe` silently drops singletons and observations with missing in any variable → compare N across
  columns; define a common sample with `gen byte s = e(sample)` from the fullest model.
- Locals vanish at the end of a do-file; in `stata_do` each file must define its own locals/globals.
- Weights: `[pw=]` for sampling weights (robust SE), `[aw=]` for cell means; they are not interchangeable.

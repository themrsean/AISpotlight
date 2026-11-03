# THR-04 Anomaly Detection — Requirements

| | |
|---|---|
| Status | Partly approved (see below). **Not implemented.** |
| Last updated | 2026-11-03 |
| Applies to | `summarize_thr04.py` and the `thr04/` package |

### Approval status
| Requirements | Status |
|---|---|
| FR-1, FR-7 rows 1–2 (ambient range and drift), FR-9, FR-10, FR-11, FR-12, FR-14, FR-15, FR-16 | **Approved** for implementation (D17) |
| Everything else, including FR-7 row 3 (correlation) | Draft |

## 1. Purpose

The THR-04 summary tool reads a cleaned thermal-response CSV and reports an overview, data quality, ambient statistics, heating rates and a Newton's-law cooling fit. This feature adds **anomaly detection**: it flags suspicious data and physically implausible behaviour, so people reading the results know which reported numbers to trust.

The motivation is general robustness ("the data may contain problems"). It is not a response to one known failure. (D1)

## 2. Scope

### 2.1 In scope (D2, D5)
Version 1 has seven checks on a single run:

| ID | Check | Category |
|---|---|---|
| C1 | Stuck sensor | Sensor / data |
| C2 | Step change | Sensor / data |
| C3 | Gaps | Sensor / data |
| C4 | Wrong direction for the phase | Physical / process |
| C5 | Cooling fit quality | Physical / process |
| C6 | Ambient instability | Physical / process |
| C7 | Phase label consistency | Physical / process |

### 2.2 Out of scope (deferred)
- Comparing a run against other runs or against reference values.
- Noisy-stretch detection and clusters of cleaner flags.
- Re-analysing the data without the flagged points. The design must leave room for it (see CON-2).
- Severity that depends on how big the anomaly is.
- In the GUI, clicking a finding to jump to it in the data or plot.
- Any change to, or reimplementation of, the cleaning step (see OQ-8).

## 3. Definitions

| Term | Meaning |
|---|---|
| Run | One cleaned CSV: a heating phase followed by a cooling phase. |
| Reading | One row of the CSV. The nominal interval is the most common time step (10 s in THR-04). |
| Heater-off time | `time_s` of the first row whose `phase` is `cooling`. |
| Finding | One detected anomaly (structure in FR-9). |
| Severity | `critical` (a reported result probably can't be trusted) or `warning` (the data is suspicious, but the results are probably still usable). |
| Affects | The reported sections a finding undermines: `overview`, `ambient`, `heating`, `cooling`. |
| Robust noise | 1.4826 × the median absolute deviation (MAD) of the gaps between each reading and a centred rolling median, calculated per phase. |
| Threshold multiple | An injected anomaly's size divided by the threshold of the check that should catch it (used in the acceptance tests). |

## 4. Constraints

| ID | Constraint | Source |
|---|---|---|
| CON-1 | Input is the **cleaned CSV only**, with the columns `time_s, phase, ambient_C, sample_C, ambient_flag, sample_flag`. The raw log is not read. | D3 |
| CON-2 | **Report only.** The values in the existing overview, quality, ambient, heating and cooling sections must not change because of anomaly detection. The input file is never modified. The code must be structured so a "rerun without flagged points" option could be added later without rework. | D4 |
| CON-3 | The cleaner's existing flags (`spike`, `out_of_range`, `missing`, `duplicate_merged`, `converted_from_F`) keep appearing in the Data Quality section. The detector does not duplicate or contradict them. | D3 |
| CON-4 | No new runtime dependencies. TOML is read with the built-in `tomllib`, so Python 3.11 or later is required. No scipy. | D6 |
| CON-5 | The default exit code doesn't change. Existing scripts that call the tool keep working. | D14 |
| CON-6 | **Prerequisite:** the existing refactor stays, and bugs B1–B8 from the code review are fixed (with all their tests passing) before work on this feature starts. | D15 |
| CON-7 | Responsibilities are split. `load()` rejects **invalid** files (non-numeric or duplicate `time_s`, unknown phase values) with an error. C7 reports **valid but suspicious** phase layouts as findings. | D15 |
| CON-8 | The default thresholds were set from a single run and are **provisional**. If they conflict with the acceptance criteria, the thresholds change, not the criteria. | D7, D12 |
| CON-9 | The cleaning script (`clean_thr04.py`) does not exist in the repo, so the cleaner's rules are unknown. Documentation must not refer to it as if it were available. | D16 |

## 5. Functional requirements

### 5.1 Detection

**FR-1 — Anomaly section.** The analysis produces a new section, `anomalies`, after the existing sections. It runs by default and can be selected with `-s anomalies`.

**FR-2 — C1 Stuck sensor.** Report a `warning` when the **sample** reading has the same value for at least `stuck_min_readings` consecutive valid readings, *and* the local trend predicts more than `stuck_min_expected_change_C` of change over that stretch. The local trend is estimated from the readings on either side. Ambient is not checked, because repeated ambient values are normal. `affects` = the phase(s) the stretch falls in.

**FR-3 — C2 Step change.** Report a `warning` when, after removing the local trend, the sample level shifts by more than `step_noise_multiple` × the robust noise for that phase, and the new level holds for at least `step_min_hold_readings` readings. `affects` = the phase it occurs in.

**FR-4 — C3 Gaps.** Report a `warning` when either sensor has at least `gap_min_missing` consecutive missing values, or when a time step differs from the nominal interval. `affects` = the phase it occurs in.

**FR-5 — C4 Wrong direction.** Report a `warning` when either of these happens:
- During heating, the sample falls more than `direction_tolerance_C` below its highest reading so far in the heating phase.
- During cooling, the sample rises more than `direction_tolerance_C` above its lowest reading so far in the cooling phase. Readings within `direction_grace_s` after heater off are ignored.

`affects` = `heating` or `cooling`.

**FR-6 — C5 Cooling fit.** The check uses the same fit as the cooling section. That fit is computed once, and the cooling section and this check both use it.

| Condition | Severity | Time range |
|---|---|---|
| R² < `fit_min_r2` | critical | whole run (`null`) |
| Runs test on the signs of the fit errors gives p < `fit_runs_p` (the errors follow a pattern) | warning | whole run (`null`) |
| A point's fit error > `fit_outlier_multiple` × the robust spread of the errors | warning | that reading |

`affects` = `cooling`.

**FR-7 — C6 Ambient instability.**

| Condition | Severity | Affects |
|---|---|---|
| Ambient range > `ambient_max_range_C`. Range = max − min of the valid ambient readings after a centred 5-reading rolling median (D20). | warning | ambient, cooling |
| Absolute ambient drift > `ambient_max_drift_C`. Drift = mean of the valid ambient readings in the last 60 s minus the mean of those in the first 60 s (D20). | warning | ambient, cooling |
| Pearson correlation between ambient and sample > `ambient_max_correlation` (the ambient sensor is probably being heated by the sample) | critical | cooling |

**FR-8 — C7 Phase labels.** Report a `critical` finding, with `affects` = overview, heating, cooling, for any of these:
- more than one heating→cooling switch;
- a heating row after the first cooling row;
- the labelled heater-off time more than `phase_peak_tolerance_s` away from the time of the highest sample reading (the earliest one if there's a tie).

### 5.2 Findings

**FR-9 — Finding structure.** Each finding has:

| Field | Type | Notes |
|---|---|---|
| `check` | string | `stuck_sensor`, `step_change`, `gap`, `wrong_direction`, `cooling_fit`, `ambient`, `phase_labels` |
| `severity` | string | `critical` or `warning` |
| `affects` | list of strings | at least one section name |
| `start_s`, `end_s` | number or null | `null` for findings about the whole run |
| `message` | string | plain language, with units |
| `hint` | string | what to check |
| `measured` | number or null | the value that triggered the finding |
| `threshold` | number or null | the threshold it was compared with |

**FR-10 — Order.** Findings are sorted with critical first, then by `start_s` (run-wide findings first), then by `check`.

**FR-11 — Messages.** Messages and hints are written for students and instructors. Each hint suggests a physical or practical thing to check, e.g. "Check the sensor contact or cable." (D13)

### 5.3 Configuration

**FR-12 — Defaults.** Default thresholds are defined in one documented place in code:

| Key | Default |
|---|---|
| `stuck_min_readings` | 6 |
| `stuck_min_expected_change_C` | 0.5 |
| `step_noise_multiple` | 5.0 |
| `step_min_hold_readings` | 3 |
| `gap_min_missing` | 3 |
| `direction_tolerance_C` | 0.5 |
| `direction_grace_s` | 60 |
| `fit_min_r2` | 0.99 |
| `fit_runs_p` | 0.01 |
| `fit_outlier_multiple` | 4.0 |
| `ambient_max_range_C` | 1.0 |
| `ambient_max_drift_C` | 0.5 |
| `ambient_max_correlation` | 0.7 |
| `phase_peak_tolerance_s` | 60 |

**FR-13 — Config file.** `--config PATH` loads a TOML file of overrides. Keys not in the file keep their defaults. An unknown key, a non-numeric value, a value outside its valid range (negative; probabilities or R² outside 0–1; counts below 1), a missing file or invalid TOML is an **error** that names the problem (exit code 1). It is never silently ignored. (D6)

**FR-14 — Reproducibility.** The output records the full set of thresholds in use and the config file's path, or `null` if there wasn't one.

### 5.4 Output

**FR-15 — JSON.** `--json` output includes:
```json
"anomalies": {
  "summary": {"critical": 0, "warning": 0},
  "thresholds": { "...": "all values in use" },
  "config_file": null,
  "findings": [ /* FR-9 objects, FR-10 order */ ]
}
```
All JSON output is strict: NaN and infinity become `null`.

**FR-16 — Text report.**
- When anomalies are included, a summary line goes directly under the header, e.g. `⚠ 1 critical, 2 warnings — see ANOMALIES`, or `No anomalies detected`.
- An `ANOMALIES` section goes at the end. Each finding shows its severity, time range (`hh:mm:ss`, or "whole run"), check, message, hint and affects.

**FR-17 — Exit codes / `--fail-on`.**

| Code | Meaning |
|---|---|
| 0 | Success (the default even when there are findings) |
| 1 | Tool, input or config error |
| 2 | Command-line usage error |
| 3 | `--fail-on critical` and at least one critical finding, or `--fail-on warning` and at least one finding of any severity |

The output is printed in full before the tool exits with code 3. (D14)

**FR-18 — GUI anomalies tab.** A tab labelled `Anomalies (n)` shows the findings in a table with these columns: severity, check, start, end, affects, message, hint. Clicking a column heading sorts by it. (D9)

**FR-19 — GUI plot.** Findings with a time range are shaded on the temperature plot: red for critical, amber for warning, semi-transparent, with one legend entry per severity. Run-wide findings are not shaded.

**FR-20 — GUI data column.** The Data tab gets an `anomaly` column listing the checks whose time ranges include that row. The existing yellow highlight keeps meaning "flagged by the cleaner."

**FR-21 — GUI config.** The GUI accepts the same config file: through `--config` when launched, and through a "Thresholds…" button that reloads the file and re-runs the analysis. Config errors appear in an error dialog.

## 6. Edge cases

| ID | Situation | Required behaviour |
|---|---|---|
| EC-1 | The cooling fit can't be computed (fewer than 3 usable readings, ambient missing, sample ≤ ambient) | No crash. The cooling section reports its error; C5 produces no fit findings (see OQ-5). |
| EC-2 | A phase is missing entirely (heating only, or cooling only) | Checks for the missing phase are skipped. C7 doesn't report a missing phase as a phase-switch problem. |
| EC-3 | One-row file, or a phase with too few readings to estimate noise | Checks that need more data are skipped. No crash. |
| EC-4 | A single missing reading (e.g. a spike the cleaner blanked) | **Not** a gap (below `gap_min_missing`). It doesn't break a stuck-sensor stretch or the step-change trend estimate. |
| EC-5 | A gap at the very start or end of the run | Reported, with the time range clipped to the run. |
| EC-6 | Ambient repeating the same value (normal at 0.1 °C resolution) | Never reported as stuck (C1 checks the sample only). |
| EC-7 | Sample plateau where the trend predicts little change (end of a long cooling) | Not reported as stuck, because the predicted change is ≤ `stuck_min_expected_change_C`. |
| EC-8 | Small rise just after heater off (the block keeps warming briefly) | Not reported if it's within `direction_grace_s`. |
| EC-9 | The change in slope at heater off | Not reported as a step change. The trend estimate must not span the phase boundary. |
| EC-10 | One event triggers more than one check (e.g. a downward step during heating also counts as wrong direction) | Behaviour is open, see OQ-4. |
| EC-11 | Several findings overlap in time | All are listed. Shading and the Data column show all of them. |
| EC-12 | `--fail-on` used with `-s` sections that leave out `anomalies` | Behaviour is open, see OQ-3. |
| EC-13 | A threshold set to its limit (e.g. `fit_min_r2 = 0`) | Accepted. That check then never fires. |
| EC-14 | Timestamps with small jitter (e.g. 9 s / 11 s steps) | Behaviour is open, see OQ-6. |
| EC-15 | A flag value is NaN in the CSV | Treated as `ok`, consistently in the quality section and the GUI. |

## 7. Acceptance criteria

The synthetic runs below use linear heating, exponential cooling with heater off at 600 s, 10 s sampling, ambient around 22 °C, noise SD around 0.1 °C and values rounded to 0.1 °C. Each criterion is run with at least 5 random seeds.

| ID | Criterion | Covers |
|---|---|---|
| AC-1 | For each of C1–C4 and C6 (range/drift/correlation): an anomaly injected at 2× its threshold is detected with the correct `check`, `severity` and `affects`, and its `start_s` is within ±1 reading of the injected start. For findings about the whole run (`start_s`/`end_s` = `null`, e.g. C6 range and drift), the location check doesn't apply; instead `measured` must exceed `threshold` by the injected amount (D18). | FR-2–5, FR-7, FR-9 |
| AC-2 | For each of the same checks, an anomaly injected at 0.5× its threshold produces **no** finding from that check. | FR-2–5, FR-7 |
| AC-3 | C5: a clearly non-exponential cooling curve (e.g. two time constants) gives an R² critical finding *or* a pattern-in-errors warning; a single point moved by 2× `fit_outlier_multiple` × the spread gives an outlier warning at that reading. | FR-6 |
| AC-4 | C7: each of the three layout problems in a synthetic file gives one critical finding; the correct layout gives none. | FR-8 |
| AC-5 | Clean synthetic runs (with nothing injected) give **zero findings** for every seed. | CON-8, D11 |
| AC-6 | Each of EC-4, EC-6, EC-7, EC-8 and EC-9 gives no finding. | §6 |
| AC-7 | EC-1, EC-2 and EC-3 complete without an exception. | §6 |
| AC-8 | `THR04_clean.csv` gives **no critical findings**. Any warnings are reviewed and approved by the product owner, then locked in as a regression test. | D12 |
| AC-9 | With anomaly detection on, every value in the existing sections for `THR04_clean.csv` is unchanged compared with the version without the feature. | CON-2 |
| AC-10 | A config file that overrides one threshold changes that check's result on a prepared input. The other thresholds keep their defaults, and both appear in the `thresholds` output. | FR-12–14 |
| AC-11 | An unknown key, an out-of-range value, invalid TOML or a missing file each exit with code 1 and a message naming the problem. | FR-13 |
| AC-12 | JSON output passes strict parsing (`json.loads` with `parse_constant` that rejects NaN/Infinity) and contains every field from FR-15. | FR-15 |
| AC-13 | The text report shows the summary line and the ANOMALIES section; `-s anomalies` shows only that section. | FR-1, FR-16 |
| AC-14 | Exit codes: no `--fail-on` → 0, even with findings; `--fail-on critical` → 3 only when there's a critical finding; `--fail-on warning` → 3 when there's any finding; otherwise 0. | FR-17 |
| AC-15 | Manual GUI check with a synthetic file containing every anomaly type: the tab count is correct and sorting works; shading is correct per severity; the Data column is filled in; reloading thresholds updates the results; a bad config shows an error dialog. | FR-18–21 |
| AC-16 | All existing tests, including the B1–B8 bug tests, pass before and after the feature. | CON-6 |
| AC-17 | On a synthetic file with several anomalies of mixed severity, findings come out in FR-10 order, and every finding has a non-empty `message` (with a unit) and `hint`. The wording is reviewed once by the product owner. | FR-10, FR-11 |

## 8. Open questions

| ID | Question | Recommendation | Blocks |
|---|---|---|---|
| OQ-1 | The default thresholds (FR-12) are provisional. Do they pass AC-5 and AC-8? | Tune them while implementing; record any changes here. | Final sign-off |
| OQ-2 | Should C6's correlation use raw levels, or first differences (more robust to slow drift)? | Start with levels. Switch only if AC-5 or AC-8 fail, with approval. | — |
| OQ-3 | With `--fail-on`, should anomalies be computed even if `-s` leaves the section out? | Yes: always compute them for `--fail-on`, and display them only if selected. | FR-17 |
| OQ-4 | When one event triggers several checks (EC-10), report all of them or merge them? | Report all; each check means something different. | — |
| OQ-5 | When the cooling fit can't be computed (EC-1), should C5 add a warning? | No. The cooling section already shows the error. | — |
| OQ-6 | What counts as an irregular time step (EC-14)? | Any step that differs from the nominal interval by more than 10% of it. | FR-4 |
| OQ-7 | Audience assumed to be students and instructors. Should lab staff or automated grading shape the wording too? | Confirm. | FR-11 |
| OQ-8 | `clean_thr04.py` doesn't exist. Should a cleaner be written, so the raw → clean step can be reproduced? | Separate future work. | — |
| OQ-9 | Which warnings does `THR04_clean.csv` produce, and are they acceptable? | Review once the detector is implemented. | AC-8 |
| OQ-10 | THR04's ambient drift is +0.40 °C, 80% of `ambient_max_drift_C` = 0.5. Is that margin enough for similar real runs? | Keep 0.5 for now; revisit if real runs trigger false drift warnings. | — |

## 9. Decisions behind these requirements

| # | Decision | Where |
|---|---|---|
| D1 | Motivation: general robustness | §1 |
| D2 | Scope: sensor/data checks plus physical/process checks; comparing against other runs deferred | §2 |
| D3 | Input: cleaned CSV only; cleaner flags stay as they are | CON-1, CON-3 |
| D4 | Report only; design leaves room for re-analysis without flagged points | CON-2 |
| D5 | Checks C1–C7; noisy-stretch and flag-cluster checks deferred | §2, FR-2–8 |
| D6 | Defaults in code + TOML overrides; unknown keys are an error; thresholds recorded in the output | FR-12–14 |
| D7 | Default values are provisional | CON-8, OQ-1 |
| D8 | Severity fixed per check, with an `affects` list | FR-2–9 |
| D9 | GUI: tab, plot shading, Data column; no click-to-navigate | FR-18–21 |
| D10 | JSON section; anomalies in the CLI text by default; `-s anomalies` | FR-1, FR-15, FR-16 |
| D11 | Validation using synthetic anomaly injection | §7 |
| D12 | THR04 gives no critical findings; warnings reviewed once | AC-8 |
| D13 | Plain-language messages with hints | FR-11 |
| D14 | Opt-in `--fail-on`, exit code 3 | FR-17 |
| D15 | Keep the refactor; fix B1–B8 first; split `load()` and C7 responsibilities | CON-6, CON-7 |
| D16 | No cleaner script exists | CON-9, OQ-8 |
| D17 | Approved for implementation: FR-1, FR-7 rows 1–2, FR-9–12, FR-14–16 | Approval status |
| D18 | C6 range/drift findings cover the whole run (`null` times); AC-1's location check doesn't apply to whole-run findings | FR-9, AC-1 |
| D19 | The CON-6 prerequisite (fix B1–B8, land refactor and tooling) is tracked as a separate issue and done first | CON-6 |
| D20 | C6 range and drift use noise-robust definitions (5-reading rolling median; 60 s averages at each end). The single-reading definitions fired on 79% of 0.5× range injections and 1.6% of clean runs at THR04's noise level (SD ≈ 0.15 °C). The AMBIENT section keeps its existing endpoint values (CON-2), so the two can differ slightly. | FR-7 |

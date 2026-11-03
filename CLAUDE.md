# CLAUDE.md

Analysis tool for the THR-04 thermal response experiment: it summarises a cleaned CSV (overview, data quality, ambient, heating, Newton cooling fit) as text, JSON or a Tk GUI.

Feature requirements live in `docs/requirements.md`. Don't duplicate them here. Don't implement anything marked *Draft* until the user approves it, and record new decisions there.

## Commands
```sh
.venv/bin/python -m pip install -r requirements.txt   # deps (Python 3.11+)
.venv/bin/python -m pytest -q                         # full test suite
.venv/bin/ruff check . && .venv/bin/ruff format .     # lint + format
.venv/bin/python summarize_thr04.py [CSV] [--json] [-s SECTION] [--gui]
```

## Layout
- `thr04/analysis.py`: loading, validation and pure analysis functions that return plain dicts.
- `thr04/report.py`: text report and JSON output. `thr04/plot.py`: matplotlib figure. `thr04/gui.py`: Tk interface.
- `summarize_thr04.py`: thin CLI only. Logic goes in `thr04/`.
- `tests/`: pytest. `conftest.py` has `make_df` and synthetic-run fixtures.
- `THR04_raw_thermal_log.txt` and `THR04_clean.csv` are reference data. **Never modify them.** The cleaning script (`clean_thr04.py`) doesn't exist, so don't refer to it as if it were available.

## Coding standards
- PEP 8, enforced by ruff (100-character lines). Code must pass `ruff check` and `ruff format`.
- Type hints and short docstrings on all public functions in `thr04/`.
- Keep analysis code pure: DataFrame in, dict out. No printing, I/O or GUI code outside `report.py`, `gui.py` and the CLI.
- Bad input raises `DataError` with a clear message. Only the CLI or GUI turns it into an exit code or dialog.
- JSON output must be strict (no NaN or Infinity).
- Ask before adding runtime dependencies. Dev tools (pytest, ruff) go in `requirements.txt`.

## Testing
- **Test first:** bug fixes start with a failing test; new behaviour gets tests in the same change.
- Use synthetic data for logic and `THR04_clean.csv` for regression ("golden") values. Don't change the golden values without explaining why.
- The full suite must pass before work is reported as done. If anything fails or was skipped, say so and show the output.
- GUI changes are checked by hand. Say what was checked.

## Workflow
- Work on a feature branch, never directly on `master`.
- Commit (never push) at each checkpoint where all tests pass, with descriptive messages. Push or open PRs only when asked.
- Keep each change small and focused; don't mix refactors with behaviour changes.

## Communication
- After each change, give a concise summary: what changed (`file:line`), why, test results, and anything skipped or uncertain.
- Explain reasoning in detail only for non-obvious decisions or tradeoffs.

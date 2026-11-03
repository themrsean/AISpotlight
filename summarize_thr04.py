#!/usr/bin/env python3
"""
Summarise a cleaned THR-04 thermal response CSV (output of clean_thr04.py).

Reports
  * run overview: duration, sampling interval, heater-off time
  * data quality: valid-value counts and a breakdown of cleaning flags
  * ambient stability: mean, standard deviation, range
  * heating phase: start / peak temperature, average and initial heating rate
  * cooling phase: Newton's-law-of-cooling fit, T - T_amb = dT0 * exp(-k t),
    giving the cooling constant k, time constant tau, half-life and R^2

Usage
  python summarize_thr04.py THR04_clean.csv
  python summarize_thr04.py THR04_clean.csv --section cooling
  python summarize_thr04.py THR04_clean.csv --json > summary.json
  python summarize_thr04.py --gui                     # graphical interface
  python summarize_thr04.py THR04_clean.csv --gui     # open a file in the GUI

The GUI needs tkinter (bundled with most Python installs) and, for the
plot tab, matplotlib (pip install matplotlib).
"""

import argparse
import sys

from thr04.analysis import SECTIONS, DataError, analyse, load
from thr04.report import format_report, to_json


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "csv", nargs="?", default=None, help="cleaned CSV file (default: THR04_clean.csv)"
    )
    ap.add_argument(
        "-s",
        "--section",
        choices=SECTIONS,
        action="append",
        help="show only this section (repeatable)",
    )
    ap.add_argument(
        "--json", action="store_true", help="print the results as JSON instead of a text report"
    )
    ap.add_argument("-g", "--gui", action="store_true", help="open the graphical interface")
    args = ap.parse_args(argv)

    if args.gui:
        from thr04.gui import run_gui

        run_gui(args.csv)
        return

    path = args.csv or "THR04_clean.csv"
    try:
        df = load(path)
    except DataError as err:
        sys.exit(f"error: {err}")
    results = analyse(df, args.section or SECTIONS)

    if args.json:
        print(to_json(results))
    else:
        print(format_report(path, results))


if __name__ == "__main__":
    main()

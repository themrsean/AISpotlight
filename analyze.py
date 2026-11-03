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
"""

import argparse
import json
import sys

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = {"time_s", "phase", "ambient_C", "sample_C",
                    "ambient_flag", "sample_flag"}
SECTIONS = ("overview", "quality", "ambient", "heating", "cooling")


# ---------------------------------------------------------------- loading
def load(path: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(path)
    except FileNotFoundError:
        sys.exit(f"error: file not found: {path}")
    except pd.errors.ParserError as err:
        sys.exit(f"error: could not parse {path}: {err}")

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        sys.exit(f"error: {path} is missing columns: {', '.join(sorted(missing))}")
    if df.empty:
        sys.exit(f"error: {path} contains no data rows")
    return df.sort_values("time_s").reset_index(drop=True)


def fmt_time(seconds) -> str:
    seconds = int(round(seconds))
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def linear_fit(x, y):
    """Least-squares line; returns slope, intercept, R^2."""
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res = np.sum((y - pred) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return float(slope), float(intercept), float(r2)


# ---------------------------------------------------------------- analysis
def overview(df):
    t = df["time_s"]
    steps = t.diff().dropna()
    cooling = df[df["phase"] == "cooling"]
    return {
        "rows": int(len(df)),
        "start": fmt_time(t.iloc[0]),
        "end": fmt_time(t.iloc[-1]),
        "duration_min": round((t.iloc[-1] - t.iloc[0]) / 60, 2),
        "sample_interval_s": float(steps.mode().iloc[0]) if len(steps) else None,
        "heater_off": fmt_time(cooling["time_s"].iloc[0]) if len(cooling) else None,
    }


def quality(df):
    out = {}
    for s in ("ambient", "sample"):
        flags = df[f"{s}_flag"].fillna("ok").str.split(";").explode()
        counts = flags[flags != "ok"].value_counts()
        out[s] = {
            "valid": int(df[f"{s}_C"].notna().sum()),
            "total": int(len(df)),
            "flags": {k: int(v) for k, v in counts.items()},
        }
    return out


def ambient(df):
    a = df["ambient_C"].dropna()
    return {
        "mean_C": round(a.mean(), 2),
        "std_C": round(a.std(), 2),
        "min_C": round(a.min(), 2),
        "max_C": round(a.max(), 2),
        "drift_C": round(a.iloc[-1] - a.iloc[0], 2),
    }


def heating(df, initial_window_s=60):
    h = df[(df["phase"] == "heating") & df["sample_C"].notna()]
    allv = df[df["sample_C"].notna()]
    if len(h) < 2:
        return {"error": "not enough heating data"}

    peak = allv.loc[allv["sample_C"].idxmax()]
    t0, T0 = h["time_s"].iloc[0], h["sample_C"].iloc[0]
    t1, T1 = h["time_s"].iloc[-1], h["sample_C"].iloc[-1]

    early = h[h["time_s"] <= t0 + initial_window_s]
    init_rate = linear_fit(early["time_s"].values, early["sample_C"].values)[0] \
        if len(early) >= 3 else float("nan")
    late = h[h["time_s"] >= t1 - initial_window_s]
    final_rate = linear_fit(late["time_s"].values, late["sample_C"].values)[0] \
        if len(late) >= 3 else float("nan")

    return {
        "start_C": round(T0, 2),
        "end_of_heating_C": round(T1, 2),
        "temperature_rise_C": round(T1 - T0, 2),
        "peak_C": round(peak["sample_C"], 2),
        "peak_time": fmt_time(peak["time_s"]),
        "avg_rate_C_per_min": round((T1 - T0) / (t1 - t0) * 60, 3),
        "initial_rate_C_per_min": round(init_rate * 60, 3),
        "final_rate_C_per_min": round(final_rate * 60, 3),
    }


def cooling(df):
    c = df[(df["phase"] == "cooling")
           & df["sample_C"].notna()].copy()
    if len(c) < 3:
        return {"error": "not enough cooling data"}

    # Use the mean ambient over the cooling phase as the reference temperature.
    t_amb = df.loc[df["phase"] == "cooling", "ambient_C"].mean()
    c["excess"] = c["sample_C"] - t_amb
    c = c[c["excess"] > 0]
    t = (c["time_s"] - c["time_s"].iloc[0]).values

    slope, intercept, r2 = linear_fit(t, np.log(c["excess"].values))
    k = -slope
    dT0 = float(np.exp(intercept))
    tau = 1 / k if k > 0 else float("inf")

    return {
        "start_C": round(c["sample_C"].iloc[0], 2),
        "end_C": round(c["sample_C"].iloc[-1], 2),
        "temperature_drop_C": round(c["sample_C"].iloc[0] - c["sample_C"].iloc[-1], 2),
        "reference_ambient_C": round(t_amb, 2),
        "fit_initial_excess_C": round(dT0, 2),
        "k_per_s": round(k, 6),
        "time_constant_s": round(tau, 1),
        "time_constant_min": round(tau / 60, 2),
        "half_life_min": round(np.log(2) / k / 60, 2) if k > 0 else None,
        "fit_r2": round(r2, 4),
        "final_excess_C": round(c["excess"].iloc[-1], 2),
    }


ANALYSES = {"overview": overview, "quality": quality, "ambient": ambient,
            "heating": heating, "cooling": cooling}


# ---------------------------------------------------------------- printing
def print_report(path, results):
    line = "=" * 52
    print(line)
    print(f" THR-04 thermal response summary")
    print(f" {path}")
    print(line)

    if "overview" in results:
        o = results["overview"]
        print("\nRUN OVERVIEW")
        print(f"  Time span           {o['start']} to {o['end']}  ({o['duration_min']} min)")
        print(f"  Rows                {o['rows']}")
        print(f"  Sample interval     {o['sample_interval_s']:g} s")
        print(f"  Heater off at       {o['heater_off']}")

    if "quality" in results:
        print("\nDATA QUALITY")
        for s, q in results["quality"].items():
            pct = 100 * q["valid"] / q["total"]
            print(f"  {s.capitalize():<10} {q['valid']}/{q['total']} valid ({pct:.1f}%)")
            for flag, n in q["flags"].items():
                print(f"      {flag:<18} {n}")

    if "ambient" in results:
        a = results["ambient"]
        print("\nAMBIENT")
        print(f"  Mean ± SD           {a['mean_C']:.2f} ± {a['std_C']:.2f} °C")
        print(f"  Range               {a['min_C']:.2f} to {a['max_C']:.2f} °C")
        print(f"  Drift (end-start)   {a['drift_C']:+.2f} °C")

    if "heating" in results:
        h = results["heating"]
        print("\nHEATING PHASE")
        if "error" in h:
            print(f"  {h['error']}")
        else:
            print(f"  Start temperature   {h['start_C']:.2f} °C")
            print(f"  Peak temperature    {h['peak_C']:.2f} °C at {h['peak_time']}")
            print(f"  Temperature rise    {h['temperature_rise_C']:.2f} °C")
            print(f"  Average rate        {h['avg_rate_C_per_min']:.2f} °C/min")
            print(f"  Rate, first minute  {h['initial_rate_C_per_min']:.2f} °C/min")
            print(f"  Rate, last minute   {h['final_rate_C_per_min']:.2f} °C/min")

    if "cooling" in results:
        c = results["cooling"]
        print("\nCOOLING PHASE  (Newton's law fit)")
        if "error" in c:
            print(f"  {c['error']}")
        else:
            print(f"  Start -> end        {c['start_C']:.2f} -> {c['end_C']:.2f} °C "
                  f"(drop {c['temperature_drop_C']:.2f} °C)")
            print(f"  Reference ambient   {c['reference_ambient_C']:.2f} °C")
            print(f"  Cooling constant k  {c['k_per_s']:.6f} 1/s")
            print(f"  Time constant tau   {c['time_constant_s']:.1f} s "
                  f"({c['time_constant_min']:.2f} min)")
            print(f"  Half-life of excess {c['half_life_min']:.2f} min")
            print(f"  Fit R²              {c['fit_r2']:.4f}")
            print(f"  Remaining excess    {c['final_excess_C']:.2f} °C above ambient")
    print()


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", nargs="?", default="THR04_clean.csv",
                    help="cleaned CSV file (default: THR04_clean.csv)")
    ap.add_argument("-s", "--section", choices=SECTIONS, action="append",
                    help="show only this section (repeatable)")
    ap.add_argument("--json", action="store_true",
                    help="print the results as JSON instead of a text report")
    args = ap.parse_args()

    df = load(args.csv)
    sections = args.section or SECTIONS
    results = {name: ANALYSES[name](df) for name in SECTIONS if name in sections}

    if args.json:
        print(json.dumps(results, indent=2, default=float))
    else:
        print_report(args.csv, results)


if __name__ == "__main__":
    main()

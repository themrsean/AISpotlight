"""Loading and analysis of a cleaned THR-04 CSV.

Every analysis function takes the loaded DataFrame and returns a plain dict,
so the results can be formatted as text, dumped as JSON, or plotted.
"""

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = {"time_s", "phase", "ambient_C", "sample_C", "ambient_flag", "sample_flag"}
SECTIONS = ("overview", "quality", "ambient", "heating", "cooling")


# ---------------------------------------------------------------- loading
class DataError(Exception):
    """Raised when the CSV cannot be used."""


def load(path: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(path)
    except FileNotFoundError:
        raise DataError(f"file not found: {path}") from None
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as err:
        raise DataError(f"could not parse {path}: {err}") from err

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise DataError(f"{path} is missing columns: {', '.join(sorted(missing))}")
    if df.empty:
        raise DataError(f"{path} contains no data rows")
    return df.sort_values("time_s").reset_index(drop=True)


def analyse(df, sections=SECTIONS):
    return {name: ANALYSES[name](df) for name in SECTIONS if name in sections}


# ---------------------------------------------------------------- helpers
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


# ---------------------------------------------------------------- analyses
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
    init_rate = (
        linear_fit(early["time_s"].values, early["sample_C"].values)[0]
        if len(early) >= 3
        else float("nan")
    )
    late = h[h["time_s"] >= t1 - initial_window_s]
    final_rate = (
        linear_fit(late["time_s"].values, late["sample_C"].values)[0]
        if len(late) >= 3
        else float("nan")
    )

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
    c = df[(df["phase"] == "cooling") & df["sample_C"].notna()].copy()
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
        "fit_start_time_s": float(c["time_s"].iloc[0]),
        "fit_initial_excess_C": round(dT0, 2),
        "k_per_s": round(k, 6),
        "time_constant_s": round(tau, 1),
        "time_constant_min": round(tau / 60, 2),
        "half_life_min": round(np.log(2) / k / 60, 2) if k > 0 else None,
        "fit_r2": round(r2, 4),
        "final_excess_C": round(c["excess"].iloc[-1], 2),
    }


ANALYSES = {
    "overview": overview,
    "quality": quality,
    "ambient": ambient,
    "heating": heating,
    "cooling": cooling,
}

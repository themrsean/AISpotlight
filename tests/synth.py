"""Synthetic THR-04 runs and anomaly injectors for tests.

Runs resemble THR04_clean.csv: 10 s sampling, 10 min linear heating, 20 min Newton
cooling, ambient around 22 °C. Noise SDs match THR04 (ambient ~0.15 °C) and values
are rounded to 0.1 °C like the logger.
"""

import numpy as np
import pandas as pd

INTERVAL_S = 10
HEATER_OFF_S = 600
END_S = 1800
AMBIENT_C = 22.0


def make_run(seed: int, ambient_sd: float = 0.15, sample_sd: float = 0.1) -> pd.DataFrame:
    """A clean synthetic run with realistic noise and 0.1 °C rounding."""
    rng = np.random.default_rng(seed)
    t = np.arange(0, END_S + INTERVAL_S, INTERVAL_S)
    heating = t < HEATER_OFF_S
    peak = AMBIENT_C + 0.09 * HEATER_OFF_S
    sample = np.where(
        heating,
        AMBIENT_C + 0.09 * t,
        AMBIENT_C + (peak - AMBIENT_C) * np.exp(-0.0019 * (t - HEATER_OFF_S)),
    )
    n = len(t)
    return pd.DataFrame(
        {
            "time_s": t,
            "phase": np.where(heating, "heating", "cooling"),
            "ambient_C": np.round(AMBIENT_C + rng.normal(0, ambient_sd, n), 1),
            "sample_C": np.round(sample + rng.normal(0, sample_sd, n), 1),
            "ambient_flag": ["ok"] * n,
            "sample_flag": ["ok"] * n,
        }
    )


def inject_ambient_drift(df: pd.DataFrame, total_C: float) -> pd.DataFrame:
    """Add a linear ambient ramp of ``total_C`` from the first to the last reading."""
    out = df.copy()
    out["ambient_C"] = out["ambient_C"] + np.linspace(0, total_C, len(out))
    return out


def inject_ambient_excursion(df: pd.DataFrame, size_C: float, at_s: float = 900) -> pd.DataFrame:
    """Add a temporary ambient bump of height ``size_C`` that returns to baseline.

    The bump changes the range but leaves the start and end (so the drift) untouched.
    """
    out = df.copy()
    bump = size_C * np.exp(-(((out["time_s"] - at_s) / 120.0) ** 2))
    out["ambient_C"] = out["ambient_C"] + bump
    return out

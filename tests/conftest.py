import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CLEAN_CSV = ROOT / "THR04_clean.csv"


def make_df(time_s, phase, ambient, sample, ambient_flag=None, sample_flag=None):
    n = len(time_s)
    return pd.DataFrame(
        {
            "time_s": time_s,
            "phase": phase if isinstance(phase, list) else [phase] * n,
            "ambient_C": ambient if isinstance(ambient, (list, np.ndarray)) else [ambient] * n,
            "sample_C": sample,
            "ambient_flag": ambient_flag or ["ok"] * n,
            "sample_flag": sample_flag or ["ok"] * n,
        }
    )


@pytest.fixture
def clean_csv():
    return CLEAN_CSV


@pytest.fixture
def synthetic_run():
    """10 min linear heating at 6 °C/min, then 20 min exact Newton cooling."""
    t_heat = np.arange(0, 600, 10)
    t_cool = np.arange(600, 1810, 10)
    amb, k = 20.0, 0.002
    heat = 20.0 + 0.1 * t_heat  # 0.1 °C/s
    peak = 20.0 + 0.1 * 600
    cool = amb + (peak - amb) * np.exp(-k * (t_cool - 600))
    return make_df(
        list(np.concatenate([t_heat, t_cool])),
        ["heating"] * len(t_heat) + ["cooling"] * len(t_cool),
        amb,
        list(np.concatenate([heat, cool])),
    )

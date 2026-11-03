import math

import numpy as np
import pytest
from conftest import make_df

from thr04.analysis import (
    DataError,
    ambient,
    analyse,
    cooling,
    fmt_time,
    heating,
    linear_fit,
    load,
    overview,
    quality,
)


# ---------------------------------------------------------------- helpers
@pytest.mark.parametrize(
    "seconds, expected",
    [
        (0, "00:00:00"),
        (59.6, "00:01:00"),
        (600, "00:10:00"),
        (3725, "01:02:05"),
    ],
)
def test_fmt_time(seconds, expected):
    assert fmt_time(seconds) == expected


def test_linear_fit_exact_line():
    x = np.arange(10.0)
    slope, intercept, r2 = linear_fit(x, 3 * x + 2)
    assert slope == pytest.approx(3)
    assert intercept == pytest.approx(2)
    assert r2 == pytest.approx(1)


def test_linear_fit_constant_y_gives_nan_r2():
    slope, _, r2 = linear_fit(np.arange(5.0), np.full(5, 7.0))
    assert slope == pytest.approx(0, abs=1e-12)
    assert math.isnan(r2)


# ---------------------------------------------------------------- load
def test_load_sorts_by_time(tmp_path):
    p = tmp_path / "x.csv"
    make_df([20, 0, 10], "heating", 22.0, [3.0, 1.0, 2.0]).to_csv(p, index=False)
    df = load(str(p))
    assert list(df["time_s"]) == [0, 10, 20]
    assert list(df["sample_C"]) == [1.0, 2.0, 3.0]


def test_load_missing_file(tmp_path):
    with pytest.raises(DataError, match="not found"):
        load(str(tmp_path / "nope.csv"))


def test_load_missing_columns(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("time_s,phase\n0,heating\n")
    with pytest.raises(DataError, match="missing columns"):
        load(str(p))


def test_load_empty_file(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("")
    with pytest.raises(DataError, match="could not parse"):
        load(str(p))


def test_load_header_only(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("time_s,phase,ambient_C,sample_C,ambient_flag,sample_flag\n")
    with pytest.raises(DataError, match="no data rows"):
        load(str(p))


def test_load_bad_encoding(tmp_path):
    p = tmp_path / "x.csv"
    p.write_bytes(b"\xff\xfe\x00\x81\x82garbage")
    with pytest.raises(DataError):
        load(str(p))


def test_load_rejects_non_numeric_time(tmp_path):  # B7
    p = tmp_path / "x.csv"
    make_df(["0", "abc"], "heating", 22.0, [1.0, 2.0]).to_csv(p, index=False)
    with pytest.raises(DataError, match="time_s"):
        load(str(p))


def test_load_rejects_unknown_phase(tmp_path):  # B7
    p = tmp_path / "x.csv"
    make_df([0, 10], ["heating", "Cooling"], 22.0, [1.0, 2.0]).to_csv(p, index=False)
    with pytest.raises(DataError, match="phase"):
        load(str(p))


def test_load_rejects_duplicate_times(tmp_path):  # B4
    p = tmp_path / "x.csv"
    make_df([0, 10, 10], "heating", 22.0, [1.0, 2.0, 3.0]).to_csv(p, index=False)
    with pytest.raises(DataError, match="duplicate"):
        load(str(p))


# ---------------------------------------------------------------- overview / quality / ambient
def test_overview_synthetic(synthetic_run):
    o = overview(synthetic_run)
    assert o["rows"] == len(synthetic_run)
    assert o["sample_interval_s"] == 10.0
    assert o["heater_off"] == "00:10:00"
    assert o["duration_min"] == 30.0


def test_overview_single_row():
    o = overview(make_df([0], "heating", 22.0, [22.0]))
    assert o["sample_interval_s"] is None
    assert o["heater_off"] is None


def test_quality_counts_split_and_nan_flags():
    df = make_df(
        [0, 10, 20, 30],
        "heating",
        22.0,
        [1.0, None, 3.0, 4.0],
        sample_flag=["ok", "missing", "spike;duplicate_merged", None],
    )
    q = quality(df)["sample"]
    assert q["valid"] == 3
    assert q["total"] == 4
    assert q["flags"] == {"missing": 1, "spike": 1, "duplicate_merged": 1}


def test_ambient_stats():
    a = ambient(make_df([0, 10, 20], "heating", [21.0, 22.0, 23.0], [1.0, 2.0, 3.0]))
    assert a == {"mean_C": 22.0, "std_C": 1.0, "min_C": 21.0, "max_C": 23.0, "drift_C": 2.0}


def test_ambient_all_missing_returns_error():  # B5
    a = ambient(make_df([0, 10], "heating", [np.nan, np.nan], [1.0, 2.0]))
    assert "error" in a


# ---------------------------------------------------------------- heating
def test_heating_synthetic_rates(synthetic_run):
    h = heating(synthetic_run)
    assert h["avg_rate_C_per_min"] == pytest.approx(6.0)
    assert h["initial_rate_C_per_min"] == pytest.approx(6.0)
    assert h["final_rate_C_per_min"] == pytest.approx(6.0)
    assert h["start_C"] == 20.0
    assert h["peak_C"] == 80.0  # first cooling sample is the true peak


def test_heating_too_few_points_for_rate_gives_nan():
    h = heating(make_df([0, 100], "heating", 22.0, [20.0, 30.0]))
    assert h["avg_rate_C_per_min"] == pytest.approx(6.0)
    assert math.isnan(h["initial_rate_C_per_min"])


def test_heating_not_enough_data():
    assert "error" in heating(make_df([0], "heating", 22.0, [20.0]))


# ---------------------------------------------------------------- cooling
def test_cooling_recovers_known_constant(synthetic_run):
    c = cooling(synthetic_run)
    assert c["k_per_s"] == pytest.approx(0.002, rel=1e-3)
    assert c["time_constant_s"] == pytest.approx(500, rel=1e-3)
    assert c["half_life_min"] == pytest.approx(math.log(2) / 0.002 / 60, rel=1e-2)
    assert c["fit_r2"] == pytest.approx(1.0)
    assert c["reference_ambient_C"] == 20.0
    assert c["fit_start_time_s"] == 600.0


def test_cooling_not_enough_data():
    assert "error" in cooling(make_df([0, 10], "cooling", 20.0, [50.0, 40.0]))


def test_cooling_sample_below_ambient_returns_error():  # B1
    df = make_df([0, 10, 20, 30], "cooling", 30.0, [29.0, 28.0, 27.0, 26.0])
    assert "error" in cooling(df)


def test_cooling_all_ambient_missing_returns_error():  # B1
    df = make_df([0, 10, 20], "cooling", [np.nan] * 3, [50.0, 40.0, 35.0])
    assert "error" in cooling(df)


# ---------------------------------------------------------------- analyse
def test_analyse_respects_sections_and_order(synthetic_run):
    r = analyse(synthetic_run, ["cooling", "overview"])
    assert list(r) == ["overview", "cooling"]

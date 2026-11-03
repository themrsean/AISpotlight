import json

import pytest

import summarize_thr04
from thr04.analysis import analyse, load
from thr04.report import format_report, to_json


def strict_json(text):
    def reject(c):
        raise ValueError(f"non-standard JSON constant {c}")

    return json.loads(text, parse_constant=reject)


# ---------------------------------------------------------------- golden regression
def test_golden_values_on_clean_csv(clean_csv):
    r = analyse(load(str(clean_csv)))
    assert r["overview"]["rows"] == 181
    assert r["overview"]["heater_off"] == "00:10:00"
    assert r["quality"]["sample"]["valid"] == 173
    assert r["quality"]["ambient"]["valid"] == 175
    assert r["ambient"]["mean_C"] == 22.08
    h = r["heating"]
    assert (
        h["peak_C"],
        h["avg_rate_C_per_min"],
        h["initial_rate_C_per_min"],
        h["final_rate_C_per_min"],
    ) == (76.3, 5.502, 9.686, 2.807)
    c = r["cooling"]
    assert (c["k_per_s"], c["time_constant_s"], c["half_life_min"], c["fit_r2"]) == (
        0.001894,
        527.9,
        6.1,
        0.9993,
    )


# ---------------------------------------------------------------- format_report
def test_format_report_full(clean_csv):
    text = format_report("f.csv", analyse(load(str(clean_csv))))
    for heading in ("RUN OVERVIEW", "DATA QUALITY", "AMBIENT", "HEATING PHASE", "COOLING PHASE"):
        assert heading in text
    assert "Time constant tau   527.9 s (8.80 min)" in text


def test_format_report_error_sections():
    text = format_report(
        "f.csv",
        {
            "heating": {"error": "not enough heating data"},
            "cooling": {"error": "not enough cooling data"},
            "ambient": {"error": "no valid ambient data"},
        },
    )
    assert "not enough heating data" in text
    assert "no valid ambient data" in text


def test_format_report_handles_missing_values():  # B2, B3
    results = {
        "overview": {
            "rows": 1,
            "start": "00:00:00",
            "end": "00:00:00",
            "duration_min": 0.0,
            "sample_interval_s": None,
            "heater_off": None,
        },
        "heating": {
            "start_C": 20.0,
            "end_of_heating_C": 30.0,
            "temperature_rise_C": 10.0,
            "peak_C": 30.0,
            "peak_time": "00:01:40",
            "avg_rate_C_per_min": 6.0,
            "initial_rate_C_per_min": float("nan"),
            "final_rate_C_per_min": float("nan"),
        },
        "cooling": {
            "start_C": 30.0,
            "end_C": 30.5,
            "temperature_drop_C": -0.5,
            "reference_ambient_C": 20.0,
            "fit_start_time_s": 0.0,
            "fit_initial_excess_C": 10.0,
            "k_per_s": -0.0001,
            "time_constant_s": float("inf"),
            "time_constant_min": float("inf"),
            "half_life_min": None,
            "fit_r2": 0.5,
            "final_excess_C": 10.5,
        },
    }
    text = format_report("f.csv", results)
    assert "None" not in text
    assert "n/a" in text


# ---------------------------------------------------------------- JSON
def test_to_json_is_strict_on_clean_data(clean_csv):
    strict_json(to_json(analyse(load(str(clean_csv)))))


def test_to_json_converts_nan_and_inf_to_null():  # B6
    out = strict_json(to_json({"a": {"x": float("nan"), "y": float("inf"), "z": 1.5}}))
    assert out == {"a": {"x": None, "y": None, "z": 1.5}}


# ---------------------------------------------------------------- CLI
def test_cli_text(clean_csv, capsys):
    summarize_thr04.main([str(clean_csv)])
    assert "COOLING PHASE" in capsys.readouterr().out


def test_cli_json_sections(clean_csv, capsys):
    summarize_thr04.main([str(clean_csv), "--json", "-s", "cooling", "-s", "overview"])
    out = strict_json(capsys.readouterr().out)
    assert list(out) == ["overview", "cooling"]


def test_cli_missing_file_exits(tmp_path):
    with pytest.raises(SystemExit) as exc:
        summarize_thr04.main([str(tmp_path / "missing.csv")])
    assert "file not found" in str(exc.value)


# ---------------------------------------------------------------- plot / GUI helpers
def test_build_figure_smoke(clean_csv):
    pytest.importorskip("matplotlib")
    from thr04.plot import build_figure

    df = load(str(clean_csv))
    fig = build_figure(df, analyse(df))
    assert len(fig.axes) == 2


def test_build_figure_without_cooling_fit(synthetic_run):
    pytest.importorskip("matplotlib")
    from thr04.plot import build_figure

    fig = build_figure(synthetic_run, {"cooling": {"error": "x"}})
    assert len(fig.axes) == 2


def test_flagged_rows_treats_nan_as_ok():  # B8
    from conftest import make_df

    from thr04.analysis import flagged_rows

    df = make_df([0, 10, 20], "heating", 22.0, [1.0, 2.0, 3.0], sample_flag=["ok", None, "spike"])
    assert list(flagged_rows(df)) == [False, False, True]

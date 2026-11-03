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


# ---------------------------------------------------------------- anomalies section (issue #3)
def _warning(message="Ambient temperature drifted +0.80 °C", threshold=0.5):
    return {
        "check": "ambient",
        "severity": "warning",
        "affects": ["ambient", "cooling"],
        "start_s": None,
        "end_s": None,
        "message": message,
        "hint": "Check the room temperature.",
        "measured": 0.8,
        "threshold": threshold,
    }


def _anomalies(findings):
    return {
        "summary": {
            "critical": sum(f["severity"] == "critical" for f in findings),
            "warning": sum(f["severity"] == "warning" for f in findings),
        },
        "thresholds": {"ambient_max_range_C": 1.0, "ambient_max_drift_C": 0.5},
        "config_file": None,
        "findings": findings,
    }


def test_report_without_anomalies_says_none_detected(clean_csv):
    lines = format_report("f.csv", analyse(load(str(clean_csv)))).splitlines()
    assert lines[4] == " No anomalies detected"  # directly under the header block
    assert "ANOMALIES" in lines
    assert lines[lines.index("ANOMALIES") + 1] == "  None detected"


def test_report_summary_line_and_section_with_findings():
    text = format_report("f.csv", {"anomalies": _anomalies([_warning()])})
    lines = text.splitlines()
    assert lines[4] == " ⚠ 0 critical, 1 warning — see ANOMALIES"
    section = text.split("\nANOMALIES\n", 1)[1]
    assert "[warning] ambient — whole run" in section
    assert "Ambient temperature drifted +0.80 °C" in section
    assert "Check: Check the room temperature." in section
    assert "Affects: ambient, cooling" in section


def test_report_summary_pluralises():
    text = format_report("f.csv", {"anomalies": _anomalies([_warning(), _warning()])})
    assert " ⚠ 0 critical, 2 warnings — see ANOMALIES" in text


def test_report_shows_time_range_for_timed_findings():
    f = _warning() | {"start_s": 1250.0, "end_s": 1290.0}
    text = format_report("f.csv", {"anomalies": _anomalies([f])})
    assert "[warning] ambient — 00:20:50 to 00:21:30" in text


def test_report_without_anomalies_section_has_no_summary_line():
    text = format_report("f.csv", {"heating": {"error": "x"}})
    assert "anomal" not in text.lower()


def test_cli_anomalies_section_only(clean_csv, capsys):
    summarize_thr04.main([str(clean_csv), "-s", "anomalies"])
    out = capsys.readouterr().out
    assert "No anomalies detected" in out
    assert "ANOMALIES" in out
    assert "RUN OVERVIEW" not in out and "COOLING PHASE" not in out


def test_cli_json_includes_anomalies(clean_csv, capsys):
    summarize_thr04.main([str(clean_csv), "--json"])
    out = strict_json(capsys.readouterr().out)
    assert list(out) == ["overview", "quality", "ambient", "heating", "cooling", "anomalies"]
    a = out["anomalies"]
    assert a == {
        "summary": {"critical": 0, "warning": 0},
        "thresholds": {"ambient_max_range_C": 1.0, "ambient_max_drift_C": 0.5},
        "config_file": None,
        "findings": [],
    }

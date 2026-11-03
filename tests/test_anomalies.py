"""Tests for anomaly detection: findings framework and C6 ambient range/drift (issue #3)."""

import numpy as np
import pytest
from conftest import make_df
from synth import inject_ambient_drift, inject_ambient_excursion, make_run

from thr04.analysis import load
from thr04.anomalies import DEFAULT_THRESHOLDS, Finding, detect, sort_findings

SEEDS = range(5)
RANGE_TH = DEFAULT_THRESHOLDS["ambient_max_range_C"]
DRIFT_TH = DEFAULT_THRESHOLDS["ambient_max_drift_C"]
FINDING_KEYS = {
    "check",
    "severity",
    "affects",
    "start_s",
    "end_s",
    "message",
    "hint",
    "measured",
    "threshold",
}


def ambient_findings(df, kind=None):
    """Ambient findings; kind='range' or 'drift' selects by the threshold compared against."""
    found = [f for f in detect(df)["findings"] if f["check"] == "ambient"]
    if kind == "range":
        return [f for f in found if f["threshold"] == RANGE_TH]
    if kind == "drift":
        return [f for f in found if f["threshold"] == DRIFT_TH]
    return found


# ---------------------------------------------------------------- B-AC1: detect at 2x
@pytest.mark.parametrize("seed", SEEDS)
def test_range_detected_at_2x(seed):
    df = inject_ambient_excursion(make_run(seed), 2 * RANGE_TH)
    (f,) = ambient_findings(df, "range")
    assert f["severity"] == "warning"
    assert f["affects"] == ["ambient", "cooling"]
    assert f["start_s"] is None and f["end_s"] is None
    assert f["threshold"] == RANGE_TH
    assert f["measured"] > RANGE_TH
    assert f["measured"] == pytest.approx(2 * RANGE_TH, abs=0.5)


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("sign", [1, -1])
def test_drift_detected_at_2x(seed, sign):
    df = inject_ambient_drift(make_run(seed), sign * 2 * DRIFT_TH)
    # A large drift also widens the range; only require the drift finding here.
    (f,) = ambient_findings(df, "drift")
    assert f["severity"] == "warning"
    assert f["affects"] == ["ambient", "cooling"]
    assert f["start_s"] is None and f["end_s"] is None
    assert f["measured"] > DRIFT_TH  # absolute value is compared
    assert f["measured"] == pytest.approx(2 * DRIFT_TH, abs=0.2)
    assert ("+" if sign > 0 else "-") in f["message"]


# ---------------------------------------------------------------- B-AC2: ignore at 0.5x
@pytest.mark.parametrize("seed", SEEDS)
def test_range_not_detected_at_half(seed):
    df = inject_ambient_excursion(make_run(seed), 0.5 * RANGE_TH)
    assert ambient_findings(df) == []


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("sign", [1, -1])
def test_drift_not_detected_at_half(seed, sign):
    df = inject_ambient_drift(make_run(seed), sign * 0.5 * DRIFT_TH)
    assert ambient_findings(df) == []


# ---------------------------------------------------------------- B-AC3 / B-AC4
@pytest.mark.parametrize("seed", SEEDS)
def test_clean_runs_have_no_findings(seed):
    assert detect(make_run(seed))["findings"] == []


def test_thr04_has_no_findings(clean_csv):
    result = detect(load(str(clean_csv)))
    assert result["findings"] == []
    assert result["summary"] == {"critical": 0, "warning": 0}


# ---------------------------------------------------------------- thresholds and float edges
def _ambient_df(values):
    n = len(values)
    return make_df(list(range(0, 10 * n, 10)), "heating", list(values), [30.0] * n)


def test_drift_exactly_at_threshold_is_not_flagged():
    # 22.4 - 21.9 == 0.5000000000000036 in floating point; must not count as > 0.5.
    values = [21.9] * 6 + [22.0] * 20 + [22.4] * 6
    assert ambient_findings(_ambient_df(values), "drift") == []


def test_drift_just_over_threshold_is_flagged():
    values = [21.9] * 6 + [22.0] * 20 + [22.5] * 6
    (f,) = ambient_findings(_ambient_df(values), "drift")
    assert f["measured"] == pytest.approx(0.6)


@pytest.mark.parametrize("plateau, flagged", [(23.0, False), (23.1, True)])
def test_range_boundary(plateau, flagged):
    values = [22.0] * 15 + [plateau] * 10 + [22.0] * 15
    assert bool(ambient_findings(_ambient_df(values), "range")) is flagged


def test_single_reading_spike_does_not_count_towards_range():
    values = [22.0] * 20 + [24.0] + [22.0] * 20
    assert ambient_findings(_ambient_df(values), "range") == []


def test_drift_uses_valid_readings_at_the_ends():
    values = [np.nan] * 3 + [22.0] * 30 + [np.nan] * 3
    assert ambient_findings(_ambient_df(values)) == []
    ramp = [np.nan] * 3 + list(np.linspace(22.0, 23.0, 30)) + [np.nan] * 3
    assert len(ambient_findings(_ambient_df(ramp), "drift")) == 1


def test_threshold_override_changes_result_and_is_echoed():
    df = inject_ambient_drift(make_run(0), 2 * DRIFT_TH)
    result = detect(df, thresholds={"ambient_max_drift_C": 5.0})
    assert [f for f in result["findings"] if f["threshold"] == 5.0] == []
    assert result["thresholds"] == {"ambient_max_range_C": RANGE_TH, "ambient_max_drift_C": 5.0}


# ---------------------------------------------------------------- B-AC9: degenerate input
@pytest.mark.parametrize(
    "df",
    [
        pytest.param(_ambient_df([np.nan] * 10), id="all-nan-ambient"),
        pytest.param(_ambient_df([np.nan] * 5 + [22.0] + [np.nan] * 4), id="one-valid"),
        pytest.param(_ambient_df([22.0]), id="one-row"),
        pytest.param(make_run(0).query("phase == 'heating'"), id="heating-only"),
    ],
)
def test_degenerate_input_gives_no_findings(df):
    assert detect(df)["findings"] == []


# ---------------------------------------------------------------- structure (B-AC6, B-AC8)
def test_detect_structure():
    result = detect(make_run(0))
    assert set(result) == {"summary", "thresholds", "config_file", "findings"}
    assert result["config_file"] is None
    assert result["thresholds"] == DEFAULT_THRESHOLDS


def test_finding_fields_message_and_hint():
    df = inject_ambient_drift(make_run(0), 3.0)  # trips both range and drift
    findings = ambient_findings(df)
    assert len(findings) == 2
    for f in findings:
        assert set(f) == FINDING_KEYS
        assert "°C" in f["message"]
        assert f["hint"].strip()
    assert detect(df)["summary"] == {"critical": 0, "warning": 2}


def test_range_reported_before_drift():
    df = inject_ambient_drift(make_run(0), 3.0)
    assert [f["threshold"] for f in ambient_findings(df)] == [RANGE_TH, DRIFT_TH]


def test_sort_order_severity_then_time_then_check():
    def f(check, severity, start):
        return Finding(check=check, severity=severity, affects=("cooling",), message="m", hint="h",
                       start_s=start, end_s=start)  # fmt: skip

    findings = [
        f("gap", "warning", 300.0),
        f("step_change", "warning", None),
        f("ambient", "warning", None),
        f("gap", "warning", 100.0),
        f("phase_labels", "critical", 500.0),
        f("cooling_fit", "critical", None),
    ]
    ordered = [(x.severity, x.start_s, x.check) for x in sort_findings(findings)]
    assert ordered == [
        ("critical", None, "cooling_fit"),
        ("critical", 500.0, "phase_labels"),
        ("warning", None, "ambient"),
        ("warning", None, "step_change"),
        ("warning", 100.0, "gap"),
        ("warning", 300.0, "gap"),
    ]

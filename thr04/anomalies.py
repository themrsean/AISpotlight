"""Anomaly detection for a cleaned THR-04 run (see docs/requirements.md).

Each check takes the loaded DataFrame and the thresholds in use and returns a list of
``Finding``s. ``detect`` runs every check and returns the ``anomalies`` result section.
Detection is report-only: it never changes the data or the other analyses.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

import pandas as pd

# FR-12: default thresholds. Only keys used by implemented checks are defined.
DEFAULT_THRESHOLDS: dict[str, float] = {
    "ambient_max_range_C": 1.0,
    "ambient_max_drift_C": 0.5,
}

SEVERITY_ORDER = {"critical": 0, "warning": 1}

# Measured values are rounded before comparing, so float noise such as
# 22.4 - 21.9 == 0.5000000000000036 does not count as exceeding 0.5.
_COMPARE_DECIMALS = 6

# D20: ambient range uses a centred rolling median; drift compares end-window means.
_AMBIENT_SMOOTH_READINGS = 5
_AMBIENT_DRIFT_WINDOW_S = 60.0


@dataclass(frozen=True)
class Finding:
    """One detected anomaly (FR-9). ``start_s``/``end_s`` are None for whole-run findings."""

    check: str
    severity: str
    affects: tuple[str, ...]
    message: str
    hint: str
    start_s: float | None = None
    end_s: float | None = None
    measured: float | None = None
    threshold: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "check": self.check,
            "severity": self.severity,
            "affects": list(self.affects),
            "start_s": self.start_s,
            "end_s": self.end_s,
            "message": self.message,
            "hint": self.hint,
            "measured": self.measured,
            "threshold": self.threshold,
        }


def _exceeds(measured: float, threshold: float) -> bool:
    return round(measured, _COMPARE_DECIMALS) > threshold


def sort_findings(findings: Iterable[Finding]) -> list[Finding]:
    """FR-10 order: critical first, then by start time (whole-run first), then check.

    The sort is stable, so findings that tie keep the order their check emitted them.
    """

    def key(f: Finding) -> tuple[int, bool, float, str]:
        timed = f.start_s is not None
        return (SEVERITY_ORDER[f.severity], timed, f.start_s if timed else 0.0, f.check)

    return sorted(findings, key=key)


# ---------------------------------------------------------------- C6 ambient
def check_ambient(df: pd.DataFrame, th: dict[str, float]) -> list[Finding]:
    """C6 rows 1-2: ambient range and drift over the whole run (FR-7, D18, D20)."""
    valid = df.loc[df["ambient_C"].notna(), ["time_s", "ambient_C"]].sort_values("time_s")
    if valid.empty:
        return []
    temps = valid["ambient_C"].reset_index(drop=True)
    times = valid["time_s"].reset_index(drop=True)
    findings = []

    smoothed = temps.rolling(_AMBIENT_SMOOTH_READINGS, center=True, min_periods=1).median()
    spread = float(smoothed.max() - smoothed.min())
    limit = th["ambient_max_range_C"]
    if _exceeds(spread, limit):
        findings.append(
            Finding(
                check="ambient",
                severity="warning",
                affects=("ambient", "cooling"),
                message=(
                    f"Ambient temperature varied by {spread:.2f} °C during the run "
                    f"(limit {limit:.2f} °C, short spikes ignored)."
                ),
                hint=(
                    "drafts, air-conditioning cycling or sunlight on the setup. "
                    "The cooling fit assumes a steady room temperature."
                ),
                measured=round(spread, _COMPARE_DECIMALS),
                threshold=limit,
            )
        )

    first = temps[times < times.iloc[0] + _AMBIENT_DRIFT_WINDOW_S].mean()
    last = temps[times > times.iloc[-1] - _AMBIENT_DRIFT_WINDOW_S].mean()
    drift = float(last - first)
    limit = th["ambient_max_drift_C"]
    if _exceeds(abs(drift), limit):
        findings.append(
            Finding(
                check="ambient",
                severity="warning",
                affects=("ambient", "cooling"),
                message=(
                    f"Ambient temperature drifted {drift:+.2f} °C from the first minute "
                    f"to the last minute of the run (limit ±{limit:.2f} °C)."
                ),
                hint=(
                    "whether the room warmed or cooled during the run, or whether "
                    "the ambient sensor is too close to the heated block."
                ),
                measured=round(abs(drift), _COMPARE_DECIMALS),
                threshold=limit,
            )
        )
    return findings


CHECKS: tuple[Callable[[pd.DataFrame, dict[str, float]], list[Finding]], ...] = (check_ambient,)


def detect(df: pd.DataFrame, thresholds: dict[str, float] | None = None) -> dict[str, Any]:
    """Run every check and return the ``anomalies`` section (FR-1, FR-14, FR-15)."""
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    findings = sort_findings(f for check in CHECKS for f in check(df, th))
    return {
        "summary": {
            severity: sum(f.severity == severity for f in findings) for severity in SEVERITY_ORDER
        },
        "thresholds": th,
        "config_file": None,  # FR-13 (--config) not implemented yet
        "findings": [f.to_dict() for f in findings],
    }

"""Text and JSON rendering of analysis results."""

import json
import math
from typing import Any

import numpy as np

NA = "n/a"


def _clean(value: Any) -> Any:
    """Recursively convert numpy scalars to Python and NaN/inf to None (B6)."""
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def to_json(results: dict) -> str:
    """Serialise results as strict JSON (no NaN or Infinity)."""
    return json.dumps(_clean(results), indent=2, allow_nan=False)


def _fmt(value: Any, spec: str = "") -> str:
    """Format a number, or return 'n/a' for None, NaN or infinity (B2, B3)."""
    if value is None:
        return NA
    if isinstance(value, (int, float, np.number)) and not math.isfinite(float(value)):
        return NA
    return format(value, spec)


def format_report(path: str, results: dict) -> str:
    """Render analysis results as a plain-text report."""
    lines: list[str] = []
    out = lines.append
    line = "=" * 52
    out(line)
    out(" THR-04 thermal response summary")
    out(f" {path}")
    out(line)

    if "overview" in results:
        o = results["overview"]
        out("\nRUN OVERVIEW")
        out(f"  Time span           {o['start']} to {o['end']}  ({o['duration_min']} min)")
        out(f"  Rows                {o['rows']}")
        out(f"  Sample interval     {_fmt(o['sample_interval_s'], 'g')} s")
        out(f"  Heater off at       {_fmt(o['heater_off'])}")

    if "quality" in results:
        out("\nDATA QUALITY")
        for s, q in results["quality"].items():
            pct = 100 * q["valid"] / q["total"]
            out(f"  {s.capitalize():<10} {q['valid']}/{q['total']} valid ({pct:.1f}%)")
            for flag, n in q["flags"].items():
                out(f"      {flag:<18} {n}")

    if "ambient" in results:
        a = results["ambient"]
        out("\nAMBIENT")
        if "error" in a:
            out(f"  {a['error']}")
        else:
            out(f"  Mean ± SD           {_fmt(a['mean_C'], '.2f')} ± {_fmt(a['std_C'], '.2f')} °C")
            out(f"  Range               {_fmt(a['min_C'], '.2f')} to {_fmt(a['max_C'], '.2f')} °C")
            out(f"  Drift (end-start)   {_fmt(a['drift_C'], '+.2f')} °C")

    if "heating" in results:
        h = results["heating"]
        out("\nHEATING PHASE")
        if "error" in h:
            out(f"  {h['error']}")
        else:
            out(f"  Start temperature   {_fmt(h['start_C'], '.2f')} °C")
            out(f"  Peak temperature    {_fmt(h['peak_C'], '.2f')} °C at {h['peak_time']}")
            out(f"  Temperature rise    {_fmt(h['temperature_rise_C'], '.2f')} °C")
            out(f"  Average rate        {_fmt(h['avg_rate_C_per_min'], '.2f')} °C/min")
            out(f"  Rate, first minute  {_fmt(h['initial_rate_C_per_min'], '.2f')} °C/min")
            out(f"  Rate, last minute   {_fmt(h['final_rate_C_per_min'], '.2f')} °C/min")

    if "cooling" in results:
        c = results["cooling"]
        out("\nCOOLING PHASE  (Newton's law fit)")
        if "error" in c:
            out(f"  {c['error']}")
        else:
            out(
                f"  Start -> end        {_fmt(c['start_C'], '.2f')} -> "
                f"{_fmt(c['end_C'], '.2f')} °C "
                f"(drop {_fmt(c['temperature_drop_C'], '.2f')} °C)"
            )
            out(f"  Reference ambient   {_fmt(c['reference_ambient_C'], '.2f')} °C")
            out(f"  Cooling constant k  {_fmt(c['k_per_s'], '.6f')} 1/s")
            out(
                f"  Time constant tau   {_fmt(c['time_constant_s'], '.1f')} s "
                f"({_fmt(c['time_constant_min'], '.2f')} min)"
            )
            out(f"  Half-life of excess {_fmt(c['half_life_min'], '.2f')} min")
            out(f"  Fit R²              {_fmt(c['fit_r2'], '.4f')}")
            out(f"  Remaining excess    {_fmt(c['final_excess_C'], '.2f')} °C above ambient")
    out("")
    return "\n".join(lines)

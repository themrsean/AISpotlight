"""Text and JSON rendering of analysis results."""

import json


def to_json(results) -> str:
    return json.dumps(results, indent=2, default=float)


def format_report(path, results) -> str:
    lines = []
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
        out(f"  Sample interval     {o['sample_interval_s']:g} s")
        out(f"  Heater off at       {o['heater_off']}")

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
        out(f"  Mean ± SD           {a['mean_C']:.2f} ± {a['std_C']:.2f} °C")
        out(f"  Range               {a['min_C']:.2f} to {a['max_C']:.2f} °C")
        out(f"  Drift (end-start)   {a['drift_C']:+.2f} °C")

    if "heating" in results:
        h = results["heating"]
        out("\nHEATING PHASE")
        if "error" in h:
            out(f"  {h['error']}")
        else:
            out(f"  Start temperature   {h['start_C']:.2f} °C")
            out(f"  Peak temperature    {h['peak_C']:.2f} °C at {h['peak_time']}")
            out(f"  Temperature rise    {h['temperature_rise_C']:.2f} °C")
            out(f"  Average rate        {h['avg_rate_C_per_min']:.2f} °C/min")
            out(f"  Rate, first minute  {h['initial_rate_C_per_min']:.2f} °C/min")
            out(f"  Rate, last minute   {h['final_rate_C_per_min']:.2f} °C/min")

    if "cooling" in results:
        c = results["cooling"]
        out("\nCOOLING PHASE  (Newton's law fit)")
        if "error" in c:
            out(f"  {c['error']}")
        else:
            out(
                f"  Start -> end        {c['start_C']:.2f} -> {c['end_C']:.2f} °C "
                f"(drop {c['temperature_drop_C']:.2f} °C)"
            )
            out(f"  Reference ambient   {c['reference_ambient_C']:.2f} °C")
            out(f"  Cooling constant k  {c['k_per_s']:.6f} 1/s")
            out(
                f"  Time constant tau   {c['time_constant_s']:.1f} s "
                f"({c['time_constant_min']:.2f} min)"
            )
            out(f"  Half-life of excess {c['half_life_min']:.2f} min")
            out(f"  Fit R²              {c['fit_r2']:.4f}")
            out(f"  Remaining excess    {c['final_excess_C']:.2f} °C above ambient")
    out("")
    return "\n".join(lines)

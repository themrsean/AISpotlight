"""Matplotlib figure of the temperature curves and cooling fit."""

import numpy as np


def build_figure(df, results, fig=None):
    """Draw the temperature curves and the cooling fit onto a matplotlib figure."""
    from matplotlib.figure import Figure

    if fig is None:
        fig = Figure(figsize=(9, 7), layout="constrained")
    fig.clear()
    ax1, ax2 = fig.subplots(2, 1)
    t_min = df["time_s"] / 60

    # Top: temperature vs time
    ax1.plot(t_min, df["sample_C"], ".-", ms=3, lw=1, label="Sample")
    ax1.plot(t_min, df["ambient_C"], ".-", ms=3, lw=1, label="Ambient")
    cooling_rows = df[df["phase"] == "cooling"]
    if len(cooling_rows):
        t_off = cooling_rows["time_s"].iloc[0] / 60
        ax1.axvline(t_off, color="grey", ls="--", lw=1)
        ax1.text(
            t_off,
            0.5,
            "heater off  ",
            rotation=90,
            ha="right",
            va="center",
            color="grey",
            fontsize=9,
            transform=ax1.get_xaxis_transform(),
        )

    c = results.get("cooling", {})
    if "k_per_s" in c:
        tc = cooling_rows["time_s"].values
        fit = c["reference_ambient_C"] + c["fit_initial_excess_C"] * np.exp(
            -c["k_per_s"] * (tc - c["fit_start_time_s"])
        )
        ax1.plot(
            tc / 60,
            fit,
            "--",
            lw=1.5,
            color="black",
            label=f"Newton fit (τ = {c['time_constant_min']:.2f} min)",
        )
    ax1.set_xlabel("Time (min)")
    ax1.set_ylabel("Temperature (°C)")
    ax1.set_title("Thermal response")
    ax1.grid(alpha=0.3)
    ax1.legend(loc="center right")

    # Bottom: excess temperature during cooling on a log axis
    if "k_per_s" in c:
        cr = cooling_rows[cooling_rows["sample_C"].notna()]
        excess = cr["sample_C"] - c["reference_ambient_C"]
        keep = excess > 0
        ax2.semilogy(cr["time_s"][keep] / 60, excess[keep], ".", ms=4, label="Measured")
        ax2.semilogy(
            tc / 60,
            fit - c["reference_ambient_C"],
            "-",
            color="black",
            lw=1,
            label=f"Fit, R² = {c['fit_r2']:.4f}",
        )
        ax2.set_title("Cooling: excess over ambient (log scale)")
        ax2.set_xlabel("Time (min)")
        ax2.set_ylabel("T − T_ambient (°C)")
        ax2.grid(alpha=0.3, which="both")
        ax2.legend()
    else:
        ax2.text(
            0.5,
            0.5,
            "Not enough cooling data to fit",
            ha="center",
            va="center",
            transform=ax2.transAxes,
        )
        ax2.set_axis_off()

    return fig

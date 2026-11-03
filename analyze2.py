#!/usr/bin/env python3
"""
Summarise a cleaned THR-04 thermal response CSV (output of clean_thr04.py).

Reports
  * run overview: duration, sampling interval, heater-off time
  * data quality: valid-value counts and a breakdown of cleaning flags
  * ambient stability: mean, standard deviation, range
  * heating phase: start / peak temperature, average and initial heating rate
  * cooling phase: Newton's-law-of-cooling fit, T - T_amb = dT0 * exp(-k t),
    giving the cooling constant k, time constant tau, half-life and R^2

Usage
  python summarize_thr04.py THR04_clean.csv
  python summarize_thr04.py THR04_clean.csv --section cooling
  python summarize_thr04.py THR04_clean.csv --json > summary.json
  python summarize_thr04.py --gui                     # graphical interface
  python summarize_thr04.py THR04_clean.csv --gui     # open a file in the GUI

The GUI needs tkinter (bundled with most Python installs) and, for the
plot tab, matplotlib (pip install matplotlib).
"""

import argparse
import json
import sys

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = {"time_s", "phase", "ambient_C", "sample_C",
                    "ambient_flag", "sample_flag"}
SECTIONS = ("overview", "quality", "ambient", "heating", "cooling")


# ---------------------------------------------------------------- loading
class DataError(Exception):
    """Raised when the CSV cannot be used."""


def load(path: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(path)
    except FileNotFoundError:
        raise DataError(f"file not found: {path}")
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as err:
        raise DataError(f"could not parse {path}: {err}")

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise DataError(f"{path} is missing columns: {', '.join(sorted(missing))}")
    if df.empty:
        raise DataError(f"{path} contains no data rows")
    return df.sort_values("time_s").reset_index(drop=True)


def analyse(df, sections=SECTIONS):
    return {name: ANALYSES[name](df) for name in SECTIONS if name in sections}


def fmt_time(seconds) -> str:
    seconds = int(round(seconds))
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def linear_fit(x, y):
    """Least-squares line; returns slope, intercept, R^2."""
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res = np.sum((y - pred) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return float(slope), float(intercept), float(r2)


# ---------------------------------------------------------------- analysis
def overview(df):
    t = df["time_s"]
    steps = t.diff().dropna()
    cooling = df[df["phase"] == "cooling"]
    return {
        "rows": int(len(df)),
        "start": fmt_time(t.iloc[0]),
        "end": fmt_time(t.iloc[-1]),
        "duration_min": round((t.iloc[-1] - t.iloc[0]) / 60, 2),
        "sample_interval_s": float(steps.mode().iloc[0]) if len(steps) else None,
        "heater_off": fmt_time(cooling["time_s"].iloc[0]) if len(cooling) else None,
    }


def quality(df):
    out = {}
    for s in ("ambient", "sample"):
        flags = df[f"{s}_flag"].fillna("ok").str.split(";").explode()
        counts = flags[flags != "ok"].value_counts()
        out[s] = {
            "valid": int(df[f"{s}_C"].notna().sum()),
            "total": int(len(df)),
            "flags": {k: int(v) for k, v in counts.items()},
        }
    return out


def ambient(df):
    a = df["ambient_C"].dropna()
    return {
        "mean_C": round(a.mean(), 2),
        "std_C": round(a.std(), 2),
        "min_C": round(a.min(), 2),
        "max_C": round(a.max(), 2),
        "drift_C": round(a.iloc[-1] - a.iloc[0], 2),
    }


def heating(df, initial_window_s=60):
    h = df[(df["phase"] == "heating") & df["sample_C"].notna()]
    allv = df[df["sample_C"].notna()]
    if len(h) < 2:
        return {"error": "not enough heating data"}

    peak = allv.loc[allv["sample_C"].idxmax()]
    t0, T0 = h["time_s"].iloc[0], h["sample_C"].iloc[0]
    t1, T1 = h["time_s"].iloc[-1], h["sample_C"].iloc[-1]

    early = h[h["time_s"] <= t0 + initial_window_s]
    init_rate = linear_fit(early["time_s"].values, early["sample_C"].values)[0] \
        if len(early) >= 3 else float("nan")
    late = h[h["time_s"] >= t1 - initial_window_s]
    final_rate = linear_fit(late["time_s"].values, late["sample_C"].values)[0] \
        if len(late) >= 3 else float("nan")

    return {
        "start_C": round(T0, 2),
        "end_of_heating_C": round(T1, 2),
        "temperature_rise_C": round(T1 - T0, 2),
        "peak_C": round(peak["sample_C"], 2),
        "peak_time": fmt_time(peak["time_s"]),
        "avg_rate_C_per_min": round((T1 - T0) / (t1 - t0) * 60, 3),
        "initial_rate_C_per_min": round(init_rate * 60, 3),
        "final_rate_C_per_min": round(final_rate * 60, 3),
    }


def cooling(df):
    c = df[(df["phase"] == "cooling")
           & df["sample_C"].notna()].copy()
    if len(c) < 3:
        return {"error": "not enough cooling data"}

    # Use the mean ambient over the cooling phase as the reference temperature.
    t_amb = df.loc[df["phase"] == "cooling", "ambient_C"].mean()
    c["excess"] = c["sample_C"] - t_amb
    c = c[c["excess"] > 0]
    t = (c["time_s"] - c["time_s"].iloc[0]).values

    slope, intercept, r2 = linear_fit(t, np.log(c["excess"].values))
    k = -slope
    dT0 = float(np.exp(intercept))
    tau = 1 / k if k > 0 else float("inf")

    return {
        "start_C": round(c["sample_C"].iloc[0], 2),
        "end_C": round(c["sample_C"].iloc[-1], 2),
        "temperature_drop_C": round(c["sample_C"].iloc[0] - c["sample_C"].iloc[-1], 2),
        "reference_ambient_C": round(t_amb, 2),
        "fit_start_time_s": float(c["time_s"].iloc[0]),
        "fit_initial_excess_C": round(dT0, 2),
        "k_per_s": round(k, 6),
        "time_constant_s": round(tau, 1),
        "time_constant_min": round(tau / 60, 2),
        "half_life_min": round(np.log(2) / k / 60, 2) if k > 0 else None,
        "fit_r2": round(r2, 4),
        "final_excess_C": round(c["excess"].iloc[-1], 2),
    }


ANALYSES = {"overview": overview, "quality": quality, "ambient": ambient,
            "heating": heating, "cooling": cooling}


# ---------------------------------------------------------------- printing
def format_report(path, results) -> str:
    lines = []
    out = lines.append
    line = "=" * 52
    out(line)
    out(f" THR-04 thermal response summary")
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
            out(f"  Start -> end        {c['start_C']:.2f} -> {c['end_C']:.2f} °C "
                  f"(drop {c['temperature_drop_C']:.2f} °C)")
            out(f"  Reference ambient   {c['reference_ambient_C']:.2f} °C")
            out(f"  Cooling constant k  {c['k_per_s']:.6f} 1/s")
            out(f"  Time constant tau   {c['time_constant_s']:.1f} s "
                  f"({c['time_constant_min']:.2f} min)")
            out(f"  Half-life of excess {c['half_life_min']:.2f} min")
            out(f"  Fit R²              {c['fit_r2']:.4f}")
            out(f"  Remaining excess    {c['final_excess_C']:.2f} °C above ambient")
    out("")
    return "\n".join(lines)


# ---------------------------------------------------------------- plotting
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
        ax1.text(t_off, 0.5, "heater off  ", rotation=90, ha="right",
                 va="center", color="grey", fontsize=9,
                 transform=ax1.get_xaxis_transform())

    c = results.get("cooling", {})
    if "k_per_s" in c:
        tc = cooling_rows["time_s"].values
        fit = c["reference_ambient_C"] + c["fit_initial_excess_C"] * np.exp(
            -c["k_per_s"] * (tc - c["fit_start_time_s"]))
        ax1.plot(tc / 60, fit, "--", lw=1.5, color="black",
                 label=f"Newton fit (τ = {c['time_constant_min']:.2f} min)")
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
        ax2.semilogy(cr["time_s"][keep] / 60, excess[keep], ".", ms=4,
                     label="Measured")
        ax2.semilogy(tc / 60, fit - c["reference_ambient_C"], "-", color="black",
                     lw=1, label=f"Fit, R² = {c['fit_r2']:.4f}")
        ax2.set_title("Cooling: excess over ambient (log scale)")
        ax2.set_xlabel("Time (min)")
        ax2.set_ylabel("T − T_ambient (°C)")
        ax2.grid(alpha=0.3, which="both")
        ax2.legend()
    else:
        ax2.text(0.5, 0.5, "Not enough cooling data to fit", ha="center",
                 va="center", transform=ax2.transAxes)
        ax2.set_axis_off()

    return fig


# ---------------------------------------------------------------- GUI
def run_gui(initial_path=None):
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
        from tkinter.scrolledtext import ScrolledText
    except ImportError:
        sys.exit("error: tkinter is not available in this Python installation")

    try:
        from matplotlib.backends.backend_tkagg import (
            FigureCanvasTkAgg, NavigationToolbar2Tk)
        from matplotlib.figure import Figure
        have_mpl = True
    except ImportError:
        have_mpl = False

    try:
        root = tk.Tk()
    except tk.TclError as err:
        sys.exit(f"error: could not open a window ({err}). "
                 "Is a display available?")
    root.title("THR-04 thermal response summary")
    root.geometry("980x760")
    root.minsize(640, 480)

    state = {"path": None, "df": None, "results": None}

    # --- toolbar
    bar = ttk.Frame(root, padding=(8, 6))
    bar.pack(fill="x")
    open_btn = ttk.Button(bar, text="Open CSV…")
    open_btn.pack(side="left")
    export_btn = ttk.Button(bar, text="Export JSON…", state="disabled")
    export_btn.pack(side="left", padx=(6, 0))
    save_plot_btn = ttk.Button(bar, text="Save plot…", state="disabled")
    if have_mpl:
        save_plot_btn.pack(side="left", padx=(6, 0))
    path_var = tk.StringVar(value="No file loaded")
    ttk.Label(bar, textvariable=path_var, foreground="grey").pack(
        side="left", padx=12)

    # --- tabs
    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=8, pady=(0, 4))

    summary_tab = ttk.Frame(notebook)
    notebook.add(summary_tab, text="Summary")
    text = ScrolledText(summary_tab, wrap="none", font=("Courier", 11),
                        padx=10, pady=8)
    text.pack(fill="both", expand=True)
    text.insert("1.0", "Open a cleaned THR-04 CSV file to see its summary.")
    text.configure(state="disabled")

    plot_tab = ttk.Frame(notebook)
    notebook.add(plot_tab, text="Plot")
    if have_mpl:
        # Small initial size; the canvas grows to fill the tab.
        fig = Figure(figsize=(6, 4.5), layout="constrained")
        canvas = FigureCanvasTkAgg(fig, master=plot_tab)
        toolbar = NavigationToolbar2Tk(canvas, plot_tab, pack_toolbar=False)
        toolbar.update()
        toolbar.pack(side="bottom", fill="x")
        canvas.get_tk_widget().pack(side="top", fill="both", expand=True)
    else:
        ttk.Label(plot_tab, padding=20,
                  text="Install matplotlib to see plots:  pip install matplotlib"
                  ).pack()

    data_tab = ttk.Frame(notebook)
    notebook.add(data_tab, text="Data")
    tree = ttk.Treeview(data_tab, show="headings")
    vsb = ttk.Scrollbar(data_tab, orient="vertical", command=tree.yview)
    hsb = ttk.Scrollbar(data_tab, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")
    data_tab.rowconfigure(0, weight=1)
    data_tab.columnconfigure(0, weight=1)
    tree.tag_configure("flagged", background="#fff3cd", foreground="black")

    status_var = tk.StringVar(value="Ready")
    ttk.Label(root, textvariable=status_var, relief="sunken", anchor="w",
              padding=(6, 2)).pack(fill="x", side="bottom")

    # --- actions
    def show_text(content):
        text.configure(state="normal")
        text.delete("1.0", "end")
        text.insert("1.0", content)
        text.configure(state="disabled")

    def fill_table(df):
        tree.delete(*tree.get_children())
        cols = list(df.columns)
        tree["columns"] = cols
        for col in cols:
            tree.heading(col, text=col)
            tree.column(col, width=110 if "flag" in col else 80,
                        anchor="w" if "flag" in col or col == "phase" else "e")
        for row in df.itertuples(index=False):
            values = ["" if pd.isna(v) else v for v in row]
            flagged = any(str(getattr(row, f)) != "ok"
                          for f in ("ambient_flag", "sample_flag"))
            tree.insert("", "end", values=values,
                        tags=("flagged",) if flagged else ())

    def load_file(path):
        try:
            df = load(path)
            results = analyse(df)
        except DataError as err:
            messagebox.showerror("Could not load file", str(err))
            status_var.set("Load failed")
            return
        except Exception as err:  # unexpected analysis failure
            messagebox.showerror("Analysis failed", f"{type(err).__name__}: {err}")
            status_var.set("Analysis failed")
            return

        state.update(path=path, df=df, results=results)
        path_var.set(path)
        show_text(format_report(path, results))
        fill_table(df)
        if have_mpl:
            build_figure(df, results, fig)
            canvas.draw()
            save_plot_btn.configure(state="normal")
        export_btn.configure(state="normal")
        status_var.set(f"Loaded {len(df)} rows")

    def on_open():
        path = filedialog.askopenfilename(
            title="Select cleaned CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if path:
            load_file(path)

    def on_export():
        path = filedialog.asksaveasfilename(
            title="Export results", defaultextension=".json",
            filetypes=[("JSON", "*.json")], initialfile="THR04_summary.json")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(state["results"], fh, indent=2, default=float)
            status_var.set(f"Saved {path}")

    def on_save_plot():
        path = filedialog.asksaveasfilename(
            title="Save plot", defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("PDF", "*.pdf"), ("SVG", "*.svg")],
            initialfile="THR04_plot.png")
        if path:
            fig.savefig(path, dpi=150)
            status_var.set(f"Saved {path}")

    open_btn.configure(command=on_open)
    export_btn.configure(command=on_export)
    save_plot_btn.configure(command=on_save_plot)
    root.bind("<Control-o>", lambda e: on_open())

    if initial_path:
        root.after(100, lambda: load_file(initial_path))
    root.mainloop()


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", nargs="?", default=None,
                    help="cleaned CSV file (default: THR04_clean.csv)")
    ap.add_argument("-s", "--section", choices=SECTIONS, action="append",
                    help="show only this section (repeatable)")
    ap.add_argument("--json", action="store_true",
                    help="print the results as JSON instead of a text report")
    ap.add_argument("-g", "--gui", action="store_true",
                    help="open the graphical interface")
    args = ap.parse_args()

    if args.gui:
        run_gui(args.csv)
        return

    path = args.csv or "THR04_clean.csv"
    try:
        df = load(path)
    except DataError as err:
        sys.exit(f"error: {err}")
    results = analyse(df, args.section or SECTIONS)

    if args.json:
        print(json.dumps(results, indent=2, default=float))
    else:
        print(format_report(path, results))


if __name__ == "__main__":
    main()

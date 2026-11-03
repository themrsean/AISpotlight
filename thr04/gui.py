"""Tk graphical interface for the THR-04 summary."""

import json
import sys

import pandas as pd

from .analysis import DataError, analyse, load
from .plot import build_figure
from .report import format_report


def run_gui(initial_path=None):
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
        from tkinter.scrolledtext import ScrolledText
    except ImportError:
        sys.exit("error: tkinter is not available in this Python installation")

    try:
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
        from matplotlib.figure import Figure

        have_mpl = True
    except ImportError:
        have_mpl = False

    try:
        root = tk.Tk()
    except tk.TclError as err:
        sys.exit(f"error: could not open a window ({err}). Is a display available?")
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
    ttk.Label(bar, textvariable=path_var, foreground="grey").pack(side="left", padx=12)

    # --- tabs
    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=8, pady=(0, 4))

    summary_tab = ttk.Frame(notebook)
    notebook.add(summary_tab, text="Summary")
    text = ScrolledText(summary_tab, wrap="none", font=("Courier", 11), padx=10, pady=8)
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
        ttk.Label(
            plot_tab, padding=20, text="Install matplotlib to see plots:  pip install matplotlib"
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
    ttk.Label(root, textvariable=status_var, relief="sunken", anchor="w", padding=(6, 2)).pack(
        fill="x", side="bottom"
    )

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
            tree.column(
                col,
                width=110 if "flag" in col else 80,
                anchor="w" if "flag" in col or col == "phase" else "e",
            )
        for row in df.itertuples(index=False):
            values = ["" if pd.isna(v) else v for v in row]
            flagged = any(str(getattr(row, f)) != "ok" for f in ("ambient_flag", "sample_flag"))
            tree.insert("", "end", values=values, tags=("flagged",) if flagged else ())

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
            title="Select cleaned CSV", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if path:
            load_file(path)

    def on_export():
        path = filedialog.asksaveasfilename(
            title="Export results",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            initialfile="THR04_summary.json",
        )
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(state["results"], fh, indent=2, default=float)
            status_var.set(f"Saved {path}")

    def on_save_plot():
        path = filedialog.asksaveasfilename(
            title="Save plot",
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("PDF", "*.pdf"), ("SVG", "*.svg")],
            initialfile="THR04_plot.png",
        )
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

# app.py
from Neuromatch_IO import EXPERIMENTS, N_PARCELS, N_SUBJECTS
import os
import threading
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from Neuromatch_helper_functions import (
    load_evs,
    load_single_timeseries,
    average_frames
)
from nilearn import datasets, plotting

class WMContrastApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("HCP WM Group Contrast")
        self.geometry("900x650")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Load metadata
        WM_INFO = EXPERIMENTS["WM"]
        HCP_DIR = "./hcp/hcp_task"
        regions = np.load(os.path.join(HCP_DIR, "regions.npy")).T
        region_info = dict(
            name    = regions[0].tolist(),
            network = regions[1].tolist(),
            hemi    = ["Right"] * (N_PARCELS // 2) + ["Left"] * (N_PARCELS // 2)
        )
        self.labels_df = pd.DataFrame(region_info)
        self.WM_INFO    = WM_INFO
        self.HCP_DIR    = HCP_DIR

        # --- UI Widgets ---
        control_frame = ttk.Frame(self)
        control_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)

        # Control condition
        ttk.Label(control_frame, text="Control Condition:")\
            .grid(row=0, column=0, sticky=tk.W)
        self.cond1_cb = ttk.Combobox(
            control_frame, values=self.WM_INFO["cond"], state="readonly"
        )
        self.cond1_cb.current(0)
        self.cond1_cb.grid(row=0, column=1, padx=5)
        self.cond1_cb.bind("<<ComboboxSelected>>", lambda e: self._update_cond2())

        # Experimental condition
        ttk.Label(control_frame, text="Experimental Condition:")\
            .grid(row=0, column=2, sticky=tk.W)
        self.cond2_cb = ttk.Combobox(
            control_frame, values=self._other_conds(), state="readonly"
        )
        self.cond2_cb.current(1 if len(self._other_conds()) > 1 else 0)
        self.cond2_cb.grid(row=0, column=3, padx=5)

        # Hemisphere selector
        ttk.Label(control_frame, text="Hemisphere:")\
            .grid(row=0, column=4, sticky=tk.W)
        self.hemi_cb = ttk.Combobox(
            control_frame, values=["Left", "Right"], state="readonly"
        )
        self.hemi_cb.current(0)
        self.hemi_cb.grid(row=0, column=5, padx=5)

        # Compute, Save, View buttons
        self.compute_btn = ttk.Button(
            control_frame, text="Compute Contrast", command=self._on_compute
        )
        self.compute_btn.grid(row=0, column=6, padx=10)

        self.save_btn = ttk.Button(
            control_frame, text="Save CSV...", command=self._save_csv, state=tk.DISABLED
        )
        self.save_btn.grid(row=0, column=7, padx=10)

        self.brain_btn = ttk.Button(
            control_frame, text="View Surface", command=self._view_surface, state=tk.DISABLED
        )
        self.brain_btn.grid(row=0, column=8, padx=10)

        # Status label
        self.status = ttk.Label(
            self, text="Select conditions and click Compute Contrast"
        )
        self.status.pack(side=tk.TOP, fill=tk.X, padx=10)

        # Plot area
        self.fig, self.ax = plt.subplots(figsize=(8,4))
        self.canvas = None
        self._embed_plot()

    def _other_conds(self):
        c1 = self.cond1_cb.get()
        return [c for c in self.WM_INFO["cond"] if c != c1]

    def _update_cond2(self):
        vals = self._other_conds()
        self.cond2_cb['values'] = vals
        if self.cond2_cb.get() not in vals:
            self.cond2_cb.current(0)

    def _embed_plot(self):
        if self.canvas:
            self.canvas.get_tk_widget().pack_forget()
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.draw()
        self.canvas.get_tk_widget()\
            .pack(side=tk.TOP, fill=tk.BOTH, expand=1)

    def _on_compute(self):
        threading.Thread(target=self._compute_contrast, daemon=True).start()

    def _compute_contrast(self):
        cond1, cond2 = self.cond1_cb.get(), self.cond2_cb.get()
        if cond1 == cond2:
            messagebox.showwarning(
                "Invalid Selection", "Please choose two different conditions."
            )
            return

        # disable until done
        for btn in (self.compute_btn, self.save_btn, self.brain_btn):
            btn.config(state=tk.DISABLED)
        self.status.config(text="Computing…")

        runs = self.WM_INFO['runs']
        all_contrasts = []
        for subj in range(N_SUBJECTS):
            vals = []
            for cond in (cond1, cond2):
                per_run = []
                for run_idx in range(len(runs)):
                    ts  = load_single_timeseries(
                        subj, "WM", run_idx, self.HCP_DIR, remove_mean=True
                    )
                    evs = load_evs(subj, "WM", run_idx, self.HCP_DIR)
                    per_run.append(average_frames(ts, evs, "WM", cond))
                vals.append(np.mean(per_run, axis=0))
            all_contrasts.append(vals[0] - vals[1])
            pct = (subj + 1) / N_SUBJECTS * 100
            self.status.config(text=f"Computing… ({pct:.1f}%)")

        # finalize
        self.group_vec = np.mean(all_contrasts, axis=0)
        contrast_df = pd.DataFrame({"contrast": self.group_vec})
        plot_df = pd.concat([self.labels_df, contrast_df], axis=1)
        self.summary_df = (
            plot_df.groupby(["network","hemi"], as_index=False)["contrast"].mean()
        )

        # bar‐plot
        self.ax.clear()
        nets = self.summary_df["network"].unique()
        x = np.arange(len(nets))
        for offset, hemi in [(-0.2, "Left"), (0.2, "Right")]:
            hemi_df = self.summary_df[self.summary_df["hemi"] == hemi]
            self.ax.bar(x + offset, hemi_df["contrast"], width=0.4, label=hemi)
        self.ax.set_xticks(x)
        self.ax.set_xticklabels(nets, rotation=45, ha="right")
        self.ax.set_ylabel("Mean contrast")
        self.ax.set_title(f"Group contrast: {cond1} – {cond2}")
        self.ax.legend(title="Hemisphere")
        self.fig.tight_layout()
        self._embed_plot()

        # re-enable buttons
        self.status.config(text="Done.")
        self.compute_btn.config(state=tk.NORMAL)
        self.save_btn.config(state=tk.NORMAL)
        self.brain_btn.config(state=tk.NORMAL)

    def _view_surface(self):
        # pick atlas .npz
        fname = filedialog.askopenfilename(
            title="Select atlas .npz", filetypes=[("NumPy .npz","*.npz")]
        )
        if not fname:
            return

        with np.load(fname) as dobj:
            atlas = dict(**dobj)

        hemi = self.hemi_cb.get().lower()  # 'left' or 'right'
        labels_key = f"labels_{hemi[0].upper()}"  # 'labels_L' or 'labels_R'
        surf_contrast = self.group_vec[atlas[labels_key]]

        fs = datasets.fetch_surf_fsaverage()
        surf_map = fs[f'infl_{hemi}']
        plotting.view_surf(
            surf_map, surf_contrast,
            hemi=hemi, cmap='cold_hot',
            vmax=np.max(np.abs(surf_contrast))
        ).open_in_browser()

    def _save_csv(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV files","*.csv")]
        )
        if path:
            self.summary_df.to_csv(path, index=False)
            messagebox.showinfo("Saved", f"Results saved to:\n{path}")

    def _on_close(self):
        self.quit()
        self.destroy()


if __name__ == "__main__":
    app = WMContrastApp()
    app.mainloop()
#!/usr/bin/env python3
"""Create the Task 2/3 figures from the GridLAB-D recorder output."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from gridlab_io import (
    OUTPUT_DIR,
    ROOT,
    load_house_load,
    load_service,
    load_transformer,
    load_water_heater,
)

FIG_DIR = ROOT / "figures"
ANALYSIS_DIR = OUTPUT_DIR / "analysis"
ZIP_CASES = ["constant_power", "constant_current", "constant_impedance", "mixed"]
SIM_START = pd.Timestamp("2025-09-01 00:00:00")
SIM_END = SIM_START + pd.Timedelta(days=1)


def _time_axis(ax: plt.Axes) -> None:
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=3))
    ax.grid(True, alpha=0.25)
    ax.set_xlim(SIM_START, SIM_END)


def _load(case: str, rating: float):
    return {
        "transformer": load_transformer(case, rating),
        "services": [load_service(case, rating, index) for index in (1, 2, 3)],
        "loads": [load_house_load(case, rating, index) for index in (1, 2, 3)],
        "wh": [load_water_heater(case, rating, index) for index in (1, 2, 3)],
    }


def plot_demand_components(case: str, rating: float) -> Path:
    data = _load(case, rating)
    transformer = data["transformer"]
    t = transformer["timestamp"]
    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True)

    for index, frame in enumerate(data["loads"], start=1):
        axes[0].plot(t, frame["measured_power"].to_numpy().real / 1000.0,
                     label=f"House {index} household load")
    axes[0].set_ylabel("Household real power (kW)")
    axes[0].set_title(f"Household demand excluding water heating ({case}, {rating:g} kVA)")
    axes[0].legend(loc="upper left", ncol=3, fontsize=8)

    for index, frame in enumerate(data["wh"], start=1):
        axes[1].plot(t, frame["actual_load_kw"], label=f"Water heater {index}")
    axes[1].set_ylabel("Water-heater real power (kW)")
    axes[1].set_title("Explicit electric water-heater demand")
    axes[1].legend(loc="upper left", ncol=3, fontsize=8)

    for index, frame in enumerate(data["services"], start=1):
        axes[2].plot(t, frame["measured_power"].to_numpy().real / 1000.0,
                     label=f"Service {index} combined")
    axes[2].plot(t, transformer["power_in"].to_numpy().real / 1000.0,
                 color="black", linewidth=1.8, label="Transformer input")
    axes[2].set_ylabel("Real power (kW)")
    axes[2].set_xlabel("Time of day (PDT)")
    axes[2].set_title("Combined service demand and transformer input")
    axes[2].legend(loc="upper left", ncol=4, fontsize=8)

    for ax in axes:
        _time_axis(ax)
    fig.tight_layout()
    path = FIG_DIR / f"demand_components_{case}.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return path


def plot_source_service_balance(case: str, rating: float) -> Path:
    data = _load(case, rating)
    transformer = data["transformer"]
    t = transformer["timestamp"]
    p_in = transformer["power_in"].to_numpy().real / 1000.0
    p_services = sum(frame["measured_power"].to_numpy().real for frame in data["services"]) / 1000.0

    fig, axes = plt.subplots(2, 1, figsize=(11, 6.5), sharex=True)
    axes[0].plot(t, p_in, label="Transformer primary input", linewidth=1.8)
    axes[0].plot(t, p_services, label="Sum of three service meters", linewidth=1.5)
    axes[0].set_ylabel("Real power (kW)")
    axes[0].set_title(f"Source-to-service real-power comparison ({case}, {rating:g} kVA)")
    axes[0].legend(loc="upper left")
    axes[0].grid(True, alpha=0.25)

    axes[1].plot(t, p_in - p_services, color="tab:red", label="Difference (losses)")
    axes[1].set_ylabel("Real-power difference (kW)")
    axes[1].set_xlabel("Time of day (PDT)")
    axes[1].legend(loc="upper left")
    axes[1].grid(True, alpha=0.25)

    _time_axis(axes[0])
    _time_axis(axes[1])
    fig.tight_layout()
    path = FIG_DIR / f"source_service_balance_{case}.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return path


def plot_water_heaters(case: str, rating: float) -> Path:
    data = _load(case, rating)
    fig, axes = plt.subplots(3, 2, figsize=(12, 9), sharex=True)
    for index, (wh, row) in enumerate(zip(data["wh"], axes), start=1):
        t = wh["timestamp"]
        power_ax = row[0]
        temp_ax = row[1]

        power_ax.plot(t, wh["actual_load_kw"], color="tab:blue", label="Electrical power")
        power_ax.set_ylabel("Power (kW)")
        power_ax.set_title(f"Water heater {index}: power and draw")
        power_ax.grid(True, alpha=0.25)

        draw_ax = power_ax.twinx()
        draw_ax.plot(t, wh["water_demand_gpm"], color="tab:orange", alpha=0.7, label="Water draw")
        draw_ax.set_ylabel("Water draw (gpm)")
        power_ax.legend(loc="upper left", fontsize=8)
        draw_ax.legend(loc="upper right", fontsize=8)

        temp_ax.plot(t, wh["temperature_degF"], color="tab:red")
        temp_ax.set_ylabel("Tank temperature (degF)")
        temp_ax.set_title(f"Water heater {index}: temperature")
        temp_ax.grid(True, alpha=0.25)
        temp_ax.set_ylim(115, 125)

    for ax in axes.ravel():
        _time_axis(ax)
    fig.suptitle(f"Water-heater response ({case}, {rating:g} kVA)", y=1.01)
    fig.tight_layout()
    path = FIG_DIR / f"water_heaters_{case}.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_zip_comparison() -> Path | None:
    path = ANALYSIS_DIR / "zip_comparison.csv"
    if not path.exists():
        return None
    table = pd.read_csv(path)
    order = {name: index for index, name in enumerate(ZIP_CASES)}
    table = table.sort_values("case", key=lambda series: series.map(order))
    labels = [case.replace("_", "\n") for case in table["case"]]

    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2))
    axes[0].bar(labels, table["peak_transformer_kva"], color="tab:blue")
    axes[0].set_ylabel("Peak coincident apparent power (kVA)")
    axes[0].set_title("Transformer-input peak")

    axes[1].bar(labels, table["min_voltage_pu"], color="tab:green")
    axes[1].axhline(0.95, color="red", linestyle="--", linewidth=1, label="0.95 p.u. limit")
    axes[1].set_ylim(0.94, 1.0)
    axes[1].set_ylabel("Minimum service voltage (p.u.)")
    axes[1].set_title("Minimum line-to-neutral voltage")
    axes[1].legend(fontsize=8)

    axes[2].bar(labels, table["transformer_energy_kwh"], color="tab:orange")
    axes[2].set_ylabel("Transformer-input energy (kWh/day)")
    axes[2].set_title("Daily energy")

    for ax in axes:
        ax.grid(True, axis="y", alpha=0.25)
    fig.suptitle("ZIP comparison at the selected transformer rating", y=1.02)
    fig.tight_layout()
    out = FIG_DIR / "zip_comparison.png"
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_candidates() -> list[Path]:
    path = ANALYSIS_DIR / "candidate_comparison.csv"
    if not path.exists():
        return []
    table = pd.read_csv(path)
    outputs = []

    fig, ax = plt.subplots(figsize=(8, 4.8))
    for case in ZIP_CASES:
        subset = table[table["case"] == case].sort_values("xfmr_kva")
        ax.plot(subset["xfmr_kva"], subset["peak_loading_pct"], marker="o", label=case)
    ax.axhline(100.0, color="red", linestyle="--", linewidth=1, label="100% nameplate")
    ax.set_xlabel("Transformer rating (kVA)")
    ax.set_ylabel("Peak transformer-input loading (% of nameplate)")
    ax.set_title("Candidate loading comparison")
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=8)
    fig.tight_layout()
    out = FIG_DIR / "candidate_loading.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    outputs.append(out)

    fig, ax = plt.subplots(figsize=(8, 4.8))
    for case in ZIP_CASES:
        subset = table[table["case"] == case].sort_values("xfmr_kva")
        ax.plot(subset["xfmr_kva"], subset["min_voltage_pu"], marker="o", label=case)
    ax.axhline(0.95, color="red", linestyle="--", linewidth=1, label="0.95 p.u. limit")
    ax.set_xlabel("Transformer rating (kVA)")
    ax.set_ylabel("Minimum service voltage (p.u.)")
    ax.set_title("Candidate minimum service-voltage comparison")
    ax.set_ylim(0.94, 1.0)
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=8)
    fig.tight_layout()
    out = FIG_DIR / "candidate_voltage.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)
    outputs.append(out)
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="constant_power",
                        choices=ZIP_CASES)
    parser.add_argument("--xfmr", type=float, default=25.0)
    args = parser.parse_args()

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    written = [
        plot_demand_components(args.case, args.xfmr),
        plot_source_service_balance(args.case, args.xfmr),
        plot_water_heaters(args.case, args.xfmr),
    ]
    zip_plot = plot_zip_comparison()
    if zip_plot:
        written.append(zip_plot)
    written.extend(plot_candidates())

    for path in written:
        print(f"Wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

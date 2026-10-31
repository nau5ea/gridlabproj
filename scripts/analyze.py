#!/usr/bin/env python3
"""Compute the Task 2/3 metrics from the GridLAB-D recorder output.

Outputs
-------
outputs/analysis/case_metrics.csv
outputs/analysis/candidate_comparison.csv
outputs/analysis/zip_comparison.csv
outputs/analysis/recommendation.json
outputs/analysis/summary_<case>_xfmr<rating>kva.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from gridlab_io import (
    OUTPUT_DIR,
    ROOT,
    load_house_load,
    load_service,
    load_transformer,
    load_water_heater,
    output_prefix,
)

ANALYSIS_DIR = OUTPUT_DIR / "analysis"
ZIP_CASES = ["constant_power", "constant_current", "constant_impedance", "mixed"]
DEFAULT_CANDIDATES = [10.0, 15.0, 25.0, 37.5]
NOMINAL_LEG_VOLTAGE = 120.0
V_MIN_PU = 0.95
V_MAX_PU = 1.05
LOADING_LIMIT_PCT = 100.0


def _first_time(mask: pd.Series, timestamps: pd.Series) -> str | None:
    positions = np.flatnonzero(mask.to_numpy())
    return timestamps.iloc[positions[0]].isoformat(sep=" ") if len(positions) else None


def case_metrics(case: str, xfmr_kva: float) -> dict:
    transformer = load_transformer(case, xfmr_kva)
    services = [load_service(case, xfmr_kva, index) for index in (1, 2, 3)]
    house_loads = [load_house_load(case, xfmr_kva, index) for index in (1, 2, 3)]
    water_heaters = [load_water_heater(case, xfmr_kva, index) for index in (1, 2, 3)]

    s_in = transformer["power_in"].to_numpy()
    p_in = s_in.real
    s_in_mag = np.abs(s_in)
    rating_va = xfmr_kva * 1000.0

    peak_index = int(np.argmax(s_in_mag))
    peak_time = transformer.loc[peak_index, "timestamp"].isoformat(sep=" ")
    peak_loading_pct = float(100.0 * s_in_mag[peak_index] / rating_va)

    overload_mask = pd.Series(s_in_mag > rating_va, index=transformer.index)
    overload_minutes = int(overload_mask.sum())

    # Service voltages are recorded leg-to-neutral; the 120 V leg is the base.
    v1 = np.concatenate([np.abs(frame["voltage_1"].to_numpy()) for frame in services])
    v2 = np.concatenate([np.abs(frame["voltage_2"].to_numpy()) for frame in services])
    v_all = np.concatenate([v1, v2])
    v_min = float(v_all.min())
    v_max = float(v_all.max())
    v_min_pu = v_min / NOMINAL_LEG_VOLTAGE
    v_max_pu = v_max / NOMINAL_LEG_VOLTAGE

    # Line-to-line magnitudes are reported for information.  For a center-tapped
    # secondary the two leg-to-neutral magnitudes add (the legs are opposite
    # polarity).  The pass/fail check uses the 120 V line-to-neutral values above.
    v_ll = np.concatenate([
        np.abs(frame["voltage_1"].to_numpy()) + np.abs(frame["voltage_2"].to_numpy())
        for frame in services
    ])
    v_ll_min = float(v_ll.min())
    v_ll_max = float(v_ll.max())

    transformer_current = np.maximum.reduce([
        np.abs(transformer["current_in_A"].to_numpy()),
        np.abs(transformer["current_in_B"].to_numpy()),
        np.abs(transformer["current_in_C"].to_numpy()),
    ])

    # Voltage violation across all three service meters and both legs.
    voltage_bad = []
    for frame in services:
        voltage_bad.append(
            (frame["voltage_1"].abs() < V_MIN_PU * NOMINAL_LEG_VOLTAGE)
            | (frame["voltage_1"].abs() > V_MAX_PU * NOMINAL_LEG_VOLTAGE)
            | (frame["voltage_2"].abs() < V_MIN_PU * NOMINAL_LEG_VOLTAGE)
            | (frame["voltage_2"].abs() > V_MAX_PU * NOMINAL_LEG_VOLTAGE)
        )
    voltage_bad_any = pd.concat(voltage_bad, axis=1).any(axis=1)
    first_voltage_violation = _first_time(voltage_bad_any, transformer["timestamp"])

    service_p = sum(frame["measured_power"].to_numpy().real for frame in services)
    service_s = np.sqrt(
        sum(frame["measured_power"].to_numpy().real for frame in services) ** 2
        + sum(frame["measured_power"].to_numpy().imag for frame in services) ** 2
    )
    loss_p = p_in - service_p

    energy_kwh = float(p_in.sum() / 60.0 / 1000.0)
    service_energy_kwh = float(service_p.sum() / 60.0 / 1000.0)
    loss_energy_kwh = energy_kwh - service_energy_kwh

    house_metrics = []
    for index, (service, frame, wh) in enumerate(zip(services, house_loads, water_heaters), start=1):
        house_s = frame["measured_power"].to_numpy()
        service_p_house = service["measured_power"].to_numpy().real
        wh_p_w = wh["actual_load_kw"].to_numpy() * 1000.0
        component_p = house_s.real + wh_p_w
        component_diff = service_p_house - component_p
        wh_energy = float(wh["actual_load_kw"].sum() / 60.0)
        house_metrics.append(
            {
                "house": index,
                "peak_house_kw": float(house_s.real.max() / 1000.0),
                "peak_house_kva": float(np.abs(house_s).max() / 1000.0),
                "daily_house_energy_kwh": float(house_s.real.sum() / 60.0 / 1000.0),
                "wh_peak_kw": float(wh["actual_load_kw"].max()),
                "wh_daily_energy_kwh": wh_energy,
                "wh_on_minutes": int(wh["is_on"].sum()),
                "wh_min_temperature_degF": float(wh["temperature_degF"].min()),
                "wh_max_temperature_degF": float(wh["temperature_degF"].max()),
                "wh_water_gal": float(wh["water_demand_gpm"].sum()),
                "service_minus_load_wh_max_w": float(np.max(np.abs(component_diff))),
                "service_minus_load_wh_energy_kwh": float(component_diff.sum() / 60.0 / 1000.0),
                "service_peak_current_a": float(max(
                    np.abs(service["current_1"].to_numpy()).max(),
                    np.abs(service["current_2"].to_numpy()).max(),
                )),
            }
        )

    peak_service_kw = max(item["peak_house_kw"] for item in house_metrics)
    peak_service_kva = max(item["peak_house_kva"] for item in house_metrics)

    if overload_minutes > 0:
        limiting_condition = f"loading: first exceedance {_first_time(overload_mask, transformer['timestamp'])}"
    elif first_voltage_violation is not None:
        limiting_condition = f"voltage: first violation {first_voltage_violation}"
    else:
        limiting_condition = "none"

    passed = (
        peak_loading_pct <= LOADING_LIMIT_PCT
        and v_min_pu >= V_MIN_PU
        and v_max_pu <= V_MAX_PU
        and overload_minutes == 0
    )

    return {
        "case": case,
        "xfmr_kva": xfmr_kva,
        "prefix": output_prefix(case, xfmr_kva),
        "peak_loading_pct": peak_loading_pct,
        "peak_transformer_kva": float(s_in_mag[peak_index] / 1000.0),
        "peak_transformer_kw": float(p_in[peak_index] / 1000.0),
        "peak_time": peak_time,
        "min_voltage_v": v_min,
        "min_voltage_pu": v_min_pu,
        "max_voltage_v": v_max,
        "max_voltage_pu": v_max_pu,
        "min_voltage_ll_v": v_ll_min,
        "max_voltage_ll_v": v_ll_max,
        "min_voltage_ll_pu": v_ll_min / (2.0 * NOMINAL_LEG_VOLTAGE),
        "max_voltage_ll_pu": v_ll_max / (2.0 * NOMINAL_LEG_VOLTAGE),
        "transformer_peak_current_a": float(transformer_current.max()),
        "overload_minutes": overload_minutes,
        "first_overload": _first_time(overload_mask, transformer["timestamp"]),
        "first_voltage_violation": first_voltage_violation,
        "pass": bool(passed),
        "limiting_condition": limiting_condition,
        "transformer_energy_kwh": energy_kwh,
        "service_energy_kwh": service_energy_kwh,
        "loss_energy_kwh": loss_energy_kwh,
        "max_source_service_difference_kw": float(loss_p.max() / 1000.0),
        "mean_source_service_difference_kw": float(loss_p.mean() / 1000.0),
        "peak_service_kw": peak_service_kw,
        "peak_service_kva": peak_service_kva,
        "peak_coincident_service_kva": float(np.max(service_s) / 1000.0),
        "houses": house_metrics,
    }


def candidate_comparison(records: list[dict]) -> pd.DataFrame:
    rows = []
    for record in records:
        metrics = case_metrics(record["case"], float(record["xfmr_kva"]))
        rows.append(
            {
                "xfmr_kva": metrics["xfmr_kva"],
                "case": metrics["case"],
                "peak_loading_pct": round(metrics["peak_loading_pct"], 3),
                "peak_transformer_kva": round(metrics["peak_transformer_kva"], 3),
                "peak_time": metrics["peak_time"],
                "min_voltage_v": round(metrics["min_voltage_v"], 3),
                "min_voltage_pu": round(metrics["min_voltage_pu"], 5),
                "max_voltage_pu": round(metrics["max_voltage_pu"], 5),
                "min_voltage_ll_pu": round(metrics["min_voltage_ll_pu"], 5),
                "max_voltage_ll_pu": round(metrics["max_voltage_ll_pu"], 5),
                "transformer_peak_current_a": round(metrics["transformer_peak_current_a"], 2),
                "overload_minutes": metrics["overload_minutes"],
                "first_overload": metrics["first_overload"],
                "first_voltage_violation": metrics["first_voltage_violation"],
                "pass": metrics["pass"],
                "limiting_condition": metrics["limiting_condition"],
                "transformer_energy_kwh": round(metrics["transformer_energy_kwh"], 3),
                "service_energy_kwh": round(metrics["service_energy_kwh"], 3),
                "loss_energy_kwh": round(metrics["loss_energy_kwh"], 4),
            }
        )
    return pd.DataFrame(rows).sort_values(["xfmr_kva", "case"]).reset_index(drop=True)


def recommendation(comparison: pd.DataFrame) -> dict:
    by_rating = comparison.groupby("xfmr_kva")["pass"].all().sort_index()
    passing = [float(rating) for rating, ok in by_rating.items() if ok]
    recommended = min(passing) if passing else None
    next_smaller = None
    if recommended is not None:
        smaller = [float(rating) for rating in by_rating.index if float(rating) < recommended]
        next_smaller = max(smaller) if smaller else None

    limiting = None
    if next_smaller is not None:
        subset = comparison[
            (comparison["xfmr_kva"] == next_smaller) & (~comparison["pass"])
        ].copy()
        if len(subset):
            # Report the earliest limiting event among the failing cases, not
            # merely the alphabetically first case.
            event_time = pd.to_datetime(
                subset["first_overload"].fillna(subset["first_voltage_violation"]),
                errors="coerce",
            )
            subset["_event_time"] = event_time
            row = subset.sort_values("_event_time", na_position="last").iloc[0]
            limiting = {
                "xfmr_kva": float(row["xfmr_kva"]),
                "case": row["case"],
                "condition": row["limiting_condition"],
                "peak_loading_pct": float(row["peak_loading_pct"]),
                "min_voltage_pu": float(row["min_voltage_pu"]),
            }

    return {
        "recommended_xfmr_kva": recommended,
        "next_smaller_xfmr_kva": next_smaller,
        "next_smaller_first_limiting_condition": limiting,
        "candidates_tested_kva": [float(rating) for rating in by_rating.index],
        "candidates_passing_all_cases_kva": passing,
        "criteria": {
            "loading_limit_pct": LOADING_LIMIT_PCT,
            "voltage_min_pu": V_MIN_PU,
            "voltage_max_pu": V_MAX_PU,
            "interval": "one minute per recorder sample",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xfmr", type=float, default=25.0,
                        help="Rating used for the ZIP comparison table (default: 25).")
    args = parser.parse_args()

    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    runs_path = OUTPUT_DIR / "runs.csv"
    if runs_path.exists():
        runs = pd.read_csv(runs_path)
        runs = runs[runs["exit_code"] == 0]
        records = runs[["case", "xfmr_kva"]].drop_duplicates().to_dict("records")
    else:
        records = [{"case": case, "xfmr_kva": rating}
                   for rating in DEFAULT_CANDIDATES for case in ZIP_CASES]

    if not records:
        raise SystemExit("No successful runs found.  Run scripts/run_cases.py first.")

    comparison = candidate_comparison(records)
    comparison.to_csv(ANALYSIS_DIR / "candidate_comparison.csv", index=False)

    # Full metrics for every run (including house-level details).
    metrics_rows = []
    for record in records:
        metrics = case_metrics(record["case"], float(record["xfmr_kva"]))
        metrics_rows.append(metrics)
        summary_path = ANALYSIS_DIR / f"summary_{output_prefix(metrics['case'], metrics['xfmr_kva'])}.json"
        summary_path.write_text(json.dumps(metrics, indent=2) + "\n")
    (ANALYSIS_DIR / "case_metrics.csv").write_text(
        pd.json_normalize(metrics_rows, "houses", ["case", "xfmr_kva"]).to_csv(index=False)
    )

    zip_rows = comparison[comparison["xfmr_kva"] == args.xfmr].copy()
    if zip_rows.empty:
        available = sorted(comparison["xfmr_kva"].unique())
        raise SystemExit(
            f"No {args.xfmr:g} kVA runs found for the ZIP table.  "
            f"Available ratings: {available}"
        )
    zip_rows = zip_rows.sort_values(
        "case", key=lambda series: series.map({name: i for i, name in enumerate(ZIP_CASES)})
    )
    zip_rows.to_csv(ANALYSIS_DIR / "zip_comparison.csv", index=False)

    result = recommendation(comparison)
    (ANALYSIS_DIR / "recommendation.json").write_text(json.dumps(result, indent=2) + "\n")

    print("\nZIP comparison at", f"{args.xfmr:g} kVA")
    print(zip_rows[[
        "case", "peak_transformer_kva", "peak_loading_pct",
        "min_voltage_pu", "max_voltage_pu", "transformer_energy_kwh"
    ]].to_string(index=False))

    print("\nCandidate comparison")
    print(comparison[[
        "xfmr_kva", "case", "peak_loading_pct", "min_voltage_pu",
        "overload_minutes", "pass", "limiting_condition"
    ]].to_string(index=False))

    print("\nRecommendation")
    print(json.dumps(result, indent=2))
    print(f"\nWrote analysis files to {ANALYSIS_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

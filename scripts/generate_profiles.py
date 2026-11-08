#!/usr/bin/env python3
"""Generate deterministic placeholder household-demand and water-draw profiles.

This is a fallback for environments without the supplied datasets.  The normal
workflow is ``scripts/prepare_real_profiles.py``, which selects three real
``data/input/house_profile_*.csv`` files.  Because this script overwrites the
player files, it refuses to run when real profiles are present unless
``--force`` is passed.

Replace ``data/input/*.csv`` with the supplied datasets and re-run the real
preparation script for the actual study.

Units
-----
household demand : kW, nominal real power excluding water heating
water draw       : gal/min (gpm), hot-water draw entering the water heater

GridLAB-D ``triplex_load`` base powers are *apparent* power in VA.  With a
common 0.95 lagging power factor the conversion used here is

    base_power_phase = (demand_kw * 1000 / 2) / 0.95

for a balanced split between the two 120 V legs.  The player files therefore
contain VA, not kW.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = ROOT / "data" / "input"
PLAYER_DIR = ROOT / "data" / "players"

# One common simulated day.  Change these two values together with glm/model.glm.
START = pd.Timestamp("2025-09-01 00:00:00")
PERIODS = 24 * 60 + 1  # inclusive 00:00 through 24:00
POWER_FACTOR = 0.95
RANDOM_SEED = 530

HOUSES = {
    "house1": dict(
        base_kw=0.35,
        morning_kw=1.9,
        evening_kw=2.6,
        morning_center=7.2,
        evening_center=19.0,
        event_count=10,
        event_scale=1.0,
        water_scale=1.0,
    ),
    "house2": dict(
        base_kw=0.45,
        morning_kw=1.3,
        evening_kw=3.1,
        morning_center=6.7,
        evening_center=20.0,
        event_count=12,
        event_scale=1.15,
        water_scale=1.1,
    ),
    "house3": dict(
        base_kw=0.30,
        morning_kw=2.2,
        evening_kw=1.9,
        morning_center=7.8,
        evening_center=18.2,
        event_count=8,
        event_scale=0.9,
        water_scale=0.9,
    ),
}


def _smooth_pulses(
    rng: np.random.Generator,
    t_hours: np.ndarray,
    count: int,
    amplitude_range: tuple[float, float],
    duration_range: tuple[float, float],
) -> np.ndarray:
    """Return a sum of rectangular/smoothed appliance events."""
    signal = np.zeros_like(t_hours)
    for _ in range(count):
        start = rng.uniform(0.0, 24.0)
        duration = rng.uniform(*duration_range)
        amplitude = rng.uniform(*amplitude_range)
        # 2-minute raised-cosine edges keep the one-minute player data smooth.
        edge = 2.0 / 60.0
        left = np.clip((t_hours - start) / edge, 0.0, 1.0)
        right = np.clip((start + duration - t_hours) / edge, 0.0, 1.0)
        signal += amplitude * 0.5 * (1.0 - np.cos(np.pi * np.minimum(left, right)))
    return signal


def demand_profile(name: str, cfg: dict, rng: np.random.Generator) -> pd.Series:
    t = np.linspace(0.0, 24.0, PERIODS)
    base = cfg["base_kw"] * (1.0 + 0.08 * np.sin(2 * np.pi * (t - 1.0) / 24.0))
    morning = cfg["morning_kw"] * np.exp(-0.5 * ((t - cfg["morning_center"]) / 0.85) ** 2)
    evening = cfg["evening_kw"] * np.exp(-0.5 * ((t - cfg["evening_center"]) / 1.65) ** 2)
    events = _smooth_pulses(
        rng,
        t,
        count=cfg["event_count"],
        amplitude_range=(0.25 * cfg["event_scale"], 1.6 * cfg["event_scale"]),
        duration_range=(5.0 / 60.0, 45.0 / 60.0),
    )
    load = np.maximum(0.05, base + morning + evening + events)
    return pd.Series(load, index=pd.date_range(START, periods=PERIODS, freq="1min"), name=name)


def water_profile(name: str, cfg: dict, rng: np.random.Generator) -> pd.Series:
    t = np.linspace(0.0, 24.0, PERIODS)
    draws = np.zeros_like(t)
    name_id = sum(ord(character) for character in name)

    def add_draw(center: float, duration: float, gpm: float) -> None:
        edge = 0.5 / 60.0
        left = np.clip((t - (center - duration / 2.0)) / edge, 0.0, 1.0)
        right = np.clip(((center + duration / 2.0) - t) / edge, 0.0, 1.0)
        draws[:] += gpm * np.minimum(left, right)

    # Morning shower and evening household draws, different for each house.
    add_draw(6.8 + 0.25 * (name_id % 3), rng.uniform(7.0, 11.0) / 60.0, 1.9 * cfg["water_scale"])
    add_draw(19.2 + 0.3 * (name_id % 2), rng.uniform(5.0, 9.0) / 60.0, 1.5 * cfg["water_scale"])
    for _ in range(5):
        add_draw(
            rng.uniform(7.0, 22.0),
            rng.uniform(1.0, 4.0) / 60.0,
            rng.uniform(0.5, 1.2) * cfg["water_scale"],
        )

    # A small continuous draw keeps the tank from sitting perfectly idle.
    draws += 0.003 * (1.0 + np.sin(2 * np.pi * t / 12.0))
    return pd.Series(draws, index=pd.date_range(START, periods=PERIODS, freq="1min"), name=name)


def write_player_load(path: Path, demand_kw: pd.Series) -> None:
    values_va = demand_kw.to_numpy() * 1000.0 / 2.0 / POWER_FACTOR
    lines = ["# timestamp,base_power_1_VA,base_power_2_VA"]
    for ts, value in zip(demand_kw.index, values_va):
        lines.append(f"{ts:%Y-%m-%d %H:%M:%S},{value:.6f},{value:.6f}")
    path.write_text("\n".join(lines) + "\n")


def write_player_water(path: Path, water_gpm: pd.Series) -> None:
    lines = ["# timestamp,water_demand_gpm"]
    for ts, value in zip(water_gpm.index, water_gpm.to_numpy()):
        lines.append(f"{ts:%Y-%m-%d %H:%M:%S},{value:.6f}")
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite players even when real house_profile_*.csv files are present.",
    )
    args = parser.parse_args()

    if any(INPUT_DIR.glob("house_profile_*.csv")) and not args.force:
        raise SystemExit(
            "Real house profiles are present in data/input.  Use "
            "scripts/prepare_real_profiles.py for the real study, or pass "
            "--force to overwrite the players with synthetic placeholders."
        )

    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    PLAYER_DIR.mkdir(parents=True, exist_ok=True)

    metadata = {
        "seed": args.seed,
        "start": str(START),
        "periods": PERIODS,
        "power_factor": POWER_FACTOR,
        "note": "Synthetic placeholders; replace data/input with the course datasets.",
        "houses": {},
    }

    for index, (name, cfg) in enumerate(HOUSES.items(), start=1):
        rng = np.random.default_rng(args.seed + index)
        demand = demand_profile(name, cfg, rng)
        water = water_profile(name, cfg, rng)

        demand_frame = pd.DataFrame({"timestamp": demand.index, "demand_kw": demand.to_numpy()})
        water_frame = pd.DataFrame({"timestamp": water.index, "water_gpm": water.to_numpy()})
        demand_frame.to_csv(INPUT_DIR / f"{name}_demand.csv", index=False, float_format="%.6f")
        water_frame.to_csv(INPUT_DIR / f"{name}_water.csv", index=False, float_format="%.6f")

        write_player_load(PLAYER_DIR / f"{name}_load.player", demand)
        write_player_water(PLAYER_DIR / f"{name}_water.player", water)

        metadata["houses"][name] = {
            "peak_demand_kw": round(float(demand.max()), 4),
            "daily_energy_kwh": round(float(demand.sum() / 60.0), 4),
            "peak_water_gpm": round(float(water.max()), 4),
            # One row per minute, so sum(gpm) is gallons for the day.
            "daily_water_gal": round(float(water.sum()), 4),
        }

    (ROOT / "data" / "profiles_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Wrote profiles for {len(HOUSES)} houses to {INPUT_DIR} and {PLAYER_DIR}")


if __name__ == "__main__":
    main()

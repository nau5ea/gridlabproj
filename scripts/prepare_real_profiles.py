#!/usr/bin/env python3
"""Prepare GridLAB-D players from the supplied household demand profiles.

The course package provides a pool of one-minute household demand profiles in
``data/input/house_profile_<id>.csv``.  The project model has three houses, so
this script selects three profiles (the first three available IDs by default),
validates them, and writes the GridLAB-D player files used by ``glm/model.glm``.

Units and conversions
---------------------
household demand : kW, nominal real power excluding water heating
water draw       : gal/min (gpm), hot-water draw entering the water heater

``triplex_load`` base powers are apparent power in VA.  With a common 0.95
lagging power factor the conversion is

    base_power_leg = (demand_kw * 1000 / 2) / 0.95

for a balanced split between the two 120 V legs.

Water draw is read from ``data/input/water_draw.csv`` (a two-column,
minute-by-minute gpm profile).  Duplicate timestamps are summed because they
represent simultaneous draw events.  Only one water-draw file is supplied for
the three-house model; by default the same profile is applied to each water
heater (``--water-mode shared``).  Use ``--water-mode split`` to treat the file
as an aggregate three-house draw and divide it equally among the services.  If
the file is absent, the script falls back to deterministic synthetic draws
(seed 530) and records that fallback in ``data/selected_profiles.json``.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = ROOT / "data" / "input"
SELECTED_DIR = ROOT / "data" / "selected"
PLAYER_DIR = ROOT / "data" / "players"

# The supplied profiles all cover this day.  Keep this in sync with glm/model.glm.
DEFAULT_START = pd.Timestamp("2025-09-01 00:00:00")
PERIODS = 24 * 60 + 1  # inclusive 00:00 through 24:00
POWER_FACTOR = 0.95
RANDOM_SEED = 530
DEFAULT_HOUSE_IDS = (1, 2, 3)
DEFAULT_WATER_FILE = INPUT_DIR / "water_draw.csv"

# Water-heater draw scale per service for the synthetic fallback.
WATER_SCALES = (1.0, 1.1, 0.9)


def available_house_ids(directory: Path) -> list[int]:
    ids = []
    for path in directory.glob("house_profile_*.csv"):
        match = re.fullmatch(r"house_profile_(\d+)\.csv", path.name)
        if match:
            ids.append(int(match.group(1)))
    return sorted(ids)


def read_house_profile(path: Path, start: pd.Timestamp) -> pd.Series:
    """Read and validate one supplied household demand profile."""
    frame = pd.read_csv(path)
    time_column = next(
        (column for column in frame.columns if column.strip().lower() in {"time", "timestamp"}),
        None,
    )
    power_columns = [
        column for column in frame.columns
        if column != time_column and "power" in column.lower()
    ]
    if time_column is None or len(power_columns) != 1:
        raise ValueError(
            f"{path.name}: expected one time column and one house-power column; "
            f"found {list(frame.columns)}"
        )

    timestamps = pd.to_datetime(frame[time_column], errors="raise")
    values = pd.to_numeric(frame[power_columns[0]], errors="raise")
    series = pd.Series(values.to_numpy(), index=timestamps, name=path.stem)

    if len(series) != 1440:
        raise ValueError(f"{path.name}: expected 1440 minute samples, found {len(series)}")
    if series.index.has_duplicates:
        raise ValueError(f"{path.name}: duplicate timestamps")
    if not series.index.is_monotonic_increasing:
        raise ValueError(f"{path.name}: timestamps are not strictly increasing")
    expected = pd.date_range(start, periods=1440, freq="1min")
    if not series.index.equals(expected):
        raise ValueError(
            f"{path.name}: expected {expected[0]} through {expected[-1]}, "
            f"found {series.index[0]} through {series.index[-1]}"
        )
    if series.isna().any():
        raise ValueError(f"{path.name}: missing demand values")
    if (series < 0).any():
        raise ValueError(f"{path.name}: negative demand values")
    return series


def read_water_draw(path: Path, start: pd.Timestamp) -> tuple[pd.Series, int]:
    """Read, validate, and de-duplicate a minute-by-minute water-draw file.

    The supplied file has no header and two columns: timestamp and gpm.
    Duplicate timestamps are summed: they represent simultaneous draw events
    (for example two fixtures in the same minute).
    """
    frame = pd.read_csv(path, header=None, names=["timestamp", "water_gpm"])
    # Tolerate a header row if one is present.
    if not pd.api.types.is_datetime64_any_dtype(frame["timestamp"]):
        first = pd.to_datetime(frame["timestamp"].iloc[0], errors="coerce")
        if pd.isna(first):
            frame = pd.read_csv(path)
            time_column = next(
                (column for column in frame.columns
                 if column.strip().lower() in {"time", "timestamp"}),
                None,
            )
            water_columns = [
                column for column in frame.columns
                if column != time_column
                and ("water" in column.lower() or "gpm" in column.lower())
            ]
            if time_column is None or len(water_columns) != 1:
                raise ValueError(
                    f"{path.name}: expected one time column and one water-gpm column; "
                    f"found {list(frame.columns)}"
                )
            frame = frame.rename(columns={time_column: "timestamp",
                                          water_columns[0]: "water_gpm"})

    timestamps = pd.to_datetime(frame["timestamp"], errors="raise")
    values = pd.to_numeric(frame["water_gpm"], errors="raise")
    if values.isna().any():
        raise ValueError(f"{path.name}: missing water-draw values")
    if (values < 0).any():
        raise ValueError(f"{path.name}: negative water-draw values")

    series = pd.Series(values.to_numpy(), index=timestamps, name="water_gpm")
    duplicate_count = int(series.index.duplicated().sum())
    if duplicate_count:
        series = series.groupby(level=0).sum()

    expected = pd.date_range(start, periods=1440, freq="1min")
    missing = expected.difference(series.index)
    extra = series.index.difference(expected)
    if len(missing) or len(extra):
        raise ValueError(
            f"{path.name}: expected the full minute grid {expected[0]} through "
            f"{expected[-1]}; missing={len(missing)} extra={len(extra)}"
        )
    series = series.reindex(expected)
    return series, duplicate_count


def water_profile(index: int, start: pd.Timestamp, seed: int) -> pd.Series:
    """Create a deterministic synthetic water draw for one service."""
    rng = np.random.default_rng(seed + index)
    t = np.linspace(0.0, 24.0, PERIODS)
    scale = WATER_SCALES[index - 1]
    draws = np.zeros_like(t)

    def add_draw(center: float, duration: float, gpm: float) -> None:
        edge = 0.5 / 60.0
        left = np.clip((t - (center - duration / 2.0)) / edge, 0.0, 1.0)
        right = np.clip(((center + duration / 2.0) - t) / edge, 0.0, 1.0)
        draws[:] += gpm * np.minimum(left, right)

    # Morning shower and evening household draws, plus shorter daytime draws.
    add_draw(6.8 + 0.25 * (index % 3), rng.uniform(7.0, 11.0) / 60.0, 1.9 * scale)
    add_draw(19.2 + 0.3 * (index % 2), rng.uniform(5.0, 9.0) / 60.0, 1.5 * scale)
    for _ in range(5):
        add_draw(
            rng.uniform(7.0, 22.0),
            rng.uniform(1.0, 4.0) / 60.0,
            rng.uniform(0.5, 1.2) * scale,
        )
    # A small continuous draw keeps the tank from sitting perfectly idle.
    draws += 0.003 * (1.0 + np.sin(2 * np.pi * t / 12.0))
    return pd.Series(draws, index=pd.date_range(start, periods=PERIODS, freq="1min"))


def write_player_load(path: Path, demand_kw: pd.Series) -> None:
    values_va = demand_kw.to_numpy() * 1000.0 / 2.0 / POWER_FACTOR
    lines = ["# timestamp,base_power_1_VA,base_power_2_VA"]
    for timestamp, value in zip(demand_kw.index, values_va):
        lines.append(f"{timestamp:%Y-%m-%d %H:%M:%S},{value:.6f},{value:.6f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_player_water(path: Path, water_gpm: pd.Series) -> None:
    lines = ["# timestamp,water_demand_gpm"]
    for timestamp, value in zip(water_gpm.index, water_gpm.to_numpy()):
        lines.append(f"{timestamp:%Y-%m-%d %H:%M:%S},{value:.6f}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--house-ids",
        default=",".join(str(value) for value in DEFAULT_HOUSE_IDS),
        help="Comma-separated profile IDs from data/input (default: 1,2,3).",
    )
    parser.add_argument(
        "--start",
        default=DEFAULT_START.strftime("%Y-%m-%d %H:%M:%S"),
        help="Simulation start timestamp (default: 2025-09-01 00:00:00).",
    )
    parser.add_argument("--seed", type=int, default=RANDOM_SEED,
                        help="Seed for the synthetic water-draw fallback (default: 530).")
    parser.add_argument(
        "--water-file",
        default=str(DEFAULT_WATER_FILE),
        help="Water-draw CSV (default: data/input/water_draw.csv).",
    )
    parser.add_argument(
        "--water-mode",
        choices=("shared", "split"),
        default="shared",
        help=(
            "shared: apply the supplied profile to every water heater; "
            "split: treat it as an aggregate three-house draw and divide equally "
            "(default: shared)."
        ),
    )
    args = parser.parse_args()

    start = pd.Timestamp(args.start)
    if start != DEFAULT_START:
        raise SystemExit(
            f"This model clock is fixed to {DEFAULT_START}; got --start {start}."
        )

    ids = [int(value) for value in args.house_ids.split(",") if value.strip()]
    if len(ids) != 3:
        raise SystemExit("Exactly three house profiles are required by the three-house model.")
    available = set(available_house_ids(INPUT_DIR))
    missing = [house_id for house_id in ids if house_id not in available]
    if missing:
        raise SystemExit(f"Missing house profile IDs in {INPUT_DIR}: {missing}")

    SELECTED_DIR.mkdir(parents=True, exist_ok=True)
    PLAYER_DIR.mkdir(parents=True, exist_ok=True)

    water_path = Path(args.water_file)
    if not water_path.is_absolute():
        water_path = ROOT / water_path
    duplicate_count = 0
    if water_path.exists():
        water_base, duplicate_count = read_water_draw(water_path, start)
        if args.water_mode == "split":
            water_base = water_base / 3.0
        water_source = str(water_path.relative_to(ROOT))
        water_note = (
            "supplied water_draw.csv; duplicate timestamps summed; "
            + ("same profile applied to all three water heaters"
               if args.water_mode == "shared"
               else "aggregate profile divided equally among the three water heaters")
        )
    else:
        water_base = None
        water_source = (
            "synthetic fallback: no water-draw file found; "
            f"deterministic draws seed {args.seed}"
        )
        water_note = water_source
        print(f"WARNING: {water_path} not found; using synthetic water draws.")

    metadata = {
        "selection_rule": (
            "first three available house_profile_<id>.csv files in data/input"
        ),
        "selected_house_ids": ids,
        "source_dir": "data/input",
        "simulation_start": str(start),
        "periods": PERIODS,
        "power_factor": POWER_FACTOR,
        "conversion": "base_power_1 = base_power_2 = demand_kw*1000/2/0.95 VA",
        "water_source": water_source,
        "water_assignment": water_note,
        "water_mode": args.water_mode if water_base is not None else "synthetic",
        "water_duplicate_timestamps_summed": duplicate_count,
        "water_total_gal": (
            round(float(water_base.sum()), 6) if water_base is not None else None
        ),
        "houses": {},
    }

    if water_base is not None:
        print(
            f"water draw: {water_source}  mode={args.water_mode}  "
            f"total={water_base.sum():.3f} gal/day  "
            f"peak={water_base.max():.3f} gpm  "
            f"duplicates summed={duplicate_count}"
        )

    for service, house_id in enumerate(ids, start=1):
        source = INPUT_DIR / f"house_profile_{house_id}.csv"
        demand = read_house_profile(source, start)
        # The supplied files end at 23:59.  Add the closing 24:00 sample so the
        # player covers the full simulated day.
        demand = pd.concat([
            demand,
            pd.Series([demand.iloc[-1]], index=[start + pd.Timedelta(days=1)]),
        ])

        if water_base is None:
            water = water_profile(service, start, args.seed)
        else:
            water = pd.concat([
                water_base,
                pd.Series([0.0], index=[start + pd.Timedelta(days=1)]),
            ])

        # Keep a normalized copy of the selected inputs alongside the players.
        pd.DataFrame({
            "timestamp": demand.index,
            "demand_kw": demand.to_numpy(),
        }).to_csv(SELECTED_DIR / f"house{service}_demand.csv", index=False,
                  float_format="%.9f")
        pd.DataFrame({
            "timestamp": water.index,
            "water_gpm": water.to_numpy(),
        }).to_csv(SELECTED_DIR / f"house{service}_water.csv", index=False,
                  float_format="%.9f")

        write_player_load(PLAYER_DIR / f"house{service}_load.player", demand)
        write_player_water(PLAYER_DIR / f"house{service}_water.player", water)

        metadata["houses"][f"house{service}"] = {
            "source_file": str(source.relative_to(ROOT)),
            "peak_demand_kw": round(float(demand.max()), 6),
            "daily_energy_kwh": round(float(demand.iloc[:-1].sum() / 60.0), 6),
            "minimum_demand_kw": round(float(demand.min()), 6),
            "peak_water_gpm": round(float(water.max()), 6),
            "daily_water_gal": round(float(water.iloc[:-1].sum()), 6),
        }
        print(
            f"house{service}: {source.name}  peak={demand.max():.3f} kW  "
            f"energy={demand.iloc[:-1].sum() / 60.0:.3f} kWh/day"
        )

    (ROOT / "data" / "selected_profiles.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote selected CSVs to {SELECTED_DIR.relative_to(ROOT)}")
    print(f"Wrote player files to {PLAYER_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

"""Small readers for the GridLAB-D recorder files used in this project.

GridLAB-D writes CSV comments (``# ...``) followed by data rows.  Complex
values may appear in either rectangular (``+1.2-3.4j``) or polar
(``+1.2-45.6d``) form, so both are handled here.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "outputs"

_COMPLEX_RECT = re.compile(
    r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
    r"([+-](?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)$"
)


def parse_complex(value) -> complex:
    """Parse GridLAB-D rectangular or polar complex text."""
    if isinstance(value, complex):
        return value
    if isinstance(value, (int, float, np.number)):
        return complex(float(value), 0.0)
    text = str(value).strip()
    if text.endswith("j"):
        match = _COMPLEX_RECT.match(text[:-1])
        if match:
            return complex(float(match.group(1)), float(match.group(2)))
    elif text.endswith("d"):
        match = _COMPLEX_RECT.match(text[:-1])
        if match:
            magnitude = float(match.group(1))
            angle = np.deg2rad(float(match.group(2)))
            return complex(magnitude * np.cos(angle), magnitude * np.sin(angle))
    return complex(float(text), 0.0)


def complex_series(series: pd.Series) -> np.ndarray:
    return np.array([parse_complex(value) for value in series], dtype=complex)


def output_prefix(case: str, xfmr_kva: float) -> str:
    return f"{case}_xfmr{xfmr_kva:g}kva"


def recorder_path(case: str, xfmr_kva: float, suffix: str) -> Path:
    return OUTPUT_DIR / f"{output_prefix(case, xfmr_kva)}_{suffix}.csv"


def read_recorder(path: Path, columns: dict[int, tuple[str, str]]) -> pd.DataFrame:
    """Read a recorder CSV and name selected columns.

    ``columns`` maps CSV column index -> (new name, kind), where kind is
    ``"complex"``, ``"float"``, or ``"int"``.
    """
    if not path.exists():
        raise FileNotFoundError(path)
    raw = pd.read_csv(path, comment="#", header=None)
    timestamps = pd.to_datetime(
        raw[0].astype(str).str.replace(r"\s+[A-Z]{2,4}$", "", regex=True),
        errors="raise",
    )
    frame = pd.DataFrame({"timestamp": timestamps})
    for index, (name, kind) in columns.items():
        if kind == "complex":
            frame[name] = complex_series(raw[index])
        elif kind == "int":
            frame[name] = pd.to_numeric(raw[index]).astype(int)
        else:
            frame[name] = pd.to_numeric(raw[index])
    return frame


def load_transformer(case: str, xfmr_kva: float) -> pd.DataFrame:
    return read_recorder(
        recorder_path(case, xfmr_kva, "transformer"),
        {
            1: ("power_in", "complex"),
            2: ("power_out", "complex"),
            3: ("current_in_A", "complex"),
            4: ("current_in_B", "complex"),
            5: ("current_in_C", "complex"),
        },
    )


def load_service(case: str, xfmr_kva: float, index: int) -> pd.DataFrame:
    return read_recorder(
        recorder_path(case, xfmr_kva, f"service{index}"),
        {
            1: ("measured_power", "complex"),
            2: ("voltage_1", "complex"),
            3: ("voltage_2", "complex"),
            4: ("current_1", "complex"),
            5: ("current_2", "complex"),
        },
    )


def load_house_load(case: str, xfmr_kva: float, index: int) -> pd.DataFrame:
    return read_recorder(
        recorder_path(case, xfmr_kva, f"house{index}_load"),
        {1: ("measured_power", "complex")},
    )


def load_water_heater(case: str, xfmr_kva: float, index: int) -> pd.DataFrame:
    return read_recorder(
        recorder_path(case, xfmr_kva, f"wh{index}"),
        {
            1: ("actual_load_kw", "float"),
            2: ("temperature_degF", "float"),
            3: ("water_demand_gpm", "float"),
            4: ("is_on", "int"),
        },
    )

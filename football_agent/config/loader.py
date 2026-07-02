from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
import yaml

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PACKAGE_ROOT / "config"


def load_yaml(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    if not p.is_absolute():
        p = CONFIG_DIR / p
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config {p} moet een dictionary bevatten.")
    return data


def load_competitions() -> Dict[str, Any]:
    return load_yaml("competitions.yml")


def load_bookmaker_profiles() -> Dict[str, Any]:
    return load_yaml("bookmaker_profiles.yml")


def load_model_settings() -> Dict[str, Any]:
    return load_yaml("model_settings.yml")

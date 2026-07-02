from __future__ import annotations

import csv
import json
import math
import os
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

FEATURE_COLUMNS = {
    "elo_adjustment": "selected_attr_elo",
    "xg_form_adjustment": "selected_attr_xg",
    "poisson_adjustment": "selected_attr_poisson",
    "injury_impact": "selected_attr_injury",
    "fatigue_impact": "selected_attr_fatigue",
    "motivation_impact": "selected_attr_motivation",
    "calibration_adjustment": "selected_attr_calibration",
}


def _f(row: Dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, "") or default)
    except ValueError:
        return default


def _actual_hit(row: Dict[str, str]) -> int | None:
    actual = (row.get("actual") or row.get("actual_result") or "").upper()
    sel = (row.get("selection") or "").upper()
    if not actual or not sel:
        return None
    return 1 if actual == sel else 0


def _binary_log_loss(p: float, y: int) -> float:
    p = min(1 - 1e-12, max(1e-12, p))
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def train_weights(rows: Iterable[Dict[str, str]], min_rows: int = 100) -> Dict:
    """Conservative candidate weight tuner.

    V25.0.5 does not overwrite production weights by default. It creates candidate
    weights and a validation report. Promotion should only happen after enough
    samples and measurable improvement versus the existing weights.
    """
    buckets: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in rows:
        if (row.get("status") or "") != "VALUE_PICK":
            continue
        if _actual_hit(row) is None:
            continue
        comp = row.get("competition_key") or "global"
        buckets[comp].append(row)

    out = {"version": "v25.0.5-candidate-conservative", "global": {}, "competitions": {}, "samples": {}}
    for comp, comp_rows in buckets.items():
        out["samples"][comp] = len(comp_rows)
        if len(comp_rows) < min_rows:
            continue
        comp_weights: Dict[str, float] = {}
        for feature, col in FEATURE_COLUMNS.items():
            xs = [_f(r, col) for r in comp_rows]
            ys = [_actual_hit(r) or 0 for r in comp_rows]
            pos = [x for x, y in zip(xs, ys) if y == 1]
            neg = [x for x, y in zip(xs, ys) if y == 0]
            if not pos or not neg:
                continue
            diff = (sum(pos) / len(pos)) - (sum(neg) / len(neg))
            multiplier = 1.0 + max(-0.20, min(0.20, diff * 2.5))
            comp_weights[feature] = round(max(0.80, min(1.20, multiplier)), 4)
        if comp_weights:
            out["competitions"][comp] = comp_weights
    return out


def _current_probability(row: Dict[str, str]) -> float:
    return _f(row, "model_probability") or _f(row, "selected_model_probability") or _f(row, "model_prob")


def _candidate_probability(row: Dict[str, str], candidate: Dict) -> float:
    p = _current_probability(row)
    comp = row.get("competition_key") or "global"
    weights = candidate.get("competitions", {}).get(comp, {}) or {}
    if not weights:
        return p
    # Approximate candidate effect for the selected side using logged feature attribution.
    delta = 0.0
    for feature, col in FEATURE_COLUMNS.items():
        val = _f(row, col)
        multiplier = float(weights.get(feature, 1.0))
        delta += val * (multiplier - 1.0)
    return min(0.999, max(0.001, p + delta))


def validate_candidate(rows: Iterable[Dict[str, str]], candidate: Dict, min_rows: int = 100, min_improvement: float = 0.0025) -> Dict:
    usable = [r for r in rows if (r.get("status") or "") == "VALUE_PICK" and _actual_hit(r) is not None and _current_probability(r) > 0]
    if len(usable) < min_rows:
        return {
            "usable_rows": len(usable),
            "production_log_loss": None,
            "candidate_log_loss": None,
            "improvement": 0.0,
            "promotion_recommended": False,
            "reason": f"Te weinig data voor veilige promotie: {len(usable)} < {min_rows}.",
        }
    prod_losses = []
    cand_losses = []
    for row in usable:
        y = _actual_hit(row) or 0
        prod_losses.append(_binary_log_loss(_current_probability(row), y))
        cand_losses.append(_binary_log_loss(_candidate_probability(row, candidate), y))
    production = sum(prod_losses) / len(prod_losses)
    candidate_loss = sum(cand_losses) / len(cand_losses)
    improvement = production - candidate_loss
    return {
        "usable_rows": len(usable),
        "production_log_loss": production,
        "candidate_log_loss": candidate_loss,
        "improvement": improvement,
        "promotion_recommended": bool(improvement >= min_improvement),
        "reason": "Candidate verbetert log-loss voldoende." if improvement >= min_improvement else "Candidate verbetert log-loss onvoldoende; niet promoveren.",
    }


def main() -> None:
    input_path = Path(os.getenv("TRAINING_LOG", "output/prediction_log.csv"))
    candidate_path = Path(os.getenv("CANDIDATE_WEIGHTS_OUTPUT", "output/candidate_learned_model_weights.json"))
    report_path = Path(os.getenv("WEIGHT_TRAINING_REPORT", "output/weight_training_report.json"))
    promote = os.getenv("PROMOTE_WEIGHTS", "false").lower() in {"1", "true", "yes", "ja"}
    production_path = Path(os.getenv("PRODUCTION_WEIGHTS_OUTPUT", "football_agent/config/learned_model_weights.json"))
    min_rows = int(os.getenv("MIN_TRAINING_ROWS", "100"))
    if not input_path.exists():
        print(f"Geen trainingslog gevonden: {input_path}")
        return
    with input_path.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    candidate = train_weights(rows, min_rows=min_rows)
    validation = validate_candidate(rows, candidate, min_rows=min_rows)
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.write_text(json.dumps(candidate, indent=2), encoding="utf-8")
    report_path.write_text(json.dumps({"candidate": candidate, "validation": validation}, indent=2), encoding="utf-8")
    if promote and validation.get("promotion_recommended"):
        production_path.parent.mkdir(parents=True, exist_ok=True)
        production_path.write_text(json.dumps(candidate, indent=2), encoding="utf-8")
        print(f"Candidate gepromoveerd naar {production_path}")
    else:
        print(f"Candidate weights geschreven naar {candidate_path}")
        print(f"Validatierapport geschreven naar {report_path}")
        print(json.dumps(validation, indent=2))


if __name__ == "__main__":
    main()

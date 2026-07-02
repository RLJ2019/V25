from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from football_agent.evaluation.roi import settle_pick, roi
from football_agent.evaluation.closing_line_value import clv_decimal
from football_agent.evaluation.calibration_buckets import summarize as summarize_buckets


REQUIRED_COLUMNS = {"competition_key", "selection", "actual", "odds", "model_probability"}


def _float(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_dt(value: str):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _read_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def validate_backtest_integrity(rows: List[Dict[str, str]]) -> Tuple[List[Dict[str, str]], List[str]]:
    valid = []
    warnings: List[str] = []
    for i, row in enumerate(rows, start=2):
        kickoff = _parse_dt(row.get("kickoff_utc", ""))
        prediction_time = _parse_dt(row.get("prediction_time_utc", "") or row.get("created_at_utc", ""))
        odds_ts = _parse_dt(row.get("odds_timestamp_utc", "") or row.get("odds_timestamp", ""))
        if kickoff and prediction_time and prediction_time > kickoff:
            warnings.append(f"Rij {i}: prediction_time na aftrap; uitgesloten tegen lookahead bias.")
            continue
        if kickoff and odds_ts and odds_ts > kickoff:
            warnings.append(f"Rij {i}: odds_timestamp na aftrap; uitgesloten tegen lookahead bias.")
            continue
        if row.get("result_known_before_prediction", "").lower() in {"1", "true", "yes", "ja"}:
            warnings.append(f"Rij {i}: resultaat lijkt vooraf bekend; uitgesloten.")
            continue
        valid.append(row)
    return valid, warnings


def evaluate_rows(rows: List[Dict[str, str]]) -> Dict[str, float | int]:
    if not rows:
        return {"rows": 0, "picks": 0, "roi": 0.0, "avg_brier": 0.0, "avg_log_loss": 0.0, "avg_clv": 0.0, "positive_clv_rate": 0.0}
    picks = [r for r in rows if (r.get("status") or "VALUE_PICK") in {"VALUE_PICK", "PICK", "value_pick"}]
    if not picks:
        picks = rows
    returns = []
    stakes = []
    briers = []
    losses = []
    clvs = []
    for r in picks:
        selection = r.get("selection", "")
        actual = r.get("actual", "")
        odds = _float(r.get("odds", ""), 0.0)
        p = _float(r.get("model_probability") or r.get("selected_model_probability") or r.get("model_prob"), 0.0)
        stake = _float(r.get("stake_units", ""), 1.0) or 1.0
        if odds > 1:
            returns.append(settle_pick(selection, actual, odds, stake))
            stakes.append(stake)
        if p > 0 and actual:
            y = 1 if selection == actual else 0
            briers.append((p - y) ** 2)
            import math
            p_clip = min(1 - 1e-12, max(1e-12, p))
            losses.append(-(y * math.log(p_clip) + (1 - y) * math.log(1 - p_clip)))
        closing = _float(r.get("closing_odds", ""), 0.0)
        if odds > 1 and closing > 1:
            clvs.append(clv_decimal(odds, closing))
    return {
        "rows": len(rows),
        "picks": len(picks),
        "roi": roi(returns, stakes) if stakes else 0.0,
        "avg_brier": sum(briers) / len(briers) if briers else 0.0,
        "avg_log_loss": sum(losses) / len(losses) if losses else 0.0,
        "avg_clv": sum(clvs) / len(clvs) if clvs else 0.0,
        "positive_clv_rate": sum(1 for c in clvs if c > 0) / len(clvs) if clvs else 0.0,
    }


def _group_by(rows: List[Dict[str, str]], key: str) -> Dict[str, List[Dict[str, str]]]:
    out: Dict[str, List[Dict[str, str]]] = {}
    for r in rows:
        out.setdefault(r.get(key) or "UNKNOWN", []).append(r)
    return out


def main():
    out = Path(os.getenv("LOCAL_OUTPUT_DIR", "output"))
    out.mkdir(exist_ok=True)
    input_path = Path(os.getenv("BACKTEST_INPUT", str(out / "historical_predictions.csv")))
    rows = _read_rows(input_path)
    report_path = out / "backtest_report.txt"
    if not rows:
        report_path.write_text(
            "Geen historische backtestdata gevonden.\n"
            f"Verwacht CSV-bestand: {input_path}\n\n"
            "Minimale kolommen: competition_key, selection, actual, odds, model_probability.\n"
            "Sterk aanbevolen tegen lookahead bias: prediction_time_utc, kickoff_utc, odds_timestamp_utc, closing_odds, market.\n"
            "Gebruik alleen data die vóór aftrap beschikbaar was.\n",
            encoding="utf-8",
        )
        print(report_path.read_text(encoding="utf-8"))
        return
    missing = REQUIRED_COLUMNS - set(rows[0].keys())
    if missing:
        raise SystemExit(f"Backtest-input mist kolommen: {sorted(missing)}")
    valid_rows, warnings = validate_backtest_integrity(rows)
    metrics = evaluate_rows(valid_rows)
    buckets = summarize_buckets([{
        "competition_key": r.get("competition_key", ""),
        "selection": r.get("selection", ""),
        "actual": r.get("actual", ""),
        "model_probability": r.get("model_probability", "0"),
    } for r in valid_rows])
    text = [
        "V25.0.5 Backtest Report",
        "=========================" ,
        f"Input: {input_path}",
        f"Rows input: {len(rows)}",
        f"Rows valid after integrity filter: {metrics['rows']}",
        f"Integrity warnings: {len(warnings)}",
        f"Picks evaluated: {metrics['picks']}",
        f"ROI: {metrics['roi']:.2%}",
        f"Average Brier: {metrics['avg_brier']:.4f}",
        f"Average Log-loss: {metrics['avg_log_loss']:.4f}",
        f"Average CLV: {metrics['avg_clv']:.2%}",
        f"Positive CLV rate: {metrics['positive_clv_rate']:.2%}",
        "",
        "Market-specific performance:",
    ]
    for market, group in sorted(_group_by(valid_rows, "market").items()):
        m = evaluate_rows(group)
        text.append(f"- {market}: picks={m['picks']} ROI={m['roi']:.2%} Brier={m['avg_brier']:.4f} LogLoss={m['avg_log_loss']:.4f} CLV={m['avg_clv']:.2%}")
    text.append("")
    text.append("Calibration buckets:")
    for bucket, data in sorted(buckets.items()):
        text.append(f"- {bucket}: n={data['count']} hit_rate={data['hit_rate']:.2%}")
    if warnings:
        text.append("")
        text.append("Integrity warnings / uitgesloten rijen:")
        for w in warnings[:50]:
            text.append(f"- {w}")
    report_path.write_text("\n".join(text) + "\n", encoding="utf-8")
    print(report_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()

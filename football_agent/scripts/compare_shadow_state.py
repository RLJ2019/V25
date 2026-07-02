from __future__ import annotations

import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from football_agent.database.connection import DatabaseSettings, SupabaseRestClient
from football_agent.database.repository import DatabaseRepository, pick_identity_from_values

NUMERIC_TOLERANCE = 0.0001
NUMERIC_FIELD_MAP = {
    "entry_odds": "odds",
    "model_probability": None,  # expanded below from local model_HOME/DRAW/AWAY by selected side
    "market_probability": None,  # expanded below from local market_HOME/DRAW/AWAY by selected side
    "expected_value": "expected_value",
    "probability_edge": "probability_edge",
    "stake_units": "stake_units",
}


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "ja"}


def _row_completeness(row: Dict[str, str]) -> int:
    """Score a local CSV row so duplicate identities keep the richest row.

    prediction_log.csv is append-only and restored from GitHub cache. The same
    future proposition can appear in multiple daily runs. For shadow parity, the
    current proposition identity is unique, so we compare the newest/most complete
    row rather than failing solely because an append-only CSV contains historical
    duplicates.
    """
    important_fields = [
        "selected_model_probability",
        "selected_market_probability",
        "model_home",
        "model_draw",
        "model_away",
        "market_home",
        "market_draw",
        "market_away",
        "odds",
        "expected_value",
        "probability_edge",
        "stake_units",
    ]
    return sum(1 for field in important_fields if str(row.get(field, "")).strip() not in {"", "None", "null"})


def _is_at_or_after(value: str, since_utc: str) -> bool:
    if not since_utc:
        return True
    text = str(value or "").strip()
    if not text:
        return False
    return text >= since_utc


def _local_pick_identities(path: Path, since_utc: str = "") -> tuple[list[str], Dict[str, Dict[str, str]]]:
    if not path.exists():
        return [], {}
    identities: list[str] = []
    rows_by_identity: Dict[str, Dict[str, str]] = {}
    with path.open("r", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            created_at = str(row.get("created_at_utc", ""))
            if since_utc and not _is_at_or_after(created_at, since_utc):
                continue
            identity = pick_identity_from_values(
                row.get("fixture_id", ""),
                row.get("market", "1X2"),
                row.get("selection", "NONE"),
                row.get("model_version", "unknown"),
            )
            identities.append(identity)
            previous = rows_by_identity.get(identity)
            if previous is None:
                rows_by_identity[identity] = row
                continue
            previous_key = (str(previous.get("created_at_utc", "")), _row_completeness(previous))
            current_key = (created_at, _row_completeness(row))
            if current_key >= previous_key:
                rows_by_identity[identity] = row
    return identities, rows_by_identity


def _local_state(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    result: Dict[str, Dict[str, Any]] = {}
    for item in payload.get("picks", {}).values():
        fixture_id = str(item.get("fixture_id", ""))
        selection = str(item.get("selection") or "NONE")
        # V25.0.9 local keys do not persist the market separately. The signature does.
        signature = str(item.get("signature", ""))
        parts = signature.split("|")
        market = parts[2] if len(parts) > 2 and parts[2] else "1X2"
        result[f"{fixture_id}|{market}|{selection}"] = item
    return result


def _state_key_from_identity(identity_key: str) -> Optional[str]:
    parts = str(identity_key or "").split("|")
    if len(parts) < 3:
        return None
    fixture_id, market, selection = parts[0], parts[1] or "1X2", parts[2] or "NONE"
    if not fixture_id:
        return None
    return f"{fixture_id}|{market}|{selection}"


def _state_keys_from_identities(identities: Iterable[str]) -> set[str]:
    keys = set()
    for identity in identities:
        key = _state_key_from_identity(identity)
        if key:
            keys.add(key)
    return keys


def _filter_state_to_eligible_keys(
    state: Dict[str, Dict[str, Any]],
    eligible_state_keys: set[str],
) -> Dict[str, Dict[str, Any]]:
    """Keep notification state rows only for picks in the current compare window.

    GitHub cache keeps notification_state.json across runs. When
    SHADOW_COMPARE_SINCE_UTC is moved forward, the current compare window can
    legitimately contain zero eligible picks. In that case notification state
    must also compare as an empty set. Otherwise old/orphan notification-state
    rows from cached output can fail a clean compare even though there are no
    current local/database pick identities to validate.
    """
    if not eligible_state_keys:
        return {}
    return {key: value for key, value in state.items() if key in eligible_state_keys}


def _filter_database_picks_by_since(database_picks: list[dict[str, Any]], since_utc: str) -> list[dict[str, Any]]:
    if not since_utc:
        return database_picks
    filtered = []
    for row in database_picks:
        timestamp = str(row.get("last_seen_at") or row.get("original_created_at") or "")
        if _is_at_or_after(timestamp, since_utc):
            filtered.append(row)
    return filtered


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text == "":
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _selection_suffix(selection: str) -> Optional[str]:
    selection = (selection or "").upper()
    return {"HOME": "home", "DRAW": "draw", "AWAY": "away"}.get(selection)


def _local_numeric_value(local_row: Dict[str, str], db_field: str) -> Optional[float]:
    if db_field == "model_probability":
        selected_value = _to_float(local_row.get("selected_model_probability"))
        if selected_value is not None:
            return selected_value
        suffix = _selection_suffix(local_row.get("selection", ""))
        return _to_float(local_row.get(f"model_{suffix}")) if suffix else None
    if db_field == "market_probability":
        selected_value = _to_float(local_row.get("selected_market_probability"))
        if selected_value is not None:
            return selected_value
        suffix = _selection_suffix(local_row.get("selection", ""))
        return _to_float(local_row.get(f"market_{suffix}")) if suffix else None
    local_field = NUMERIC_FIELD_MAP.get(db_field)
    if not local_field:
        return None
    return _to_float(local_row.get(local_field))


def _is_no_bet_probability_null_zero_equivalent(
    local_row: Dict[str, str],
    db_field: str,
    local_value: Optional[float],
    db_value: Optional[float],
) -> bool:
    """Treat local empty NO_BET probabilities and database 0.0 as equivalent.

    Local CSV output can keep model/market probability fields empty for NO_BET
    rows where there is no active market/selection. The database layer stores
    the same non-selection state as 0.0. That is a serialization difference,
    not a shadow parity error.
    """
    if db_field not in {"model_probability", "market_probability"}:
        return False

    selection = str(local_row.get("selection") or "").strip().upper()
    market = str(local_row.get("market") or "").strip().upper()
    no_active_selection_or_market = selection in {"", "NONE"} or market in {"", "NONE"}
    if not no_active_selection_or_market:
        return False

    values = {local_value, db_value}
    return values == {None, 0.0}


def _numeric_mismatches(
    local_rows_by_identity: Dict[str, Dict[str, str]],
    database_rows_by_identity: Dict[str, Dict[str, Any]],
    *,
    tolerance: float = NUMERIC_TOLERANCE,
) -> List[Dict[str, Any]]:
    mismatches: List[Dict[str, Any]] = []
    for identity in sorted(set(local_rows_by_identity) & set(database_rows_by_identity)):
        local_row = local_rows_by_identity[identity]
        db_row = database_rows_by_identity[identity]
        for db_field in NUMERIC_FIELD_MAP:
            local_value = _local_numeric_value(local_row, db_field)
            db_value = _to_float(db_row.get(db_field))
            if local_value is None and db_value is None:
                continue
            if _is_no_bet_probability_null_zero_equivalent(local_row, db_field, local_value, db_value):
                continue
            if local_value is None or db_value is None:
                mismatches.append({
                    "identity_key": identity,
                    "field": db_field,
                    "local": local_value,
                    "database": db_value,
                    "reason": "missing_value",
                })
                continue
            if abs(local_value - db_value) > tolerance:
                mismatches.append({
                    "identity_key": identity,
                    "field": db_field,
                    "local": round(local_value, 8),
                    "database": round(db_value, 8),
                    "difference": round(abs(local_value - db_value), 8),
                    "tolerance": tolerance,
                })
    return mismatches


def _critical_count(report: Dict[str, Any]) -> int:
    critical_lists = [
        "missing_in_database",
        "unexpected_in_database",
        "database_duplicate_identities",
        "state_missing_in_database",
        "state_unexpected_in_database",
        "state_mismatches",
        "numeric_mismatches",
    ]
    return sum(len(report.get(key, []) or []) for key in critical_lists)


def _finish(report_path: Path, report: Dict[str, Any], *, fail_closed: bool) -> None:
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if fail_closed and int(report.get("critical_errors", 0) or 0) > 0:
        print(
            "FATAL: shadow compare fail-closed gate blocked this run; "
            f"critical_errors={report.get('critical_errors')}",
            file=sys.stderr,
        )
        sys.exit(1)


def main() -> None:
    out_dir = Path(os.getenv("LOCAL_OUTPUT_DIR", "output"))
    out_dir.mkdir(parents=True, exist_ok=True)
    settings = DatabaseSettings.from_env()
    report_path = out_dir / "shadow_parity_report.json"
    fail_closed = _env_bool("SHADOW_COMPARE_FAIL_CLOSED", True)

    if not settings.enabled or not settings.configured:
        report = {
            "status": "SKIPPED",
            "reason": "Database disabled or not configured.",
            "settings": settings.safe_summary(),
            "fail_closed": fail_closed,
            "critical_errors": 0,
        }
        _finish(report_path, report, fail_closed=fail_closed)
        return

    repository = DatabaseRepository(SupabaseRestClient(settings))
    try:
        database_picks = repository.fetch_picks()
        database_state = repository.fetch_notification_state()
    except Exception as exc:
        report = {
            "status": "DATABASE_ERROR",
            "error": str(exc),
            "settings": settings.safe_summary(),
            "fail_closed": fail_closed,
            "critical_errors": 1,
        }
        _finish(report_path, report, fail_closed=fail_closed)
        if not settings.fail_open:
            raise
        return

    compare_since_utc = os.getenv("SHADOW_COMPARE_SINCE_UTC", "").strip()
    database_picks = _filter_database_picks_by_since(database_picks, compare_since_utc)
    local_ids, local_rows_by_identity = _local_pick_identities(out_dir / "prediction_log.csv", compare_since_utc)
    local_counter = Counter(local_ids)
    local_unique = set(local_counter)
    database_ids = [str(row.get("identity_key", "")) for row in database_picks if row.get("identity_key")]
    database_counter = Counter(database_ids)
    database_unique = set(database_counter)
    database_rows_by_identity = {
        str(row.get("identity_key", "")): row
        for row in database_picks
        if row.get("identity_key")
    }

    eligible_state_keys = _state_keys_from_identities(local_unique | database_unique)
    local_state_all = _local_state(out_dir / "notification_state.json")
    local_state = _filter_state_to_eligible_keys(local_state_all, eligible_state_keys)
    db_state_all = {
        f"{row.get('fixture_id')}|{row.get('market')}|{row.get('selection')}": row
        for row in database_state
    }
    db_state = _filter_state_to_eligible_keys(db_state_all, eligible_state_keys)
    common_state_keys = set(local_state) & set(db_state)
    state_mismatches = []
    for key in sorted(common_state_keys):
        local = local_state[key]
        remote = db_state[key]
        if local.get("status") != remote.get("status") or local.get("signature") != remote.get("signature"):
            state_mismatches.append({
                "key": key,
                "local_status": local.get("status"),
                "database_status": remote.get("status"),
                "local_signature": local.get("signature"),
                "database_signature": remote.get("signature"),
            })

    missing = sorted(local_unique - database_unique)
    unexpected = sorted(database_unique - local_unique)
    duplicates_local = sorted(key for key, count in local_counter.items() if count > 1)
    duplicates_database = sorted(key for key, count in database_counter.items() if count > 1)
    numeric_mismatches = _numeric_mismatches(local_rows_by_identity, database_rows_by_identity)
    matched = len(local_unique & database_unique)
    denominator = max(1, len(local_unique))
    parity = matched / denominator

    report = {
        "status": "PASS",
        "compare_since_utc": compare_since_utc or None,
        "fail_closed": fail_closed,
        "numeric_tolerance": NUMERIC_TOLERANCE,
        "local_rows": len(local_ids),
        "local_unique_picks": len(local_unique),
        "database_rows": len(database_ids),
        "database_unique_picks": len(database_unique),
        "matched_unique_picks": matched,
        "missing_in_database": missing,
        "unexpected_in_database": unexpected,
        "local_duplicate_identities": duplicates_local,
        "local_duplicate_identities_deduped": duplicates_local,
        "database_duplicate_identities": duplicates_database,
        "eligible_notification_state_keys": len(eligible_state_keys),
        "local_notification_states": len(local_state),
        "local_notification_states_raw": len(local_state_all),
        "database_notification_states": len(db_state),
        "database_notification_states_raw": len(db_state_all),
        "state_missing_in_database": sorted(set(local_state) - set(db_state)),
        "state_unexpected_in_database": sorted(set(db_state) - set(local_state)),
        "state_mismatches": state_mismatches,
        "numeric_mismatches": numeric_mismatches,
        "shadow_parity": round(parity, 6),
        "shadow_parity_percent": round(parity * 100.0, 2),
    }
    report["critical_errors"] = _critical_count(report)
    report["status"] = "PASS" if report["critical_errors"] == 0 else "FAIL"
    _finish(report_path, report, fail_closed=fail_closed)


if __name__ == "__main__":
    main()

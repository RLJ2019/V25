from __future__ import annotations

import os
from typing import Iterable, List
import requests
from football_agent.schemas import PickDecision
from .gemini_explainer import GeminiExplainer


class TelegramReporter:
    def __init__(self, token: str | None = None, chat_id: str | None = None, enabled: bool | None = None):
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.enabled = enabled if enabled is not None else os.getenv("TELEGRAM_ENABLED", "false").lower() in {"1", "true", "yes", "ja"}
        self.live_sheet_url = os.getenv("LIVE_SHEET_URL", "").strip()
        self.explainer = GeminiExplainer()

    def build_daily_message(self, picks: Iterable[PickDecision]) -> str:
        picks = list(picks)
        value = [p for p in picks if p.status == "VALUE_PICK"]
        watch = [p for p in picks if p.status == "WATCHLIST"]
        nobet = [p for p in picks if p.status == "NO_BET"]
        lines: List[str] = [
            "⚽ <b>V25 Multi-League Value Engine</b>",
            "🔕 Dagrapport — stille melding",
            f"🔍 Gescreend: {len(picks)} wedstrijden",
            f"✅ Value Picks: {len(value)}",
            f"👀 Watchlist: {len(watch)}",
            f"⛔ No Bet: {len(nobet)}",
            "",
        ]
        if value:
            lines.append("✅ <b>Actieve Value Picks</b>")
        for p in value[:5]:
            lines.extend(self._compact_pick_lines(p))
        if watch:
            lines.append("👀 <b>Watchlist</b>")
        for p in watch[:5]:
            lines.extend(self._compact_pick_lines(p))
        if not value and not watch:
            lines.append("Geen value picks of watchlist-wedstrijden gevonden. Dat is correct gedrag bij onvoldoende edge/data.")
        if self.live_sheet_url:
            lines.extend(["", f"📄 Live sheet: {self.live_sheet_url}"])
        return "\n".join(lines)[:3900]

    def _compact_pick_lines(self, p: PickDecision) -> List[str]:
        f = p.fixture
        val = p.value_decision
        return [
            "━━━━━━━━━━━━━━━",
            f"🏟️ <b>{f.competition_name}: {f.home_team} vs {f.away_team}</b>",
            f"🔮 {p.status}: {p.advice}",
            f"💰 {val.market if val else '-'} | EV: {val.expected_value:.1%} | Odds: {val.odds or '-'} | Bookmaker: {val.bookmaker or '-'}" if val else "💰 EV: -",
            f"📊 Confidence {p.confidence:.1f}/10 | Data {p.data_quality:.1f}/10 | Onzekerheid {p.uncertainty_score:.1f}/10 | Stake {p.stake_units:.2f}u",
        ]

    def build_value_pick_alert(self, p: PickDecision, alert_type: str = "new_value_pick") -> str:
        f = p.fixture
        val = p.value_decision
        facts = p.explanation_facts
        min_odds = (val.min_acceptable_odds or val.fair_odds) if val else None
        title = {
            "new_value_pick": "🔔 <b>VALUE PICK</b>",
            "upgraded_to_value_pick": "🔔 <b>WATCHLIST → VALUE PICK</b>",
            "value_pick_changed": "🔔 <b>VALUE PICK UPDATE</b>",
        }.get(alert_type, "🔔 <b>VALUE PICK</b>")
        lines = [
            title,
            f"⚽ <b>{f.competition_name}</b>: {f.home_team} vs {f.away_team}",
            f"🎯 <b>Markt</b>: {val.market if val else '-'} | Selectie: {p.selection or '-'}",
            f"📈 <b>Bookmaker / Odds</b>: {(val.bookmaker or '-') if val else '-'} @ {(val.odds or '-') if val else '-'}",
            f"⚖️ <b>Sharp/no-vig fair odds</b>: {val.sharp_fair_odds:.2f} <i>(bron: {val.baseline_source})</i>" if val and val.sharp_fair_odds else "⚖️ <b>Sharp/no-vig fair odds</b>: -",
            f"📉 <b>Min. odds voor value</b>: {min_odds:.2f}" if min_odds else "📉 <b>Min. odds voor value</b>: -",
            f"📊 <b>Edge</b>: {val.expected_value:.1%} | Prob-edge: {val.probability_edge:.1%}" if val else "📊 <b>Edge</b>: -",
            f"💰 <b>Stake</b>: {p.stake_units:.2f} units <i>(1 unit = eigen bankroll-eenheid, geen euroadvies)</i>",
            f"🧠 Confidence: {p.confidence:.1f}/10 | Data: {p.data_quality:.1f}/10 | Onzekerheid: {p.uncertainty_score:.1f}/10",
            f"⏱️ Scan: {p.time_window} | Line-up bevestigd: {'ja' if p.lineup_confirmed else 'nee'}",
        ]
        if not p.lineup_confirmed:
            lines.append("⚠️ Deze pick wordt opnieuw gecontroleerd rond T-55 minuten voor aftrap.")
        if p.stake_reason:
            lines.append(f"🛡️ Stake-logica: {p.stake_reason}")
        lines.append("🧾 Discipline: volg alleen de minimum-odds en unitgrootte; geen chasing bij gemiste odds.")
        lines.extend([
            "",
            "🤖 <b>Waarom?</b>",
            self.explainer.explain(facts),
        ])
        if self.live_sheet_url:
            lines.extend(["", f"📄 Live sheet: {self.live_sheet_url}"])
        return "\n".join(lines)[:3900]

    def build_withdrawal_alert(self, p: PickDecision) -> str:
        f = p.fixture
        lines = [
            "🚨 <b>PICK INGETROKKEN / GEDOWNGRADED</b>",
            f"⚽ {f.competition_name}: {f.home_team} vs {f.away_team}",
            f"Nieuwe status: {p.status}",
            f"Reden: {p.advice}",
            "Actie: niet meer instappen. Heb je nog niet gespeeld: overslaan. Heb je al gespeeld: volg je eigen cash-out/risicobeleid.",
        ]
        return "\n".join(lines)[:3900]

    def build_heartbeat_message(self, picks: Iterable[PickDecision], next_scan: str = "volgende geplande scan") -> str:
        picks = list(picks)
        watch = [p for p in picks if p.status == "WATCHLIST"]
        return "\n".join([
            "🔍 <b>Status Update</b>",
            f"De agent heeft {len(picks)} wedstrijden geanalyseerd.",
            f"Value Picks: 0 | Watchlist: {len(watch)}",
            "De odds zijn momenteel scherp of de data is nog onvoldoende. We pushen pas wanneer de wiskunde aan onze kant staat.",
            f"Volgende check: {next_scan}.",
        ])[:3900]

    def _interval_line(self, p: PickDecision) -> str:
        if p.probability_interval_low is None or p.probability_interval_high is None:
            return "📉 Kansrange: -"
        return f"📉 Kansrange selectie: {p.probability_interval_low:.0%} - {p.probability_interval_high:.0%}"

    def send(self, message: str, *, disable_notification: bool = False) -> bool:
        if not self.enabled:
            prefix = "[Telegram silent]" if disable_notification else "[Telegram loud]"
            print(prefix)
            print(message)
            return False
        if not self.token or not self.chat_id:
            print("Telegram ontbreekt: token/chat_id niet ingesteld.")
            print(message)
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        resp = requests.post(
            url,
            json={
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
                "disable_notification": bool(disable_notification),
            },
            timeout=30,
        )
        resp.raise_for_status()
        return True

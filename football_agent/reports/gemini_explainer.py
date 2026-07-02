from __future__ import annotations

import os
from typing import Dict


class GeminiExplainer:
    def __init__(self, api_key: str | None = None, model_name: str | None = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    def explain(self, facts: Dict) -> str:
        # By design Gemini explains hard model facts; it does not change predictions.
        if not self.api_key:
            return self._fallback_explanation(facts)
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(self.model_name)
            prompt = self._prompt(facts)
            response = model.generate_content(prompt)
            text = getattr(response, "text", None)
            return text.strip() if text else self._fallback_explanation(facts)
        except Exception:
            return self._fallback_explanation(facts)

    def _prompt(self, facts: Dict) -> str:
        return (
            "Je bent alleen rapporteur. Je mag de voorspelling, selectie, odds of stake nooit wijzigen. "
            "Schrijf maximaal 5 korte bullets voor betalende Telegramleden. "
            "Vertaal de modeldata naar begrijpelijke sporttaal. "
            "Gebruik GEEN technische/statistische termen zoals logit, Poisson, Dixon-Coles, overround, Shin, "
            "isotonic regression, decay, bootstrap, Monte Carlo, Brier of CLV. "
            "Focus op sportieve taal: vorm, rust, blessures, opstelling, marktbeweging, odds en risico. "
            "Noem geen garanties en geen eurobedragen. "
            f"Harde modeldata: {facts}"
        )

    def _fallback_explanation(self, facts: Dict) -> str:
        value = facts.get("value", {})
        market_attr = facts.get("market_attribution", {}) or {}
        lines = []
        if market_attr:
            summary = market_attr.get("summary")
            if summary:
                lines.append(summary)
            positive = market_attr.get("positive_factors", [])[:3]
            negative = market_attr.get("negative_factors", [])[:2]
            for item in positive:
                lines.append(f"+ {item}")
            for item in negative:
                lines.append(f"- {item}")
        if not lines:
            attr = facts.get("attribution", {})
            selection = value.get("selection", "")
            selected_attr = attr.get(selection, {}) if isinstance(attr, dict) else {}
            lines.append("Korte modeluitleg:")
            if selected_attr:
                if selected_attr.get("xg_form_adjustment", 0) > 0:
                    lines.append("+ Recente onderliggende aanvalsvorm ondersteunt deze selectie.")
                if selected_attr.get("injury_impact", 0) > 0:
                    lines.append("+ Teamnieuws/blessures vallen gunstig uit voor deze selectie.")
                if selected_attr.get("fatigue_impact", 0) > 0:
                    lines.append("+ Rust- en schemafactoren zijn gunstig.")
        if value.get("reason"):
            lines.append(value.get("reason"))
        return "\n".join(lines[:6]) if lines else "Geen extra toelichting."

from __future__ import annotations

import os
from football_agent.config.loader import load_competitions, load_model_settings, load_bookmaker_profiles


def main():
    comps = load_competitions().get("competitions", [])
    settings = load_model_settings()
    books = load_bookmaker_profiles().get("bookmakers", {})
    print("V25 healthcheck")
    print(f"Competities: {len(comps)}")
    print(f"Bookmakerprofielen: {len(books)}")
    print(f"Thresholds: {settings.get('thresholds', {})}")
    print(f"FOOTBALL_DATA_API_KEY aanwezig: {bool(os.getenv('FOOTBALL_DATA_API_KEY'))}")
    print(f"API_FOOTBALL_KEY aanwezig: {bool(os.getenv('API_FOOTBALL_KEY'))}")
    print(f"GEMINI_API_KEY aanwezig: {bool(os.getenv('GEMINI_API_KEY'))}")
    print(f"TELEGRAM configuratie aanwezig: {bool(os.getenv('TELEGRAM_BOT_TOKEN') and os.getenv('TELEGRAM_CHAT_ID'))}")


if __name__ == "__main__":
    main()

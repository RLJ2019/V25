# AUDIT V25.0.2 — Professional Math Upgrade

Datum: 2026-06-19
Versie: V25.0.2-professional-math-upgrade

## Aanleiding
Deze versie verwerkt de tweede Gemini-audit op V25.0.1. De audit vroeg om verbeteringen die de agent wiskundig professioneler maken en minder gevoelig voor foutieve edges:

1. Dixon-Coles correctie in het Poisson-model.
2. Log-odds/logit overlays in plaats van lineaire kansoptelling.
3. Automatische motivatie-overlay op basis van standenlijst.
4. Dynamische vervangingskwaliteit in het blessuremodel.
5. Empirische kalibratie via isotonic regression zodra genoeg historische data beschikbaar is.

## Gewijzigde modules

### football_agent/models/poisson_model.py
- Dixon-Coles low-score correction toegevoegd.
- `project()` accepteert `use_dixon_coles=True` en optioneel `rho`.
- Standaard `rho=-0.08` om lage-score draws realistischer te behandelen.
- Matrix wordt na correctie opnieuw genormaliseerd.

### football_agent/models/ensemble.py
- Lineaire kansoptelling vervangen door logit/log-odds-transformatie.
- Feature-attributies worden nu als effectieve probability-point bijdragen opgeslagen na elke logit-stap.
- Motivatie-overlay toegevoegd via standings-context.
- Poisson-projectie gebruikt nu standaard Dixon-Coles.
- Data quality krijgt kleine bonus als standings beschikbaar zijn.

### football_agent/models/motivation_model.py
- `StandingRow` toegevoegd.
- Standenlijst-gebaseerde motivatieberekening toegevoegd.
- Meetbare signalen: titelrace, Europese race, degradatiedruk, late-season no-stakes.
- Alle impact blijft strikt gecapt tussen -2.5% en +2.5%.

### football_agent/data/football_data.py
- `standings_table()` toegevoegd.
- Parseert football-data.org standings naar `StandingRow` objecten.
- Gebruikt de TOTAL table waar beschikbaar.

### football_agent/scripts/run_daily.py
- Haalt standen één keer per competitie op.
- Geeft standings en competition_type door aan EnsembleModel.
- Standings-failures zijn non-fatal; de agent draait door zonder motivatie-overlay.

### football_agent/models/injury_model.py
- `PlayerAbsence` uitgebreid met optionele marktwaarde- en minutenvelden.
- Dynamische replacement_quality toegevoegd:
  - player_market_value / replacement_market_value
  - player_minutes_12m / replacement_minutes_12m
- Fallback blijft de oude statische replacement_quality.
- Impact blijft gecapt per linie en totaal.

### football_agent/models/calibration.py
- `CalibrationPoint` toegevoegd.
- `IsotonicSegment` toegevoegd.
- Lightweight Pool Adjacent Violators isotonic regression toegevoegd.
- Geen sklearn dependency nodig.
- Inactief tot voldoende sample size beschikbaar is.

### tests/test_v25_0_2_professional_math.py
Nieuwe tests voor:
- Dixon-Coles verhoogt draw probability bij negatieve rho.
- Logit overlay voorkomt extreme overshoot.
- Motivatie uit standings werkt en blijft gecapt.
- Dynamische replacement_quality werkt op marktwaarde-ratio.
- Isotonic calibration produceert monotone segmenten.

## Testresultaten
Uitgevoerd:

```bash
python smoke_test.py
python -m unittest discover -s tests
python -m compileall football_agent -q
python -m football_agent.scripts.healthcheck
TELEGRAM_ENABLED=false python run_agent.py
```

Resultaat:

```text
V25 smoke test OK
Ran 18 tests
OK
Compile check OK
Healthcheck OK
Daily run zonder API-keys crasht niet
```

## Professionele beoordeling
V25.0.2 is wiskundig sterker dan V25.0.1 omdat:

- Het scoremodel realistischer omgaat met lage-score afhankelijkheid.
- Kansaanpassingen niet meer plat bovenop de marktbaseline worden geplakt.
- Motivatie niet meer handmatig hoeft te worden gezet, maar objectief uit de stand kan komen.
- Blessure-impact beter rekening houdt met teamdiepte.
- Kalibratie voorbereid is op empirisch leren zodra er genoeg historische picks zijn.

## Belangrijke beperking
Deze versie is nog steeds een engine-fundament. Voor echte voorspellingskwaliteit zijn live/historische odds, xG-data, line-ups, blessures en voldoende backtestdata essentieel. Zonder die databronnen blijft de agent bewust streng en zal hij vaak No Bet geven.

from football_agent.models.market_model import MarketModel
from football_agent.models.poisson_model import PoissonModel
from football_agent.models.value_engine import ValueEngine
from football_agent.schemas import OddsSnapshot, ModelProbabilities


def main():
    market = MarketModel()
    probs = market.no_vig_probabilities({"HOME": 2.0, "DRAW": 3.5, "AWAY": 3.8})
    assert abs(sum(probs.values()) - 1.0) < 1e-9

    poisson = PoissonModel()
    score = poisson.project(home_xg=1.6, away_xg=0.9)
    assert 0.99 <= sum(score.outcome_probabilities.values()) <= 1.01

    ev = ValueEngine(min_edge=0.04)
    odds = OddsSnapshot(bookmaker="softbook", market="1X2", selection="HOME", odds=2.05, timestamp_utc="2026-01-01T10:00:00Z")
    decision = ev.evaluate_selection(ModelProbabilities(home=0.58, draw=0.24, away=0.18), {"HOME": 0.50, "DRAW": 0.27, "AWAY": 0.23}, odds)
    assert decision.expected_value >= 0.04
    assert decision.edge == decision.expected_value
    print("V25 smoke test OK")


if __name__ == "__main__":
    main()

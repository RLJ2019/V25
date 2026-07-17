"""V25.1.3 settlement pipeline package.

Settlement is intentionally separated from pick generation. Importing this
package must not change model probabilities, staking, odds discovery or daily
pick identity.
"""

from football_agent.settlement.policies import SETTLEMENT_POLICY_VERSION

__all__ = ["SETTLEMENT_POLICY_VERSION"]

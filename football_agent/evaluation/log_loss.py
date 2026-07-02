from __future__ import annotations

import math
from typing import Dict


def log_loss(probabilities: Dict[str, float], actual: str, eps: float = 1e-12) -> float:
    p = max(eps, min(1.0 - eps, probabilities.get(actual, eps)))
    return -math.log(p)

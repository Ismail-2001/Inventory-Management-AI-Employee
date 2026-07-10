from typing import List


def exponential_smoothing(values: List[float], alpha: float = 0.3) -> float:
    if not values:
        return 0.0
    smoothed = values[0]
    for v in values[1:]:
        smoothed = alpha * v + (1 - alpha) * smoothed
    return smoothed

"""Cluster selection must not let one high-scoring window outvote the field.

Correlation scores are peak-to-noise-floor ratios, not probabilities.  A window
that happens to line up two stretches of near-silence — end credits, a gap
between reels — can score two orders of magnitude above windows carrying real
dialogue.  Weighting linearly by that number lets a single such window decide
the delay for a whole film.
"""

from __future__ import annotations

import numpy as np
import pytest

from audio_sync.core.analyzer import AudioAnalyzer

FINE_RATE = 50.0  # 20 ms per frame, the production value


def window(center_sec: float, lag_ms: float, score: float) -> dict[str, float]:
    lag = lag_ms / 1000.0 * FINE_RATE
    return {
        "center_sec": center_sec,
        "lag": lag,
        "predicted_lag": lag,
        "residual_lag": lag,
        "score": score,
    }


def test_majority_cluster_survives_a_single_huge_outlier() -> None:
    """Reproduces the real failure on a 138-minute film.

    23 windows agreed on -9490 ms; two outliers scored 176 and 3, and the
    analyzer kept only those two, putting ~120 minutes of the film 135 ms out.
    """
    rows = [window(120.0 + i * 300.0, -9490.0, 4.0) for i in range(23)]
    rows.append(window(4560.0, -7902.0, 3.1))
    rows.append(window(8256.0, -7720.0, 176.5))

    kept = AudioAnalyzer()._filter_segment_results(rows, FINE_RATE, 3.5)

    kept_ms = np.array([r["lag"] / FINE_RATE * 1000.0 for r in kept])
    assert len(kept) >= 20, f"kept only {len(kept)} of the 23 agreeing windows"
    assert np.all(np.abs(kept_ms - (-9490.0)) < 60.0), kept_ms


def test_dominant_center_follows_the_crowd_not_the_loudest() -> None:
    values = np.array([100.0] * 20 + [300.0, 301.0], dtype=np.float64)
    weights = np.array([4.0] * 20 + [180.0, 176.0], dtype=np.float64)

    center = AudioAnalyzer._find_dominant_cluster_center(values, weights, FINE_RATE)
    assert abs(center - 100.0) < 5.0, center


def test_a_genuinely_confident_majority_still_wins() -> None:
    """Capping must not flip the answer when the strong windows are the majority."""
    values = np.array([500.0] * 3 + [900.0] * 15, dtype=np.float64)
    weights = np.array([2.0] * 3 + [40.0] * 15, dtype=np.float64)

    center = AudioAnalyzer._find_dominant_cluster_center(values, weights, FINE_RATE)
    assert abs(center - 900.0) < 5.0, center


def test_scores_still_order_two_equally_sized_clusters() -> None:
    """Within the cap, a better-correlating cluster should still be preferred."""
    values = np.array([200.0] * 8 + [800.0] * 8, dtype=np.float64)
    weights = np.array([1.2] * 8 + [9.0] * 8, dtype=np.float64)

    center = AudioAnalyzer._find_dominant_cluster_center(values, weights, FINE_RATE)
    assert abs(center - 800.0) < 5.0, center


@pytest.mark.parametrize("outlier_score", [50.0, 200.0, 5000.0])
def test_outlier_influence_is_bounded_however_extreme(outlier_score: float) -> None:
    rows = [window(100.0 + i * 200.0, 250.0, 3.5) for i in range(15)]
    rows.append(window(5000.0, -4000.0, outlier_score))

    kept = AudioAnalyzer()._filter_segment_results(rows, FINE_RATE, 3.5)
    kept_ms = np.array([r["lag"] / FINE_RATE * 1000.0 for r in kept])
    assert np.all(np.abs(kept_ms - 250.0) < 60.0), kept_ms


def test_capping_is_a_no_op_when_scores_are_uniform() -> None:
    weights = np.full(12, 5.0)
    capped = AudioAnalyzer._cap_segment_weights(weights)
    assert np.allclose(capped, weights)

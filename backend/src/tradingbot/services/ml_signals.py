"""Classical ML signal pipeline for blending with LLM committee signals.

Provides:
- Feature matrix builder from existing features.py / indicators.py
- Abstract MLSignalModel interface with predict/score
- GradientBoostSignalModel using a simple decision-tree ensemble
- Signal blending with LLM committee confidence scores
- Local filesystem model persistence
"""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

from tradingbot.services.metrics import observe_counter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model storage
# ---------------------------------------------------------------------------
_MODEL_DIR = Path(os.getenv("ML_MODEL_DIR", "data/models"))


def _ensure_model_dir() -> Path:
    _MODEL_DIR.mkdir(parents=True, exist_ok=True)
    return _MODEL_DIR


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class FeatureRow:
    """A single feature vector for ML scoring."""

    symbol: str
    features: dict[str, float]
    timestamp: datetime
    label: float | None = None  # Populated for training data


@dataclass(slots=True)
class MLSignal:
    """Output of an ML model prediction."""

    symbol: str
    score: float  # -1.0 (strong sell) to +1.0 (strong buy)
    confidence: float  # 0.0 to 1.0
    model_name: str
    model_version: str
    features_used: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_payload(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "score": round(self.score, 6),
            "confidence": round(self.confidence, 6),
            "model_name": self.model_name,
            "model_version": self.model_version,
            "features_used": self.features_used,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass(slots=True)
class BlendedSignal:
    """Combined ML + LLM committee signal."""

    symbol: str
    ml_score: float
    llm_confidence: float
    blended_score: float
    blended_confidence: float
    ml_weight: float
    llm_weight: float

    def to_payload(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "ml_score": round(self.ml_score, 6),
            "llm_confidence": round(self.llm_confidence, 6),
            "blended_score": round(self.blended_score, 6),
            "blended_confidence": round(self.blended_confidence, 6),
            "ml_weight": round(self.ml_weight, 4),
            "llm_weight": round(self.llm_weight, 4),
        }


# ---------------------------------------------------------------------------
# Feature matrix builder
# ---------------------------------------------------------------------------
_CORE_FEATURES = [
    "last_close",
    "sma_10",
    "sma_20",
    "rsi_14",
    "avg_volume",
    "momentum_pct",
    "intraday_volatility_pct",
    "gap_latest_pct",
    "gap_mean_abs_pct",
    "relative_volume_10",
    "atr_14",
    "atr_stop_distance_pct",
    "opening_range_width_pct",
    "opening_range_position",
    "opening_range_breakout_pct",
    "trend_alignment_score",
    "spy_trend_pct",
    "qqq_trend_pct",
    "index_breadth_score",
    "index_regime_score",
]


def build_feature_matrix(
    feature_snapshots: list[dict[str, float]],
    *,
    symbols: list[str] | None = None,
    feature_names: list[str] | None = None,
) -> list[FeatureRow]:
    """Convert raw feature snapshots into normalized FeatureRow objects."""
    names = feature_names or _CORE_FEATURES
    rows: list[FeatureRow] = []
    for i, snapshot in enumerate(feature_snapshots):
        symbol = symbols[i] if symbols and i < len(symbols) else f"SYM_{i}"
        features = {name: float(snapshot.get(name, 0.0)) for name in names}
        rows.append(FeatureRow(symbol=symbol, features=features, timestamp=datetime.now(UTC)))
    return rows


# ---------------------------------------------------------------------------
# Abstract ML model
# ---------------------------------------------------------------------------
class MLSignalModel(ABC):
    """Abstract base class for ML signal models."""

    @abstractmethod
    def predict(self, features: FeatureRow) -> MLSignal:
        """Generate a signal from feature inputs."""

    @abstractmethod
    def train(self, training_data: list[FeatureRow]) -> dict[str, Any]:
        """Train the model on labeled data. Returns training metrics."""

    @abstractmethod
    def save(self, path: Path | None = None) -> Path:
        """Persist the model to local filesystem."""

    @abstractmethod
    def load(self, path: Path) -> None:
        """Load a persisted model from local filesystem."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Human-readable model name."""

    @property
    @abstractmethod
    def model_version(self) -> str:
        """Model version identifier."""


# ---------------------------------------------------------------------------
# Gradient Boost Signal Model (pure Python — no sklearn dependency)
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class _DecisionStump:
    """A single decision stump (threshold-based split on one feature)."""

    feature: str
    threshold: float
    left_value: float  # prediction when feature <= threshold
    right_value: float  # prediction when feature > threshold


class GradientBoostSignalModel(MLSignalModel):
    """Simple gradient-boosted decision stump ensemble.

    Uses pure Python (no external ML libraries) with the feature set
    already computed in features.py and indicators.py.
    """

    def __init__(
        self,
        *,
        n_estimators: int = 50,
        learning_rate: float = 0.1,
        version: str = "v1",
    ) -> None:
        self._n_estimators = n_estimators
        self._learning_rate = learning_rate
        self._version = version
        self._stumps: list[_DecisionStump] = []
        self._initial_prediction: float = 0.0
        self._feature_importances: dict[str, float] = {}
        self._trained_at: datetime | None = None

    @property
    def model_name(self) -> str:
        return "gradient_boost_signal"

    @property
    def model_version(self) -> str:
        return self._version

    def predict(self, features: FeatureRow) -> MLSignal:
        """Generate a signal from the ensemble prediction."""
        if not self._stumps:
            return MLSignal(
                symbol=features.symbol,
                score=0.0,
                confidence=0.0,
                model_name=self.model_name,
                model_version=self.model_version,
                features_used=list(features.features.keys()),
            )

        raw_score = self._initial_prediction
        for stump in self._stumps:
            value = features.features.get(stump.feature, 0.0)
            if value <= stump.threshold:
                raw_score += self._learning_rate * stump.left_value
            else:
                raw_score += self._learning_rate * stump.right_value

        # Clamp to [-1, 1]
        score = max(min(raw_score, 1.0), -1.0)
        confidence = min(abs(score), 1.0)

        observe_counter("ml.predictions", tags={"model": self.model_name})
        return MLSignal(
            symbol=features.symbol,
            score=round(score, 6),
            confidence=round(confidence, 6),
            model_name=self.model_name,
            model_version=self.model_version,
            features_used=list(features.features.keys()),
        )

    def train(self, training_data: list[FeatureRow]) -> dict[str, Any]:
        """Train the ensemble on labeled feature rows."""
        if not training_data or not any(row.label is not None for row in training_data):
            return {"error": "No labeled training data provided.", "samples": 0}

        labeled = [row for row in training_data if row.label is not None]
        if len(labeled) < 10:
            return {"error": "Insufficient labeled samples (need >= 10).", "samples": len(labeled)}

        feature_names = list(labeled[0].features.keys())
        labels = [row.label for row in labeled]  # type: ignore[arg-type]
        self._initial_prediction = mean(labels)

        # Gradient boosting: iteratively fit stumps to residuals
        residuals = [label - self._initial_prediction for label in labels]
        self._stumps = []
        feature_usage: dict[str, int] = {name: 0 for name in feature_names}

        for _ in range(self._n_estimators):
            best_stump = self._find_best_stump(labeled, residuals, feature_names)
            if best_stump is None:
                break
            self._stumps.append(best_stump)
            feature_usage[best_stump.feature] = feature_usage.get(best_stump.feature, 0) + 1

            # Update residuals
            for i, row in enumerate(labeled):
                value = row.features.get(best_stump.feature, 0.0)
                if value <= best_stump.threshold:
                    residuals[i] -= self._learning_rate * best_stump.left_value
                else:
                    residuals[i] -= self._learning_rate * best_stump.right_value

        total_usage = sum(feature_usage.values()) or 1
        self._feature_importances = {k: round(v / total_usage, 4) for k, v in feature_usage.items()}
        self._trained_at = datetime.now(UTC)

        # Training metrics
        predictions = [self._predict_raw(row) for row in labeled]
        mse = mean([(p - lab) ** 2 for p, lab in zip(predictions, labels)])
        observe_counter("ml.training_completed", tags={"model": self.model_name})

        return {
            "model": self.model_name,
            "version": self.model_version,
            "samples": len(labeled),
            "n_estimators_used": len(self._stumps),
            "mse": round(mse, 6),
            "feature_importances": self._feature_importances,
            "trained_at": self._trained_at.isoformat(),
        }

    def _predict_raw(self, row: FeatureRow) -> float:
        score = self._initial_prediction
        for stump in self._stumps:
            value = row.features.get(stump.feature, 0.0)
            if value <= stump.threshold:
                score += self._learning_rate * stump.left_value
            else:
                score += self._learning_rate * stump.right_value
        return score

    def _find_best_stump(
        self,
        data: list[FeatureRow],
        residuals: list[float],
        feature_names: list[str],
    ) -> _DecisionStump | None:
        """Find the best single-feature split to minimize residual MSE."""
        best_stump: _DecisionStump | None = None
        best_loss = float("inf")

        for feature in feature_names:
            values = [row.features.get(feature, 0.0) for row in data]
            unique_values = sorted(set(values))
            if len(unique_values) < 2:
                continue

            # Try a few candidate thresholds
            n_candidates = min(len(unique_values) - 1, 20)
            step = max(len(unique_values) // n_candidates, 1)
            candidates = [unique_values[i] for i in range(0, len(unique_values) - 1, step)]

            for threshold in candidates:
                left_residuals = [r for v, r in zip(values, residuals) if v <= threshold]
                right_residuals = [r for v, r in zip(values, residuals) if v > threshold]

                if not left_residuals or not right_residuals:
                    continue

                left_mean = mean(left_residuals)
                right_mean = mean(right_residuals)

                loss = sum((r - left_mean) ** 2 for r in left_residuals) + sum(
                    (r - right_mean) ** 2 for r in right_residuals
                )

                if loss < best_loss:
                    best_loss = loss
                    best_stump = _DecisionStump(
                        feature=feature,
                        threshold=threshold,
                        left_value=left_mean,
                        right_value=right_mean,
                    )

        return best_stump

    def save(self, path: Path | None = None) -> Path:
        """Persist model to local filesystem as JSON."""
        model_dir = _ensure_model_dir()
        target = path or (model_dir / f"{self.model_name}_{self.model_version}.json")
        payload = {
            "model_name": self.model_name,
            "version": self.model_version,
            "n_estimators": self._n_estimators,
            "learning_rate": self._learning_rate,
            "initial_prediction": self._initial_prediction,
            "stumps": [
                {
                    "feature": s.feature,
                    "threshold": s.threshold,
                    "left_value": s.left_value,
                    "right_value": s.right_value,
                }
                for s in self._stumps
            ],
            "feature_importances": self._feature_importances,
            "trained_at": self._trained_at.isoformat() if self._trained_at else None,
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info("ml.model_saved", extra={"path": str(target), "stumps": len(self._stumps)})
        return target

    def load(self, path: Path) -> None:
        """Load a persisted model from local filesystem."""
        data = json.loads(path.read_text(encoding="utf-8"))
        self._version = data.get("version", self._version)
        self._n_estimators = data.get("n_estimators", self._n_estimators)
        self._learning_rate = data.get("learning_rate", self._learning_rate)
        self._initial_prediction = data.get("initial_prediction", 0.0)
        self._feature_importances = data.get("feature_importances", {})
        trained_at = data.get("trained_at")
        self._trained_at = datetime.fromisoformat(trained_at) if trained_at else None
        self._stumps = [
            _DecisionStump(
                feature=s["feature"],
                threshold=s["threshold"],
                left_value=s["left_value"],
                right_value=s["right_value"],
            )
            for s in data.get("stumps", [])
        ]
        logger.info("ml.model_loaded", extra={"path": str(path), "stumps": len(self._stumps)})


# ---------------------------------------------------------------------------
# Signal blending
# ---------------------------------------------------------------------------
def blend_signals(
    ml_signal: MLSignal,
    llm_confidence: float,
    *,
    ml_weight: float = 0.3,
    llm_weight: float = 0.7,
) -> BlendedSignal:
    """Blend an ML signal with an LLM committee confidence score.

    Default weights favor the LLM committee (70/30) since it has more
    context (news, events, qualitative reasoning).
    """
    total_weight = ml_weight + llm_weight
    normalized_ml = ml_weight / total_weight
    normalized_llm = llm_weight / total_weight

    blended_score = (ml_signal.score * normalized_ml) + (llm_confidence * normalized_llm)
    blended_confidence = (ml_signal.confidence * normalized_ml) + (llm_confidence * normalized_llm)

    return BlendedSignal(
        symbol=ml_signal.symbol,
        ml_score=ml_signal.score,
        llm_confidence=llm_confidence,
        blended_score=round(max(min(blended_score, 1.0), -1.0), 6),
        blended_confidence=round(max(min(blended_confidence, 1.0), 0.0), 6),
        ml_weight=normalized_ml,
        llm_weight=normalized_llm,
    )

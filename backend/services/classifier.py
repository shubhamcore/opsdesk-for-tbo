"""Module 1 — Stage B calibrated intent classification.

The served confidence is always the model's own calibrated probability for the
winning class. Nothing is hardcoded: the numbers come from
``predict_proba`` of a TF-IDF + Logistic Regression pipeline wrapped in
``CalibratedClassifierCV``. If the artifact is missing or corrupt the service
degrades to an explicit rule-based fallback whose confidence is capped at
0.60 — an uncalibrated number is never presented as a calibrated one.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from backend.config import settings

logger = logging.getLogger(__name__)

INTENT_LABELS = {
    "REFUND_DELAY": "Refund Delay",
    "CANCELLATION_LCD_WAIVER": "Cancellation LCD Waiver",
    "VOUCHER_CONFIRMATION_ISSUE": "Voucher Confirmation Issue",
    "AMENDMENT_NAME_DATE": "Amendment (Name / Date)",
    "INVENTORY_RATE_SYNC_BUG": "Inventory & Rate Sync Bug",
    "SPECIAL_REQUEST": "Special Request",
    "SUPPLIER_OVERBOOKING_RELOCATION": "Supplier Overbooking / Relocation",
    "BILLING_INVOICE_DISPUTE": "Billing & Invoice Dispute",
}

# Vocabulary used to explain a decision in plain language. Not used for
# scoring — the model scores; these terms make the reasoning readable.
EVIDENCE_TERMS = {
    "REFUND_DELAY": ["refund", "credited", "credit note", "not received", "money back", "chase", "out of pocket"],
    "CANCELLATION_LCD_WAIVER": ["waiver", "last cancellation", "lcd", "penalty", "cancel", "free cancellation"],
    "VOUCHER_CONFIRMATION_ISSUE": ["voucher", "confirmation", "no record", "unconfirmed", "check-in", "front desk", "reservation"],
    "AMENDMENT_NAME_DATE": ["amend", "name", "passport", "date change", "correct", "spelling", "modify"],
    "INVENTORY_RATE_SYNC_BUG": ["api", "rate mismatch", "cache", "sync", "error code", "availability", "bug"],
    "SPECIAL_REQUEST": ["honeymoon", "cake", "cot", "early check-in", "view", "decoration", "birthday", "flowers"],
    "SUPPLIER_OVERBOOKING_RELOCATION": ["overbooked", "overbooking", "walked", "relocation", "oversold", "denied"],
    "BILLING_INVOICE_DISPUTE": ["invoice", "credit note", "billed", "duplicate charge", "commission", "gst", "tax invoice"],
}

# Rule fallback: ordered keyword weights, used only when the artifact is gone.
RULE_WEIGHTS: dict[str, list[str]] = {
    "REFUND_DELAY": ["refund", "credited", "credit note", "money back", "not been paid", "out of pocket"],
    "CANCELLATION_LCD_WAIVER": ["waiver", "last cancellation date", "lcd", "penalty", "free cancellation"],
    "VOUCHER_CONFIRMATION_ISSUE": ["voucher", "confirmation", "no booking on file", "no record", "unconfirmed", "front desk"],
    "AMENDMENT_NAME_DATE": ["amend", "name correction", "passport", "date change", "spelling", "modify the booking"],
    "INVENTORY_RATE_SYNC_BUG": ["rate mismatch", "cache", "sync", "error code", "api error", "inventory"],
    "SPECIAL_REQUEST": ["honeymoon", "cake", "cot", "early check-in", "decoration", "birthday", "flowers", "connecting rooms"],
    "SUPPLIER_OVERBOOKING_RELOCATION": ["overbooked", "overbooking", "walked", "relocation", "oversold", "denied the room"],
    "BILLING_INVOICE_DISPUTE": ["invoice", "billed twice", "duplicate charge", "commission", "gst", "tax invoice"],
}

NUMERIC_FEATURES = ["hours_to_checkin", "hours_to_lcd", "prior_count"]


@dataclass
class Prediction:
    intent: str
    label: str
    confidence: float
    scores: dict[str, float] = field(default_factory=dict)
    reasoning: list[str] = field(default_factory=list)
    source: str = "ML"            # ML | FALLBACK | MANUAL
    model_mode: str = "ML"        # mirrors source, surfaced in /api/health
    model_version: str | None = None

    def as_dict(self) -> dict:
        return {
            "intent": self.intent,
            "label": self.label,
            "confidence": round(self.confidence, 6),
            "scores": {k: round(v, 6) for k, v in self.scores.items()},
            "reasoning": self.reasoning,
            "source": self.source,
            "model_mode": self.model_mode,
            "model_version": self.model_version,
        }


class RuleBasedPredictor:
    """Deterministic keyword fallback. Confidence is capped at 0.60 because it
    is not a calibrated model."""

    CAP = 0.60

    def predict(self, text: str) -> tuple[str, float, dict[str, float]]:
        lowered = (text or "").lower()
        raw: dict[str, float] = {}
        for intent, keywords in RULE_WEIGHTS.items():
            hits = sum(1.0 for keyword in keywords if keyword in lowered)
            raw[intent] = hits
        total = sum(raw.values()) or 1.0
        scores = {intent: (value / total) * self.CAP for intent, value in raw.items()}
        intent = max(raw, key=lambda key: raw[key]) if any(raw.values()) else "REFUND_DELAY"
        if not any(raw.values()):
            scores[intent] = 0.35
        confidence = min(self.CAP, max(scores[intent], 0.05))
        return intent, confidence, scores


class IntentClassifier:
    def __init__(self, model_path: Path | None = None) -> None:
        self.model_path = model_path or settings.model_path
        self.pipeline = None
        self.classes: list[str] = []
        self.version: str | None = None
        self.load_error: str | None = None
        self.numeric_medians: dict[str, float] = {
            "hours_to_checkin": 72.0, "hours_to_lcd": 48.0, "prior_count": 0.0,
        }
        self.mode = "FALLBACK"
        self.rule_based = RuleBasedPredictor()
        self._load()

    def _load(self) -> None:
        import joblib

        try:
            if not Path(self.model_path).exists():
                raise FileNotFoundError(f"model artifact not found at {self.model_path}")
            artifact = joblib.load(self.model_path)
            if not isinstance(artifact, dict) or "pipeline" not in artifact:
                raise ValueError("artifact is not a recognised pipeline bundle")
            self.pipeline = artifact["pipeline"]
            self.classes = list(artifact.get("classes") or getattr(self.pipeline, "classes_", []))
            self.version = artifact.get("version")
            self.numeric_medians.update(artifact.get("numeric_medians") or {})
            self.mode = "ML"
            logger.info("Classifier loaded (%s) classes=%d", Path(self.model_path).name, len(self.classes))
        except Exception as exc:  # missing or corrupt artifact → rules
            self.mode = "FALLBACK"
            self.load_error = f"{type(exc).__name__}: {exc}"
            logger.warning("Classifier fallback mode: %s", self.load_error)

    # ------------------------------------------------------------- features
    @staticmethod
    def _frame(text: str, hours_to_checkin: float, hours_to_lcd: float, prior_count: float):
        import pandas as pd

        return pd.DataFrame([{
            "text": text,
            "hours_to_checkin": float(hours_to_checkin),
            "hours_to_lcd": float(hours_to_lcd),
            "prior_count": float(prior_count),
        }])

    # ------------------------------------------------------------- reasoning
    def _evidence_terms(self, text: str, intent: str) -> list[str]:
        lowered = (text or "").lower()
        return [term for term in EVIDENCE_TERMS.get(intent, []) if term in lowered]

    def _explain(
        self,
        *,
        intent: str,
        text: str,
        tboh_id: str | None,
        extraction_source: str | None,
        prior_count: int,
        hours_to_checkin: float | None,
        hours_to_lcd: float | None,
        mode: str,
    ) -> list[str]:
        bullets: list[str] = []

        matched = self._evidence_terms(text, intent)
        if matched:
            shown = ", ".join(f"“{term}”" for term in matched[:4])
            bullets.append(f"{INTENT_LABELS[intent]}-related language detected: {shown}")
        else:
            bullets.append(
                f"No explicit {INTENT_LABELS[intent].lower()} keywords found; decision driven by "
                "overall phrasing and travel features"
            )

        if tboh_id:
            if extraction_source == "DESCRIPTION":
                bullets.append(
                    f"Booking context identified: {tboh_id} recovered from the description "
                    "(TBOH field was left empty)"
                )
            else:
                bullets.append(f"Booking context identified: {tboh_id}")
        else:
            bullets.append(
                "No TBOH booking id present — classification relies on text and travel features only"
            )

        if prior_count > 0:
            bullets.append(
                f"Previous related contacts found: {prior_count} prior ticket(s) on the same booking"
            )
        else:
            bullets.append("No previous tickets on this booking")

        urgency_bits = []
        if hours_to_lcd is not None:
            urgency_bits.append(
                f"LCD in {hours_to_lcd:.1f}h" if hours_to_lcd >= 0
                else f"LCD passed {abs(hours_to_lcd):.1f}h ago"
            )
        if hours_to_checkin is not None:
            urgency_bits.append(
                f"check-in in {hours_to_checkin:.1f}h" if hours_to_checkin >= 0
                else f"check-in passed {abs(hours_to_checkin):.1f}h ago"
            )
        if urgency_bits:
            bullets.append("Travel features used by the model: " + "; ".join(urgency_bits))

        if mode == "FALLBACK":
            bullets.append("Rule-based fallback in use — ML artifact unavailable, confidence capped at 0.60")
        return bullets

    # --------------------------------------------------------------- predict
    def classify(
        self,
        *,
        title: str = "",
        description: str = "",
        tboh_id: str | None = None,
        extraction_source: str | None = None,
        prior_count: int = 0,
        hours_to_checkin: float | None = None,
        hours_to_lcd: float | None = None,
    ) -> Prediction:
        text = f"{title or ''} {description or ''}".strip()

        if self.mode == "ML" and self.pipeline is not None:
            try:
                # Missing booking context is imputed with training medians, not
                # zero — zero would be a distribution shift the model never saw.
                row = self._frame(
                    text,
                    hours_to_checkin if hours_to_checkin is not None
                    else self.numeric_medians.get("hours_to_checkin", 72.0),
                    hours_to_lcd if hours_to_lcd is not None
                    else self.numeric_medians.get("hours_to_lcd", 48.0),
                    max(0, prior_count),
                )
                proba = self.pipeline.predict_proba(row)[0]
                scores = {cls: float(p) for cls, p in zip(self.pipeline.classes_, proba)}
                intent = max(scores, key=scores.get)
                return Prediction(
                    intent=intent,
                    label=INTENT_LABELS.get(intent, intent),
                    confidence=scores[intent],
                    scores=scores,
                    reasoning=self._explain(
                        intent=intent, text=text, tboh_id=tboh_id,
                        extraction_source=extraction_source, prior_count=prior_count,
                        hours_to_checkin=hours_to_checkin, hours_to_lcd=hours_to_lcd, mode="ML",
                    ),
                    source="ML",
                    model_mode="ML",
                    model_version=self.version,
                )
            except Exception as exc:  # runtime failure → fall back, never 500
                logger.error("ML prediction failed (%s); using rules", exc)

        intent, confidence, scores = self.rule_based.predict(text)
        return Prediction(
            intent=intent,
            label=INTENT_LABELS.get(intent, intent),
            confidence=confidence,
            scores=scores,
            reasoning=self._explain(
                intent=intent, text=text, tboh_id=tboh_id,
                extraction_source=extraction_source, prior_count=prior_count,
                hours_to_checkin=hours_to_checkin, hours_to_lcd=hours_to_lcd, mode="FALLBACK",
            ),
            source="FALLBACK",
            model_mode="FALLBACK",
            model_version=None,
        )


_classifier: IntentClassifier | None = None


def get_classifier() -> IntentClassifier:
    global _classifier
    if _classifier is None:
        _classifier = IntentClassifier()
    return _classifier


def reset_classifier() -> None:
    """Used by tests / after retraining."""
    global _classifier
    _classifier = None

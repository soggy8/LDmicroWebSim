"""
Target MCU detection heuristics for Intel HEX programs.
"""

from __future__ import annotations

from dataclasses import dataclass

from .hex_runtime import ProgramImage


@dataclass
class TargetScore:
    target: str
    score: float
    reasons: list[str]

    def to_dict(self) -> dict:
        return {"target": self.target, "score": round(self.score, 3), "reasons": self.reasons}


@dataclass
class TargetDetectionResult:
    best_target: str
    confidence: float
    candidates: list[TargetScore]

    def to_dict(self) -> dict:
        return {
            "bestTarget": self.best_target,
            "confidence": round(self.confidence, 3),
            "candidates": [c.to_dict() for c in sorted(self.candidates, key=lambda x: x.score, reverse=True)],
        }


def detect_target(image: ProgramImage) -> TargetDetectionResult:
    """
    Score likely target families. This is heuristic but transparent.
    """
    pic16 = TargetScore(target="pic16f", score=0.0, reasons=[])
    pic18 = TargetScore(target="pic18", score=0.0, reasons=[])
    avr = TargetScore(target="avr", score=0.0, reasons=[])

    cfg_candidates = image.extract_config_region_words()
    if cfg_candidates:
        pic16.score += 0.8
        pic16.reasons.append("Config-word-like data found at >=0x4000")
        pic18.score += 0.3
        pic18.reasons.append("PIC-style high config region detected")

    words = image.to_word_view(2)
    if words:
        # PIC14-bit programs often have high 2 bits clear frequently in low words.
        sample = list(words.values())[: min(128, len(words))]
        low_14bit_ratio = sum(1 for w in sample if (w & 0xC000) == 0) / max(1, len(sample))
        if low_14bit_ratio > 0.65:
            pic16.score += 1.0
            pic16.reasons.append(f"{low_14bit_ratio:.2f} of sample words fit 14-bit shape")
        if low_14bit_ratio < 0.45:
            pic18.score += 0.4
            avr.score += 0.4
            pic18.reasons.append("Word patterns less PIC14-like")
            avr.reasons.append("Word patterns less PIC14-like")

    if image.start_linear_address is not None:
        avr.score += 0.2
        avr.reasons.append("Start linear address record present")

    # Bias toward pic16f for LDmicro training-board usage where family is unknown.
    pic16.score += 0.15
    pic16.reasons.append("Default bias for LDmicro educational PIC workflows")

    candidates = [pic16, pic18, avr]
    candidates_sorted = sorted(candidates, key=lambda c: c.score, reverse=True)
    best = candidates_sorted[0]
    second = candidates_sorted[1]
    spread = max(0.0, best.score - second.score)
    confidence = min(0.99, 0.5 + spread)

    return TargetDetectionResult(
        best_target=best.target,
        confidence=confidence,
        candidates=candidates_sorted,
    )

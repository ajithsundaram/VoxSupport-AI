"""
Lightweight rule-based sentiment detector.
Returns: "angry" | "neutral"

Keeps it fast (no extra API call) and deterministic.
Upgrade to an LLM classifier later if needed.
"""

import re
from typing import Literal

SentimentType = Literal["angry", "neutral"]

# Words/phrases strongly associated with frustration or anger
_ANGRY_SIGNALS = [
    # Explicit anger
    "angry", "furious", "outraged", "livid", "enraged",
    # Frustration
    "frustrated", "frustrating", "fed up", "sick of", "tired of",
    # Negative product opinions
    "terrible", "horrible", "awful", "disgusting", "useless",
    "incompetent", "pathetic", "ridiculous", "unacceptable",
    "outrageous", "appalling", "shameful", "disgrace",
    # Strong negative outcomes
    "worst", "scam", "fraud", "waste", "rip off", "ripped off",
    "never again", "cancel everything",
    # Urgent demands
    "fix this now", "this is wrong", "this is broken",
    "not acceptable", "cannot believe", "how dare",
    "what is wrong", "totally unacceptable",
    # Disappointment markers
    "disappointed", "let down", "expected better",
    "unprofessional", "unbelievable",
]

# Stop-words to skip for partial matching
_STOP = {"i", "a", "is", "the", "my", "me", "we", "it", "in", "on", "at", "to"}


def detect_sentiment(text: str) -> SentimentType:
    """
    Classify text as 'angry' or 'neutral'.

    Scoring:
    - Each matched angry signal phrase  → +2
    - Each '!' (exclamation mark)       → +0.5
    - Each CAPS word (≥3 letters)       → +1  (shouting)

    Threshold: score >= 1 → "angry"
    """
    text_lower = text.lower()
    score: float = 0.0

    for signal in _ANGRY_SIGNALS:
        if signal in text_lower:
            score += 2

    # Exclamation marks
    score += text.count("!") * 0.5

    # ALL-CAPS words (shouting)
    caps_words = re.findall(r"\b[A-Z]{3,}\b", text)
    score += len(caps_words) * 1.0

    return "angry" if score >= 1 else "neutral"

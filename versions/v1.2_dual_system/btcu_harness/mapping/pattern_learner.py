"""
PatternLearner: Real pattern accumulation for the internalize stage.

In the school stage, every input is projected by the LLM. As patterns
accumulate, the internalize stage can match new inputs to similar past
projections, reducing LLM calls.

The pattern learner uses a feature extraction + nearest neighbor approach:
1. Extract features from input text (keywords, length, sentiment markers)
2. Store (features -> cognitive state) mappings from LLM projections
3. For new inputs, find the most similar stored pattern
4. If similarity is above threshold, use the stored state (no LLM call)
5. If not, fall back to LLM and store the new pattern

This is the mechanism that makes C ∝ N_unknown possible.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..core.state import CognitiveState, NUM_DIMENSIONS


@dataclass
class Pattern:
    """A learned projection pattern."""

    features: Dict[str, float]  # feature -> weight
    state_values: Tuple[int, ...]
    state_index: int
    input_text: str  # original input (for debugging)
    source: str = "llm"  # how this pattern was created
    confidence: float = 1.0
    use_count: int = 0  # how many times this pattern was reused
    success_count: int = 0  # how many times reuse led to positive outcome


class PatternLearner:
    """
    Learns and retrieves projection patterns.

    Features extracted from input text:
    - Keywords (top-N most frequent meaningful words)
    - Text length (short/medium/long)
    - Sentiment markers (presence of negation, affirmation, uncertainty words)
    - Question type (what/why/how/should/is)
    """

    # Sentiment marker words
    POSITIVE_WORDS = frozenset({
        "good", "great", "excellent", "positive", "success", "benefit",
        "advantage", "opportunity", "strength", "support", "yes", "should",
        "invest", "adopt", "proceed", "advance", "improve", "best",
    })
    NEGATIVE_WORDS = frozenset({
        "bad", "poor", "negative", "failure", "risk", "problem",
        "disadvantage", "threat", "weakness", "oppose", "no", "not",
        "avoid", "stop", "cancel", "decline", "worsen", "worst",
    })
    UNCERTAINTY_WORDS = frozenset({
        "maybe", "perhaps", "uncertain", "unclear", "unknown", "might",
        "could", "possibly", "seems", "appear", "think", "guess",
        "not sure", "unclear", "ambiguous", "depends",
    })
    QUESTION_MARKERS = frozenset({
        "what", "why", "how", "should", "is", "are", "can", "will",
        "when", "where", "which", "who", "do", "does",
    })

    def __init__(self, similarity_threshold: float = 0.7) -> None:
        self.patterns: List[Pattern] = []
        self.threshold = similarity_threshold

    def extract_features(self, text: str) -> Dict[str, float]:
        """Extract features from input text."""
        words = text.lower().split()
        words = [w.strip(".,!?;:\"'()[]{}") for w in words]
        words = [w for w in words if len(w) > 1]

        features: Dict[str, float] = {}

        # Keyword features (top 10 most meaningful)
        word_freq: Dict[str, int] = {}
        for w in words:
            if w not in self.QUESTION_MARKERS and w not in {"the", "a", "an", "to", "of", "in", "for", "and", "or", "but"}:
                word_freq[w] = word_freq.get(w, 0) + 1

        for word, freq in sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:10]:
            features[f"kw_{word}"] = freq / len(words) if words else 0

        # Length feature
        total_words = len(words)
        if total_words < 10:
            features["len_short"] = 1.0
        elif total_words < 30:
            features["len_medium"] = 1.0
        else:
            features["len_long"] = 1.0

        # Sentiment markers
        pos_count = sum(1 for w in words if w in self.POSITIVE_WORDS)
        neg_count = sum(1 for w in words if w in self.NEGATIVE_WORDS)
        unc_count = sum(1 for w in words if w in self.UNCERTAINTY_WORDS)

        total_sentiment = pos_count + neg_count + unc_count
        if total_sentiment > 0:
            features["sent_positive"] = pos_count / total_sentiment
            features["sent_negative"] = neg_count / total_sentiment
            features["sent_uncertain"] = unc_count / total_sentiment

        # Question type
        if words:
            first_word = words[0]
            if first_word in self.QUESTION_MARKERS:
                features[f"q_{first_word}"] = 1.0

        return features

    def similarity(self, features_a: Dict[str, float], features_b: Dict[str, float]) -> float:
        """
        Cosine similarity between two feature vectors.
        """
        all_keys = set(features_a.keys()) | set(features_b.keys())

        dot_product = sum(features_a.get(k, 0) * features_b.get(k, 0) for k in all_keys)
        norm_a = math.sqrt(sum(v ** 2 for v in features_a.values()))
        norm_b = math.sqrt(sum(v ** 2 for v in features_b.values()))

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot_product / (norm_a * norm_b)

    def learn(
        self,
        input_text: str,
        state: CognitiveState,
        source: str = "llm",
        confidence: float = 1.0,
    ) -> Pattern:
        """Learn a new projection pattern from an LLM projection."""
        features = self.extract_features(input_text)

        pattern = Pattern(
            features=features,
            state_values=state.values,
            state_index=state.index,
            input_text=input_text[:200],  # truncate for storage
            source=source,
            confidence=confidence,
        )
        self.patterns.append(pattern)
        return pattern

    def match(self, input_text: str) -> Optional[Tuple[Pattern, float]]:
        """
        Find the best matching pattern for an input.

        Returns (pattern, similarity) if best match is above threshold.
        Returns None if no match is good enough.
        """
        if not self.patterns:
            return None

        input_features = self.extract_features(input_text)

        best_pattern = None
        best_sim = 0.0

        for pattern in self.patterns:
            sim = self.similarity(input_features, pattern.features)
            if sim > best_sim:
                best_sim = sim
                best_pattern = pattern

        if best_pattern and best_sim >= self.threshold:
            best_pattern.use_count += 1
            return (best_pattern, best_sim)

        return None

    def reinforce(self, state_index: int, positive: bool) -> None:
        """Reinforce patterns by state index based on outcome."""
        for p in self.patterns:
            if p.state_index == state_index:
                if positive:
                    p.success_count += 1
                # Increase confidence for successful patterns
                if positive and p.success_count >= 3:
                    p.confidence = min(1.0, p.confidence + 0.1)

    @property
    def pattern_count(self) -> int:
        return len(self.patterns)

    @property
    def total_reuses(self) -> int:
        return sum(p.use_count for p in self.patterns)

    @property
    def reuse_rate(self) -> float:
        """Fraction of pattern lookups that resulted in a reuse."""
        total_lookups = sum(1 + p.use_count for p in self.patterns)
        if total_lookups == 0:
            return 0.0
        return self.total_reuses / total_lookups

    def to_dict(self) -> Dict[str, Any]:
        return {
            "patterns": [
                {
                    "features": p.features,
                    "state_values": list(p.state_values),
                    "state_index": p.state_index,
                    "input_text": p.input_text,
                    "source": p.source,
                    "confidence": p.confidence,
                    "use_count": p.use_count,
                    "success_count": p.success_count,
                }
                for p in self.patterns
            ],
            "threshold": self.threshold,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PatternLearner":
        learner = cls(similarity_threshold=data.get("threshold", 0.7))
        for p_data in data.get("patterns", []):
            learner.patterns.append(Pattern(
                features=p_data["features"],
                state_values=tuple(p_data["state_values"]),
                state_index=p_data["state_index"],
                input_text=p_data.get("input_text", ""),
                source=p_data.get("source", "llm"),
                confidence=p_data.get("confidence", 1.0),
                use_count=p_data.get("use_count", 0),
                success_count=p_data.get("success_count", 0),
            ))
        return learner

    def __repr__(self) -> str:
        return (
            f"PatternLearner(patterns={self.pattern_count}, "
            f"reuses={self.total_reuses}, "
            f"reuse_rate={self.reuse_rate:.1%})"
        )

"""
System 1 cognitive pattern library for the BTCU Harness.

Kahneman's "Thinking Fast and Slow" -- System 1 operates via learned
pattern-recognition: fast, intuitive, experience-based. It maps inputs to
actions by matching against a memory of (cognitive_state, input) -> action
couplings. When System 1 lacks confidence, System 2 (LLM) takes over.

The library supports three matching strategies:
    1. Exact hash match -- O(1) lookup by input text hash
    2. k-NN search -- find nearest cognitive state neighbours in 9D ternary space
    3. Fuzzy match -- embedding-based semantic similarity of input text

Patterns age (confidence decays over time) and are reinforced by positive
outcomes, creating an adaptive intuition that improves with use.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from ..core.state import CognitiveState, NUM_DIMENSIONS, SPACE_SIZE

logger = logging.getLogger("btcu_harness.cognition.system1")


@dataclass
class CognitivePattern:
    """
    A single learned System 1 cognitive pattern.

    Represents the mapping: (input_hash, cognitive_state) -> action,
    annotated with success tracking and audit metadata.
    """

    input_hash: str
    state_index: int
    state_values: List[int]  # 9D ternary values in {-1, 0, +1}
    action: str
    context: Dict[str, Any] = field(default_factory=dict)
    success_rate: float = 0.5
    use_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_used: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    confidence: float = 0.5  # computed from success_rate * recency_factor
    system2_audit_score: float = 0.0  # score from System 2 validation

    # --- computed properties ---

    @property
    def recency_factor(self) -> float:
        """Decay factor based on time since last use (0 = stale, 1 = fresh)."""
        now = datetime.now(timezone.utc)
        age_days = (now - self.last_used).total_seconds() / 86400
        return math.exp(-age_days / 7.0)  # half-life ~7 days

    @property
    def computed_confidence(self) -> float:
        """Confidence = success_rate weighted by recency."""
        return self.success_rate * self.recency_factor

    # --- serialization ---

    def to_dict(self) -> Dict[str, Any]:
        return {
            "input_hash": self.input_hash,
            "state_index": self.state_index,
            "state_values": self.state_values,
            "action": self.action,
            "context": self.context,
            "success_rate": self.success_rate,
            "use_count": self.use_count,
            "created_at": self.created_at.isoformat(),
            "last_used": self.last_used.isoformat(),
            "confidence": self.computed_confidence,
            "system2_audit_score": self.system2_audit_score,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CognitivePattern":
        return cls(
            input_hash=data["input_hash"],
            state_index=data["state_index"],
            state_values=list(data["state_values"]),
            action=data["action"],
            context=data.get("context", {}),
            success_rate=data.get("success_rate", 0.5),
            use_count=data.get("use_count", 0),
            created_at=datetime.fromisoformat(data["created_at"]),
            last_used=datetime.fromisoformat(data["last_used"]),
            confidence=data.get("confidence", 0.5),
            system2_audit_score=data.get("system2_audit_score", 0.0),
        )

    def __repr__(self) -> str:
        return (
            f"CognitivePattern(hash={self.input_hash[:8]}, "
            f"state=#{self.state_index}, action={self.action[:40]}, "
            f"sr={self.success_rate:.2f}, uses={self.use_count}, "
            f"conf={self.computed_confidence:.2f})"
        )


class System1PatternLibrary:
    """
    System 1 fast-intuition pattern library.

    Maintains an associative memory of (input_hash -> cognitive_state -> action
    -> success_rate). Supports exact, k-NN, and fuzzy matching. Patterns age
    through confidence decay and are reinforced by successful outcomes.

    The library is designed to be the "fast" pathway in a dual-system engine:
    when an input arrives, try exact match (instant), then k-NN (nearby states),
    then fuzzy (semantic). If no match is confident enough, escalate to System 2
    (the LLM bridge).
    """

    # Thresholds for escalation to System 2
    EXACT_CONFIDENCE_THRESHOLD = 0.6
    KNN_CONFIDENCE_THRESHOLD = 0.5
    FUZZY_CONFIDENCE_THRESHOLD = 0.5

    def __init__(
        self,
        similarity_threshold: float = 0.7,
        persistence_path: Optional[str] = None,
        mongo_persistence: Any = None,
    ) -> None:
        """
        Args:
            similarity_threshold: minimum cosine similarity for fuzzy match
            persistence_path: JSON file path for save/load (optional)
            mongo_persistence: MongoPersistence instance for MongoDB backend
        """
        # In-memory pattern store
        # Layer 1: exact lookup by input_hash -> state_index -> pattern
        self._hash_index: Dict[str, Dict[int, CognitivePattern]] = {}

        # Layer 2: all patterns for k-NN and fuzzy fallback
        self._patterns: List[CognitivePattern] = []

        # State coverage tracking
        self._covered_states: Set[int] = set()

        # Fuzzy matching: text -> input_hash (for quick embedding-based lookup)
        # This is populated externally if an embedding service is wired in
        self._text_to_hash: Dict[str, str] = {}

        self.similarity_threshold = similarity_threshold
        self.persistence_path = persistence_path
        self.mongo_persistence = mongo_persistence

        # Statistics
        self._total_lookups = 0
        self._exact_hits = 0
        self._knn_hits = 0
        self._fuzzy_hits = 0
        self._misses = 0

    # ------------------------------------------------------------------
    # Learning
    # ------------------------------------------------------------------

    def _compute_input_hash(self, input_text: str) -> str:
        """Stable hash of input text for exact indexing."""
        return hashlib.sha256(input_text.encode("utf-8")).hexdigest()

    def learn(
        self,
        input_text: str,
        state: CognitiveState,
        action: str,
        context: Optional[Dict[str, Any]] = None,
        success: bool = True,
        system2_audit_score: float = 0.0,
    ) -> CognitivePattern:
        """
        Learn from a new experience.

        If an exact match already exists, reinforce it. Otherwise create a new
        pattern and index it for all three matching strategies.
        """
        input_hash = self._compute_input_hash(input_text)
        state_idx = state.index
        now = datetime.now(timezone.utc)

        # Try exact match first
        existing = self._hash_index.get(input_hash, {}).get(state_idx)
        if existing:
            # Reinforce existing pattern
            existing.use_count += 1
            existing.last_used = now
            if success:
                # Bayesian-like success rate update
                existing.success_rate = (
                    existing.success_rate * existing.use_count + 1.0
                ) / (existing.use_count + 1)
            else:
                existing.success_rate = (
                    existing.success_rate * existing.use_count
                ) / (existing.use_count + 1)
            if system2_audit_score > 0:
                existing.system2_audit_score = max(
                    existing.system2_audit_score, system2_audit_score
                )
            existing.confidence = existing.computed_confidence
            return existing

        # Create new pattern
        pattern = CognitivePattern(
            input_hash=input_hash,
            state_index=state_idx,
            state_values=list(state.values),
            action=action,
            context=context or {},
            success_rate=1.0 if success else 0.0,
            use_count=1,
            created_at=now,
            last_used=now,
            confidence=1.0 if success else 0.0,
            system2_audit_score=system2_audit_score,
        )

        # Index it
        if input_hash not in self._hash_index:
            self._hash_index[input_hash] = {}
        self._hash_index[input_hash][state_idx] = pattern
        self._patterns.append(pattern)
        self._covered_states.add(state_idx)
        self._text_to_hash[input_text[:200]] = input_hash

        return pattern

    # ------------------------------------------------------------------
    # Matching strategies
    # ------------------------------------------------------------------

    def match_exact(self, input_text: str) -> Optional[CognitivePattern]:
        """
        O(1) exact hash lookup.

        Returns the highest-confidence pattern for this exact input hash,
        across all known state_index variants. Returns None if no exact match.
        """
        input_hash = self._compute_input_hash(input_text)
        state_map = self._hash_index.get(input_hash)
        if not state_map:
            return None

        # If multiple states for same input, pick highest confidence
        best = max(state_map.values(), key=lambda p: p.computed_confidence)
        if best.computed_confidence >= self.EXACT_CONFIDENCE_THRESHOLD:
            best.last_used = datetime.now(timezone.utc)
            return best
        return None

    def match_knn(
        self,
        state_values: List[int],
        k: int = 3,
        min_confidence: Optional[float] = None,
    ) -> List[CognitivePattern]:
        """
        k-NN search in 9D cognitive space using Euclidean distance.

        Args:
            state_values: target 9D ternary state
            k: number of neighbours to return
            min_confidence: filter threshold (default: KNN_CONFIDENCE_THRESHOLD)

        Returns:
            List of up to k nearest patterns, sorted by distance ascending,
            then confidence descending.
        """
        if not self._patterns:
            return []

        threshold = min_confidence if min_confidence is not None else self.KNN_CONFIDENCE_THRESHOLD

        # Compute Euclidean distances
        scored: List[Tuple[float, CognitivePattern]] = []
        for pattern in self._patterns:
            dist = math.sqrt(
                sum((a - b) ** 2 for a, b in zip(state_values, pattern.state_values))
            )
            scored.append((dist, pattern))

        # Sort by distance, then by confidence descending
        scored.sort(key=lambda x: (x[0], -x[1].computed_confidence))

        # Take top-k above threshold
        results: List[CognitivePattern] = []
        for dist, pattern in scored[:k]:
            if pattern.computed_confidence >= threshold:
                pattern.last_used = datetime.now(timezone.utc)
                results.append(pattern)

        return results

    def match_fuzzy(
        self,
        input_text: str,
        threshold: float = 0.7,
    ) -> Optional[CognitivePattern]:
        """
        Fuzzy match via input text embedding similarity.

        This is a lightweight keyword-overlap similarity (cosine on bag-of-words
        features). In production, replace with dense embedding cosine similarity.

        Returns the best matching pattern if similarity >= threshold.
        """
        if not self._patterns:
            return None

        # Extract features from query
        query_features = self._extract_text_features(input_text)

        best_pattern: Optional[CognitivePattern] = None
        best_sim = 0.0

        for pattern in self._patterns:
            # Use stored context["features"] if available
            stored_features = pattern.context.get("features")
            if stored_features is None:
                # Fallback: reconstruct from input_text if stored
                stored_text = pattern.context.get("input_text", "")
                stored_features = self._extract_text_features(stored_text)
                pattern.context["features"] = stored_features

            sim = self._cosine_similarity(query_features, stored_features)
            if sim > best_sim:
                best_sim = sim
                best_pattern = pattern

        if best_pattern and best_sim >= threshold:
            best_pattern.last_used = datetime.now(timezone.utc)
            return best_pattern
        return None

    # ------------------------------------------------------------------
    # Coverage & aging
    # ------------------------------------------------------------------

    def get_state_coverage(self) -> float:
        """Percentage of 19683 states that have at least one pattern."""
        if SPACE_SIZE == 0:
            return 0.0
        return len(self._covered_states) / SPACE_SIZE

    def age_patterns(self, decay_factor: float = 0.99) -> None:
        """
        Decay confidence of all patterns that haven't been reinforced recently.

        This is called periodically (e.g. once per session) to prune stale
        intuitions. Patterns with very low confidence are candidates for removal.
        """
        pruned = 0
        for pattern in self._patterns:
            # Decay success_rate towards neutral (0.5)
            pattern.success_rate = 0.5 + decay_factor * (pattern.success_rate - 0.5)
            pattern.confidence = pattern.computed_confidence
            if pattern.confidence < 0.05:
                pruned += 1

        if pruned > 0:
            logger.info("Pruned %d stale patterns (< 0.05 confidence)", pruned)
            self._rebuild_indexes()

    def _rebuild_indexes(self) -> None:
        """Rebuild all indexes after pruning."""
        self._hash_index = {}
        self._covered_states = set()
        self._text_to_hash = {}
        alive: List[CognitivePattern] = []
        for pattern in self._patterns:
            if pattern.computed_confidence >= 0.05:
                alive.append(pattern)
                if pattern.input_hash not in self._hash_index:
                    self._hash_index[pattern.input_hash] = {}
                self._hash_index[pattern.input_hash][pattern.state_index] = pattern
                self._covered_states.add(pattern.state_index)
        self._patterns = alive

    # ------------------------------------------------------------------
    # Feature extraction (for fuzzy matching)
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_text_features(text: str) -> Dict[str, float]:
        """Extract bag-of-words feature vector from text."""
        words = text.lower().split()
        words = [w.strip(".,!?;:\"'()[]{}") for w in words]
        words = [w for w in words if len(w) > 2]

        stopwords = {
            "the", "and", "for", "are", "but", "not", "you", "all",
            "can", "had", "her", "was", "one", "our", "out", "day",
            "get", "has", "him", "his", "how", "its", "may", "new",
            "now", "old", "see", "two", "way", "who", "boy", "did",
            "she", "use", "her", "man", "men", "run", "she", "sun",
        }

        freq: Dict[str, int] = {}
        for w in words:
            if w not in stopwords:
                freq[w] = freq.get(w, 0) + 1

        total = len(words) or 1
        return {w: c / total for w, c in freq.items()}

    @staticmethod
    def _cosine_similarity(
        a: Dict[str, float], b: Dict[str, float]
    ) -> float:
        """Cosine similarity between two sparse feature vectors."""
        keys = set(a.keys()) | set(b.keys())
        dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
        norm_a = math.sqrt(sum(v ** 2 for v in a.values()))
        norm_b = math.sqrt(sum(v ** 2 for v in b.values()))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "patterns": [p.to_dict() for p in self._patterns],
            "similarity_threshold": self.similarity_threshold,
            "covered_states": sorted(self._covered_states),
            "total_lookups": self._total_lookups,
            "exact_hits": self._exact_hits,
            "knn_hits": self._knn_hits,
            "fuzzy_hits": self._fuzzy_hits,
            "misses": self._misses,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "System1PatternLibrary":
        lib = cls(similarity_threshold=data.get("similarity_threshold", 0.7))
        for p_data in data.get("patterns", []):
            lib._patterns.append(CognitivePattern.from_dict(p_data))
        lib._rebuild_indexes()
        lib._total_lookups = data.get("total_lookups", 0)
        lib._exact_hits = data.get("exact_hits", 0)
        lib._knn_hits = data.get("knn_hits", 0)
        lib._fuzzy_hits = data.get("fuzzy_hits", 0)
        lib._misses = data.get("misses", 0)
        return lib

    def save(self, path: Optional[str] = None) -> str:
        """Save pattern library to JSON file."""
        target = path or self.persistence_path
        if not target:
            raise ValueError("No persistence path provided")
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        return target

    @classmethod
    def load(cls, path: str) -> "System1PatternLibrary":
        """Load pattern library from JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    # ------------------------------------------------------------------
    # MongoDB persistence (mirrors storage/mongo_persistence.py interface)
    # ------------------------------------------------------------------

    def save_to_mongo(self, project_id: str = "default") -> str:
        """Save pattern library to MongoDB."""
        if self.mongo_persistence is None:
            raise ValueError("mongo_persistence not configured")
        doc = {
            "project_id": project_id,
            "type": "system1_pattern_library",
            "data": self.to_dict(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        # Delegate to mongo persistence backend
        collection = getattr(self.mongo_persistence, "_db", None)
        if collection is None:
            raise RuntimeError("MongoDB connection not available")
        coll = collection["system1_patterns"]
        coll.replace_one(
            {"project_id": project_id, "type": "system1_pattern_library"},
            doc,
            upsert=True,
        )
        return project_id

    @classmethod
    def load_from_mongo(cls, mongo_persistence: Any, project_id: str = "default") -> "System1PatternLibrary":
        """Load pattern library from MongoDB."""
        collection = getattr(mongo_persistence, "_db", None)
        if collection is None:
            raise RuntimeError("MongoDB connection not available")
        doc = collection["system1_patterns"].find_one(
            {"project_id": project_id, "type": "system1_pattern_library"}
        )
        if doc is None:
            return cls()
        return cls.from_dict(doc["data"])

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    @property
    def pattern_count(self) -> int:
        return len(self._patterns)

    def stats(self) -> Dict[str, Any]:
        return {
            "patterns": self.pattern_count,
            "covered_states": len(self._covered_states),
            "coverage_pct": self.get_state_coverage() * 100,
            "lookups": self._total_lookups,
            "exact_hits": self._exact_hits,
            "knn_hits": self._knn_hits,
            "fuzzy_hits": self._fuzzy_hits,
            "misses": self._misses,
            "hit_rate": (
                (self._exact_hits + self._knn_hits + self._fuzzy_hits)
                / max(1, self._total_lookups)
            ),
        }

    def __repr__(self) -> str:
        return (
            f"System1PatternLibrary(patterns={self.pattern_count}, "
            f"states={len(self._covered_states)}, "
            f"coverage={self.get_state_coverage():.4%})"
        )

"""Tests for InputProjector: mapping inputs to cognitive states."""
import json
import pytest

from btcu_harness.core.state import CognitiveState, SPACE_SIZE
from btcu_harness.mapping.dimension_adapter import DimensionAdapter, DimensionSet
from btcu_harness.mapping.projector import InputProjector, ProjectionResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def dim_set():
    adapter = DimensionAdapter()
    ds = adapter.use_example("default")
    adapter.lock(ds)
    return ds


@pytest.fixture
def projector(dim_set):
    return InputProjector(dim_set, growth_stage="school")


def _make_llm_callback(values, reasons=None):
    """Create a mock LLM callback returning the given dimension values."""
    def cb(prompt: str) -> str:
        assessments = []
        for i, v in enumerate(values):
            r = reasons[i] if reasons and i < len(reasons) else f"reason-{i}"
            assessments.append({"dimension": f"d{i}", "value": v, "reason": r})
        return json.dumps({"assessments": assessments})
    return cb


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------

class TestInit:
    def test_requires_locked_dimset(self):
        ds = DimensionSet(labels=["a", "b", "c", "d", "e", "f", "g", "h", "i"])
        with pytest.raises(ValueError, match="locked"):
            InputProjector(ds)

    def test_defaults(self, dim_set):
        p = InputProjector(dim_set)
        assert p.growth_stage == "school"
        assert p.pattern_count == 0

    def test_custom_stage(self, dim_set):
        p = InputProjector(dim_set, growth_stage="graduate")
        assert p.growth_stage == "graduate"


# ---------------------------------------------------------------------------
# project() - school stage
# ---------------------------------------------------------------------------

class TestProjectSchool:
    def test_with_llm(self, projector):
        values = [1, -1, 0, 1, -1, 0, 1, -1, 0]
        cb = _make_llm_callback(values)
        result = projector.project("test input", llm_callback=cb)

        assert result.source == "llm"
        assert result.confidence == 0.8
        assert result.state.values == tuple(values)
        assert len(result.dimension_assessments) == 9

    def test_no_callback_raises(self, projector):
        with pytest.raises(ValueError, match="LLM callback required"):
            projector.project("test input")

    def test_parse_error_fallback(self, projector):
        def bad_cb(prompt):
            return "not json"
        result = projector.project("test", llm_callback=bad_cb)
        assert result.source == "llm_parse_error"
        assert result.confidence == 0.0
        assert result.state.index == SPACE_SIZE // 2  # all void

    def test_values_clamped(self, projector):
        """Values outside [-1, 1] should be clamped."""
        cb = _make_llm_callback([5, -5, 0, 1, -1, 0, 1, -1, 0])
        result = projector.project("test", llm_callback=cb)
        assert result.state.values[0] == 1
        assert result.state.values[1] == -1

    def test_missing_assessments_uses_void(self, projector):
        """Fewer than 9 assessments -> remaining dims default to 0."""
        cb = _make_llm_callback([1, -1])  # only 2 values
        result = projector.project("test", llm_callback=cb)
        assert result.state.values[0] == 1
        assert result.state.values[1] == -1
        assert result.state.values[2:] == (0, 0, 0, 0, 0, 0, 0)

    def test_assessment_reasons_stored(self, projector):
        reasons = ["good", "bad", "neutral", "pos", "neg",
                   "zero", "yes", "no", "maybe"]
        cb = _make_llm_callback([1, -1, 0, 1, -1, 0, 1, -1, 0], reasons)
        result = projector.project("test", llm_callback=cb)
        labels = projector.dim_set.labels
        for i, label in enumerate(labels):
            assert result.dimension_assessments[label] == reasons[i]


# ---------------------------------------------------------------------------
# project() - internalize stage
# ---------------------------------------------------------------------------

class TestProjectInternalize:
    def test_pattern_match_first(self, dim_set):
        p = InputProjector(dim_set, growth_stage="internalize")
        p.learn_pattern("hello world test", CognitiveState.from_values([1, 1, 1, 1, 1, 1, 1, 1, 1]))
        result = p.project("hello world", llm_callback=None)
        assert result.source == "pattern"
        assert result.state.values == (1, 1, 1, 1, 1, 1, 1, 1, 1)

    def test_fallback_to_llm(self, dim_set):
        p = InputProjector(dim_set, growth_stage="internalize")
        # No patterns learned -> LLM
        cb = _make_llm_callback([-1, -1, -1, -1, -1, -1, -1, -1, -1])
        result = p.project("novel input", llm_callback=cb)
        assert result.source == "llm"


# ---------------------------------------------------------------------------
# project() - graduate stage
# ---------------------------------------------------------------------------

class TestProjectGraduate:
    def test_pattern_match(self, dim_set):
        p = InputProjector(dim_set, growth_stage="graduate")
        p.learn_pattern("machine learning ai", CognitiveState.from_values([1, 0, -1, 1, 0, -1, 1, 0, -1]))
        result = p.project("machine learning", llm_callback=None)
        assert result.source == "pattern"
        assert result.state.values == (1, 0, -1, 1, 0, -1, 1, 0, -1)

    def test_llm_for_novel(self, dim_set):
        p = InputProjector(dim_set, growth_stage="graduate")
        cb = _make_llm_callback([1, 1, 1, 1, 1, 1, 1, 1, 1])
        result = p.project("brand new topic", llm_callback=cb)
        assert result.source == "llm"

    def test_void_fallback_no_llm(self, dim_set):
        p = InputProjector(dim_set, growth_stage="graduate")
        result = p.project("unknown", llm_callback=None)
        assert result.source == "void_fallback"
        assert result.confidence == 0.0
        assert result.state.index == SPACE_SIZE // 2


# ---------------------------------------------------------------------------
# _project_with_patterns
# ---------------------------------------------------------------------------

class TestPatternMatching:
    def test_no_patterns_returns_none(self, dim_set):
        p = InputProjector(dim_set, growth_stage="internalize")
        assert p._project_with_patterns("anything") is None

    def test_keyword_match(self, dim_set):
        p = InputProjector(dim_set, growth_stage="internalize")
        p.learn_pattern("deep learning model", CognitiveState.from_values([1, 1, 0, 0, 0, 0, 0, 0, 0]))
        result = p._project_with_patterns("deep learning is great")
        assert result is not None
        assert result.source == "pattern"

    def test_no_keyword_overlap(self, dim_set):
        p = InputProjector(dim_set, growth_stage="internalize")
        p.learn_pattern("alpha beta gamma", CognitiveState.from_values([1, 1, 1, 0, 0, 0, 0, 0, 0]))
        result = p._project_with_patterns("completely different words")
        assert result is None

    def test_best_match_selected(self, dim_set):
        p = InputProjector(dim_set, growth_stage="internalize")
        p.learn_pattern("foo bar", CognitiveState.from_values([1, 1, 0, 0, 0, 0, 0, 0, 0]))
        p.learn_pattern("foo bar baz qux", CognitiveState.from_values([-1, -1, 0, 0, 0, 0, 0, 0, 0]))
        # "foo bar baz qux" has 4 keyword overlap vs 2
        result = p._project_with_patterns("foo bar baz qux test")
        assert result is not None
        assert result.state.values[0] == -1  # second pattern wins


# ---------------------------------------------------------------------------
# learn_pattern
# ---------------------------------------------------------------------------

class TestLearnPattern:
    def test_stores_pattern(self, dim_set):
        p = InputProjector(dim_set, growth_stage="school")
        p.learn_pattern("hello world", CognitiveState.from_values([1, -1] * 4 + [0]))
        assert p.pattern_count == 1

    def test_keyword_extraction(self, dim_set):
        p = InputProjector(dim_set, growth_stage="school")
        # Short words (<=2 chars) should be filtered out
        p.learn_pattern("a hi the test run", CognitiveState.from_values([1] * 9))
        assert p.pattern_count == 1
        # Check stored key excludes short words
        key = list(p._patterns.keys())[0]
        words = key.split()
        for w in words:
            assert len(w) > 2

    def test_multiple_patterns(self, dim_set):
        p = InputProjector(dim_set, growth_stage="school")
        p.learn_pattern("alpha beta", CognitiveState.from_values([1] * 9))
        p.learn_pattern("gamma delta", CognitiveState.from_values([-1] * 9))
        assert p.pattern_count == 2


# ---------------------------------------------------------------------------
# set_growth_stage
# ---------------------------------------------------------------------------

class TestSetGrowthStage:
    def test_valid_stages(self, dim_set):
        p = InputProjector(dim_set)
        for stage in ("school", "internalize", "graduate"):
            p.set_growth_stage(stage)
            assert p.growth_stage == stage

    def test_invalid_stage_raises(self, dim_set):
        p = InputProjector(dim_set)
        with pytest.raises(ValueError, match="Invalid growth stage"):
            p.set_growth_stage("kindergarten")


# ---------------------------------------------------------------------------
# __repr__
# ---------------------------------------------------------------------------

class TestRepr:
    def test_repr(self, dim_set):
        p = InputProjector(dim_set, growth_stage="graduate")
        r = repr(p)
        assert "stage=graduate" in r
        assert "patterns=0" in r

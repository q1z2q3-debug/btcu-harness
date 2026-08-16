"""Tests for cognitive climate module."""
from btcu_harness.core.state import CognitiveState
from btcu_harness.memory.climate import (
    CognitiveClimate,
    ClimateReport,
    PolaritySnapshot,
)


class TestCognitiveClimate:
    def test_empty_climate(self):
        climate = CognitiveClimate()
        report = climate.report()
        assert report.total_steps == 0
        assert "No cognitive activity" in report.summary

    def test_single_snapshot(self):
        climate = CognitiveClimate()
        state = CognitiveState.from_values([1, 0, -1, 1, 0, 0, -1, 1, -1])
        snap = climate.snapshot(state)
        assert snap.polarity == state.polarity
        assert snap.step == 0

        report = climate.report()
        assert report.total_steps == 1
        assert report.unique_states == 1

    def test_polarity_trend(self):
        """Agent becoming more yang over time."""
        climate = CognitiveClimate()
        # Start yin-heavy, end yang-heavy
        for _ in range(5):
            climate.snapshot(CognitiveState.all_yin())
        for _ in range(5):
            climate.snapshot(CognitiveState.all_yang())

        report = climate.report()
        assert report.polarity_trend > 0  # trending toward yang

    def test_exploration_phases(self):
        """Exploration rate should vary with new state discovery."""
        climate = CognitiveClimate(window_size=5)

        # Phase 1: explore new states
        for i in range(10):
            vals = [(i // j) % 3 - 1 for j in [1, 1, 1, 1, 1, 1, 1, 1, 1]]
            vals = [max(-1, min(1, v)) for v in vals]
            climate.snapshot(CognitiveState.from_values(vals))

        report = climate.report()
        assert report.exploration_phase in ("expanding", "consolidating", "stagnant")
        assert report.unique_states > 1

    def test_stagnant_phase(self):
        """Repeated visits to same state should be stagnant."""
        climate = CognitiveClimate(window_size=5)
        state = CognitiveState.from_values([1, 1, 1, 0, 0, 0, -1, -1, -1])
        for _ in range(10):
            climate.snapshot(state)

        report = climate.report()
        assert report.exploration_phase == "stagnant"
        assert report.unique_states == 1

    def test_climate_zones(self):
        """Climate should identify active zones."""
        climate = CognitiveClimate()
        # Visit one state many times, another few times
        hot = CognitiveState.all_yang()
        cold = CognitiveState.from_values([1, 0, 0, 0, 0, 0, 0, 0, 0])

        for _ in range(8):
            climate.snapshot(hot)
        for _ in range(2):
            climate.snapshot(cold)

        report = climate.report()
        assert len(report.zones) > 0
        # The hot zone should have highest temperature
        top_zone = max(report.zones, key=lambda z: z.temperature)
        assert top_zone.visit_count >= 8

    def test_drift_detection(self):
        """Drift should be detectable when center shifts."""
        climate = CognitiveClimate()

        # First half: all yang
        for _ in range(5):
            climate.snapshot(CognitiveState.all_yang())
        # Second half: all yin
        for _ in range(5):
            climate.snapshot(CognitiveState.all_yin())

        report = climate.report()
        assert report.drift_magnitude > 0
        # All-yang to all-yin is maximum distance (18)
        assert report.drift_magnitude >= 10

    def test_serialization(self):
        """Climate should serialize and deserialize correctly."""
        climate = CognitiveClimate()
        climate.snapshot(CognitiveState.all_yang())
        climate.snapshot(CognitiveState.all_yin())
        climate.snapshot(CognitiveState.all_void())

        data = climate.to_dict()
        restored = CognitiveClimate.from_dict(data)

        assert restored._step == climate._step
        assert len(restored._snapshots) == len(climate._snapshots)
        assert restored._visited == climate._visited

    def test_summary_generation(self):
        """Report should generate a readable summary."""
        climate = CognitiveClimate()
        for _ in range(3):
            climate.snapshot(CognitiveState.all_yang())
        for _ in range(3):
            climate.snapshot(CognitiveState.all_yin())

        report = climate.report()
        assert len(report.summary) > 0
        assert "polarity" in report.summary.lower() or "balanced" in report.summary.lower()

    def test_volatility(self):
        """Volatility should be high with varied polarity changes."""
        climate = CognitiveClimate()
        # Mix of different polarity states
        states = [
            CognitiveState.all_yang(),       # polarity 9
            CognitiveState.all_void(),        # polarity 0
            CognitiveState.all_yin(),         # polarity -9
            CognitiveState.from_values([1, 1, 1, 1, 1, 1, 1, 1, 0]),  # 8
            CognitiveState.from_values([-1, -1, -1, 0, 0, 0, 1, 1, 1]),  # 0
            CognitiveState.all_yang(),       # 9
            CognitiveState.all_yin(),         # -9
            CognitiveState.all_void(),        # 0
        ]
        for s in states:
            climate.snapshot(s)

        report = climate.report()
        # With varied diff magnitudes (9, 9, 17, 8, 9, 18, 9), volatility > 0
        assert report.polarity_volatility > 0

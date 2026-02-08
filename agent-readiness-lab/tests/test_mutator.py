"""Tests for trace mutator determinism."""

import pytest

import sys
sys.path.insert(0, "packages")

from arlab.traces import (
    Session,
    Step,
    ActionType,
    TraceMutator,
    MutationConfig,
)


class TestMutatorDeterminism:
    """Tests for mutator determinism."""

    def test_same_seed_same_result(self):
        """Test that the same seed produces the same mutations."""
        session = Session(
            session_id="test_001",
            goal="Test determinism",
            steps=[
                Step(ts=0, action=ActionType.GOTO, url="http://example.com"),
                Step(ts=1, action=ActionType.CLICK, selector="#btn"),
                Step(ts=2, action=ActionType.TYPE, selector="input", text="test"),
            ],
        )

        mutator1 = TraceMutator(seed=12345)
        mutator2 = TraceMutator(seed=12345)

        result1 = mutator1.mutate(session)
        result2 = mutator2.mutate(session)

        assert len(result1.steps) == len(result2.steps)
        for s1, s2 in zip(result1.steps, result2.steps):
            assert s1.ts == s2.ts
            assert s1.action == s2.action
            assert s1.selector == s2.selector

    def test_different_seed_different_result(self):
        """Test that different seeds produce different mutations."""
        session = Session(
            session_id="test_002",
            goal="Test different seeds",
            steps=[
                Step(ts=0, action=ActionType.GOTO, url="http://example.com"),
                Step(ts=1, action=ActionType.CLICK, selector="#btn"),
                Step(ts=2, action=ActionType.TYPE, selector="input", text="test"),
                Step(ts=3, action=ActionType.SUBMIT, selector="form"),
                Step(ts=4, action=ActionType.WAIT),
            ],
        )

        # Use high mutation rates to ensure differences
        config = MutationConfig(
            timing_jitter_ms=(100, 1000),
            misclick_probability=0.5,
            extra_wait_probability=0.5,
        )

        mutator1 = TraceMutator(seed=11111, config=config)
        mutator2 = TraceMutator(seed=99999, config=config)

        result1 = mutator1.mutate(session)
        result2 = mutator2.mutate(session)

        # At least timing should differ
        times1 = [s.ts for s in result1.steps]
        times2 = [s.ts for s in result2.steps]

        assert times1 != times2

    def test_session_id_affects_mutations(self):
        """Test that session ID affects mutation outcomes."""
        session1 = Session(
            session_id="session_a",
            goal="Test",
            steps=[Step(ts=i, action=ActionType.CLICK, selector=f"#btn{i}") for i in range(10)],
        )
        session2 = Session(
            session_id="session_b",
            goal="Test",
            steps=[Step(ts=i, action=ActionType.CLICK, selector=f"#btn{i}") for i in range(10)],
        )

        config = MutationConfig(timing_jitter_ms=(100, 500))
        mutator = TraceMutator(seed=42, config=config)

        result1 = mutator.mutate(session1)
        result2 = mutator.mutate(session2)

        # Same seed but different session IDs should produce different results
        times1 = [s.ts for s in result1.steps]
        times2 = [s.ts for s in result2.steps]

        assert times1 != times2


class TestMutatorBehavior:
    """Tests for mutator behavior."""

    def test_adds_mutated_tag(self):
        """Test that mutated sessions get the 'mutated' tag."""
        session = Session(
            session_id="test_003",
            goal="Test tags",
            tags=["original"],
            steps=[Step(ts=0, action=ActionType.CLICK, selector="#btn")],
        )

        mutator = TraceMutator(seed=42)
        result = mutator.mutate(session)

        assert "mutated" in result.tags
        assert "original" in result.tags

    def test_mutation_summary(self):
        """Test getting mutation summary."""
        session = Session(
            session_id="test_004",
            goal="Test summary",
            steps=[
                Step(ts=0, action=ActionType.CLICK, selector="#btn"),
                Step(ts=1, action=ActionType.TYPE, selector="input", text="test"),
            ],
        )

        # Use config that guarantees some mutations
        config = MutationConfig(
            extra_wait_probability=1.0,  # Always add waits
            timing_jitter_ms=(0, 0),
        )
        mutator = TraceMutator(seed=42, config=config)
        result = mutator.mutate(session)

        summary = mutator.get_mutation_summary(session, result)

        assert "original_steps" in summary
        assert "mutated_steps" in summary
        assert summary["original_steps"] == 2
        assert summary["extra_waits"] >= 0

    def test_abandonment_flag(self):
        """Test that abandoned sessions get proper tag."""
        session = Session(
            session_id="test_005",
            goal="Test abandonment",
            steps=[Step(ts=i, action=ActionType.CLICK, selector=f"#btn{i}") for i in range(50)],
        )

        # Force abandonment
        config = MutationConfig(abandonment_probability=1.0)
        mutator = TraceMutator(seed=42, config=config)
        result = mutator.mutate(session)

        assert "abandoned" in result.tags
        assert len(result.steps) < len(session.steps)

    def test_no_mutation_preserves_steps(self):
        """Test that zero probabilities preserve original steps."""
        session = Session(
            session_id="test_006",
            goal="Test no mutation",
            steps=[
                Step(ts=0, action=ActionType.GOTO, url="http://example.com"),
                Step(ts=1, action=ActionType.CLICK, selector="#btn"),
            ],
        )

        config = MutationConfig(
            timing_jitter_ms=(0, 0),
            misclick_probability=0.0,
            back_navigation_probability=0.0,
            alternate_selector_probability=0.0,
            retry_on_failure_probability=0.0,
            abandonment_probability=0.0,
            extra_wait_probability=0.0,
        )
        mutator = TraceMutator(seed=42, config=config)
        result = mutator.mutate(session)

        assert len(result.steps) == len(session.steps)
        for orig, mut in zip(session.steps, result.steps):
            assert orig.action == mut.action
            assert orig.selector == mut.selector

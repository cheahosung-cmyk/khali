"""Tests for Loop Engineering components."""

import pytest

from src.loop.action import ActionResult, ActionStatus, FunctionAction
from src.loop.engine import LoopEngine, LoopStatus
from src.loop.memory import LoopMemory
from src.loop.observer import LoopObserver
from src.loop.stop import (
    BudgetStopCondition,
    CompositeStopCondition,
    MaxIterationsStopCondition,
    TestPassStopCondition,
)
from src.loop.trigger import AlwaysTrigger, EventTrigger, ManualTrigger
from src.loop.verifier import TestSuiteVerifier
from src.budget.tracker import BudgetExceeded, BudgetTracker


# ---------------------------------------------------------------------------
# Trigger tests
# ---------------------------------------------------------------------------

class TestManualTrigger:
    def test_does_not_fire_before_armed(self):
        t = ManualTrigger()
        assert not t.should_fire({})

    def test_fires_once_after_arm(self):
        t = ManualTrigger()
        t.arm()
        assert t.should_fire({})
        assert not t.should_fire({})


class TestEventTrigger:
    def test_fires_on_key_present(self):
        t = EventTrigger("ready")
        assert t.should_fire({"ready": True})

    def test_does_not_fire_on_missing_key(self):
        t = EventTrigger("ready")
        assert not t.should_fire({})

    def test_does_not_fire_on_falsy_value(self):
        t = EventTrigger("ready")
        assert not t.should_fire({"ready": False})


# ---------------------------------------------------------------------------
# Stop condition tests
# ---------------------------------------------------------------------------

class TestBudgetStopCondition:
    def test_stops_when_budget_exceeded(self):
        cond = BudgetStopCondition(max_cost=1.0)
        assert cond.should_stop({"total_cost": 1.0})

    def test_does_not_stop_within_budget(self):
        cond = BudgetStopCondition(max_cost=1.0)
        assert not cond.should_stop({"total_cost": 0.5})


class TestMaxIterationsStopCondition:
    def test_stops_at_limit(self):
        cond = MaxIterationsStopCondition(max_iterations=3)
        assert cond.should_stop({"iteration": 3})

    def test_does_not_stop_before_limit(self):
        cond = MaxIterationsStopCondition(max_iterations=3)
        assert not cond.should_stop({"iteration": 2})


class TestTestPassStopCondition:
    def test_stops_when_tests_pass(self):
        cond = TestPassStopCondition(test_fn=lambda ctx: True)
        assert cond.should_stop({})

    def test_does_not_stop_when_tests_fail(self):
        cond = TestPassStopCondition(test_fn=lambda ctx: False)
        assert not cond.should_stop({})

    def test_stops_only_when_both_pass_with_regression(self):
        cond = TestPassStopCondition(
            test_fn=lambda ctx: True,
            regression_fn=lambda ctx: ctx.get("regression_ok", False),
        )
        assert not cond.should_stop({"regression_ok": False})
        assert cond.should_stop({"regression_ok": True})


class TestCompositeStopCondition:
    def test_stops_on_first_matching_condition(self):
        cond = CompositeStopCondition(
            BudgetStopCondition(max_cost=0.1),
            MaxIterationsStopCondition(max_iterations=10),
        )
        assert cond.should_stop({"total_cost": 0.5, "iteration": 0})

    def test_does_not_stop_when_none_trigger(self):
        cond = CompositeStopCondition(
            BudgetStopCondition(max_cost=10.0),
            MaxIterationsStopCondition(max_iterations=10),
        )
        assert not cond.should_stop({"total_cost": 0.5, "iteration": 5})


# ---------------------------------------------------------------------------
# Memory tests
# ---------------------------------------------------------------------------

class TestLoopMemory:
    def test_tracks_iteration_count(self):
        mem = LoopMemory()
        it = mem.start_iteration()
        mem.complete_iteration(it, ActionResult(status=ActionStatus.SUCCESS, cost=0.1))
        assert mem.iteration_count == 1

    def test_accumulates_cost(self):
        mem = LoopMemory()
        for _ in range(3):
            it = mem.start_iteration()
            mem.complete_iteration(it, ActionResult(status=ActionStatus.SUCCESS, cost=0.5))
        assert mem.total_cost == pytest.approx(1.5)

    def test_records_failures(self):
        mem = LoopMemory()
        it = mem.start_iteration()
        mem.complete_iteration(it, ActionResult(status=ActionStatus.FAILURE, error="oops"))
        assert len(mem.failed_attempts()) == 1

    def test_context_includes_iteration_and_cost(self):
        mem = LoopMemory()
        it = mem.start_iteration()
        mem.complete_iteration(it, ActionResult(status=ActionStatus.SUCCESS, cost=0.2))
        ctx = mem.to_context()
        assert ctx["iteration"] == 1
        assert ctx["total_cost"] == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# Verifier tests
# ---------------------------------------------------------------------------

class TestTestSuiteVerifier:
    def test_passes_when_fn_returns_true(self):
        v = TestSuiteVerifier(test_fn=lambda out, ctx: True)
        result = v.verify("output", {})
        assert result.passed

    def test_fails_when_fn_returns_false(self):
        v = TestSuiteVerifier(test_fn=lambda out, ctx: False)
        result = v.verify("output", {})
        assert not result.passed

    def test_numeric_score_threshold(self):
        v = TestSuiteVerifier(test_fn=lambda out, ctx: 0.8, pass_threshold=0.9)
        result = v.verify("output", {})
        assert not result.passed

        v2 = TestSuiteVerifier(test_fn=lambda out, ctx: 0.95, pass_threshold=0.9)
        result2 = v2.verify("output", {})
        assert result2.passed


# ---------------------------------------------------------------------------
# Budget tracker tests
# ---------------------------------------------------------------------------

class TestBudgetTracker:
    def test_tracks_spending(self):
        bt = BudgetTracker(limit=1.0)
        bt.record(0, 0.3)
        bt.record(1, 0.3)
        assert bt.spent == pytest.approx(0.6)

    def test_raises_on_exceeded(self):
        bt = BudgetTracker(limit=0.5)
        with pytest.raises(BudgetExceeded):
            bt.record(0, 1.0)

    def test_remaining_decreases(self):
        bt = BudgetTracker(limit=1.0)
        bt.record(0, 0.4)
        assert bt.remaining == pytest.approx(0.6)

    def test_is_exhausted(self):
        bt = BudgetTracker(limit=0.5)
        try:
            bt.record(0, 0.5)
        except BudgetExceeded:
            pass
        assert bt.is_exhausted


# ---------------------------------------------------------------------------
# Full loop engine integration test
# ---------------------------------------------------------------------------

class TestLoopEngine:
    def test_runs_until_max_iterations(self):
        call_count = 0

        def counter_action(ctx):
            nonlocal call_count
            call_count += 1
            return ActionResult(status=ActionStatus.SUCCESS, cost=0.0)

        engine = LoopEngine(
            trigger=AlwaysTrigger(),
            action=FunctionAction("counter", counter_action),
            stop_condition=MaxIterationsStopCondition(max_iterations=5),
        )
        result = engine.run()
        assert result.status == LoopStatus.STOPPED
        assert call_count == 5

    def test_stops_on_budget(self):
        def expensive_action(ctx):
            return ActionResult(status=ActionStatus.SUCCESS, cost=0.4)

        engine = LoopEngine(
            trigger=AlwaysTrigger(),
            action=FunctionAction("expensive", expensive_action),
            stop_condition=CompositeStopCondition(
                BudgetStopCondition(max_cost=1.0),
                MaxIterationsStopCondition(max_iterations=100),
            ),
        )
        result = engine.run()
        assert result.status == LoopStatus.STOPPED
        assert result.total_cost >= 1.0

    def test_verifier_rejection_counts_as_failure(self):
        call_count = [0]

        def action_fn(ctx):
            return ActionResult(status=ActionStatus.SUCCESS, output="draft", cost=0.1)

        def check_fn(out, ctx):
            call_count[0] += 1
            return call_count[0] > 2  # fail on calls 1-2, pass from call 3 onward

        verifier = TestSuiteVerifier(test_fn=check_fn)

        engine = LoopEngine(
            trigger=AlwaysTrigger(),
            action=FunctionAction("draft", action_fn),
            stop_condition=MaxIterationsStopCondition(max_iterations=10),
            verifier=verifier,
        )
        engine.run()
        failures = engine.memory.failed_attempts()
        assert len(failures) == 2

    def test_observer_records_all_iterations(self):
        engine = LoopEngine(
            trigger=AlwaysTrigger(),
            action=FunctionAction("noop", lambda ctx: ActionResult(status=ActionStatus.SUCCESS)),
            stop_condition=MaxIterationsStopCondition(max_iterations=3),
        )
        result = engine.run()
        assert len(result.observation_summary) == 3

    def test_manual_trigger_controls_iterations(self):
        trigger = ManualTrigger()
        call_count = 0

        def action_fn(ctx):
            nonlocal call_count
            call_count += 1
            return ActionResult(status=ActionStatus.SUCCESS)

        engine = LoopEngine(
            trigger=trigger,
            action=FunctionAction("manual", action_fn),
            stop_condition=MaxIterationsStopCondition(max_iterations=5),
            poll_interval_seconds=0.0,
        )

        trigger.arm()
        trigger.arm()

        result = engine.run(max_wall_seconds=0.5)
        assert call_count == 2

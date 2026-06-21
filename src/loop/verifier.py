"""Verifier component — the AI that *grades*, not the one that *builds*.

The key distinction: the agent that produces output must not also evaluate it.
Separate verification prevents self-confirming hallucinations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class VerificationResult:
    passed: bool
    score: float = 0.0
    details: str = ""
    metadata: dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class Verifier(ABC):
    """Base class for output verifiers."""

    @abstractmethod
    def verify(self, action_output: Any, context: dict[str, Any]) -> VerificationResult:
        """Evaluate the action output and return a structured result."""


class SuiteVerifier(Verifier):
    """Runs a callable test suite and treats pass/fail as the verification signal."""

    def __init__(self, test_fn, pass_threshold: float = 1.0):
        self._test_fn = test_fn
        self._threshold = pass_threshold

    def verify(self, action_output: Any, context: dict[str, Any]) -> VerificationResult:
        result = self._test_fn(action_output, context)
        if isinstance(result, bool):
            score = 1.0 if result else 0.0
        else:
            score = float(result)
        passed = score >= self._threshold
        return VerificationResult(
            passed=passed,
            score=score,
            details=f"score={score:.2f} threshold={self._threshold:.2f}",
        )


# Alias for backward compatibility
TestSuiteVerifier = SuiteVerifier


class ThresholdVerifier(Verifier):
    """Accepts any numeric score above a threshold."""

    def __init__(self, score_fn, threshold: float):
        self._score_fn = score_fn
        self._threshold = threshold

    def verify(self, action_output: Any, context: dict[str, Any]) -> VerificationResult:
        score = float(self._score_fn(action_output, context))
        passed = score >= self._threshold
        return VerificationResult(
            passed=passed,
            score=score,
            details=f"score={score:.3f} threshold={self._threshold:.3f}",
        )

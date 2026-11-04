"""BaseEvaluator: the contract every business rule follows."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import RuleContext, RuleOutcome


class BaseEvaluator(ABC):
    """INTERFACE for one business rule (Strategy pattern).

    LogicManager only ever talks to this type. It calls ``evaluate()`` on
    every rule in the same way and never checks which rule it has. That is
    why a new rule can be added without changing LogicManager (Open/Closed).

    Every subclass must keep this contract, so that any rule can stand in
    for any other (Liskov Substitution):

    * ``name`` is a short, unique string that never changes.
    * ``evaluate(context)`` only reads ``context``. It never changes it,
      prints, saves or calls the network, and it gives the same outcome
      every time for the same context.
    * It always returns a RuleOutcome whose ``rule_name`` equals ``name``.
    * It does not raise for a valid context. Rejecting a whole record is
      LogicManager's job, not a rule's.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """The rule's name, used in RuleOutcome and in the stored record."""

    @abstractmethod
    def evaluate(self, context: RuleContext) -> RuleOutcome:
        """Decide what this rule means for one record."""

"""Game-owned behavior required by the shared casino treasury and settlement services."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


class RandomSource(Protocol):
    def below(self, bound: int) -> int: ...


@dataclass(frozen=True)
class GameRules(ABC):
    game: str
    version: int
    name: str
    max_multiplier: int
    house_edge: float
    catalog_multiplier: int
    settlement_mode: str = 'instant'

    def validate_amount(self, amount: int) -> None:
        """Validate game-specific stake denominations before any money is moved."""

    def minimum_bet(self, configured: int) -> int:
        """Return the first playable denomination at or above the configured minimum."""
        return configured

    def public_result(self, bet) -> dict:
        """Only settled instant outcomes are public. Interactive games must redact their state."""
        return bet.result if bet.status == 'settled' else {}

    def start_bet(self, *, fund, bet, wallet) -> None:
        """Interactive acceptance hook, under the casino fund, bet and wallet locks."""
        raise ValueError('This game does not support interactive play.')

    def act(self, *, user, request_id, action_id, action, expected_revision):
        """Game-owned action handler; must enforce ownership, locking and idempotency."""
        raise ValueError('This game does not support interactive play.')

    @abstractmethod
    def normalize_selection(self, selection) -> dict:
        """Return the canonical selection used by idempotency and historical receipts."""

    @abstractmethod
    def multiplier(self, selection: dict) -> int:
        """Maximum total-return multiplier for this selection, including the stake."""

    @abstractmethod
    def outcome(self, random: RandomSource, selection: dict) -> dict:
        """Produce a deterministic result containing its total-return multiplier."""

    def prepare_selection(self, selection, amount: int) -> dict:
        """Canonical selection for a wager of `amount`. Override when the selection itself carries stakes."""
        return self.normalize_selection(selection)

    def exposure(self, selection: dict, amount: int) -> int:
        """Largest net amount this wager can cost the casino beyond its own stake; never negative."""
        return (self.multiplier(selection) - 1) * amount

    def payout(self, amount: int, result: dict) -> int:
        """Total returned for a result this ruleset produced, including the stake."""
        return amount * result['multiplier']

    @abstractmethod
    def catalog_data(self, maximum_bet: Callable[[int], int]) -> dict:
        """Game-specific public metadata; the casino supplies the treasury limit calculation."""

    @abstractmethod
    def verify(self) -> None:
        """Validate installed game math without touching any financial state; raise ValueError on failure."""


@dataclass(frozen=True)
class GameDefinition:
    game: str
    rules: tuple[GameRules, ...]
    default_version: int = 1
    default_min_bet: int = 1
    catalog_order: int = 100

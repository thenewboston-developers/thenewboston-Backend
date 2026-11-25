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

    @abstractmethod
    def normalize_selection(self, selection) -> dict:
        """Return the canonical selection used by idempotency and historical receipts."""

    @abstractmethod
    def multiplier(self, selection: dict) -> int:
        """Maximum total-return multiplier for this selection, including the stake."""

    @abstractmethod
    def outcome(self, random: RandomSource, selection: dict) -> dict:
        """Produce a deterministic result containing its total-return multiplier."""

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

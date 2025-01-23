from __future__ import annotations

from abc import ABC, abstractmethod
from asyncio import Lock
from datetime import datetime, timedelta
from types import TracebackType
from typing import Optional, Type

from utils.ParamsUtils import CURRENCY_NAME_GOLD
from world.cultivation import CultivationStage


class Character(ABC):
    def __init__(self):
        super().__init__()
        self._lock: Lock = Lock()

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"Character {{id: {self.id}}}"

    def __str__(self):
        return self.__repr__()

    def __hash__(self) -> int:
        return hash(self.id) * 17

    def __eq__(self, other):
        return other is not None and type(other) is type(self) and self.id == other.id

    def __ne__(self, other):
        return not self.__eq__(other)

    async def __aenter__(self) -> Character:
        await self._lock.acquire()

        return self

    async def __aexit__(self, exc_type: Optional[Type], exc_val: BaseException, exc_tb: Optional[TracebackType]):
        try:
            if exc_type is None:
                await self.persist()
        finally:
            self._lock.release()

    # ================================================ Properties ===============================================

    @property
    @abstractmethod
    def claimed_daily(self) -> bool:
        pass

    @claimed_daily.setter
    @abstractmethod
    def claimed_daily(self, claimed: bool) -> None:
        pass

    @property
    @abstractmethod
    def cultivation(self) -> CultivationStage:
        pass

    @property
    @abstractmethod
    def cultivation_cooldown(self) -> Optional[datetime]:
        pass

    @cultivation_cooldown.setter
    @abstractmethod
    def cultivation_cooldown(self, new_cooldown: Optional[datetime]) -> None:
        pass

    @property
    @abstractmethod
    def current_experience(self) -> int:
        pass

    @property
    @abstractmethod
    def current_arena_coins(self) -> int:
        pass

    @property
    @abstractmethod
    def current_gold(self) -> int:
        pass

    @property
    @abstractmethod
    def energy(self) -> int:
        pass

    @property
    @abstractmethod
    def id(self) -> int:
        pass

    @property
    @abstractmethod
    def is_missing_energy(self) -> bool:
        pass

    @property
    @abstractmethod
    def maximum_energy(self) -> int:
        pass

    @property
    @abstractmethod
    def missing_energy(self) -> int:
        pass

    @property
    @abstractmethod
    def total_experience(self) -> int:
        pass

    # ============================================== "Real" methods =============================================

    @abstractmethod
    async def acquire_loot(self, loot: dict[str, int]) -> None:
        pass

    @abstractmethod
    def add_energy(self, amount: int, ignore_cap: bool = True) -> tuple[int, bool]:
        pass

    @abstractmethod
    async def add_experience(self, base_amount: int, apply_bonus: bool = True, message_cooldown: Optional[timedelta] = None) -> tuple[int, int]:
        pass

    @abstractmethod
    def add_funds(self, amount: int, currency: str = CURRENCY_NAME_GOLD) -> None:
        pass

    @abstractmethod
    def alter_energy_by(self, amount: int, ignore_cap: bool = False) -> tuple[int, bool]:
        pass

    @abstractmethod
    def balance(self, currency: str = CURRENCY_NAME_GOLD) -> int:
        pass

    @abstractmethod
    def consume_energy(self, amount: int, force: bool = False) -> bool:
        pass

    @abstractmethod
    def demote(self, times: int) -> CultivationStage:
        pass

    @abstractmethod
    def get_funds(self, currency: str = CURRENCY_NAME_GOLD) -> int:
        pass

    @abstractmethod
    def promote(self, times: int) -> CultivationStage:
        pass

    @abstractmethod
    def regen_energy(self, amount: int = 1) -> tuple[int, bool]:
        pass

    @abstractmethod
    def remove_funds(self, amount: int, currency: str = CURRENCY_NAME_GOLD) -> bool:
        pass

    @abstractmethod
    def spend_funds(self, amount: int, currency: str = CURRENCY_NAME_GOLD) -> bool:
        pass

    @abstractmethod
    def remove_experience(self, amount: int) -> int:
        pass

    @abstractmethod
    def set_current_experience(self, amount: int) -> int:
        pass

    @abstractmethod
    def set_energy(self, new_energy: int, ignore_cap: bool = False) -> tuple[int, bool]:
        pass

    @abstractmethod
    async def start_cultivating_exp(self) -> tuple[bool, Optional[str]]:
        pass

    @abstractmethod
    async def persist(self):
        pass

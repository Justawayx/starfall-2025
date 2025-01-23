from __future__ import annotations

import json
import math
import random
from abc import ABC, abstractmethod
from functools import reduce
from typing import Optional, TypeVar, Generic, Union, Iterable, Callable, Any, Type

import disnake
from disnake import Interaction

from utils.base import UnsupportedOperationError, PlayerInputException

K = TypeVar("K")
D = TypeVar("D", bound="LootDistributionLogic")
L = TypeVar("L", bound="Loot")
T = TypeVar("T")

PSEUDO_ITEM_ID_ENERGY_FLAT: str = "_energy_flat_"
PSEUDO_ITEM_ID_ENERGY_RATIO: str = "_energy_ratio_"
PSEUDO_ITEM_ID_EXP_FLAT: str = "_exp_flat_"
PSEUDO_ITEM_ID_EXP_RATIO: str = "_exp_ratio_"
PSEUDO_ITEM_ID_GOLD: str = "_gold_"
PSEUDO_ITEM_ID_ARENA_COIN: str = "_ac_"
PSEUDO_ITEM_ID_STAR: str = "_star_"
PSEUDO_ITEM_IDS: set[str] = {PSEUDO_ITEM_ID_ENERGY_FLAT, PSEUDO_ITEM_ID_ENERGY_RATIO, PSEUDO_ITEM_ID_EXP_FLAT, PSEUDO_ITEM_ID_EXP_RATIO, PSEUDO_ITEM_ID_GOLD, PSEUDO_ITEM_ID_ARENA_COIN, PSEUDO_ITEM_ID_STAR}

RELATIVE_EXP_VALUE_FACTOR: int = 10000

MODE_RANDOM: int = 0
MODE_SPREAD: int = 1
MODE_EVERYONE: int = 2
DEFAULT_MODE: int = MODE_RANDOM


class WeightedChoice(Generic[T]):
    def __init__(self, choices: Optional[dict[T, int]]):
        """
        Create a weighted choice that can randomly choose elements based on a weighted distribution. Choices can bet set and altered like a dict

        Parameters
        ----------
        choices: dict[T, int], optional
                 The initial valid choice and their weight
        """
        super().__init__()
        if choices is None:
            self._choices: dict[T, int] = {}
            self._total_weight = 0
        else:
            self._choices: dict[T, int] = choices.copy()
            self._total_weight = sum(self._choices.values())

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"WeightedChoice {self._choices}"

    def __str__(self):
        percent_str: dict[T, str] = {choice: f"{chance:.1f}%" for choice, chance in self.as_percentages().items()}
        return f"WeightedChoice: {percent_str}"

    def __add__(self, choices: Union[WeightedChoice, dict[T, int]]) -> WeightedChoice:
        return self.add(choices)

    def __contains__(self, choice: T):
        return choice in self._choices

    def __delitem__(self, choice: T):
        self.pop(choice)

    def __getitem__(self, choice: T) -> Optional[int]:
        return self._choices.get(choice, None)

    def __len__(self) -> int:
        return len(self._choices)

    def __setitem__(self, choice: T, value: Optional[int]):
        if value is None or value <= 0:
            if choice in self._choices:
                self._choices.pop(choice)
                self._recompute_total()
        else:
            self._choices[choice] = value
            self._recompute_total()

    # ================================================ Properties ===============================================

    @property
    def choices(self) -> dict[T, int]:
        return self._choices.copy()

    @property
    def possible_choices(self) -> dict[T, int]:
        return {choice: weight for choice, weight in self._choices.items() if weight > 0}

    @property
    def total_weight(self) -> int:
        return self._total_weight

    @property
    def valid(self) -> bool:
        return len([weight for weight in self._choices.values() if weight > 0]) > 0

    # ============================================== "Real" methods =============================================

    def add(self, choices: Union[WeightedChoice, dict[T, int]]) -> WeightedChoice:
        choices_1: dict[T, int] = self._choices.copy()
        if isinstance(choices, WeightedChoice):
            choices_2: dict[T, int] = choices._choices
        else:
            # Assuming dict[T, int]
            choices_2: dict[T, int] = choices

        # Reusing loot merge function to actually combine the dict since it's the same logic
        choices_1 = merge_loot(choices_1, choices_2)

        return WeightedChoice(choices_1)

    def as_percentages(self) -> dict[T, float]:
        return {choice: weight / self._total_weight * 100.0 for choice, weight in self._choices.items() if weight > 0}

    def choose(self) -> Optional[T]:
        if len(self._choices) == 0:
            return None

        possible_choices = {choice: weight for choice, weight in self._choices.items() if weight > 0}
        if len(possible_choices) == 0:
            return None

        return roll_from_weighted_dict(possible_choices)

    def copy(self) -> WeightedChoice:
        return WeightedChoice(self._choices)

    def get(self, choice: T, default: int = 0) -> int:
        return self._choices.get(choice, default)

    def chances_to_choose(self, value: T) -> float:
        """
        Determines the [0.0, 1.0] chances that this choice choose the specified value.

        Parameters
        ----------
        value: T
               The value whose % chance to happen has to be computed

        Returns
        -------
        float
            The [0.0, 1.0] chance of the specified value to be selected by this choice
        """
        if value not in self._choices:
            return 0.0

        choice_chance: int = self._choices[value]
        return float(choice_chance) / self._total_weight

    def chances_to_not_choose(self, value: T) -> float:
        """
        Determines the [0.0, 1.0] chances that this choice does NOT choose the specified value.

        Parameters
        ----------
        value: T
               The value whose % chance to not happen has to be computed

        Returns
        -------
        float
            The [0.0, 1.0] chance of the specified value to not be selected by this choice
        """
        return 1.0 - self.chances_to_choose(value)

    def pop(self, choice: T, default: Optional[T] = None) -> Optional[T]:
        if choice in self._choices:
            previous: T = self._choices.pop(choice)
            self._recompute_total()
            return previous
        else:
            return default

    def _recompute_total(self):
        self._total_weight = sum([weight for weight in self._choices.values() if weight > 0])


class Loot(ABC):
    def __init__(self):
        super().__init__()

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"Loot"

    def __str__(self) -> str:
        return self.__repr__()

    def __add__(self, other) -> Loot:
        return self.__and__(other)

    def __and__(self, other) -> Loot:
        if other is None:
            return self

        return CompositeLoot([self, other])

    def __or__(self, other) -> Loot:
        if other is None:
            return self

        return ChoiceLoot([self, other])

    # ================================================ Properties ===============================================

    @property
    def single_item_id(self) -> bool:
        return False

    @property
    def distinct_item_ids(self) -> bool:
        return False

    # ============================================= Abstract methods ============================================

    @abstractmethod
    def drop_chance(self, item_id: str) -> float:
        """
        Compute the chance of at least one of the specified item to drop from this loot

        Parameters
        ----------
        item_id: str
                 The item identifier to get the drop chance for

        Returns
        -------
        float
            The [0.0, 1.0] chance of the specified item to drop at least once from this loot
        """
        pass

    @abstractmethod
    def _roll_once(self) -> dict[str, int]:
        pass

    # ============================================== "Real" methods =============================================

    def can_drop(self, item_id: str) -> bool:
        """
        Determines if this Loot instance can drop the specified item. The default implementation of this method calls self.drop_chance(item_id) and return True if the result is > 0.0. Subclasses are encouraged to override this method if the test can
        be performed faster

        Parameters
        ----------
        item_id: str
                 The item identifier to test

        Returns
        -------
        bool
            True if this Loot can drop the specified item, False otherwise
        """
        return self.drop_chance(item_id) > 0.0

    def roll(self, times: int = 1) -> dict[str, int]:
        """
        Generate random loot up to the specified number of times.

        Parameters
        ----------
        times: int
               The number of times the loot should be generated. Default: 1

        Returns
        -------
        dict[str, int]
            The generated loot in a <item_id>: <quantity> association dictionary

        Raises
        ------
        ValueError
            If times is negative
        """
        _validate_positive(times, "times")

        loot: dict[str, int] = {}
        for _ in range(0, times):
            merge_loot(loot, self._roll_once())

        return loot

    @staticmethod
    def _as_weighted_choices(fixed_choice: Optional[K] = None, choices: Optional[WeightedChoice[K]] = None, choices_dict: Optional[dict[K, int]] = None) -> Optional[WeightedChoice[K]]:
        if choices is not None and len(choices) > 0:
            return choices.copy()

        if choices_dict is not None:
            weighted_choice: WeightedChoice[str] = WeightedChoice(choices_dict)
            if len(weighted_choice) > 0:
                return weighted_choice

        if fixed_choice is not None:
            return WeightedChoice({fixed_choice: 1})

        return None

    def serialize(self) -> dict[str, Any]:
        serialized: dict[str, Any] = {
            "type": type(self).__name__,
            "data": self._serialize_data()
        }

        return serialized

    @abstractmethod
    def _serialize_data(self) -> Any:
        pass

    @staticmethod
    def deserialize(data: Optional[dict[str, Any]]) -> Optional[L]:
        if data is None:
            return None

        type_name: str = data["type"]
        loot_data: Any = data["data"]
        clazz: Type[L] = globals()[type_name]
        if hasattr(clazz, "_deserialize_data") and issubclass(clazz, Loot):
            return clazz._deserialize_data(loot_data)

        raise UnsupportedOperationError(f"Trying to deserialize an abstract loot type {clazz}")

    @staticmethod
    def _deserialize_data(data: Any) -> L:
        raise UnsupportedOperationError("Trying to deserialize an abstract loot type")


class EmptyLoot(Loot):
    def __init__(self):
        """
        Create a new loot that yields nothing.
        """
        super().__init__()

    # ============================================= Special methods =============================================

    def __repr__(self):
        return "EmptyLoot"

    def __str__(self) -> str:
        return "Nothing"

    # ================================================ Properties ===============================================

    @property
    def quantity(self) -> int:
        return 0

    # ============================================== "Real" methods =============================================

    def can_drop(self, item_id: str) -> bool:
        return False

    def drop_chance(self, item_id: str) -> float:
        return 0.0

    def _roll_once(self) -> dict[str, int]:
        return {}

    @staticmethod
    def _deserialize_data(data: dict[str, Any]) -> Loot:
        return EmptyLoot()

    def _serialize_data(self) -> Any:
        return ""


class FixedLoot(Loot):
    def __init__(self, item_id: str, quantity: int = 1):
        """
        Create a new loot that yields a fixed quantity of a fixed item without any random element whatsoever.
        
        This class should be used when you want to always drop a fixed quantity of a fixed item. For example, always drop 2x scales_1

        Parameters
        ----------
        item_id: str
                 Identifier of the item dropped by this loot.
        quantity: int
                  Number of items drop per roll by this loot. Default = 1

        Raises
        ------
        ValueError
            if quantity is negative
        """
        super().__init__()

        _validate_positive(quantity, "quantity")

        self._item_id: str = item_id
        self._quantity: int = quantity

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"FixedLoot yielding {self._quantity:,} x {self._item_id}"

    def __str__(self) -> str:
        return f"{self._quantity:,}x {self._item_id}"

    # ================================================ Properties ===============================================

    @property
    def item_id(self) -> str:
        return self._item_id

    @property
    def quantity(self) -> int:
        return self._quantity

    @property
    def single_item_id(self) -> bool:
        return True

    @property
    def distinct_item_ids(self) -> bool:
        return False

    # ============================================== "Real" methods =============================================

    def can_drop(self, item_id: str) -> bool:
        return item_id == self._item_id

    def drop_chance(self, item_id: str) -> float:
        return 1.0 if item_id == self._item_id else 0.0

    def _roll_once(self) -> dict[str, int]:
        return {self._item_id: self._quantity}

    @staticmethod
    def _deserialize_data(data: dict[str, Any]) -> Loot:
        item_id: str = data["item_id"]
        quantity: int = data["quantity"]
        return FixedLoot(item_id, quantity)

    def _serialize_data(self) -> Any:
        return {
            "item_id": self._item_id,
            "quantity": self._quantity
        }


class FixedItemLoot(Loot):
    def __init__(self, item_id: str, quantity: dict[int, int]):
        """
        Create a new random loot that can roll a random number of a fixed item type.
        
        This represents the use case where you want to drop 1 to 4 common herb

        Parameters
        ----------
        item_id: str
                 Identifier of the item dropped by this loot.
        quantity: dict[int, int]
                  Number of items drop per roll by this loot in a <quantity>: <weight> association. A given quantity will have <weight>/<total weight> chances to occur.

        Raises
        ------
        ValueError
            if quantity contains only zero or negative weighted values
        """
        super().__init__()

        self._item_id = item_id
        self._quantity = WeightedChoice(quantity)
        if not self._quantity.valid:
            raise ValueError(f"quantity should have selectable (weight > 0) values, found: {quantity}")

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"FixedItemRandomLoot yielding {self._quantity} x {self._item_id}"

    def __str__(self) -> str:
        min_quantity: int = min(self._quantity.possible_choices.keys())
        max_quantity: int = max(self._quantity.possible_choices.keys())

        return f"{min_quantity:,}x {self._item_id}" if max_quantity >= min_quantity else f"[{min_quantity:,}, {max_quantity:,}]x {self._item_id}"

    # ================================================ Properties ===============================================

    @property
    def item_id(self) -> str:
        return self._item_id

    @property
    def single_item_id(self) -> bool:
        return True

    @property
    def distinct_item_ids(self) -> bool:
        return False

    # ============================================== "Real" methods =============================================

    def can_drop(self, item_id: str) -> bool:
        return item_id == self._item_id

    def drop_chance(self, item_id: str) -> float:
        return self._quantity.chances_to_not_choose(0) if item_id == self._item_id else 0.0

    def _roll_once(self) -> dict[str, int]:
        quantity: int = self._quantity.choose()
        return {self._item_id: quantity} if quantity > 0 else {}

    @staticmethod
    def _deserialize_data(data: dict[str, Any]) -> Loot:
        item_id: str = data["item_id"]
        quantity: dict[int, int] = _json_to_quantity_dict(data["quantity"])
        return FixedItemLoot(item_id, quantity)

    def _serialize_data(self) -> Any:
        return {
            "item_id": self._item_id,
            "quantity": self._quantity.possible_choices
        }


class RandomItemLoot(Loot):
    def __init__(self, item_ids: dict[str, int], quantity_caps: Optional[dict[str, int]] = None, single_item_id: bool = False, distinct_item_ids: bool = False):
        """
        Create a new random loot that yields a random quantity of a random item

        Parameters
        ----------
        item_ids: dict[str, int]
                  Identifiers of the item dropped by this loot with their weight in a <item_id>: <weight> association. A given item_id will have <weight>/<total weight> chances to occur.
        quantity_caps: dict[str, int], optional
                       Maximum number of given items to drop in a single roll in a <item_id>: <max_quantity> association.
        single_item_id: bool
                        If True then the roll method will select a single item id among the choice and then roll the quantity, applying on the single preselected item id. Mutually exclusive with distinct_item_ids. Has priority over distinct_item_ids
        distinct_item_ids: bool
                           If True then the roll method will ensure that at most 1 of item of a given item id is rolled. Incidentally, that will affect the overall drop rate of the remaining items. For example, if a roll is made on a quantity of
                           2 items within {"item_1": 99, "item_2": 1}, then the result will systematically be {"item_1": 1, "item_2": 1} since the roll will have to choose item items among 2. Mutually exclusive with distinct_item_ids

        Raises
        ------
        ValueError
            if none of the items has a chance to drop
        """
        super().__init__()

        self._item_ids: WeightedChoice[str] = WeightedChoice(item_ids)
        if not self._item_ids.valid:
            raise ValueError(f"item_ids should have selectable (weight > 0) values, found: {item_ids}")

        self._quantity_caps: Optional[dict[str, int]] = quantity_caps
        self._single_item_id: bool = single_item_id
        self._distinct_item_ids: bool = distinct_item_ids and not single_item_id

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"RandomItemLoot yielding {self._item_ids} with a max of {self._quantity_caps}"

    def __str__(self) -> str:
        return "Random Loot"

    # ================================================ Properties ===============================================

    @property
    def distinct_item_ids(self) -> bool:
        return self._distinct_item_ids

    @property
    def quantity_caps(self) -> dict[str, int]:
        return self._quantity_caps.copy()

    @property
    def single_item_id(self) -> bool:
        return self._single_item_id

    @property
    def item_ids(self) -> WeightedChoice[str]:
        return self._item_ids

    # ============================================= Abstract methods ============================================

    @abstractmethod
    def roll_quantity(self) -> int:
        pass

    # ============================================== "Real" methods =============================================

    def can_drop(self, item_id: str) -> bool:
        return item_id in self._item_ids

    def _roll_once(self) -> dict[str, int]:
        loot: dict[str, int] = {}

        quantity: int = self.roll_quantity()
        if quantity > 0:
            item_choice: WeightedChoice[str] = self._item_ids
            if self._single_item_id:
                item_id = item_choice.choose()
                if self._quantity_caps and item_id in self._quantity_caps:
                    quantity = min(quantity, self._quantity_caps[item_id])

                return {item_id: quantity}

            item_chances: dict[str, int] = item_choice.possible_choices
            if self._distinct_item_ids or (self._quantity_caps and len(self._quantity_caps) > 0):
                # Create a copies if quantity constraints exist because we'll be altering both dictionary during processing in such case
                # Also remove the items that are not supposed to drop
                item_chances = {item_id: weight for item_id, weight in item_chances.items() if self._quantity_caps.get(item_id, 999) > 0}
                item_constraints = self._quantity_caps.copy() if self._quantity_caps and len(self._quantity_caps) > 0 else {}
            else:
                item_constraints = {}

            generated_quantity = 0
            while generated_quantity < quantity and len(item_chances) > 0:
                item_id = roll_from_weighted_dict(item_chances)
                add_loot(loot, item_id, 1)
                generated_quantity += 1

                if self._distinct_item_ids:
                    item_chances.pop(item_id)
                elif item_id in item_constraints:
                    left = item_constraints[item_id] - 1
                    if left <= 0:
                        item_chances.pop(item_id)
                        item_constraints.pop(item_id)
                    else:
                        item_constraints[item_id] = left

        return loot

    @staticmethod
    def _deserialize_data(data: dict[str, Any]) -> Loot:
        item_ids: dict[str, int] = data["item_ids"]
        quantity_caps: Optional[dict[str, int]] = data["quantity_caps"]
        single_item_id: bool = data["single_item_id"]
        distinct_item_ids: bool = data["distinct_item_ids"]
        return RandomItemLoot(item_ids, quantity_caps, single_item_id, distinct_item_ids)

    def _serialize_data(self) -> Any:
        return {
            "item_ids": self._item_ids.possible_choices,
            "quantity_caps": self._quantity_caps,
            "single_item_id": self._single_item_id,
            "distinct_item_ids": self._distinct_item_ids
        }


class FixedQuantityLoot(RandomItemLoot):
    def __init__(self, item_ids: dict[str, int], quantity: int = 1, quantity_caps: Optional[dict[str, int]] = None, single_item_id: bool = False, distinct_item_ids: bool = False):
        """
        Create a new random loot that yields a fixed quantity of random items

        Parameters
        ----------
        item_ids: dict[str, int]
                  Identifiers of the item dropped by this loot with their weight in a <item_id>: <weight> association. A given item_id will have <weight>/<total weight> chances to occur.
        quantity: int, optional
                  Number of items drop per roll by this loot.
        quantity_caps: dict[str, int], optional
                       Maximum number of given items to drop in a single roll in a <item_id>: <max_quantity> association.
        single_item_id: bool
                        If True then the roll method will select a single item id among the choice and then roll the quantity, applying on the single preselected item id. Mutually exclusive with distinct_item_ids. Has priority over distinct_item_ids.
        distinct_item_ids: bool
                           If True then the roll method will ensure that at most 1 of item of a given item id is rolled. Incidentally, that will affect the overall drop rate of the remaining items. For example, if a roll is made on a quantity of
                           2 items within {"item_1": 99, "item_2": 1}, then the result will systematically be {"item_1": 1, "item_2": 1} since the roll will have to choose item items among 2. Mutually exclusive with distinct_item_ids

        Raises
        ------
        ValueError
            if none of the items has a chance to drop
        """
        super().__init__(item_ids, quantity_caps, single_item_id, distinct_item_ids)

        self._quantity: int = quantity

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"FixedQuantityRandomLoot yielding {self._quantity:,} x {self._item_ids}"

    def __str__(self) -> str:
        return "Random Loot"

    # ================================================ Properties ===============================================

    @property
    def quantity(self) -> int:
        return self._quantity

    @property
    def quantity_chances(self) -> WeightedChoice[int]:
        return WeightedChoice({self._quantity: 1})

    # ============================================== "Real" methods =============================================

    def drop_chance(self, item_id: str) -> float:
        return self.item_ids.chances_to_choose(item_id)

    def roll_quantity(self) -> int:
        return self._quantity

    @staticmethod
    def _deserialize_data(data: dict[str, Any]) -> Loot:
        item_ids: dict[str, int] = data["item_ids"]
        quantity: int = data["quantity"]
        quantity_caps: Optional[dict[str, int]] = data["quantity_caps"]
        single_item_id: bool = data["single_item_id"]
        distinct_item_ids: bool = data["distinct_item_ids"]
        return FixedQuantityLoot(item_ids, quantity, quantity_caps, single_item_id, distinct_item_ids)

    def _serialize_data(self) -> Any:
        return {
            "item_ids": self._item_ids.possible_choices,
            "quantity": self._quantity,
            "quantity_caps": self._quantity_caps,
            "single_item_id": self._single_item_id,
            "distinct_item_ids": self._distinct_item_ids
        }


class RandomLoot(RandomItemLoot):
    def __init__(self, item_ids: dict[str, int], quantity: dict[int, int], quantity_caps: Optional[dict[str, int]] = None, single_item_id: bool = False, distinct_item_ids: bool = False):
        """
        Create a new random loot that yields a fixed quantity of random items

        Parameters
        ----------
        item_ids: dict[str, int]
                  Identifiers of the item dropped by this loot with their weight in a <item_id>: <weight> association. A given item_id will have <weight>/<total weight> chances to occur.
        quantity: dict[int, int]
                  Number of items drop per roll by this loot in a <quantity>: <weight> association. A given quantity will have <weight>/<total weight> chances to occur.
        quantity_caps: dict[str, int], optional
                       Maximum number of given items to drop in a single roll in a <item_id>: <max_quantity> association.
        single_item_id: bool
                        If True then the roll method will select a single item id among the choice and then roll the quantity, applying on the single preselected item id. Mutually exclusive with distinct_item_ids. Has priority over distinct_item_ids.
        distinct_item_ids: bool
                           If True then the roll method will ensure that at most 1 of item of a given item id is rolled. Incidentally, that will affect the overall drop rate of the remaining items. For example, if a roll is made on a quantity of
                           2 items within {"item_1": 99, "item_2": 1}, then the result will systematically be {"item_1": 1, "item_2": 1} since the roll will have to choose item items among 2. Mutually exclusive with distinct_item_ids

        Raises
        ------
        ValueError
            if none of the items has a chance to drop or if quantity contains only zero or negative weighted values
        """
        super().__init__(item_ids, quantity_caps, single_item_id, distinct_item_ids)

        self._quantity: WeightedChoice = WeightedChoice(quantity)
        if not self._quantity.valid:
            raise ValueError(f"quantity should have selectable (weight > 0) values, found: {quantity}")

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"FullRandomLoot yielding {self._quantity:,} x {self._item_ids}"

    # ================================================ Properties ===============================================

    @property
    def quantity_chances(self) -> WeightedChoice[int]:
        return self._quantity.copy()

    # ============================================== "Real" methods =============================================

    def drop_chance(self, item_id: str) -> float:
        return self.item_ids.chances_to_choose(item_id) * self._quantity.chances_to_not_choose(0)

    def roll_quantity(self) -> int:
        return self._quantity.choose()

    @staticmethod
    def _deserialize_data(data: dict[str, Any]) -> Loot:
        item_ids: dict[str, int] = data["item_ids"]
        quantity: dict[int, int] = _json_to_quantity_dict(data["quantity"])
        quantity_caps: Optional[dict[str, int]] = data["quantity_caps"]
        single_item_id: bool = data["single_item_id"]
        distinct_item_ids: bool = data["distinct_item_ids"]
        return RandomLoot(item_ids, quantity, quantity_caps, single_item_id, distinct_item_ids)

    def _serialize_data(self) -> Any:
        return {
            "item_ids": self._item_ids.possible_choices,
            "quantity": self._quantity.possible_choices,
            "quantity_caps": self._quantity_caps,
            "single_item_id": self._single_item_id,
            "distinct_item_ids": self._distinct_item_ids
        }


class PossibleLoot(Loot):
    def __init__(self, loot: Loot, probability: int = 100):
        """
        Create a loot that yields a specified loot <probability>% of the times.

        Parameters
        ----------
        loot: Loot
              The loot to yield
        probability: int
                     The probability of the loot to be produced in percentage. E.g., for 90% this parameter should be set to 90. By default, the item will always drop.

        Raises
        ------
        ValueError
            if probability is negative
        """
        super().__init__()
        _validate_positive(probability, "probability")

        self._loot: Loot = loot
        self._probability: int = probability

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"PossibleLoot having {self._probability}% to drop {self._loot}"

    def __str__(self) -> str:
        return f"{self._loot} ({self._probability}%)"

    # ================================================ Properties ===============================================

    @property
    def loot(self) -> Loot:
        return self._loot

    @property
    def probability(self) -> int:
        return self._probability

    # ============================================== "Real" methods =============================================

    def alter_probability(self, probability_mod: int) -> PossibleLoot:
        if probability_mod == 0:
            return self

        target_probability: int = min(max(self._probability + probability_mod, 0), 100)
        return self.set_probability(target_probability)

    def can_drop(self, item_id: str) -> bool:
        return self._loot.can_drop(item_id)

    def drop_chance(self, item_id: str) -> float:
        return self._loot.drop_chance(item_id) * self._probability / 100.0

    def set_probability(self, new_probability: int) -> PossibleLoot:
        if new_probability == self._probability:
            return self

        return PossibleLoot(self._loot, new_probability)

    def _roll_once(self) -> dict[str, int]:
        if random.randint(1, 100) <= self._probability:
            return self._loot.roll()
        else:
            return {}

    @staticmethod
    def _deserialize_data(data: dict[str, Any]) -> Loot:
        loot: Loot = Loot.deserialize(data["loot"])
        probability: int = data["probability"]
        return PossibleLoot(loot, probability)

    def _serialize_data(self) -> Any:
        return {
            "loot": self._loot.serialize(),
            "probability": self._probability
        }


class RepeatedLoot(Loot):
    def __init__(self, loot: Loot, times: int = 1):
        """
        Create a loot that yields a specified loot multiple times.

        Parameters
        ----------
        loot: Loot
              The loot to yield
        times: int
               The number of times the loot should be yielded

        Raises
        ------
        ValueError
            if times is negative
        """
        super().__init__()
        _validate_positive(times, "times")

        self._loot: Loot = loot
        self._times: int = times

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"RepeatedLoot yielding {self._times:,} times {self._loot}"

    def __str__(self) -> str:
        return f"{self._times:,}x {self._loot}"

    # ================================================ Properties ===============================================

    @property
    def loot(self) -> Loot:
        return self._loot

    @property
    def times(self) -> int:
        return self._times

    # ============================================== "Real" methods =============================================

    def can_drop(self, item_id: str) -> bool:
        return self._loot.can_drop(item_id)

    def drop_chance(self, item_id: str) -> float:
        chance: float = self._loot.drop_chance(item_id)
        if chance > 0.0:
            chance: float = 1.0 - ((1.0 - chance) ** self._times)

        return chance

    def _roll_once(self) -> dict[str, int]:
        combined_loot: dict[str, int] = {}
        for _ in range(0, self._times):
            entry_loot = self._loot.roll()
            merge_loot(combined_loot, entry_loot)

        return combined_loot

    @staticmethod
    def _deserialize_data(data: dict[str, Any]) -> Loot:
        loot: Loot = Loot.deserialize(data["loot"])
        times: int = data["times"]
        return RepeatedLoot(loot, times)

    def _serialize_data(self) -> Any:
        return {
            "loot": self._loot.serialize(),
            "times": self._times
        }


class CompositeLoot(Loot):
    def __init__(self, components: Iterable[Loot]):
        """
        Create a loot that yields the combined loot of all its component loots

        Parameters
        ----------
        components: Iterable[Loot]
                    The loot whose yield should be combined to form this loot's yield
        """
        super().__init__()

        self._components: list[Loot] = [loot for loot in components if loot is not None]

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"CompositeLoot formed of {self._components}"

    def __str__(self) -> str:
        return "Random Loot"

    def __and__(self, other: Optional[Loot]) -> CompositeLoot:
        if other is None:
            return self
        elif isinstance(other, CompositeLoot):
            return CompositeLoot(self._components.copy() + other._components)
        else:
            components = self._components.copy()
            components.append(other)
            return CompositeLoot(components)

    # ================================================ Properties ===============================================

    @property
    def components(self) -> list[Loot]:
        return self._components.copy()

    # ============================================== "Real" methods =============================================

    def append(self, components: Iterable[Loot]) -> CompositeLoot:
        return CompositeLoot(self._components.copy() + [component for component in components if component is not None])

    def can_drop(self, item_id: str) -> bool:
        for loot in self._components:
            if loot.can_drop(item_id):
                return True

        return False

    def drop_chance(self, item_id: str) -> float:
        chances: list[float] = [loot.drop_chance(item_id) for loot in self._components]
        not_chances: list[float] = [1 - chance for chance in chances]
        not_chance = reduce((lambda x, y: x * y), not_chances)
        return 1.0 - not_chance

    def _roll_once(self) -> dict[str, int]:
        combined_loot: dict[str, int] = {}
        for loot in self._components:
            entry_loot = loot.roll()
            merge_loot(combined_loot, entry_loot)

        return combined_loot

    @staticmethod
    def _deserialize_data(data: dict[str, Any]) -> Loot:
        components_data: list[dict[str, Any]] = data["components"]
        components: list[Loot] = [Loot.deserialize(component_data) for component_data in components_data]
        return CompositeLoot(components)

    def _serialize_data(self) -> Any:
        return {"components": [loot.serialize() for loot in self._components]}


class ChoiceLoot(Loot):
    def __init__(self, components: Iterable[Loot], choice_weights: Optional[list[int]] = None):
        """
        Create a loot that yields the content of a randomly chosen loot among the specified. The choice can be weighted by the specified index choice, else the choice will be uniformly distributed between rolls

        Parameters
        ----------
        components: Iterable[Loot]
                    The loot whose yield should be combined to form this loot's yield

        choice_weights: Optional[list[int]]
                        The weight of each index in the loots iterable for the purpose of the final loot choice. Zero or negative values will be that specific index impossible to drop
        """
        super().__init__()

        self._components: list[Loot] = [component for component in components]

        loot_count: int = len(self._components)
        if choice_weights is None:
            self._index_choice = WeightedChoice(uniform_quantity(0, loot_count - 1))
        else:
            weight_count = len(choice_weights)
            if weight_count > loot_count:
                choice_weights = choice_weights[0:loot_count]

            index: int = 0
            index_choice: dict[int, int] = {}
            for weight in choice_weights:
                index_choice[index] = weight
                index += 1

            self._index_choice = WeightedChoice(index_choice)

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"ChoiceLoot formed of {self._components} chosen by index with {self._index_choice}"

    def __str__(self) -> str:
        return "Random Loot"

    def __add__(self, other: Optional[Loot]) -> ChoiceLoot:
        return self.__or__(other)

    def __or__(self, other: Optional[Loot]) -> ChoiceLoot:
        if other is None:
            return self
        else:
            loots = self._components.copy()
            weights: list[int] = []
            for i in range(0, len(self._components)):
                weights.append(self._index_choice[i])

            if isinstance(other, ChoiceLoot):
                loots = loots + other._components
                for i in range(0, len(other._components)):
                    weights.append(other._index_choice[i])
            else:
                loots.append(other)
                weights.append(1)

            return ChoiceLoot(loots, weights)

    # ================================================ Properties ===============================================

    @property
    def index_choice(self) -> WeightedChoice[int]:
        return self._index_choice.copy()

    @property
    def components(self) -> list[Loot]:
        return self._components.copy()

    # ============================================== "Real" methods =============================================

    def append(self, components: Iterable[Loot]) -> ChoiceLoot:
        other_components: list[Loot] = [component for component in components if component is not None]
        loots: list[Loot] = self._components.copy() + other_components
        weights: list[int] = []
        for i in range(0, len(self._components)):
            weights.append(self._index_choice[i])

        for i in range(0, len(other_components)):
            weights.append(1)

        return ChoiceLoot(loots, weights)

    def can_drop(self, item_id: str) -> bool:
        for loot in self._components:
            if loot.can_drop(item_id):
                return True

        return False

    def drop_chance(self, item_id: str) -> float:
        chances: list[float] = [loot.drop_chance(item_id) for loot in self._components]
        total_chance: float = 0.0
        for i in range(0, len(chances)):
            chance: float = chances[i]
            if chance > 0.0:
                total_chance += chance * self._index_choice.chances_to_choose(i)

        return total_chance

    def _roll_once(self) -> dict[str, int]:
        index: int = self._index_choice.choose()
        return self._components[index].roll()

    @staticmethod
    def _deserialize_data(data: dict[str, Any]) -> Loot:
        components_data: list[dict[str, Any]] = data["components"]
        components: list[Loot] = [Loot.deserialize(component_data) for component_data in components_data]
        return ChoiceLoot(components)

    def _serialize_data(self) -> Any:
        index_weights: dict[int, int] = self._index_choice.possible_choices
        choice_weights: list[int] = [index_weights[i] for i in range(0, len(self._components))]
        return {
            "components": [loot.serialize() for loot in self._components],
            "choice_weights": choice_weights
        }


class UniformQuantityLoot(Loot):
    def __init__(self, pseudo_item_id: str, min_value: int, max_value: int = 0):
        """
        Create a new loot that can roll a random amount of a given resource.

        This is usually used to give a random amount of gold or experience.

        Unlike most loot classes, this implementation allows negative min and max for penalties, but min and max value have opposite meaning in that case. I.e., between -100 and -1000 requires to set min to -1000 and max to -100

        Parameters
        ----------
        pseudo_item_id: str
                        Identifier of the pseudo item type dropped by this loot.
        min_value: int
                   The minimum value of the loot of the specified pseudo identifier
        max_value: int
                   The maximum value of the loot of the specified pseudo identifier
        """
        super().__init__()

        self._item_id: str = pseudo_item_id
        self._min_value: int = min_value
        self._max_value: int = max_value if max_value >= min_value else min_value

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"UniformQuantityLoot yielding [{self._min_value:,},{self._max_value:,}] {self._item_id}"

    def __str__(self) -> str:
        if self._min_value >= self._max_value:
            return f"{self._min_value:,} {self.item_label}"
        else:
            return f"[{self._min_value:,},{self._max_value:,}] {self.item_label}"

    # ================================================ Properties ===============================================

    @property
    def item_id(self) -> str:
        return self._item_id

    @property
    def item_label(self) -> str:
        return self._item_id

    @property
    def item_chances(self) -> WeightedChoice[str]:
        return WeightedChoice({self._item_id: 1})

    @property
    def quantity_chances(self) -> WeightedChoice[int]:
        return WeightedChoice(uniform_quantity(self._min_value, self._max_value))

    @property
    def single_item_id(self) -> bool:
        return True

    @property
    def distinct_item_ids(self) -> bool:
        return False

    # ============================================== "Real" methods =============================================

    def can_drop(self, item_id: str) -> bool:
        return item_id == self._item_id

    def drop_chance(self, item_id: str) -> float:
        return 1.0 if item_id == self._item_id else 0.0

    def _roll_once(self) -> dict[str, int]:
        return {self._item_id: random.randint(self._min_value, self._max_value)}

    @staticmethod
    def _deserialize_data(data: dict[str, Any]) -> Loot:
        item_id: str = data["pseudo_item_id"]
        min_value: int = data["min_value"]
        max_value: int = data["max_value"]
        return UniformQuantityLoot(item_id, min_value, max_value)

    def _serialize_data(self) -> Any:
        return {
            "pseudo_item_id": self._item_id,
            "min_value": self._min_value,
            "max_value": self._max_value
        }


class GoldLoot(UniformQuantityLoot):
    def __init__(self, min_value: int, max_value: int = 0):
        """
        Create a new loot that grants a random amount of gold.

        Parameters
        ----------
        min_value: int
                   The minimum amount of gold
        max_value: int
                   The maximum amount of gold
        """
        super().__init__(PSEUDO_ITEM_ID_GOLD, min_value, max_value)

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"GoldLoot yielding [{self._min_value:,}, {self._max_value:,}] gold"

    # ================================================ Properties ===============================================

    @property
    def item_label(self) -> str:
        return "gold"

    # ============================================== "Real" methods =============================================

    @staticmethod
    def _deserialize_data(data: dict[str, Any]) -> Loot:
        min_value: int = data["min_value"]
        max_value: int = data["max_value"]
        return GoldLoot(min_value, max_value)


class ArenaCoinLoot(UniformQuantityLoot):
    def __init__(self, min_value: int, max_value: int = 0):
        """
        Create a new loot that grants a random amount of arena coins.

        Parameters
        ----------
        min_value: int
                   The minimum amount of arena coins
        max_value: int
                   The maximum amount of arena coins
        """
        super().__init__(PSEUDO_ITEM_ID_ARENA_COIN, min_value, max_value)

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"ArenaCoinLoot yielding [{self._min_value:,},{self._max_value:,}] arena coins"

    # ================================================ Properties ===============================================

    @property
    def item_label(self) -> str:
        return "arena coin"

    # ============================================== "Real" methods =============================================

    @staticmethod
    def _deserialize_data(data: dict[str, Any]) -> Loot:
        min_value: int = data["min_value"]
        max_value: int = data["max_value"]
        return ArenaCoinLoot(min_value, max_value)


class StarLoot(UniformQuantityLoot):
    def __init__(self, min_value: int, max_value: int = 0):
        """
        Create a new loot that grants a random amount of stars.

        Parameters
        ----------
        min_value: int
                   The minimum amount of stars
        max_value: int
                   The maximum amount of stars
        """
        super().__init__(PSEUDO_ITEM_ID_STAR, min_value, max_value)

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"StarLoot yielding [{self._min_value:,},{self._max_value:,}] stars"

    # ================================================ Properties ===============================================

    @property
    def item_label(self) -> str:
        return "stars"

    # ============================================== "Real" methods =============================================

    @staticmethod
    def _deserialize_data(data: dict[str, Any]) -> Loot:
        min_value: int = data["min_value"]
        max_value: int = data["max_value"]
        return StarLoot(min_value, max_value)


class FlatEnergyLoot(UniformQuantityLoot):
    def __init__(self, min_value: int, max_value: int = 0):
        """
        Create a new loot that grants a random absolute amount of energy.

        Parameters
        ----------
        min_value: int
                   The minimum amount of energy
        max_value: int
                   The maximum amount of energy
        """
        super().__init__(PSEUDO_ITEM_ID_ENERGY_FLAT, min_value, max_value)

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"FlatEnergyLoot yielding [{self._min_value:,},{self._max_value:,}] energy"

    # ================================================ Properties ===============================================

    @property
    def item_label(self) -> str:
        return "energy"

    # ============================================== "Real" methods =============================================

    @staticmethod
    def _deserialize_data(data: dict[str, Any]) -> Loot:
        min_value: int = data["min_value"]
        max_value: int = data["max_value"]
        return FlatEnergyLoot(min_value, max_value)


class RelativeEnergyLoot(UniformQuantityLoot):
    def __init__(self, min_value: int, max_value: int = 0):
        """
        Create a new loot that grants a random amount of energy based on a % of the player's max energy.

        Parameters
        ----------
        min_value: int
                   The minimum ratio as a %. E.g., 1 represents 1%
        max_value: int
                   The maximum ratio as a %. E.g., 100 represents 100%
        """
        super().__init__(PSEUDO_ITEM_ID_ENERGY_RATIO, min_value, max_value)

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"RelativeEnergyLoot yielding [{self._min_value:,},{self._max_value:,}]% of max energy"

    # ================================================ Properties ===============================================

    @property
    def item_label(self) -> str:
        return "% of max energy"

    # ============================================== "Real" methods =============================================

    @staticmethod
    def _deserialize_data(data: dict[str, Any]) -> Loot:
        min_value: int = data["min_value"]
        max_value: int = data["max_value"]
        return RelativeEnergyLoot(min_value, max_value)


class FlatExperienceLoot(UniformQuantityLoot):
    def __init__(self, min_value: int, max_value: int = 0):
        """
        Create a new loot that grants a random absolute amount of experience.

        Parameters
        ----------
        min_value: int
                   The minimum amount of experience
        max_value: int
                   The maximum amount of experience
        """
        super().__init__(PSEUDO_ITEM_ID_EXP_FLAT, min_value, max_value)

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"FlatExperienceLoot yielding [{self._min_value:,},{self._max_value:,}] experience"

    # ================================================ Properties ===============================================

    @property
    def item_label(self) -> str:
        return "exp"

    # ============================================== "Real" methods =============================================

    @staticmethod
    def _deserialize_data(data: dict[str, Any]) -> Loot:
        min_value: int = data["min_value"]
        max_value: int = data["max_value"]
        return FlatExperienceLoot(min_value, max_value)


class RelativeExperienceLoot(UniformQuantityLoot):

    def __init__(self, min_value: int, max_value: int = 0):
        """
        Create a new loot that grants a random amount of experience based on a per ten thousand of the player's total experience.

        Parameters
        ----------
        min_value: int
                   The minimum ratio as a per 10,000 basis. E.g., 1_000 represents 100‰, 100 represents 1%
        max_value: int
                   The maximum ratio as a per 10,000 basis. E.g., 1_000 represents 100%, 100 represents 1%
        """
        super().__init__(PSEUDO_ITEM_ID_EXP_RATIO, min_value, max_value)

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"FlatExperienceLoot yielding [{self._min_value:,},{self._max_value:,}]% of breakthrough exp"

    # ================================================ Properties ===============================================

    @property
    def item_label(self) -> str:
        return "% of breakthrough exp"

    # ============================================== "Real" methods =============================================

    @staticmethod
    def as_percentage(value: int) -> float:
        return value / RELATIVE_EXP_VALUE_FACTOR

    @staticmethod
    def percent_to_param(value: float) -> int:
        return int(value * RELATIVE_EXP_VALUE_FACTOR)

    @staticmethod
    def _deserialize_data(data: dict[str, Any]) -> Loot:
        min_value: int = data["min_value"]
        max_value: int = data["max_value"]
        return RelativeExperienceLoot(min_value, max_value)


class LootDistributionLogic:
    def __init__(self, pseudo_item_proportional: bool = True, pseudo_item_mode: int = DEFAULT_MODE, item_proportional: bool = False, item_mode: int = DEFAULT_MODE):
        """
        Create a loot distribution configuration.

        Parameters
        ----------
        pseudo_item_proportional: bool, optional
                                  Determines how the pseudo item (EXP, energy, gold) quantities should be split proportionally to the contribution, or uniformly.
                                   - True: Split proportionally to the contribution
                                   - False: Split uniformly among contributors
                                  Default: True (proportional)

        pseudo_item_mode: int, optional
                          Determines how pseudo item remainders are handled. Note that experience is a special case that will always use an MODE_EVERYONE logic
                           - MODE_RANDOM: the remainders are allocated randomly based on uniform or proportional selection, depending on pseudo_items_proportional, possibly favoring the same contributor multiple times
                           - MODE_SPREAD: the remainders are allocated randomly based on uniform or proportional selection, depending on pseudo_items_proportional, but will ensure that a contributor won't receive more than one unit from remainders
                           - MODE_EVERYONE: remainders are not possible
                          Default: MODE_RANDOM

        item_proportional: bool, optional
                           Determines if the item quantities should be split proportionally to the contribution, or uniformly.
                            - True: Split proportionally to the contribution
                            - False: Split uniformly among contributors
                           Default: False (uniform)

        item_mode: int, optional
                   Determines how item divisions are handled.
                    - MODE_RANDOM: item are allocated randomly based on items_proportional selection mode
                    - MODE_SPREAD: item are allocated randomly based on items_proportional selection mode, but ensuring that each contributor received an item before allowing a contributor to get a second one
                    - MODE_EVERYONE: apply fractions uniformly or proportionally, then ceil the resulting quantity and allocate to the contributors. This mode ensure that each contributor will receive at least 1 item of each type from the loot
                   Default: MODE_RANDOM
        """
        super().__init__()
        self._pseudo_item_proportional: bool = pseudo_item_proportional
        self._pseudo_item_mode: int = pseudo_item_mode
        self._item_proportional: bool = item_proportional
        self._item_mode: int = item_mode

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"LootDistributionLogic {{pseudo_items_proportional: {self._pseudo_item_proportional}, pseudo_items_mode: {self._pseudo_item_mode}, items_proportional: {self._item_proportional}, items_mode: {self._item_mode}}}"

    def __str__(self):
        return self.__repr__()

    def __hash__(self) -> int:
        return hash(self._pseudo_item_proportional) * 7 + hash(self._pseudo_item_mode) * 5 + hash(self._item_proportional) * 3 + hash(self._item_mode)

    def __eq__(self, other):
        return (other is not None
                and isinstance(other, LootDistributionLogic)
                and self._pseudo_item_proportional == other._pseudo_item_proportional
                and self._pseudo_item_mode == other._pseudo_item_mode
                and self._item_proportional == other._item_proportional
                and self._item_mode == other._item_mode)

    def __ne__(self, other):
        return not self.__eq__(other)

    # ================================================ Properties ===============================================

    @property
    def item_mode(self) -> int:
        return self._item_mode

    @property
    def item_proportional(self) -> bool:
        return self._item_proportional

    @property
    def pseudo_item_mode(self) -> int:
        return self._pseudo_item_mode

    @property
    def pseudo_item_proportional(self) -> bool:
        return self._pseudo_item_proportional

    def distribute(self, loot: dict[str, int], contributions: dict[int, int],
                   flat_experience: int = 0, relative_experience: int = 0,
                   flat_energy: int = 0, relative_energy: int = 0,
                   gold: int = 0, arena_coins: int = 0, stars: int = 0) -> dict[int, dict[str, int]]:
        """
        Distribute the specified loot among the contributors based on this distribution configuration.

        Parameters
        ----------
        loot: dict[str, int]
              The dictionary specifying the loot, with item ids or pseudo item ids as keys and quantity as values

        contributions: dict[int, int]
                       A dictionary containing the player ids as keys and their contribution as value where a player's relative contribution is their contribution divided by the sum of the contributions within the dictionary

        flat_experience: int, optional
                         Extra flat experience amount to distribute along with the loot. Default: 0

        relative_experience: int, optional
                             Extra relative experience amount to distribute along with the loot, expressed as per ten thousand. Default: 0

        flat_energy: int, optional
                     Extra flat energy amount to distribute along with the loot. Default: 0

        relative_energy: int, optional
                         Extra relative energy amount to distribute along with the loot, expressed in percentage. Default: 0

        gold: int, optional
              Extra gold amount to distribute along with the loot. Default: 0

        arena_coins: int, optional
                     Extra arena coin number to distribute along with the loot. Default: 0

        stars: int, optional
               Extra star number to distribute along with the loot. Default: 0

        Returns
        -------
        dict[int, dict[str, int]]
            The dictionary specifying the distribution, with the player ids as keys and the quantity of each item as values. An empty dictionary means that nothing could be distributed because of no loot or no contributor. Depending on
            the internal logic settings, the sum of the quantities may be higher than the initial loot quantity, but never lower, except for the empty return case for no contributor
        """
        if contributions is None or len(contributions) == 0:
            return {}

        if loot is None:
            loot: dict[str, int] = {}
        else:
            loot: dict[str, int] = loot.copy()

        add_loot(loot, PSEUDO_ITEM_ID_EXP_FLAT, flat_experience)
        add_loot(loot, PSEUDO_ITEM_ID_EXP_RATIO, relative_experience)
        add_loot(loot, PSEUDO_ITEM_ID_ENERGY_FLAT, flat_energy)
        add_loot(loot, PSEUDO_ITEM_ID_ENERGY_RATIO, relative_energy)
        add_loot(loot, PSEUDO_ITEM_ID_GOLD, gold)
        add_loot(loot, PSEUDO_ITEM_ID_ARENA_COIN, arena_coins)
        add_loot(loot, PSEUDO_ITEM_ID_STAR, stars)
        if len(loot) == 0:
            return {}

        distributed_loot: dict[int, dict[str, int]] = {}

        pseudo_item_loot: dict[str, int] = filter_pseudo_item_loot(loot)
        pseudo_item_contributions: dict[int, int] = contributions if self._pseudo_item_proportional else {player_id: 1 for player_id in contributions.keys()}
        distributed_loot = self._distribute_main(distributed_loot, pseudo_item_loot, pseudo_item_contributions, self._pseudo_item_mode)

        item_loot: dict[str, int] = filter_item_loot(loot)
        item_contributions: dict[int, int] = contributions if self._item_proportional else {player_id: 1 for player_id in contributions.keys()}
        distributed_loot = self._distribute_main(distributed_loot, item_loot, item_contributions, self._item_mode)

        return distributed_loot

    @staticmethod
    def _allocate(distributed_loot: dict[int, dict[str, int]], player_id: int, item_id: str, quantity: int) -> dict[int, dict[str, int]]:
        if player_id not in distributed_loot:
            distributed_loot[player_id] = {item_id: quantity}
        else:
            add_loot(distributed_loot[player_id], item_id, quantity)

        return distributed_loot

    def _distribute_main(self, distributed_loot: dict[int, dict[str, int]], loot: dict[str, int], contributions: dict[int, int], mode: int) -> dict[int, dict[str, int]]:
        total_contribution: int = sum(contributions.values())
        for item_id, quantity in loot.items():
            remaining_quantity: int = quantity
            for player_id, contribution in contributions.items():
                raw_quantity: float = quantity * contribution / total_contribution
                # Special case for EXP that always ceil
                allocated_quantity: int = math.ceil(raw_quantity) if item_id == PSEUDO_ITEM_ID_EXP_FLAT or mode == MODE_EVERYONE else math.floor(raw_quantity)
                distributed_loot = self._allocate(distributed_loot, player_id, item_id, allocated_quantity)
                remaining_quantity -= allocated_quantity

            distributed_loot = self._distribute_remainder(distributed_loot, contributions, item_id, remaining_quantity, mode)

        return distributed_loot

    def _distribute_remainder(self, distributed_loot: dict[int, dict[str, int]], contributions: dict[int, int], item_id: str, quantity: int, mode: int) -> dict[int, dict[str, int]]:
        current_contributions: dict[int, int] = contributions.copy()
        total_contribution: int = sum(current_contributions.values())
        remaining_quantity: int = quantity
        while remaining_quantity > 0:
            player_id: int = roll_from_weighted_dict(current_contributions, total_contribution)
            distributed_loot = self._allocate(distributed_loot, player_id, item_id, 1)
            remaining_quantity -= 1
            if mode == MODE_SPREAD:
                current_contributions.pop(player_id)
                if len(current_contributions) == 0:
                    current_contributions: dict[int, int] = contributions.copy()

                total_contribution: int = sum(current_contributions.values())

        return distributed_loot

    def serialize(self) -> dict[str, bool]:
        data: dict[str, bool] = {
            "pseudo_item_proportional": self._pseudo_item_proportional,
            "pseudo_item_mode": self._pseudo_item_mode,
            "item_proportional": self._item_proportional,
            "item_mode": self._item_mode
        }

        return data

    @staticmethod
    def deserialize(data: Optional[dict[str, bool]]) -> D:
        if data is None:
            return LootDistributionLogic()

        pseudo_item_proportional: bool = data["pseudo_item_proportional"]
        pseudo_item_mode: int = data["pseudo_item_mode"]
        item_proportional: bool = data["item_proportional"]
        item_mode: int = data["item_mode"]
        return LootDistributionLogic(pseudo_item_proportional=pseudo_item_proportional, pseudo_item_mode=pseudo_item_mode, item_proportional=item_proportional, item_mode=item_mode)


# ======================================================= UI base classes and functions =====================================================

class LootSetupModal(disnake.ui.Modal):
    DATA_FIELD: str = "loot_json"

    def __init__(self, inter: Interaction, title: str = "Loot Setup", label: str = "Loot", custom_id: str = "loot_modal"):
        super().__init__(title=title, custom_id=f"{custom_id}-{inter.id}",
                         components=[disnake.ui.TextInput(label=label, placeholder="Specify a valid JSON-serialized Loot", custom_id=LootSetupModal.DATA_FIELD, style=disnake.TextInputStyle.multi_line, required=True)])

    def loot_value(self, inter: disnake.ModalInteraction) -> Loot:
        return loot_value(inter, self.DATA_FIELD)


def loot_value(inter: disnake.ModalInteraction, field_name: str = LootSetupModal.DATA_FIELD) -> Loot:
    """
    Gets the user input from the specified interaction, validate it, and convert it to a Loot instance.

    Parameters
    ----------
    inter: disnake.ModalInteraction
           the modal interaction containing a text field the user filled with a loot definition.

    field_name: str, optional
                The name of the field filled by the user, LootSetupModal.DATA_FIELD by default

    Returns
    -------
    Loot
        The loot specified by the user

    Raises
    ------
    PlayerInputException
        If the user specified a value, but not a valid JSON dict that can be parsed into a Loot
    """
    user_input: str = inter.text_values[field_name]
    if user_input is None:
        raise PlayerInputException(f"Loot data must be specified")

    try:
        parsed: Any = json.loads(user_input)
    except ValueError:
        raise PlayerInputException(f"Loot should be specified as a JSON object (dict), found {user_input}")

    if not isinstance(parsed, dict):
        raise PlayerInputException(f"Loot should be specified as a JSON object (dict), found {type(parsed)}")

    try:
        return Loot.deserialize(parsed)
    except UnsupportedOperationError:
        raise PlayerInputException(f"Loot should be specified as a valid loot in serialized form, found {user_input}")


def loot_values(inter: disnake.ModalInteraction, field_name: str = LootSetupModal.DATA_FIELD) -> list[Loot]:
    """
    Gets the user input from the specified interaction, validate it, and convert it to a list of Loot instances.

    Parameters
    ----------
    inter: disnake.ModalInteraction
           the modal interaction containing a text field the user filled with a loot definition.

    field_name: str, optional
                The name of the field filled by the user, LootSetupModal.DATA_FIELD by default

    Returns
    -------
    list[Loot]
        The loots specified by the user

    Raises
    ------
    PlayerInputException
        If the user specified a value, but not a valid JSON list of objects that can be parsed into a list[Loot]
    """
    user_input: str = inter.text_values[field_name]
    if user_input is None:
        raise PlayerInputException(f"Loot data must be specified")

    try:
        parsed: Any = json.loads(user_input)
    except ValueError:
        raise PlayerInputException(f"Loot should be specified as a JSON list of object, found {user_input}")

    if not isinstance(parsed, list):
        raise PlayerInputException(f"Loot should be specified as a JSON list of object, found {type(parsed)}")

    try:
        loot_data: list[Any] = parsed
        loots: list[Loot] = [Loot.deserialize(data) for data in loot_data]
        return loots
    except UnsupportedOperationError:
        raise PlayerInputException(f"Loot should be specified as a valid loot list in serialized form, found {user_input}")


# ============================================================= Utility functions =============================================================

def add_loot(loot: dict[str, int], item_id: str, quantity: Optional[int]) -> dict[str, int]:
    if quantity is None:
        quantity = 1

    if quantity > 0:
        if item_id in loot:
            loot[item_id] = loot[item_id] + quantity
        else:
            loot[item_id] = quantity

    return loot


def create_fixed_loot(item_id: str, quantity: int = 1) -> Loot:
    """
    Creates a proper fixed loot instance depending on the looted item type. Normal item ids will generate a FixedLoot instance while pseudo item ids will generate their dedicated Loot implementation instance instead.

    Parameters
    ----------
    item_id: str
             The item id or pseudo item id that should be yielded from the generated loot

    quantity: int, optional
              The quantity of the specified item pt produce. By default, 1. Specifying zero won't make this function to fail, but it will then yield an EmptyLoot instead

    Returns
    -------
    Loot
        A proper fixed loot instance for the specified item id
    """
    if item_id is None:
        raise ValueError("Item id must be specified")

    if quantity < 0:
        raise ValueError(f"Quantity must be positive, found {quantity}")

    if quantity == 0:
        return EmptyLoot()

    if not is_pseudo_item_id(item_id):
        return FixedLoot(item_id, quantity)

    if item_id == PSEUDO_ITEM_ID_GOLD:
        return GoldLoot(quantity)
    elif item_id == PSEUDO_ITEM_ID_EXP_FLAT:
        return FlatExperienceLoot(quantity)
    elif item_id == PSEUDO_ITEM_ID_ENERGY_FLAT:
        return FlatEnergyLoot(quantity)
    elif item_id == PSEUDO_ITEM_ID_ARENA_COIN:
        return ArenaCoinLoot(quantity)
    elif item_id == PSEUDO_ITEM_ID_STAR:
        return StarLoot(quantity)
    elif item_id == PSEUDO_ITEM_ID_EXP_RATIO:
        return RelativeExperienceLoot(quantity)
    elif item_id == PSEUDO_ITEM_ID_ENERGY_RATIO:
        return RelativeEnergyLoot(quantity)
    else:
        raise ValueError(f"Unknown pseudo item id {item_id}")


def filter_item_loot(loot: dict[str, int]) -> dict[str, int]:
    return {item_id: quantity for item_id, quantity in loot.items() if item_id not in PSEUDO_ITEM_IDS}


def filter_pseudo_item_loot(loot: dict[str, int]) -> dict[str, int]:
    return {item_id: quantity for item_id, quantity in loot.items() if item_id in PSEUDO_ITEM_IDS}


def fixed_quantity_cap(items: list[str], quantity_cap: int) -> dict[str, int]:
    return {items_id: quantity_cap for items_id in items}


def is_pseudo_item_id(item_id: str) -> bool:
    """
    Determines if the specified item identifier is in fact a pseudo item identifier.

    Parameters
    ----------
    item_id: str
             The potential pseudo item identifier

    Returns
    -------
    bool
        True if  the specified item identifier is a pseudo item identifier, False otherwise
    """
    return item_id in PSEUDO_ITEM_IDS


def make_uncertain(weighted_values: dict[T, int], probability: int = 100, none_value: T = None) -> dict[Optional[T], int]:
    """
    Generates a weighted value dict "uncertain", making it occur only  <probability>% of the times. This is a utility method to create choice and loot instances.


    Parameters
    ----------
    weighted_values: dict[int, int]
                     The weighted value distribution
    probability: int, optional
                 The probability of the weighted values to materialize. E.g., for 90% this parameter should be set to 90. By default, the quantity will always drop (same behavior as uniform_quantity). A zero probability result in a {0: 100} result
    none_value: T, optional
                The value representing the non-occurrence, often 0 (int) or None (other)

    Returns
    -------
    dict[int, int]
        the weighted values distribution that yields its originally specified quantities only <probability>% of the times

    Raises
    ------
    ValueError
        if probability is negative
    """
    _validate_positive(probability, "probability")

    if probability == 0:
        return {none_value: 1}
    elif probability < 100:
        positive_quantity_weights: int = sum([weight for val, weight in weighted_values.items() if weight > 0])
        # We want positive_quantity_weights to happen probability% of the times, so the total weight should be positive_quantity_weights * 100 / probability.
        # To ensure the requested precision we may have to expand the positive_quantity_weights
        target_total_weight: int = positive_quantity_weights * 100
        mod: int = target_total_weight % probability
        if mod != 0:
            # Cannot get exact match so expand the positive weight to be a sure multiple of probability, and remove the potential 0 qty while at it
            weighted_values: dict[T, int] = {val: weight * probability for val, weight in weighted_values.items()}
            positive_quantity_weights: int = positive_quantity_weights * probability
        else:
            target_total_weight: int = target_total_weight // probability

        weighted_values[none_value] = int(weighted_values.get(none_value, 0) + target_total_weight - positive_quantity_weights)

    return weighted_values


def merge_loot(merge_into: dict[str, int], additional_loot: Optional[dict[str, int]]) -> dict[str, int]:
    if additional_loot is None:
        return merge_into

    for item_id, quantity in additional_loot.items():
        if quantity != 0:
            add_loot(merge_into, item_id, quantity)

    return merge_into


def recalibrate_probability(weighted_values: dict[Optional[T], int], probability_mod: int, none_value: Optional[T] = None, criteria: Callable[[T], bool] = lambda b: True) -> dict[Optional[T], int]:
    old_total_weight: int = sum([weight for weight in weighted_values.values() if weight > 0])
    old_none_weight: int = weighted_values.get(none_value, 0)
    if old_none_weight < 0:
        old_none_weight = 0

    old_none_percent: int = int(old_none_weight / old_total_weight * 100)
    new_none_percent: int = old_none_percent - probability_mod  # Minus since probability mod argument precise the occurrence modifier

    new_valid_values: dict[T, int] = {value: weight for value, weight in weighted_values.items() if weight > 0 and value is not None and criteria(value)}
    if new_none_percent <= 0:
        return new_valid_values
    else:
        return make_uncertain(new_valid_values, 100 - new_none_percent)


def roll_from_weighted_dict(choices: dict[K, int], total_weight: Optional[int] = 0) -> K:
    """
    Choose a random key from a weighted candidate dictionary, each key having their weight over the total weight chances to be selected.

    Parameters
    ----------
    choices: dict[K, int]
             The candidates to select from with their associated weight
    total_weight: int, optional
                  The total weight of all the candidates combined. If not specified or lower than 1 then this function will recompute the total weight dynamically. This parameter is mainly a performance optimisation as well as a
                  way to skew the results toward the first half of the dictionary (total_weight lower than the real total), or toward the last item (total_weight greater than the real total)

    Returns
    -------
    K
        The randomly selected candidate
    """

    possible_choices = {choice: weight for choice, weight in choices.items() if weight > 0}
    if total_weight <= 0:
        total_weight = sum(possible_choices.values())

    if len(possible_choices) == 0:
        raise ValueError(f"At least one choice should be possible, found: {choices}")

    if len(possible_choices) == 1:
        return next(iter(possible_choices.keys()))
    else:
        rand_val = random.randint(1, total_weight)
        for item_id, weight in possible_choices.items():
            if rand_val <= weight:
                return item_id

            rand_val -= weight

        # Should not happen unless the total_weight was not consistent with the candidates, but fail gracefully with the first candidate
        return next(iter(possible_choices.values()))


def uniform_choice(values: Iterable[T], probability: int = 100, none_value: T = None) -> WeightedChoice[Optional[T]]:
    """
    Generates a uniform distribution of the specified values as a weighted choice, optionally adding a None choice occurring the specified (100 - probability)% of the times.


    Parameters
    ----------
    values: Iterable[T]
            The values to create a uniform distribution over
    probability: int, optional
                 The probability of the choice to yield a non-None a value within the specified ones, expressed as a percentage, i.e., 100 means 100%. If 100% then the choice will only yield the specified values. If the specified values already
                 contain a None value then the specified probability's chance of not occurring with be added to the uniform weight
    none_value: T, optional
                The value representing the non-occurrence, often 0 (int) or None (other)

    Returns
    -------
    WeightedChoice[Optional[T]]
        the uniform choice between the specified value, with 100-probability % chance to not yield anything (None)
    """
    _validate_positive(probability, "probability")

    choice_dict: dict[T, int] = {value: 1 for value in values}
    choice_dict = make_uncertain(choice_dict, probability, none_value)
    return WeightedChoice(choice_dict)


def uniform_distribution(values: Iterable[T]) -> dict[T, int]:
    """
    Generates a uniform distribution of the specified values, with each item having the same chance to be rolled as the others if used in roll_from_weighted_dict


    Parameters
    ----------
    values: Iterable[T]
            The values to create a uniform distribution over

    Returns
    -------
    dict[T, int]
        the uniform distribution of items in values
    """
    return {value: 1 for value in values}


def uniform_quantity(min_quantity: int = 1, max_quantity: int = 1, probability: int = 100) -> dict[int, int]:
    """
    Generates a uniform quantity spread between min_quantity and max_quantity. This is a utility method to create loot instances.


    Parameters
    ----------
    min_quantity: int
                  The minimum quantity to drop in case of a successful roll against the probability, by default 1. A zero quantity will leave this table unchanged.
    max_quantity: int
                  The maximum quantity to drop in case of a successful roll against the probability, by default 1. Will be matched to min_quantity if lower than the latter.
    probability: int, optional
                 The probability of the quantity to materialize. E.g., for 90% this parameter should be set to 90. By default, the quantity will always drop (same behavior as uniform_quantity). A zero probability result in a {0: 100} result

    Returns
    -------
    dict[int, int]
        the uniform distribution of quantities between min_quantity and max_quantity

    Raises
    ------
    ValueError
        if min_quantity or max_quantity are lower than zero
    """
    _validate_positive(min_quantity, "min_quantity")
    _validate_positive(max_quantity, "max_quantity")

    if min_quantity >= max_quantity:
        # Fixed quantity to min_quantity
        quantity: dict[int, int] = {min_quantity: 1}
    else:
        quantity: dict[int, int] = {quantity: 1 for quantity in range(min_quantity, max_quantity + 1)}

    quantity = make_uncertain(quantity, probability, 0)
    return quantity


def _json_to_quantity_dict(json_dict: dict[str, int]):
    return {int(key): value for key, value in json_dict.items()}


def _validate_item_id(item_id: str):
    if item_id is None or len(item_id) == 0:
        raise ValueError(f"item_id must be specified, found: {item_id}")


def _validate_positive(value: int, var_name: str):
    if value < 0:
        raise ValueError(f"{var_name} must be positive, found: {value}")

from __future__ import annotations

import json
import random
from functools import cmp_to_key
from typing import Any, Optional, Callable, Union, TypeVar

import disnake

from utils.CommandUtils import MAX_CHOICE_ITEMS
from utils.Database import AllItems
from utils.EconomyUtils import currency_dict_to_str
from utils.InventoryUtils import ITEM_TYPE_CAULDRON, ITEM_TYPE_RING, ITEM_TYPE_MONSTER_CORE, ITEM_TYPE_MONSTER_PART, ITEM_TYPE_ORIGIN_QI, ITEM_TYPE_WEAPON, ITEM_TYPE_BEAST_FLAME, ITEM_TYPE_MISCELLANEOUS, ITEM_TYPE_EGG, \
    ITEM_TYPE_FIGHT_TECHNIQUE_MANUAL, ITEM_TYPE_HEAVENLY_FLAME, ITEM_TYPE_HERB, ITEM_TYPE_PILL, ITEM_TYPE_QI_FLAME, ITEM_TYPE_QI_METHOD_MANUAL, ITEM_TYPE_VALUABLE, convert_id, ITEM_TYPE_CHEST, ITEM_TYPE_MAP_FRAGMENT
from utils.LoggingUtils import log_event
from utils.ParamsUtils import CURRENCY_NAME_GOLD
from utils.Styles import COLOR_LIGHT_GREEN
from utils.base import singleton
from utils.loot import roll_from_weighted_dict, PSEUDO_ITEM_ID_ENERGY_FLAT, PSEUDO_ITEM_ID_ENERGY_RATIO, PSEUDO_ITEM_ID_EXP_FLAT, PSEUDO_ITEM_ID_EXP_RATIO, PSEUDO_ITEM_ID_GOLD, PSEUDO_ITEM_ID_ARENA_COIN, PSEUDO_ITEM_ID_STAR, RelativeExperienceLoot

D = TypeVar("D", bound="ItemDefinition")

PROP_CRAFT = "craft"
PROP_EGG_HATCH_RATES = "hatch_rate"
PROP_EGG_PARENT = "parent"
PROP_CAULDRON_COOLDOWN_REDUCTION = "alchemy_cdr"
PROP_CAULDRON_REFINE_BONUS = "refine_bonus_per_tier_above"
PROP_HEAVENLY_FLAME_ABSORB_DIFFICULTY = "rank_alt_major"
PROP_FIGHT_TECHNIQUE_CP_BONUS = "cp"
PROP_FLAME_CP_BOOST = "cp_boost"
PROP_FLAME_EXP_BOOST = "xp_boost"
PROP_FLAME_REFINE_BONUS = "pill_rate_boost"
PROP_LOOT_TYPE = "loot_type"
PROP_LOOT_RANK = "loot_rank"
PROP_LOOT_TIER = "loot_tier"
PROP_MAP_FRAGMENT_ITEM = "treasure_item_id"
PROP_MAP_FRAGMENT_NUMBER = "fragment_number"
PROP_MONSTER_PART_MAX_DROP = "max_drop_per_beast"
PROP_PET_AMPLIFIER_REROLL_BONUS = "reroll_boost"
PROP_PET_FOOD_EXP = "pet_exp_ref"
PROP_PILL_BASE_REFINE_CHANCE = "make_chance"
PROP_PILL_CONSUME_EFFECTS = "effects"
PROP_PILL_REFINE_EXPERIENCE = "exp_given"
PROP_QI_FLAME_RANK_REQUIREMENT_MAJOR = "major"
PROP_QI_FLAME_RANK_REQUIREMENT_MINOR = "minor"
PROP_QI_METHOD_CP_BOOST = "cp_pct"
PROP_REQUIREMENTS = "requirements"
PROP_STORAGE_RING_CAPACITY = "total_weight"
PROP_STORAGE_RING_VALID_CONTENTS = "limited_type"

DEFAULT_MAX_DROP_PER_BEAST = 1
HEAVENLY_FLAME_RANKING_SIZE = 23
MAX_ITEM_TIER = 10

LOOT_TYPE_ARENA_COIN: str = "arena_coin"
LOOT_TYPE_ENERGY: str = "energy"
LOOT_TYPE_EXPERIENCE: str = "exp"
LOOT_TYPE_GOLD: str = "gold"
LOOT_TYPE_MIXED: str = "mixed"

UNSTACKABLE_ITEM_TYPES = [ITEM_TYPE_CAULDRON, ITEM_TYPE_RING, ITEM_TYPE_WEAPON, ITEM_TYPE_ORIGIN_QI]


async def autocomplete_item_id(_: disnake.ApplicationCommandInteraction, user_input: str) -> list[str]:
    return _autocomplete_item(user_input, lambda item: item.item_id)


async def autocomplete_item_name(_: disnake.ApplicationCommandInteraction, user_input: str) -> list[str]:
    return _autocomplete_item(user_input, lambda item: item.name)


def compute_item_file_path(item_id: str, item_type: str) -> str:
    item_id, _ = convert_id(item_id)
    return f"./media/{item_type}/{item_id}.png"


def _sanitize_price_dict(prices: dict[str, Any]) -> dict[str, int]:
    return {currency: int(value) for currency, value in prices.items()} if prices is not None else {}


class ItemDefinition:
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__()
        self._item_id: str = item_id
        self._name: str = name
        self._type: str = item_type
        self._tier: int = tier
        self._weight: int = weight
        self._description: str = description
        self._effect_description: str = effect_description
        self._shop_buy_prices: dict[str, int] = {currency: price for currency, price in shop_buy_prices.items() if price > 0} if shop_buy_prices is not None else {}
        self._shop_sell_prices: dict[str, int] = {currency: price for currency, price in shop_sell_prices.items() if price > 0} if shop_sell_prices is not None else {}
        self._extra_properties: Optional[dict[str, Any]] = extra_properties

    # ============================================= Special methods =============================================

    def __repr__(self) -> str:
        return f"ItemDefinition {{item_id: {self._item_id}, name: {self._name}, type: {self._type}, tier: {self._tier}, weight: {self._weight}}}"

    def __str__(self) -> str:
        return self._name

    def __getitem__(self, property_name: str) -> Optional[Any]:
        return self.get_property(property_name)

    def __hash__(self) -> int:
        return hash(self._item_id)

    def __eq__(self, other) -> bool:
        return other is not None and isinstance(other, ItemDefinition) and type(other) is type(self) and self._item_id == other._item_id

    def __ne__(self, other) -> bool:
        return not self.__eq__(other)

    def __lt__(self, other: D) -> bool:
        if other is None:
            # Non-None at the beginning
            return True

        if self.id == other.id:
            # Equal is not lower than
            return False

        # Sort by tier, then type, then name
        diff: int = self.tier - other.tier
        if diff < 0:
            return True
        elif diff > 0:
            return False

        if self.type < other.type:
            return True
        elif self.type > other.type:
            return False

        return self.name < other.name

    def __le__(self, other: D) -> bool:
        return self.__lt__(other) or self.__eq__(other)

    def __gt__(self, other: D) -> bool:
        return not self.__le__(other)

    def __ge__(self, other: D) -> bool:
        return self.__gt__(other) or self.__eq__(other)

    # ================================================ Properties ===============================================

    @property
    def craftable(self) -> bool:
        craft_entry: Optional[dict[str, Any]] = self._extra_properties.get(PROP_CRAFT, None)
        return craft_entry is not None

    @property
    def crafting_materials(self) -> Optional[dict[str, int]]:
        craft_entry: Optional[dict[str, Any]] = self._extra_properties.get(PROP_CRAFT, None)
        if craft_entry is None:
            return None

        return self._get_materials_from_properties(craft_entry)

    @property
    def description(self) -> str:
        return self._description

    @property
    def effect_description(self) -> str:
        return self._effect_description

    @property
    def image(self) -> Optional[disnake.File]:
        file_path = compute_item_file_path(self._item_id, self._type)
        try:
            return disnake.File(file_path)
        except OSError:
            return None

    @property
    def fungible(self) -> bool:
        return self.stackable or self._type == ITEM_TYPE_ORIGIN_QI

    @property
    def id(self) -> str:
        return self._item_id

    @property
    def item_id(self) -> str:
        return self._item_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def pet_food(self) -> bool:
        return self.pet_food_exp > 0

    @property
    def pet_food_exp(self) -> float:
        return self._extra_properties.get(PROP_PET_FOOD_EXP, 0)

    @property
    def properties(self) -> dict[str, Any]:
        return self._extra_properties.copy()

    @property
    def refinable(self) -> bool:
        refine_entry: Optional[dict[str, int]] = self._extra_properties.get(PROP_REQUIREMENTS, None)
        return refine_entry is not None

    @property
    def refine_materials(self) -> Optional[dict[str, int]]:
        return self._get_materials_from_properties(self._extra_properties)

    @property
    def shop_buy_prices(self) -> dict[str, Any]:
        return self._shop_buy_prices.copy() if self._shop_buy_prices is not None else {}

    @property
    def shop_sell_prices(self) -> dict[str, Any]:
        return self._shop_sell_prices.copy() if self._shop_sell_prices is not None else {}

    @property
    def stackable(self) -> bool:
        return self._type not in UNSTACKABLE_ITEM_TYPES

    @property
    def tier(self) -> int:
        return self._tier

    @property
    def tier_label(self) -> str:
        return "Tier"

    @property
    def type(self) -> str:
        return self._type

    @property
    def sub_type(self) -> Optional[str]:
        return None

    @property
    def weight(self) -> int:
        return self._weight

    # ============================================== "Real" methods =============================================

    def buy_price(self, currency: str = CURRENCY_NAME_GOLD) -> int:
        return self._shop_buy_prices.get(currency, 0)

    def get_property(self, name: str) -> Optional[Any]:
        return self._extra_properties.get(name, None)

    def sell_price(self, currency: str = CURRENCY_NAME_GOLD) -> int:
        return self._shop_sell_prices.get(currency, 0)

    def buyable(self, currency: Optional[str] = None) -> bool:
        if currency is None:
            return self._contains_non_null_values(self._shop_buy_prices)

        return self._shop_buy_prices.get(currency, 0) != 0

    def sellable(self, currency: Optional[str] = None) -> bool:
        if currency is None:
            return self._contains_non_null_values(self._shop_sell_prices)

        return self._shop_sell_prices.get(currency, 0) != 0

    @staticmethod
    def _contains_non_null_values(amounts: dict[str, Any]):
        for value in amounts.values():
            if value > 0:
                return True

        return False

    @staticmethod
    def _get_materials_from_properties(props: dict[str, Any]) -> Optional[dict[str, int]]:
        requirements: Optional[dict[str, int]] = props.get(PROP_REQUIREMENTS, None)
        return requirements


class FlameDefinition(ItemDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)

        self._combat_power_boost: float = float(extra_properties[PROP_FLAME_CP_BOOST]) if PROP_FLAME_CP_BOOST in extra_properties else 0.0
        self._experience_boost: float = float(extra_properties[PROP_FLAME_EXP_BOOST]) if PROP_FLAME_EXP_BOOST in extra_properties else 0.0
        self._refine_bonus: float = float(extra_properties[PROP_FLAME_REFINE_BONUS]) if PROP_FLAME_REFINE_BONUS in extra_properties else 0.0

    @property
    def combat_power_boost(self) -> float:
        return self._combat_power_boost

    @property
    def experience_boost(self) -> float:
        return self._experience_boost

    @property
    def refine_bonus(self) -> float:
        return self._refine_bonus

    @property
    def stackable(self) -> bool:
        return True


class BeastFlameDefinition(FlameDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)


class HeavenlyFlameDefinition(FlameDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)

        self._absorption_difficulty: int = int(extra_properties[PROP_HEAVENLY_FLAME_ABSORB_DIFFICULTY]) if PROP_HEAVENLY_FLAME_ABSORB_DIFFICULTY in extra_properties else 0

    @property
    def absorption_difficulty(self) -> int:
        return self._absorption_difficulty

    @property
    def tier_label(self) -> str:
        return "Heavenly Flame Rank"


class QiFlameDefinition(FlameDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)
        self.rank_requirement_major: int = extra_properties[PROP_QI_FLAME_RANK_REQUIREMENT_MAJOR]
        self.rank_requirement_minor: int = extra_properties[PROP_QI_FLAME_RANK_REQUIREMENT_MINOR]


class KnowledgeManualDefinition(ItemDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)

    @property
    def stackable(self) -> bool:
        # Not sure actually
        return True


class FightTechniqueManualDefinition(KnowledgeManualDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)

        self._combat_power_bonus: int = extra_properties[PROP_FIGHT_TECHNIQUE_CP_BONUS]

    @property
    def combat_power_bonus(self) -> int:
        return self._combat_power_bonus


class QiMethodManualDefinition(KnowledgeManualDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)

        self._combat_power_boost: float = extra_properties[PROP_QI_METHOD_CP_BOOST]

    @property
    def combat_power_boost(self) -> float:
        return self._combat_power_boost


class RingDefinition(ItemDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)

    @property
    def stackable(self) -> bool:
        return False


class StorageRingDefinition(RingDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)

        self._weight_capacity: int = extra_properties[PROP_STORAGE_RING_CAPACITY]

    @property
    def weight_capacity(self) -> int:
        return self._weight_capacity


class GeneralStorageRingDefinition(StorageRingDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)


class RestrictedStorageRingDefinition(StorageRingDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)

        self._valid_contents: list[str] = extra_properties[PROP_STORAGE_RING_VALID_CONTENTS]

    @property
    def valid_contents(self) -> list[str]:
        return self._valid_contents.copy()


class MiscellaneousItemDefinition(ItemDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)

        # Divine meat is flagged as misc so have to deal with it here
        self._pet_food_exp: Optional[int] = extra_properties[PROP_PET_FOOD_EXP] if PROP_PET_FOOD_EXP in extra_properties else None
        self._sub_type: str = "meat" if self._pet_food_exp is not None else None

    @property
    def pet_food(self) -> bool:
        return self.pet_food_exp is not None and self.pet_food_exp > 0

    @property
    def pet_food_exp(self) -> float:
        return self._pet_food_exp

    @property
    def stackable(self) -> bool:
        return True

    @property
    def sub_type(self) -> str:
        return self._sub_type


class MonsterPartDefinition(ItemDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)

        self.max_quantity_per_beast: int = extra_properties.get(PROP_MONSTER_PART_MAX_DROP, DEFAULT_MAX_DROP_PER_BEAST)

    @property
    def stackable(self) -> bool:
        return True


class ChestDefinition(ItemDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)

        self._loot_type: str = extra_properties[PROP_LOOT_TYPE]
        self._loot_rank: int = int(extra_properties[PROP_LOOT_RANK]) if PROP_LOOT_RANK in extra_properties else 1
        self._loot_tier: Optional[int] = int(extra_properties[PROP_LOOT_TIER]) if PROP_LOOT_TIER in extra_properties else None

    @property
    def loot_rank(self) -> int:
        return self._loot_rank

    @property
    def loot_tier(self) -> Optional[int]:
        return self._loot_tier

    @property
    def loot_type(self) -> str:
        return self._loot_type

    @property
    def stackable(self) -> bool:
        return True


class CoreDefinition(ItemDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)

    @property
    def stackable(self) -> bool:
        return True


class CauldronDefinition(ItemDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)

        self._cooldown_reduction_range: (int, int) = extra_properties[PROP_CAULDRON_COOLDOWN_REDUCTION]
        self._refine_bonus_range: (int, int) = extra_properties[PROP_CAULDRON_REFINE_BONUS]

    @property
    def cooldown_reduction_range(self) -> tuple[int, int]:
        return self._cooldown_reduction_range

    @property
    def refine_bonus_range(self) -> tuple[int, int]:
        return self._refine_bonus_range

    @property
    def stackable(self) -> bool:
        return False

    def roll_cooldown_reduction(self) -> int:
        min_value, max_value = self.cooldown_reduction_range
        return random.randint(min_value, max_value)

    def roll_refine_bonus(self) -> int:
        min_value, max_value = self.refine_bonus_range
        return random.randint(min_value, max_value)


class BeastArmorDefinition(MonsterPartDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)
        self._sub_type: str = "armor"

    @property
    def sub_type(self) -> str:
        return self._sub_type


class BoneDefinition(MonsterPartDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)
        self._sub_type: str = "bone"

    @property
    def sub_type(self) -> str:
        return self._sub_type


class ClawDefinition(MonsterPartDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)
        self._sub_type: str = "claw"

    @property
    def sub_type(self) -> str:
        return self._sub_type


class CoralDefinition(MonsterPartDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)
        self._sub_type: str = "coral"

    @property
    def sub_type(self) -> str:
        return self._sub_type


class CrystalDefinition(MonsterPartDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)
        self._sub_type: str = "crystal"

    @property
    def sub_type(self) -> str:
        return self._sub_type


class EggDefinition(ItemDefinition):

    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)

        self._parent_beast_name: str = extra_properties[PROP_EGG_PARENT]
        self._hatch_rates: dict[str, int] = extra_properties[PROP_EGG_HATCH_RATES]

    @property
    def hatch_rates(self) -> dict[str, int]:
        return self._hatch_rates.copy()

    @property
    def parent_beast_name(self) -> str:
        return self._parent_beast_name

    @property
    def possible_beast_names(self) -> set[str]:
        return set(self._hatch_rates.keys())

    @property
    def stackable(self) -> bool:
        return True

    def hatch(self) -> str:
        return roll_from_weighted_dict(self._hatch_rates)

    def hatch_rate(self, result: str) -> int:
        return self._hatch_rates.get(result, 0)


class EssenceDefinition(MonsterPartDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)
        self._sub_type: str = "essence"

    @property
    def sub_type(self) -> str:
        return self._sub_type


class FurDefinition(MonsterPartDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)
        self._sub_type: str = "fur"

    @property
    def sub_type(self) -> str:
        return self._sub_type


class HerbDefinition(ItemDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)

    @property
    def stackable(self) -> bool:
        return True


class HornDefinition(MonsterPartDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)
        self._sub_type: str = "horn"

    @property
    def sub_type(self) -> str:
        return self._sub_type


class LeatherDefinition(MonsterPartDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)
        self._sub_type: str = "leather"

    @property
    def sub_type(self) -> str:
        return self._sub_type


class MapFragmentDefinition(ItemDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)
        self._fragment_number: int = extra_properties[PROP_MAP_FRAGMENT_NUMBER]
        self._target_item_id: str = extra_properties[PROP_MAP_FRAGMENT_ITEM]
        self._sub_type: str = self._target_item_id
        self._all_parts: Optional[list[MapFragmentDefinition]] = None
        self._siblings: Optional[list[MapFragmentDefinition]] = None

    @property
    def all_parts(self) -> list[MapFragmentDefinition]:
        if self._all_parts is None:
            all_parts: list[MapFragmentDefinition] = []
            candidates: list[ItemDefinition] = ItemCompendium().filter(item_type=self.type, item_sub_type=self._sub_type)
            # Have to use a for and not a comprehension to make the IDE understand that typing is ok
            for definition in candidates:
                if isinstance(definition, MapFragmentDefinition):
                    all_parts.append(definition)

            all_parts.sort()
            self._all_parts = all_parts

        return self._all_parts.copy()

    @property
    def fragment_count(self) -> int:
        return len(self.sibling_fragments) + 1

    @property
    def fragment_number(self) -> int:
        return self._fragment_number

    @property
    def sibling_fragments(self) -> list[MapFragmentDefinition]:
        if self._siblings is None:
            self._siblings: list[MapFragmentDefinition] = [sibling for sibling in self.all_parts if sibling != self]

        return self._siblings.copy()

    @property
    def sub_type(self) -> str:
        return self._sub_type

    @property
    def target_item_id(self) -> str:
        return self._target_item_id


class MeatDefinition(MonsterPartDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)
        self._pet_food_exp: int = extra_properties[PROP_PET_FOOD_EXP]
        self._sub_type: str = "meat"

    @property
    def pet_food(self) -> bool:
        return True

    @property
    def pet_food_exp(self) -> float:
        return self._pet_food_exp

    @property
    def sub_type(self) -> str:
        return self._sub_type


class MetalDefinition(MonsterPartDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)
        self._sub_type: str = "metal"

    @property
    def sub_type(self) -> str:
        return self._sub_type


class MonsterHeartDefinition(MonsterPartDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)
        self._sub_type: str = "heart"

    @property
    def sub_type(self) -> str:
        return self._sub_type


class OreDefinition(MonsterPartDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)
        self._sub_type: str = "ore"

    @property
    def sub_type(self) -> str:
        return self._sub_type


class OriginQiDefinition(MiscellaneousItemDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)
        self._sub_type: str = "origin_qi"

    @property
    def stackable(self) -> bool:
        return False

    @property
    def sub_type(self) -> str:
        return self._sub_type


class PetAmplifierDefinition(MiscellaneousItemDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)

        self._reroll_quality_bonus: int = extra_properties[PROP_PET_AMPLIFIER_REROLL_BONUS]
        self._sub_type: str = "pet_amp"

    @property
    def reroll_quality_bonus(self) -> int:
        return self._reroll_quality_bonus

    @property
    def stackable(self) -> bool:
        return True

    @property
    def sub_type(self) -> str:
        return self._sub_type


class PillDefinition(ItemDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)

        self._consume_effects: dict[str, Any] = extra_properties[PROP_PILL_CONSUME_EFFECTS]
        self._refine_base_chance: int = extra_properties[PROP_PILL_BASE_REFINE_CHANCE]
        self._refine_experience: int = extra_properties[PROP_PILL_REFINE_EXPERIENCE]
        self._refine_materials: dict[str, int] = extra_properties[PROP_REQUIREMENTS]

    @property
    def consume_effects(self) -> dict[str, Any]:
        return self._consume_effects.copy()

    @property
    def craftable(self) -> bool:
        return False

    @property
    def pet_food(self) -> bool:
        return False

    @property
    def refinable(self) -> bool:
        return True

    @property
    def refine_base_chance(self) -> int:
        return self._refine_base_chance

    @property
    def refine_experience(self) -> int:
        return self._refine_experience

    @property
    def refine_materials(self) -> dict[str, int]:
        return self._refine_materials

    @property
    def stackable(self) -> bool:
        return True

    def get_consume_effect(self, effect_key: str) -> Optional[Any]:
        return self._consume_effects.get(effect_key, None)

    def has_consume_effect(self, effect_key: str) -> bool:
        return effect_key in self._consume_effects


class PincerDefinition(MonsterPartDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)
        self._sub_type: str = "pincers"

    @property
    def sub_type(self) -> str:
        return self._sub_type


class RuneBaseDefinition(MiscellaneousItemDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)

        self._sub_type: str = "rune_base"

    @property
    def stackable(self) -> bool:
        return True

    @property
    def sub_type(self) -> str:
        return self._sub_type


class RuneDefinition(MiscellaneousItemDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)

        self._sub_type: str = "rune"

    @property
    def stackable(self) -> bool:
        return True

    @property
    def sub_type(self) -> str:
        return self._sub_type


class ScaleDefinition(MonsterPartDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)

        self._sub_type: str = "scales"

    @property
    def sub_type(self) -> str:
        return self._sub_type


class StoneDefinition(MonsterPartDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)

        self._sub_type: str = "stone"

    @property
    def sub_type(self) -> str:
        return self._sub_type


class ShellDefinition(MonsterPartDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)

        self._sub_type: str = "shell"

    @property
    def sub_type(self) -> str:
        return self._sub_type


class SlimeDefinition(MonsterPartDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)
        self._sub_type: str = "slime"

    @property
    def sub_type(self) -> str:
        return self._sub_type


class TailDefinition(MonsterPartDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)

        self._sub_type: str = "tail"

    @property
    def sub_type(self) -> str:
        return self._sub_type


class TendonDefinition(MonsterPartDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)
        self._sub_type: str = "tendon"

    @property
    def sub_type(self) -> str:
        return self._sub_type


class ToothDefinition(MonsterPartDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)

        self._sub_type: str = "tooth"

    @property
    def sub_type(self) -> str:
        return self._sub_type


class ValuableDefinition(ItemDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)

    @property
    def stackable(self) -> bool:
        return True


class VenomDefinition(MonsterPartDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)

        self._sub_type: str = "venom"

    @property
    def sub_type(self) -> str:
        return self._sub_type


class WeaponDefinition(ItemDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)

    @property
    def stackable(self) -> bool:
        return False


class WingDefinition(MonsterPartDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)

        self._sub_type: str = "wings"

    @property
    def sub_type(self) -> str:
        return self._sub_type


class WoodDefinition(MonsterPartDefinition):
    def __init__(self, item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str, shop_buy_prices: Optional[dict[str, int]] = None, shop_sell_prices: Optional[dict[str, int]] = None,
                 extra_properties: Optional[dict[str, Any]] = None):
        super().__init__(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, extra_properties)

        self._sub_type: str = "wood"

    @property
    def sub_type(self) -> str:
        return self._sub_type


@singleton
class ItemCompendium:
    def __init__(self):
        self._items: dict[str, ItemDefinition] = {}
        self._item_types: set[str] = set()
        self._max_tier: int = 0

    # ============================================= Special methods =============================================

    def __repr__(self) -> str:
        return f"ItemCompendium containing {len(self._items)} item definitions"

    def __str__(self) -> str:
        return "ItemCompendium"

    def __contains__(self, key: str) -> bool:
        return key in self._items

    def __getitem__(self, item_id: str) -> Optional[ItemDefinition]:
        return self.get(item_id)

    # ================================================ Properties ===============================================

    @property
    def items(self) -> dict[str, ItemDefinition]:
        return self._items.copy()

    @property
    def item_list(self) -> list[ItemDefinition]:
        return list(self._items.values())

    @property
    def item_ids(self) -> set[str]:
        return set(self._items.keys())

    @property
    def item_names(self) -> set[str]:
        return {item.name for item in self._items.values()}

    @property
    def item_types(self) -> set[str]:
        return self._item_types.copy()

    @property
    def max_tier(self) -> int:
        return self._max_tier

    # ========================================= Disnake lifecycle methods ========================================

    async def load(self):
        self.load_from_file()
        _log("system", f"Loaded {len(self._items)} ItemDefinition")

    def load_from_file(self, file_path: str = "./data/items.json"):
        with open(file=file_path, mode="r", encoding="utf-8") as file:
            data: dict[str, dict[str, Any]] = json.load(file)

        temp_items: dict[str, ItemDefinition] = {}
        max_tier: int = 0
        for item_id, attrs in data.items():
            tier: int = attrs["tier"]
            temp_items[item_id] = self._new_definition(item_id, attrs["name"], attrs["type"], tier, attrs["weight"], attrs["description"], attrs["effect_description"], attrs.get("shop_buy_prices"), attrs.get("shop_sell_prices"),
                                                       attrs.get("properties", {}))
            if tier > max_tier:
                max_tier = tier

        self._initialize_members(temp_items, max_tier)

    async def load_from_database(self):
        item_data: list[tuple[str, str, str, int, int, str, str, dict[str, int], dict[str, int], dict[str, Any]]] = \
            await AllItems.all().order_by("type", "tier").values_list("id", "name", "type", "tier", "weight", "description", "e_description", "buy_cost_d", "sell_cost_d", "properties")

        temp_items: dict[str, ItemDefinition] = {}
        max_tier: int = 0
        for item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties in item_data:
            temp_items[item_id] = self._new_definition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
            if tier > max_tier:
                max_tier = tier

        self._initialize_members(temp_items, max_tier)

    def _initialize_members(self, definitions: dict[str, ItemDefinition], max_tier: int) -> None:
        self._items: dict[str, ItemDefinition] = definitions
        self._item_types: set[str] = {item.type for item in definitions.values()}
        self._max_tier: int = max_tier

    # ============================================== "Real" methods =============================================

    @staticmethod
    def compare_items(item_1: ItemDefinition, item_2: ItemDefinition) -> int:
        if item_1.id == item_2.id:
            # Easy equal case first
            return 0

        # Treat h_flame and b_flame as highest tiers (oqi > h_flame > b_flame > map fragment > pill > egg > core > rest)
        if item_1.type == ITEM_TYPE_ORIGIN_QI:
            return -1
        elif item_2.type == ITEM_TYPE_ORIGIN_QI:
            return 1

        if item_1.type == ITEM_TYPE_HEAVENLY_FLAME and item_2.type != ITEM_TYPE_HEAVENLY_FLAME:
            return -1
        elif item_2.type == ITEM_TYPE_HEAVENLY_FLAME and item_1.type != ITEM_TYPE_HEAVENLY_FLAME:
            return 1

        if item_1.type == ITEM_TYPE_BEAST_FLAME and item_2.type != ITEM_TYPE_BEAST_FLAME:
            return -1
        elif item_2.type == ITEM_TYPE_BEAST_FLAME and item_1.type != ITEM_TYPE_BEAST_FLAME:
            return 1

        if item_1.type == ITEM_TYPE_MAP_FRAGMENT and item_2.type != ITEM_TYPE_MAP_FRAGMENT:
            return -1
        elif item_2.type == ITEM_TYPE_MAP_FRAGMENT and item_1.type != ITEM_TYPE_MAP_FRAGMENT:
            return 1

        if item_1.type == ITEM_TYPE_PILL and item_2.type != ITEM_TYPE_PILL:
            return -1
        elif item_2.type == ITEM_TYPE_PILL and item_1.type != ITEM_TYPE_PILL:
            return 1

        if item_1.type == ITEM_TYPE_EGG and item_2.type != ITEM_TYPE_EGG:
            return -1
        elif item_2.type == ITEM_TYPE_EGG and item_1.type != ITEM_TYPE_EGG:
            return 1

        if item_1.type == ITEM_TYPE_MONSTER_CORE and item_2.type != ITEM_TYPE_MONSTER_CORE:
            return -1
        elif item_2.type == ITEM_TYPE_MONSTER_CORE and item_1.type != ITEM_TYPE_MONSTER_CORE:
            return 1

        # Tier diff has reversed impact to show higher tiered items before
        tier_diff: int = item_1.tier - item_2.tier
        if tier_diff < 0:
            return 1
        elif tier_diff > 0:
            return -1
        else:
            # Same tier
            if item_1.name < item_2.name:
                return -1
            elif item_1.name > item_2.name:
                return 1
            else:
                return 0

    def compare_item_ids(self, item_id_1: str, item_id_2: str) -> int:
        if item_id_1 == item_id_2:
            # Easy equal case first
            return 0

        # We do Energy Ratio > Energy Flat > Exp Ratio > Exp Flat > Stars > Gold > Arena Coins > Items by tier lowest to highest then alpha
        if item_id_1 == PSEUDO_ITEM_ID_ENERGY_RATIO:
            return -1
        elif item_id_2 == PSEUDO_ITEM_ID_ENERGY_RATIO:
            return 1

        if item_id_1 == PSEUDO_ITEM_ID_ENERGY_FLAT:
            return -1
        elif item_id_2 == PSEUDO_ITEM_ID_ENERGY_FLAT:
            return 1

        if item_id_1 == PSEUDO_ITEM_ID_EXP_RATIO:
            return -1
        elif item_id_2 == PSEUDO_ITEM_ID_EXP_RATIO:
            return 1

        if item_id_1 == PSEUDO_ITEM_ID_EXP_FLAT:
            return -1
        elif item_id_2 == PSEUDO_ITEM_ID_EXP_FLAT:
            return 1

        if item_id_1 == PSEUDO_ITEM_ID_STAR:
            return -1
        elif item_id_2 == PSEUDO_ITEM_ID_STAR:
            return 1

        if item_id_1 == PSEUDO_ITEM_ID_GOLD:
            return -1
        elif item_id_2 == PSEUDO_ITEM_ID_GOLD:
            return 1

        if item_id_1 == PSEUDO_ITEM_ID_ARENA_COIN:
            return -1
        elif item_id_2 == PSEUDO_ITEM_ID_ARENA_COIN:
            return 1

        base_id_1, unique_id_1 = convert_id(item_id_1)
        base_id_2, unique_id_2 = convert_id(item_id_2)

        if base_id_1 not in self._items:
            return 1
        elif base_id_2 not in self._items:
            return -1

        return self.compare_items(self.get(base_id_1), self.get(base_id_2))

    def compute_weight(self, items: dict[str, int]) -> int:
        """
        Compute the weight of the specified items expressed as an item_id -> quantity dictionary

        Parameters
        ----------
        items: dict[str, int]
               The item dictionary in an item_id -> quantity syntax

        Returns
        -------
        int
            The total weight of the items represented by the specified dictionary
        """
        return sum([self.get(convert_id(item_id)[0]).weight * quantity for item_id, quantity in items.items()])

    def describe_item(self, item_id: str, quantity: int, use_markdown: bool = True) -> str:
        if item_id == PSEUDO_ITEM_ID_ENERGY_FLAT:
            quantity_str: str = f"{quantity:,}"
            return f"{_quote_if_needed(quantity_str, use_markdown)} energy"
        elif item_id == PSEUDO_ITEM_ID_ENERGY_RATIO:
            quantity_str = _quote_if_needed(f"{quantity:,}%", use_markdown)
            return f"{quantity_str} of your maximum energy"
        elif item_id == PSEUDO_ITEM_ID_EXP_FLAT:
            quantity_str: str = f"{quantity:,}"
            return f"{_quote_if_needed(quantity_str, use_markdown)} exp"
        elif item_id == PSEUDO_ITEM_ID_EXP_RATIO:
            quantity_str = _quote_if_needed(f"{RelativeExperienceLoot.as_percentage(quantity) * 100:.2f}%", use_markdown)
            return f"{quantity_str} of your rank's breakthrough exp"
        elif item_id == PSEUDO_ITEM_ID_GOLD:
            quantity_str: str = f"{quantity:,}"
            return f"{_quote_if_needed(quantity_str, use_markdown)} gold"
        elif item_id == PSEUDO_ITEM_ID_ARENA_COIN:
            quantity_str: str = f"{quantity:,}"
            return f"{_quote_if_needed(quantity_str, use_markdown)} arena coins"
        elif item_id == PSEUDO_ITEM_ID_STAR:
            quantity_str: str = f"{quantity:,}"
            return f"{_quote_if_needed(quantity_str, use_markdown)} stars"
        else:
            base_id, unique_id = convert_id(item_id)
            quantity_str: str = f"{quantity:,}x"
            item_desc: str = self.get(base_id).name if base_id in self._items else item_id
            return f"{_quote_if_needed(quantity_str, use_markdown)} {item_desc}"

    def describe_dict(self, items: dict[str, int], selector: Optional[Callable[[list[str]], list[str]]] = None, use_markdown: bool = True, list_prefix: str = "- ") -> str:
        """
        Describe the contents of the item_id -> quantity dictionary into a human-understandable list, potentially using Discord markdown

        Parameters
        ----------
        items: dict[str, int]
               The item dictionary in an item_id -> quantity syntax

        selector: Callable[[list[str]], list[str]], optional
                  A filter to apply to the items list. It can act as a sorter as well

        use_markdown: bool, optional
                      Determines if Discord markdown should be applied to the quantity

        list_prefix: str, optional
                     The prefix to place in front of each item. If specified this will replace the default "- " that generate a list in Discord

        Returns
        -------
        str
            A string representation of the item dictionary that can be understood by a human
        """
        item_ids: list[str] = list(items.keys())
        if selector is None:
            item_ids.sort(key=cmp_to_key(self.compare_item_ids))
        else:
            item_ids = selector(item_ids)

        if len(item_ids) == 0:
            return ""

        desc_list: list[str] = []
        for item_id in item_ids:
            quantity: int = items.get(item_id, 0)
            if quantity > 0:
                desc_list.append(self.describe_item(item_id, quantity, use_markdown))

        return list_prefix + f"\n{list_prefix}".join(desc_list)

    async def dump_to_file(self, file_path: str):
        serialized_form: dict[str, dict[str, Any]] = {}
        for item_id, definition in self._items.items():
            serialized_form[item_id] = {
                "name": definition.name,
                "type": definition.type,
                "tier": definition.tier,
                "weight": definition.weight,
                "description": definition.description,
                "effect_description": definition.effect_description,
                "shop_buy_prices": definition.shop_buy_prices,
                "shop_sell_prices": definition.shop_sell_prices,
                "properties": definition.properties
            }

        with open(file=file_path, mode="w", encoding="utf-8") as file:
            json.dump(serialized_form, fp=file, indent=4, ensure_ascii=False)

    def filter(self,
               item_id: Optional[str] = None,
               item_id__in: Optional[set[str]] = None,
               name: Optional[str] = None,
               item_type: Optional[str] = None,
               item_type__in: Optional[str] = None,
               item_sub_type: Optional[str] = None,
               item_sub_type__in: Optional[str] = None,
               tier: Optional[int] = None,
               tier__gt: Optional[int] = None,
               tier__ge: Optional[int] = None,
               tier__lt: Optional[int] = None,
               tier__le: Optional[int] = None,
               tier__in: Optional[set[int]] = None,
               buyable: Optional[bool] = None,
               sellable: Optional[bool] = None,
               craftable: Optional[bool] = None,
               refinable: Optional[bool] = None,
               pet_food: Optional[bool] = None,
               criteria: Optional[Callable[[ItemDefinition], bool]] = None) -> list[ItemDefinition]:
        return self.find(item_id, item_id__in, name, item_type, item_type__in, item_sub_type, item_sub_type__in, tier, tier__gt, tier__ge, tier__lt, tier__le, tier__in, buyable, sellable, craftable, refinable, pet_food, criteria)

    def find(self,
             item_id: Optional[str] = None,
             item_id__in: Optional[set[str]] = None,
             name: Optional[str] = None,
             item_type: Optional[str] = None,
             item_type__in: Optional[str] = None,
             item_sub_type: Optional[str] = None,
             item_sub_type__in: Optional[str] = None,
             tier: Optional[int] = None,
             tier__gt: Optional[int] = None,
             tier__ge: Optional[int] = None,
             tier__lt: Optional[int] = None,
             tier__le: Optional[int] = None,
             tier__in: Optional[set[int]] = None,
             buyable: Optional[bool] = None,
             sellable: Optional[bool] = None,
             craftable: Optional[bool] = None,
             refinable: Optional[bool] = None,
             pet_food: Optional[bool] = None,
             criteria: Optional[Callable[[ItemDefinition], bool]] = None) -> list[ItemDefinition]:
        # Using successive filtering because I don't know Python well enough to do otherwise, in Java I would have used Predicate.and between the criteria
        result: list[ItemDefinition] = self.item_list
        if item_id is not None:
            result = [item for item in result if item.id == item_id]

        if item_id__in is not None:
            result = [item for item in result if item.id in item_id]

        if name is not None:
            # Case-insensitive name search
            result = [item for item in result if item.name.lower() == name.lower()]

        if item_type is not None:
            result = [item for item in result if item.type == item_type]

        if item_type__in is not None:
            result = [item for item in result if item.type in item_type__in]

        if item_sub_type is not None:
            result = [item for item in result if item.sub_type == item_sub_type]

        if item_sub_type__in is not None:
            result = [item for item in result if item.sub_type in item_sub_type__in]

        if tier is not None:
            result = [item for item in result if item.tier == tier]

        if tier__gt is not None:
            result = [item for item in result if item.tier > tier__gt]

        if tier__ge is not None:
            result = [item for item in result if item.tier <= tier__ge]

        if tier__lt is not None:
            result = [item for item in result if item.tier < tier__lt]

        if tier__le is not None:
            result = [item for item in result if item.tier <= tier__le]

        if tier__in is not None and len(tier__in) > 0:
            result = [item for item in result if item.tier in tier__in]

        if buyable is not None:
            result = [item for item in result if item.buyable == buyable]

        if sellable is not None:
            result = [item for item in result if item.sellable == sellable]

        if craftable is not None:
            result = [item for item in result if item.craftable == craftable]

        if refinable is not None:
            result = [item for item in result if item.refinable == refinable]

        if pet_food is not None:
            result = [item for item in result if item.pet_food == pet_food]

        if criteria is not None:
            result = [item for item in result if criteria(item)]

        return result

    def find_one(self,
                 item_id: Optional[str] = None,
                 item_id__in: Optional[set[str]] = None,
                 name: Optional[str] = None,
                 item_type: Optional[str] = None,
                 item_type__in: Optional[str] = None,
                 item_sub_type: Optional[str] = None,
                 item_sub_type__in: Optional[str] = None,
                 tier: Optional[int] = None,
                 tier__gt: Optional[int] = None,
                 tier__ge: Optional[int] = None,
                 tier__lt: Optional[int] = None,
                 tier__le: Optional[int] = None,
                 tier__in: Optional[set[int]] = None,
                 buyable: Optional[bool] = None,
                 sellable: Optional[bool] = None,
                 craftable: Optional[bool] = None,
                 refinable: Optional[bool] = None,
                 pet_food: Optional[bool] = None,
                 criteria: Optional[Callable[[ItemDefinition], bool]] = None) -> Optional[ItemDefinition]:
        candidates: list[ItemDefinition] = self.find(item_id, item_id__in, name, item_type, item_type__in, item_sub_type, item_sub_type__in, tier, tier__gt, tier__ge, tier__lt, tier__le, tier__in,
                                                     buyable, sellable, craftable, refinable, pet_food, criteria)
        candidate_count: int = len(candidates)
        if candidate_count == 0:
            return None
        elif candidate_count > 1:
            raise ValueError(f"The specified filter found more than one candidate item matching your criteria. Found: {candidates}")
        else:
            return candidates[0]

    def get(self, item_id: str) -> Optional[ItemDefinition]:
        return self.items.get(item_id, None)

    def ids(self) -> list[str]:
        id_list = list(self.items.keys())
        id_list.sort()
        return id_list

    def select_random(self,
                      rank: Optional[int] = None,
                      rank__gt: Optional[int] = None,
                      rank__ge: Optional[int] = None,
                      rank__lt: Optional[int] = None,
                      rank__le: Optional[int] = None,
                      rank__in: Optional[set[int]] = None,
                      affinity: Optional[str] = None,
                      affinity__in: Optional[set[str]] = None,
                      criteria: Optional[Callable[[ItemDefinition], bool]] = None) -> Optional[ItemDefinition]:
        candidates = self.find(None, rank, rank__gt, rank__ge, rank__lt, rank__le, rank__in, affinity, affinity__in, criteria)
        return random.choice(candidates) if len(candidates) > 0 else None

    async def update_database(self) -> tuple[int, int, int]:
        existing_id_data: list[tuple[str]] = await AllItems.all().values_list("id")
        existing_ids: set[str] = set()
        for row_data in existing_id_data:
            existing_ids.add(row_data[0])

        created_count: int = 0
        updated_count: int = 0
        deleted_count: int = 0
        for definition in self._items.values():
            item_id: str = definition.item_id
            if item_id in existing_ids:
                # Update
                await AllItems.filter(id=item_id).update(name=definition.name, type=definition.type, tier=definition.tier, weight=definition.weight, description=definition.description, e_description=definition.effect_description,
                                                         buy_cost_d=definition.shop_buy_prices, sell_cost_d=definition.shop_sell_prices, properties=definition.properties)
                existing_ids.remove(item_id)
                updated_count += 1
            else:
                # Create
                await AllItems.create(id=item_id, name=definition.name, type=definition.type, tier=definition.tier, weight=definition.weight, description=definition.description, e_description=definition.effect_description,
                                      buy_cost_d=definition.shop_buy_prices, sell_cost_d=definition.shop_sell_prices, properties=definition.properties)
                created_count += 1

        for item_id in existing_ids:
            # Delete
            await AllItems.filter(id=item_id).delete()
            deleted_count += 1

        return created_count, updated_count, deleted_count

    @staticmethod
    def _new_definition(item_id: str, name: str, item_type: str, tier: int, weight: int, description: str, effect_description: str,
                        shop_buy_prices: Optional[dict[str, int]], shop_sell_prices: Optional[dict[str, int]], properties: dict[str, Any]) -> ItemDefinition:
        shop_buy_prices = _sanitize_price_dict(shop_buy_prices)
        shop_sell_prices = _sanitize_price_dict(shop_sell_prices)

        # Simple cases first, then the more complex ones
        if item_type == ITEM_TYPE_BEAST_FLAME:
            return BeastFlameDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
        elif item_type == ITEM_TYPE_CAULDRON:
            return CauldronDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
        elif item_type == ITEM_TYPE_CHEST:
            return ChestDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
        elif item_type == ITEM_TYPE_EGG:
            return EggDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
        elif item_type == ITEM_TYPE_FIGHT_TECHNIQUE_MANUAL:
            return FightTechniqueManualDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
        elif item_type == ITEM_TYPE_HEAVENLY_FLAME:
            return HeavenlyFlameDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
        elif item_type == ITEM_TYPE_HERB:
            return HerbDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
        elif item_type == ITEM_TYPE_MONSTER_CORE:
            return CoreDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
        elif item_type == ITEM_TYPE_PILL:
            return PillDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
        elif item_type == ITEM_TYPE_QI_FLAME:
            return QiFlameDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
        elif item_type == ITEM_TYPE_QI_METHOD_MANUAL:
            return QiMethodManualDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
        elif item_type == ITEM_TYPE_VALUABLE:
            return ValuableDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
        elif item_type == ITEM_TYPE_WEAPON:
            return WeaponDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
        elif item_type == ITEM_TYPE_MAP_FRAGMENT:
            return MapFragmentDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
        elif item_type == ITEM_TYPE_MISCELLANEOUS:
            if item_id.startswith("rune_base"):
                return RuneBaseDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
            elif item_id.endswith("_rune"):
                return RuneDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
            elif item_id.startswith("pet_amp"):
                return PetAmplifierDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
            elif item_id == ITEM_TYPE_ORIGIN_QI:
                return OriginQiDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
            else:
                return MiscellaneousItemDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
        elif item_type == ITEM_TYPE_MONSTER_PART:
            if item_id.endswith("_armor"):
                return BeastArmorDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
            elif item_id.endswith("bone"):
                return BoneDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
            elif item_id.startswith("claws_") or item_id.endswith("_claw"):
                return ClawDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
            elif item_id.endswith("_coral"):
                return CoralDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
            elif item_id == "amethyst" or item_id.endswith("_crystal"):
                return CrystalDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
            elif item_id.endswith("_essence"):
                return EssenceDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
            elif item_id.startswith("fur_") or item_id.endswith("_mane"):
                return FurDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
            elif item_id.endswith("_heart"):
                return MonsterHeartDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
            elif item_id.startswith("horn_") or item_id.endswith("_horn"):
                return HornDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
            elif item_id.startswith("leather_"):
                return LeatherDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
            elif item_id.endswith("_ore"):
                return OreDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
            elif item_id.startswith("meat_"):
                return MeatDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
            elif item_id.startswith("metal_") or item_id.endswith("_metal_scrap"):
                return MetalDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
            elif item_id.startswith("pincers_"):
                return PincerDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
            elif item_id.startswith("scales_") or item_id.endswith("_scale"):
                return ScaleDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
            elif item_id.startswith("shell_"):
                return ShellDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
            elif item_id.endswith("_slime"):
                return SlimeDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
            elif item_id.endswith("_stone") or item_id.endswith("stone_shed"):
                return StoneDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
            elif item_id.endswith("_tail"):
                return TailDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
            elif item_id == "heartstring":
                return TendonDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
            elif item_id.startswith("tooth_") or item_id.endswith("_tooth") or item_id.endswith("_fang") or item_id.endswith("_tusk"):
                return ToothDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
            elif item_id.endswith("_venom"):
                return VenomDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
            elif item_id.startswith("wings_"):
                return WingDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
            elif item_id.startswith("wood_"):
                return WoodDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
            else:
                log_event("system", "item", f"Could not find the right monster part sub-class for item_id '{item_id}' and item_type '{item_type}'")
                return MonsterPartDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
        elif item_type == ITEM_TYPE_RING:
            if item_id == "accept_stone":
                return RestrictedStorageRingDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
            else:
                return GeneralStorageRingDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)
        else:
            _log("system", f"Could not find the right sub-class for item_id '{item_id}' and item_type '{item_type}'")
            return ItemDefinition(item_id, name, item_type, tier, weight, description, effect_description, shop_buy_prices, shop_sell_prices, properties)


class ItemDefinitionEmbed(disnake.Embed):
    def __init__(self, item: ItemDefinition):
        super().__init__()
        self._item: ItemDefinition = item

        definition: ItemDefinition = self._item
        self.title = definition.name
        self.description = f"**Type : `{definition.type}`** | **{definition.tier_label} : `{definition.tier}`**"
        self.color = COLOR_LIGHT_GREEN

        buy_cost_str: str = currency_dict_to_str(definition.shop_buy_prices)
        if len(buy_cost_str) < 1:
            buy_cost_str = "Unpurchasable"

        sell_cost_str: str = currency_dict_to_str(definition.shop_sell_prices)
        if len(sell_cost_str) < 1:
            sell_cost_str = "Unsellable"

        self.add_field(name="Cost", value=f"**Buying : **\n{buy_cost_str}\n**Selling : **\n{sell_cost_str}", inline=False)
        self.add_field(name="Description", value=definition.description, inline=False)

        if definition.type == "pill":
            requirements = ""
            pill_requirements_dict = definition.properties['requirements']
            for i in pill_requirements_dict:
                requirements += f"{i} x **`{pill_requirements_dict[i]}`**\n"
            self.add_field(name="Requirements", value=requirements, inline=False)

        self.add_field(name="Effect", value=definition.effect_description, inline=False)

    @property
    def item(self) -> ItemDefinition:
        return self._item


# =================================== Bootstrap and util class-level functions ==================================


def _autocomplete_item(user_input: str, supplier: Callable[[ItemDefinition], str]) -> list[str]:
    items = ItemCompendium().item_list
    if user_input is not None and len(user_input) > 0:
        lookup = user_input.lower()
        candidates = [supplier(item) for item in items if lookup in item.name.lower() or lookup in item.id]
    else:
        candidates = [supplier(item) for item in items]

    candidates.sort()
    if len(candidates) > MAX_CHOICE_ITEMS:
        candidates = candidates[:MAX_CHOICE_ITEMS]

    return candidates


def _log(user_id: Union[int, str], message: str):
    log_event(user_id, "compendium", message)


def _quote_if_needed(value: str, use_markdown: bool = True) -> str:
    return f"`{value}`" if use_markdown else value

from __future__ import annotations

import json
import math

import disnake
import random

from abc import ABC, abstractmethod
from functools import cmp_to_key
from typing import Callable, Optional, TypeVar, Union, Any, cast

from utils.ParamsUtils import INVALID_FILE_CHARACTERS
from utils.Styles import EXCLAMATION, PLUS
from utils.base import singleton
from utils.loot import Loot, FixedLoot, PossibleLoot, EmptyLoot, CompositeLoot, RandomLoot, uniform_distribution
from utils.CommandUtils import MAX_CHOICE_ITEMS
from utils.Database import AllBeasts, AllPets, Pet
from utils.InventoryUtils import ITEM_TYPE_MONSTER_CORE, ITEM_TYPE_MONSTER_PART, ITEM_TYPE_EGG, ITEM_TYPE_CHEST, ITEM_TYPE_MAP_FRAGMENT
from utils.LoggingUtils import log_event
from world.cultivation import BeastCultivationStage
from world.compendium import ItemCompendium, ItemDefinition, EggDefinition, LOOT_TYPE_MIXED, MapFragmentDefinition

# Could maybe add a flame and amplifier drop transform there, or not, we'll see how the bestiary gets used first
D = TypeVar("D", bound="BeastDefinition")
P = TypeVar("P", bound="PetBeastDefinition")

MATERIAL_DROP_QUANTITIES = {
    0: 20,
    1: 45,
    2: 25,
    3: 5,
    4: 4,
    5: 1
}

DEFAULT_PET_REROLL_COSTS: list[int] = [320_000, 1_280_000, 5_120_000, 20_480_000, 81_920_000, 327_680_000, 327_680_000, 1_310_720_000, 5_242_880_000, 20_971_520_000]
ABUNDANT_PET_REROLL_COSTS: list[int] = DEFAULT_PET_REROLL_COSTS
SCARCE_PET_REROLL_COSTS: list[int] = [480_000, 2_400_000, 12_000_000, 60_000_000, 300_000_000, 1_500_000_000, 7_500_000_000, 37_500_000_000]
EXOTIC_PET_REROLL_COSTS: list[int] = [640_000, 3_840_000, 23_040_000, 138_240_000, 829_440_000, 4_976_640_000, 29_859_840_000]

PET_REROLL_COST: dict[str, list[int]] = {
    "abundant": ABUNDANT_PET_REROLL_COSTS,
    "scarce": SCARCE_PET_REROLL_COSTS,
    "exotic": EXOTIC_PET_REROLL_COSTS
}

RAID_SPAWN_MIN_RANK = 2
RAID_SPAWN_MAX_RANK = 8
RAID_FIRE_SPAWN_BONUS_CHANCE = 50
RAID_AMPLIFIER_DROP_RATE: int = 20

AFFINITY_BLOOD = "Blood"
AFFINITY_DARK = "Dark"
AFFINITY_DRAGON = "Dragon"
AFFINITY_EARTH = "Earth"
AFFINITY_FIRE = "Fire"
AFFINITY_ICE = "Ice"
AFFINITY_LIGHTNING = "Lightning"
AFFINITY_MYSTERIOUS = "Mysterious"
AFFINITY_POISON = "Poison"
AFFINITY_ROCK = "Rock"
AFFINITY_WATER = "Water"
AFFINITY_WIND = "Wind"
AFFINITY_WOOD = "Wood"

AFFINITIES: list[str] = [AFFINITY_BLOOD, AFFINITY_DARK, AFFINITY_DRAGON, AFFINITY_EARTH, AFFINITY_FIRE, AFFINITY_ICE, AFFINITY_LIGHTNING, AFFINITY_MYSTERIOUS, AFFINITY_POISON, AFFINITY_ROCK, AFFINITY_WATER, AFFINITY_WIND, AFFINITY_WOOD]

RARITY_ABUNDANT = "abundant"
RARITY_SCARCE = "scarce"
RARITY_EXOTIC = "exotic"

# This constant has to be updated when added new beast ranks
MAX_BEAST_RANK: int = 9

BEAST_FLAME_DROP: dict[str, tuple[str, int]] = {
    "Fire Phoenix": ("phoenixflame", 9),  # R2
    "Winged Lion": ("lionflame", 9),  # R3
    "Two-Headed Flame Spirit Serpent": ("serpentflame", 8),  # R4
    "Fiery Breaking Mountain Rhinoceros": ("rhinoflame", 7),  # R5
    "Kui Wood Beast": ("peachflame", 7),  # R5
    "Amethyst Winged Lion": ("amethystlionflame", 6),  # R6
    "Eight-Winged Black Serpent Emperor": ("blackhellflame", 6),  # R6
    "Fire Scale Crocodile": ("magmaflame", 6),  # R6
    "Illusionary Fire Scorpion Dragon": ("illgoldenflame", 7),  # R7
    "Shock Wave Dragon": ("dryblueflame", 6),  # R7
    "Sea Demon Beast": ("seademonflame", 6),  # R7
    "Dark Sky Lion Emperor": ("darkdemonflame", 5),  # R8
    "Monstrous Demon Beast": ("monblueflame", 5),  # R8
    "Sky Bone Python": ("skycoldflame", 4)  # R8
}

VARIANT_NORMAL: str = "normal"
VARIANT_ELITE: str = "elite"
VARIANT_BOSS: str = "boss"
VARIANT_RAID: str = "raid"
VARIANTS: list[str] = [VARIANT_NORMAL, VARIANT_ELITE, VARIANT_BOSS, VARIANT_RAID]


async def autocomplete_beast_name(_: disnake.ApplicationCommandInteraction, user_input: str) -> list[str]:
    beast_names = Bestiary().beast_names
    lookup = user_input.lower()

    candidates = [name for name in beast_names if lookup in name.lower()]
    if len(candidates) > MAX_CHOICE_ITEMS:
        candidates = candidates[0:MAX_CHOICE_ITEMS]

    return candidates


async def autocomplete_pet_name(_: disnake.ApplicationCommandInteraction, user_input: str) -> list[str]:
    beast_names = Bestiary().pet_definitions
    lookup = user_input.lower()

    candidates = [name for name in beast_names if lookup in name.lower()]
    if len(candidates) > MAX_CHOICE_ITEMS:
        candidates = candidates[0:MAX_CHOICE_ITEMS]

    return candidates


def compute_beast_file_path(beast_name: str) -> str:
    if beast_name is None or len(beast_name) == 0:
        raise ValueError(f"beast_name must be specified, found: {beast_name}")

    file_name = INVALID_FILE_CHARACTERS.sub("_", beast_name)
    file_path = f"./media/beast/{file_name}.png"

    return file_path


def compute_beast_id(beast_name: str) -> str:
    if beast_name is None or len(beast_name) == 0:
        raise ValueError(f"beast_name must be specified, found: {beast_name}")

    lower_name = beast_name.lower()
    return INVALID_FILE_CHARACTERS.sub("", lower_name)


def compute_affinities(affinity_str: str) -> set[str]:
    return set() if affinity_str is None or len(affinity_str) == 0 else set(affinity_str.split("/"))


def compute_affinity_str(affinities: set[str]) -> str:
    if affinities is None or len(affinities) == 0:
        return ""

    return "/".join(sorted(affinities))


class BeastVariant(ABC):
    def __init__(self, name: str):
        super().__init__()
        self._name: str = name

    def __repr__(self) -> str:
        return f"BeastVariant {self._name}"

    def __str__(self) -> str:
        return self._name

    def __hash__(self) -> int:
        return hash(self._name) * 23

    def __eq__(self, other) -> bool:
        return other is not None and isinstance(other, BeastVariant) and self._name == other._name and type(self) is type(other)

    def __ne__(self, other) -> bool:
        return not self.__eq__(other)

    @property
    def name(self) -> str:
        return self._name

    @abstractmethod
    def alter_experience(self, beast: D, base_experience: int) -> int:
        pass

    @abstractmethod
    def alter_health(self, beast: D, base_health: int) -> int:
        pass

    @abstractmethod
    def alter_loot(self, beast: D, base_loot_table: Loot) -> Loot:
        pass


class BaseBeastVariant(BeastVariant):
    def __init__(self, name: str):
        super().__init__(name)

    def alter_experience(self, beast: D, base_experience: int) -> int:
        return base_experience

    def alter_health(self, beast: D, base_health: int) -> int:
        return base_health

    def alter_loot(self, beast: D, base_loot_table: Loot) -> Loot:
        return base_loot_table


class NormalBeastVariant(BaseBeastVariant):
    def __init__(self):
        super().__init__(VARIANT_NORMAL)


class EliteBeastVariant(BaseBeastVariant):
    def __init__(self):
        super().__init__(VARIANT_ELITE)

    def alter_experience(self, beast: D, base_experience: int) -> int:
        return base_experience * 3 // 2

    def alter_health(self, beast: D, base_health: int) -> int:
        return base_health * 5


class BaseBossBeastVariant(BaseBeastVariant):
    def __init__(self, name: str):
        super().__init__(name)

    @staticmethod
    def _has_flame_drop(beast: D) -> bool:
        return beast.name in BEAST_FLAME_DROP


class BossBeastVariant(BaseBossBeastVariant):
    def __init__(self):
        super().__init__(VARIANT_BOSS)

    def alter_experience(self, beast: D, base_experience: int) -> int:
        return base_experience * 2

    def alter_loot(self, beast: D, base_loot: Loot) -> Loot:
        compendium: ItemCompendium = ItemCompendium()
        if self._has_flame_drop(beast):
            return CompositeLoot([base_loot, self._create_flame_map_loot(beast, compendium), self._create_chest_loot(beast, compendium, {0: 75, 1: 20, 2: 5})])
        else:
            return CompositeLoot([base_loot, self._create_chest_loot(beast, compendium, {2: 75, 3: 20, 4: 5})])

    def alter_health(self, beast: D, base_health: int) -> int:
        return base_health * 20

    @staticmethod
    def _create_chest_loot(beast: D, compendium: ItemCompendium, quantity_dict: dict[int, int]) -> Loot:
        candidates: list[ItemDefinition] = compendium.filter(item_type=ITEM_TYPE_CHEST, tier=beast.rank, criteria=lambda i: i.loot_type == LOOT_TYPE_MIXED)
        return RandomLoot(uniform_distribution([item.item_id for item in candidates]), quantity_dict)

    @staticmethod
    def _create_flame_map_loot(beast: D, compendium: ItemCompendium) -> Loot:
        flame_id, drop_chance = BEAST_FLAME_DROP[beast.name]
        candidates: list[ItemDefinition] = compendium.filter(item_type=ITEM_TYPE_MAP_FRAGMENT, criteria=lambda i: cast(MapFragmentDefinition, i).target_item_id == flame_id)
        drop_chance = max(drop_chance // 4, 1)
        return RandomLoot(uniform_distribution([item.item_id for item in candidates]), {0: 100-drop_chance, 1: drop_chance})


class RaidBeastVariant(BaseBossBeastVariant):
    def __init__(self):
        super().__init__(VARIANT_RAID)

    def alter_experience(self, beast: D, base_experience: int) -> int:
        return base_experience * 5

    def alter_health(self, beast: D, base_health: int) -> int:
        return base_health * 999_999_999

    def alter_loot(self, beast: D, base_loot: Loot) -> Loot:
        # Remove all drop but potential amplifier and beast flame
        if beast.rank <= 3:
            new_loot = PossibleLoot(FixedLoot("pet_amp_1"), RAID_AMPLIFIER_DROP_RATE)
        elif beast.rank <= 6:
            new_loot = PossibleLoot(FixedLoot("pet_amp_2"), RAID_AMPLIFIER_DROP_RATE)
        else:
            new_loot = PossibleLoot(FixedLoot("pet_amp_3"), RAID_AMPLIFIER_DROP_RATE)

        return CompositeLoot([new_loot, self._create_flame_loot(beast)])

    def _create_flame_loot(self, beast: D) -> Loot:
        if self._has_flame_drop(beast):
            flame_id, drop_chance = BEAST_FLAME_DROP[beast.name]
            return PossibleLoot(FixedLoot(flame_id), drop_chance)

        return EmptyLoot()


class BeastDefinition:
    def __init__(self, name: str, rank: int, health: int, affinities: set[str], exp_value: int, core_id: str, core_drop_rate: int, material_loot: Loot, variant: BeastVariant, pet_stats: Optional[dict[str, P]] = None,
                 base_definition: Optional[BeastDefinition] = None):
        super().__init__()

        self._id: str = compute_beast_id(name)
        self._name: str = name
        self._rank: int = rank
        self._health: int = health
        self._affinities: set[str] = affinities.copy()
        self._exp_value: int = exp_value
        self._monster_core_id: str = core_id
        self._monster_core_drop_rate: int = core_drop_rate
        self._material_loot: Loot = material_loot
        self._variant: BeastVariant = variant
        self._base_definition: Optional[BeastDefinition] = base_definition
        self._pet_stats: Optional[dict[str, P]] = pet_stats

        if variant is not None and variant.name != VARIANT_NORMAL:
            if base_definition is None:
                raise ValueError("Creating a boss or raid beast definition must be base on a base definition, found: None")

            # Don't use values from base definition here in case someone want to override the base value of a boss or raid mode through constructor arguments. Not much use for it, but no real reason to prevent it either
            self._health: int = variant.alter_health(self, health)
            self._exp_value: int = variant.alter_experience(self, exp_value)
            self._loot: Loot = variant.alter_loot(self, base_definition._loot)
        else:
            if base_definition is not None:
                raise ValueError(f"Should not specify a base definition for non-boss, non-raid beasts, found: {base_definition}")

            self._loot: Loot = CompositeLoot([material_loot, PossibleLoot(FixedLoot(item_id=self._monster_core_id), probability=math.ceil(core_drop_rate / 4))])

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"BeastDefinition {{name: {self.name}, rank: {self.rank}, health: {self.health}, affinities: {compute_affinity_str(self.affinities)}, exp_value: {self.exp_value}}}"

    def __str__(self):
        return self.title

    def __hash__(self) -> int:
        return hash(self._name)

    def __eq__(self, other):
        return other is not None and isinstance(other, BeastDefinition) and self._name == other._name and self._variant == other._variant

    def __ne__(self, other):
        return not self.__eq__(other)

    # ================================================ Properties ===============================================

    @property
    def affinities(self) -> set[str]:
        return self._affinities.copy()

    @property
    def base_definition(self) -> Optional[BeastDefinition]:
        return self._base_definition

    @property
    def boss(self) -> bool:
        return not self.raid and self._variant is not None and self._variant.name == VARIANT_BOSS

    @property
    def exp_value(self) -> int:
        return self._exp_value

    @property
    def health(self) -> int:
        return self._health

    @property
    def id(self) -> str:
        return self._id

    @property
    def image(self) -> Optional[disnake.File]:
        file_path = compute_beast_file_path(self._name)
        try:
            return disnake.File(file_path)
        except OSError:
            return None

    @property
    def loot(self) -> Loot:
        return self._loot

    @property
    def material_loot(self) -> Loot:
        return self._material_loot

    @property
    def monster_core_id(self) -> str:
        return self._monster_core_id

    @property
    def monster_core_drop_rate(self) -> int:
        return self._monster_core_drop_rate

    @property
    def name(self) -> str:
        return self._name

    @property
    def pet_stats(self) -> Optional[dict[str, P]]:
        return self._pet_stats.copy() if self._pet_stats.copy() is not None else None

    @property
    def raid(self) -> bool:
        return self._variant is not None and self._variant.name == VARIANT_RAID

    @property
    def rank(self) -> int:
        return self._rank

    @property
    def tameable(self) -> bool:
        return False

    @property
    def title(self) -> str:
        if self._variant is None or self._variant.name == VARIANT_NORMAL:
            return self.name

        return f"{self._name} ({self._variant.name.capitalize()})"

    @property
    def variant(self) -> BeastVariant:
        return self._variant

    # ============================================== "Real" methods =============================================

    def as_boss(self) -> D:
        if self.boss:
            return self
        elif self.raid:
            return self.as_normal().as_boss()
        else:
            # Normal to boss
            return self._derive(Bestiary().get_variant(VARIANT_BOSS))

    def as_normal(self) -> D:
        return self.base_definition if self.base_definition is not None else self

    def as_raid(self) -> D:
        if self.boss:
            return self.as_normal().as_raid()
        elif self.raid:
            return self
        else:
            # Normal to raid
            return self._derive(Bestiary().get_variant(VARIANT_RAID))

    def generate_loot(self) -> dict[str, int]:
        return self.loot.roll()

    def has_affinity(self, affinity: str) -> bool:
        return affinity in self._affinities

    def has_variant(self, variant_name: str) -> bool:
        return variant_name == self.variant.name

    def mutate(self, variant: Optional[BeastVariant]) -> D:
        if variant is None:
            return self.as_normal()
        else:
            return self.as_normal()._derive(variant)

    def _derive(self, variant: BeastVariant) -> BeastDefinition:
        if variant.name == VARIANT_NORMAL:
            return self

        return BeastDefinition(self._name, self._rank, self._health, self._affinities, self._exp_value, self._monster_core_id, self._monster_core_drop_rate, self._material_loot, variant, self._pet_stats, self)


class PetBeastEvolution:
    def __init__(self, source_beast_name: str, target_beast_name: Optional[str], required_stage: BeastCultivationStage, required_items: Optional[dict[str, int]] = None):
        super().__init__()
        self._source_beast_name: str = source_beast_name
        self._target_beast_name: Optional[str] = target_beast_name
        self._required_stage: BeastCultivationStage = required_stage
        self._required_items: dict[str, int] = required_items.copy() if required_items is not None else {}
        self._source_beast: Optional[PetBeastDefinition] = None
        self._target_beast: Optional[PetBeastDefinition] = None

    def resolve_beasts(self, pet_beasts: dict[str, P]):
        # Prevent double init
        if self._source_beast is None:
            self._source_beast: PetBeastDefinition = pet_beasts[self._source_beast_name]
            self._target_beast: Optional[PetBeastDefinition] = pet_beasts[self._target_beast_name] if self._target_beast_name is not None else None

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"PetBeastEvolution {{source_beast_name: {self._source_beast_name}, target_beast_name: {self._target_beast_name}, required_stage: {self._required_stage}, required_items: {self._required_items}}}"

    def __str__(self):
        return self.__repr__()

    def __hash__(self) -> int:
        return hash(self._source_beast_name) * 7 + hash(self._target_beast_name) * 3

    def __eq__(self, other):
        return other is not None and isinstance(other, PetBeastEvolution) and self._source_beast_name == other._source_beast_name and self._target_beast_name == other._target_beast_name

    def __ne__(self, other):
        return not self.__eq__(other)

    # ================================================ Properties ===============================================

    @property
    def required_items(self) -> dict[str, int]:
        return self._required_items.copy()

    @property
    def required_stage(self) -> BeastCultivationStage:
        return self._required_stage

    @property
    def source_pet(self) -> P:
        return self._source_beast

    @property
    def source_pet_name(self) -> str:
        return self._source_beast_name

    @property
    def target_pet(self) -> Optional[P]:
        return self._target_beast

    @property
    def target_pet_name(self) -> str:
        return self._target_beast_name


class PetBeastDefinition:
    def __init__(self, name: str, rarity: str, initial_stage: BeastCultivationStage, growth_rate_range: tuple[float, float], next_evolution: PetBeastEvolution, source_evolution: Optional[PetBeastEvolution] = None):
        super().__init__()
        self._name: str = name
        self._rarity: str = rarity
        self._initial_stage: BeastCultivationStage = initial_stage
        self._growth_rate_range: tuple[float, float] = growth_rate_range
        self._next_evolution: PetBeastEvolution = next_evolution
        self._source_evolution: Optional[PetBeastEvolution] = source_evolution
        self._parent_beast = None
        self._parent_beast_name = None

    def resolve_parent_beast(self, beasts: dict[str, BeastDefinition], hatch_origins: dict[str, str]):
        # Prevent double init
        if self._parent_beast_name is None:
            name: str = self._compute_parent_beast_name()
            if self.rarity != RARITY_ABUNDANT:
                # Need to do some ugly magic here
                name = hatch_origins[name]

            self._parent_beast_name: str = name
            self._parent_beast: BeastDefinition = beasts[self._parent_beast_name]

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"PetBeastDefinition {{name: {self._name}, _rarity: {self._rarity}, initial_stage: {self._initial_stage}, growth_rate_range: {self._growth_rate_range}}}"

    def __str__(self):
        return self.__repr__()

    def __hash__(self) -> int:
        return hash(self._name) * 3

    def __eq__(self, other):
        return other is not None and isinstance(other, PetBeastDefinition) and self._name == other._name

    def __ne__(self, other):
        return not self.__eq__(other)

    # ================================================ Properties ===============================================

    @property
    def can_evolve(self) -> bool:
        return self._next_evolution.target_pet is not None

    @property
    def growth_rate_range(self) -> tuple[float, float]:
        return self._growth_rate_range

    @property
    def image(self) -> Optional[disnake.File]:
        file_path = compute_beast_file_path(self._name)
        try:
            return disnake.File(file_path)
        except OSError:
            return self._parent_beast.image

    @property
    def initial_stage(self) -> BeastCultivationStage:
        return self._initial_stage

    @property
    def name(self) -> str:
        return self._name

    @property
    def next_evolution(self) -> PetBeastEvolution:
        return self._next_evolution

    @property
    def parent_beast(self) -> BeastDefinition:
        return self._parent_beast

    @property
    def parent_beast_name(self) -> str:
        return self._parent_beast_name

    @property
    def rank(self) -> int:
        return self._parent_beast.rank

    @property
    def rarity(self) -> str:
        return self._rarity

    @property
    def source_evolution(self) -> Optional[PetBeastEvolution]:
        return self._source_evolution

    # ============================================== "Real" methods =============================================

    def combat_power(self, cultivation: BeastCultivationStage, growth_rate: float, inherited_power: int = 0) -> int:
        return cultivation.combat_power(self.initial_stage, growth_rate, inherited_power)

    def growth_from_quality(self, quality_percent: int) -> float:
        min_growth_rate, max_growth_rate = self._growth_rate_range
        # To prevent rounding error, bind the 0 and 100 results to min and max rate respectively
        if quality_percent == 0:
            return min_growth_rate
        elif quality_percent == 100:
            return max_growth_rate

        growth_range: float = max_growth_rate - min_growth_rate

        return round(min_growth_rate + growth_range * quality_percent / 100, 3)

    def quality_from_growth(self, growth: float) -> int:
        min_growth_rate, max_growth_rate = self._growth_rate_range
        if growth <= min_growth_rate:
            return 0
        elif growth >= max_growth_rate:
            return 100

        growth_range: float = max_growth_rate - min_growth_rate
        delta: float = growth - min_growth_rate

        return int(delta * 100 / growth_range)

    def reroll_cost(self, attempt_number: int = 0) -> int:
        if attempt_number < 0:
            raise ValueError(f"Reroll attempt number must be positive, found {attempt_number}")

        cost_array: list[int] = PET_REROLL_COST.get(self.rarity, DEFAULT_PET_REROLL_COSTS)
        if attempt_number >= len(cost_array):
            attempt_number = len(cost_array) - 1

        return cost_array[attempt_number]

    def roll_growth_rate(self, roll_mod: int = 0) -> tuple[float, int]:
        quality_percent: int = min(random.randint(0, 100) + roll_mod, 100)
        growth: float = round(self.growth_from_quality(quality_percent), 3)
        # Since it was rounded, it's possible that the quality changed, so let recompute it
        return growth, self.quality_from_growth(growth)

    def _compute_parent_beast_name(self) -> str:
        if self._source_evolution is None:
            return self._name
        else:
            source: PetBeastDefinition = self._source_evolution.source_pet
            return source._compute_parent_beast_name()


@singleton
class Bestiary:
    def __init__(self):
        self._beasts: dict[str, BeastDefinition] = {}
        self._pet_definitions: dict[str, PetBeastDefinition] = {}
        self._max_rank: int = 0
        self._variants: dict[str, BeastVariant] = {}

    # ============================================= Special methods =============================================

    def __contains__(self, key: str) -> bool:
        return key in self._beasts

    def __getitem__(self, name: str) -> Optional[BeastDefinition]:
        return self.get(name)

    # ================================================ Properties ===============================================

    @property
    def beasts(self) -> dict[str, BeastDefinition]:
        return self._beasts.copy()

    @property
    def beast_list(self) -> list[BeastDefinition]:
        return list(self.beasts.values())

    @property
    def beast_names(self) -> list[str]:
        name_list = list(self._beasts.keys())
        name_list.sort()
        return name_list

    @property
    def known_variant(self) -> dict[str, BeastVariant]:
        return self._variants.copy()

    @property
    def max_rank(self) -> int:
        return self._max_rank

    @property
    def pet_definitions(self) -> dict[str, PetBeastDefinition]:
        return self._pet_definitions.copy()

    @property
    def pet_definition_list(self) -> list[PetBeastDefinition]:
        return list(self._pet_definitions.values())

    @property
    def pet_definition_names(self) -> list[str]:
        name_list = list(self._pet_definitions.keys())
        name_list.sort()
        return name_list

    # ========================================= Disnake lifecycle methods ========================================

    async def load(self):
        await self.load_from_file()
        _log("system", f"Loaded {len(self._beasts)} BeastDefinition and {len(self._pet_definitions)} PetBeastDefinition")

    async def load_from_file(self, beast_file_path: str = "./data/beasts.json", pet_file_path: str = "./data/pets.json"):
        with open(file=beast_file_path, mode="r", encoding="utf-8") as file:
            data: dict[str, dict[str, Any]] = json.load(file)

        pet_definitions: dict[str, PetBeastDefinition] = self._load_pet_definitions_from_file(pet_file_path)
        normal, mat_properties, pet_by_parent_and_rarity = self._prepare_beast_load(pet_definitions)

        temp_beasts: dict[str, BeastDefinition] = {}
        max_rank = 0
        for name, attrs in data.items():
            rank: int = int(attrs["rank"])
            affinities: set[str] = set(attrs["affinities"])
            health: int = int(attrs["health"])
            exp_value: int = int(attrs["exp_value"])
            core_id: str = attrs["core_id"]
            core_drop_rate: int = int(attrs["core_drop_rate"])
            material_loot: Loot = Loot.deserialize(attrs["material_loot"])
            temp_beasts[name] = BeastDefinition(name, rank, health, affinities, exp_value, core_id, core_drop_rate, material_loot, normal, pet_by_parent_and_rarity.get(name, None))
            if rank > max_rank:
                max_rank = rank

        self._finalize_load(temp_beasts, pet_definitions, max_rank)

    async def load_from_database(self):
        compendium: ItemCompendium = ItemCompendium()
        pet_definitions: dict[str, PetBeastDefinition] = await self._load_pet_definitions_from_database()

        normal, mat_properties, pet_by_parent_and_rarity = self._prepare_beast_load(pet_definitions)

        cores: list[ItemDefinition] = compendium.filter(item_type=ITEM_TYPE_MONSTER_CORE)
        core_by_rank: dict[int, ItemDefinition] = {definition.tier: definition for definition in cores}

        beast_data: list[(str, int, int, str, int, dict[str, int])] = await AllBeasts.all().values_list("name", "rank", "health", "affinity", "exp_given", "drop_rate", "mat_drop_types")
        temp_beasts: dict[str, BeastDefinition] = {}

        max_rank = 0
        for name, rank, health, affinity, exp_given, core_drop_rate, beast_drop_type in beast_data:
            affinities: set[str] = compute_affinities(affinity)
            core_id: str = core_by_rank[rank].item_id
            mat_loot: Loot = Loot.deserialize(beast_drop_type)

            temp_beasts[name] = BeastDefinition(name, rank, health, affinities, exp_given, core_id, core_drop_rate, mat_loot, normal, pet_by_parent_and_rarity.get(name, None))
            if rank > max_rank:
                max_rank = rank

        self._finalize_load(temp_beasts, pet_definitions, max_rank)

    @staticmethod
    async def _load_pet_definitions_from_database() -> dict[str, PetBeastDefinition]:
        pets: list[(str, str, list[float, float], dict[str, int], dict[str, Any])] = await AllPets.all().values_list("name", "rarity", "growth_rate", "start_stage", "evolution")

        evolutions: list[PetBeastEvolution] = [PetBeastEvolution(name, evol.get("name"), BeastCultivationStage(evol["stage"][0], evol["stage"][1], rarity), evol["requirements"]) for name, rarity, _, _, evol in pets]
        evolutions_by_source: dict[str, PetBeastEvolution] = {evol.source_pet_name: evol for evol in evolutions}
        evolutions_by_target: dict[str, PetBeastEvolution] = {evol.target_pet_name: evol for evol in evolutions}

        definitions: dict[str, PetBeastDefinition] = {name: PetBeastDefinition(name=name, rarity=rarity,
                                                                               initial_stage=BeastCultivationStage(stage["major"], stage["minor"], rarity),
                                                                               growth_rate_range=(growth[0], growth[1]),
                                                                               next_evolution=evolutions_by_source.get(name, None),
                                                                               source_evolution=evolutions_by_target.get(name, None)) for name, rarity, growth, stage, _ in pets}
        for evolution in evolutions:
            evolution.resolve_beasts(definitions)

        return definitions

    @staticmethod
    def _load_pet_definitions_from_file(file_path: str) -> dict[str, PetBeastDefinition]:
        with open(file=file_path, mode="r", encoding="utf-8") as file:
            data: dict[str, dict[str, Any]] = json.load(file)

        highest_cultivation: dict[str, BeastCultivationStage] = {
            RARITY_ABUNDANT: BeastCultivationStage.max(RARITY_ABUNDANT),
            RARITY_SCARCE: BeastCultivationStage.max(RARITY_SCARCE),
            RARITY_EXOTIC: BeastCultivationStage.max(RARITY_EXOTIC)
        }

        evolutions: list[PetBeastEvolution] = []
        for name, attrs in data.items():
            evol_attrs: dict[str, Any] = attrs.get("evolution")
            if evol_attrs is not None:
                evolutions.append(PetBeastEvolution(name, evol_attrs.get("target_name"), BeastCultivationStage(evol_attrs["required_stage"]["major"], evol_attrs["required_stage"]["minor"], attrs["rarity"]), evol_attrs["required_items"]))
            else:
                evolutions.append(PetBeastEvolution(name, None, highest_cultivation[attrs["rarity"]]))

        # Big copy-paste with _load_pet_definitions_from_database, need to find a way to do better, likely with a Callable
        evolutions_by_source: dict[str, PetBeastEvolution] = {evol.source_pet_name: evol for evol in evolutions}
        evolutions_by_target: dict[str, PetBeastEvolution] = {evol.target_pet_name: evol for evol in evolutions}

        definitions: dict[str, PetBeastDefinition] = {name: PetBeastDefinition(name=name, rarity=attrs["rarity"],
                                                                               initial_stage=BeastCultivationStage(attrs["initial_stage"]["major"], attrs["initial_stage"]["minor"], attrs["rarity"]),
                                                                               growth_rate_range=(attrs["growth_rate_range"][0], attrs["growth_rate_range"][1]),
                                                                               next_evolution=evolutions_by_source.get(name, None),
                                                                               source_evolution=evolutions_by_target.get(name, None)) for name, attrs in data.items()}
        for evolution in evolutions:
            evolution.resolve_beasts(definitions)

        return definitions

    @staticmethod
    def _load_pet_origins(compendium: ItemCompendium) -> dict[str, str]:
        eggs: list[ItemDefinition] = compendium.filter(item_type=ITEM_TYPE_EGG)
        hatch_origins: dict[str, str] = {}
        for item in eggs:
            if isinstance(item, EggDefinition):
                # Should always be the case
                egg: EggDefinition = item
                origin: str = egg.parent_beast_name
                hatch_rates: dict[str, int] = egg.hatch_rates
                for offspring in hatch_rates.keys():
                    hatch_origins[offspring] = origin

        return hatch_origins

    def _prepare_beast_load(self, pet_definitions: dict[str, PetBeastDefinition]) -> tuple[BeastVariant, dict[str, dict[str, Any]], dict[str, dict[str, PetBeastDefinition]]]:
        compendium: ItemCompendium = ItemCompendium()
        normal: BeastVariant = NormalBeastVariant()

        self._variants[VARIANT_NORMAL] = normal
        self._variants[VARIANT_RAID] = RaidBeastVariant()
        self._variants[VARIANT_BOSS] = BossBeastVariant()
        self._variants[VARIANT_ELITE] = EliteBeastVariant()

        mats: list[ItemDefinition] = compendium.filter(item_type=ITEM_TYPE_MONSTER_PART)
        mat_properties: dict[str, dict[str, Any]] = {mat.item_id: mat.properties for mat in mats}

        pet_parent_names: set[str] = {pet.parent_beast_name for pet in pet_definitions.values()}
        pet_by_parent_and_rarity: dict[str, dict[str, PetBeastDefinition]] = {beast_name: {pet.rarity: pet for pet in pet_definitions.values() if pet.parent_beast_name == beast_name} for beast_name in pet_parent_names}

        return normal, mat_properties, pet_by_parent_and_rarity

    def _finalize_load(self, definitions: dict[str, BeastDefinition], pet_definitions: dict[str, PetBeastDefinition], max_rank: int) -> None:
        hatch_origins: dict[str, str] = self._load_pet_origins(ItemCompendium())
        for pet in pet_definitions.values():
            pet.resolve_parent_beast(definitions, hatch_origins)

        self._beasts: dict[str, BeastDefinition] = definitions
        self._pet_definitions: dict[str, PetBeastDefinition] = pet_definitions
        self._max_rank: int = max_rank

    # ============================================== "Real" methods =============================================
    async def add_pet_experience(self, user_id: int, amount: int, pet_info: Optional[tuple[PetBeastDefinition, float, BeastCultivationStage, int]] = None):
        if not pet_info:
            data = await Pet.get_or_none(user_id=user_id, main=1).values_list("pet_id", "growth_rate", "p_major", "p_minor", "p_exp")
            if not data:
                _log(user_id, f"Could not locate main pet to award {amount:,} exp to", "WARN")
                return

            pet_name, growth_rate, pet_major, pet_minor, exp = data
            definition: PetBeastDefinition = self.get_pet_definition(pet_name)
            cultivation: BeastCultivationStage = BeastCultivationStage(pet_major, pet_minor, definition.rarity)
        else:
            definition, growth_rate, cultivation, exp = pet_info

        content = f"Your pet have gained {amount:,} exp."
        _log(user_id, f"Rank {definition.rank} {cultivation.name} gained {amount:,} EXP", "DEBUG")

        remaining_exp: int = exp + amount
        if remaining_exp >= cultivation.breakthrough_experience:
            evolution: PetBeastEvolution = definition.next_evolution

            count = 0
            content += f"\n\n{EXCLAMATION} Your pet's exp has reached its limit!"

            while remaining_exp >= cultivation.breakthrough_experience:
                remaining_exp -= cultivation.breakthrough_experience
                if cultivation.major == evolution.required_stage.major and cultivation.minor == evolution.required_stage.minor:
                    if definition.can_evolve:
                        content += f"\n\n{EXCLAMATION} Your pet has reached its maximum potential for its current evolution! \nPlease evolve your pet to continue growing."
                    else:
                        content += f"\n\n{EXCLAMATION} Your pet has reached its maximum potential!"

                    remaining_exp = cultivation.breakthrough_experience - 1
                    break

                next_stage: Optional[BeastCultivationStage] = cultivation.next_stage
                if next_stage is not None:
                    count += 1
                    cultivation = next_stage

            if count == 1:
                content += f"\n{PLUS} Your pet has broken through to **`{cultivation.name}`**"
                log_event(user_id, "pet", f"Rank {definition.rank} {definition.name} broke through {count} time")
            elif count > 1:
                content += f"\n{PLUS} Your pet has continuously broken through `{count}` times, reaching **`{cultivation.name}`**"
                log_event(user_id, "pet", f"Rank {definition.rank} {definition.name} broke through {count} time")

        if remaining_exp < 0:
            remaining_exp = 0

        await Pet.filter(user_id=user_id, pet_id=definition.name, main=1).update(p_exp=remaining_exp, p_major=cultivation.major, p_minor=cultivation.minor)
        return content

    def choose_random(self,
                      rank: Optional[int] = None,
                      rank__gt: Optional[int] = None,
                      rank__ge: Optional[int] = None,
                      rank__lt: Optional[int] = None,
                      rank__le: Optional[int] = None,
                      rank__in: Optional[set[int]] = None,
                      affinity: Optional[str] = None,
                      affinity__in: Optional[set[str]] = None,
                      criteria: Optional[Callable[[BeastDefinition], bool]] = None) -> Optional[BeastDefinition]:
        candidates = self.find(None, rank, rank__gt, rank__ge, rank__lt, rank__le, rank__in, affinity, affinity__in, criteria)
        return random.choice(candidates) if len(candidates) > 0 else None

    def choose_random_raid_beast(self) -> BeastDefinition:
        affinity: Optional[str] = AFFINITY_FIRE if random.randint(1, 100) <= RAID_FIRE_SPAWN_BONUS_CHANCE else None
        beast_candidates: list[BeastDefinition] = self.filter(rank__ge=RAID_SPAWN_MIN_RANK, rank__le=RAID_SPAWN_MAX_RANK, affinity=affinity)
        if len(beast_candidates) == 0:
            beast_candidates: list[BeastDefinition] = self.list()

        beast: BeastDefinition = random.choice(beast_candidates)

        return beast.as_raid()

    async def dump_to_file(self, file_path: str):
        serialized_form: dict[str, dict[str, Any]] = {}
        for name, definition in self._beasts.items():
            serialized_form[name] = {
                "rank": definition.rank,
                "affinities": list(definition.affinities),
                "health": definition.health,
                "exp_value": definition.exp_value,
                "core_id": definition.monster_core_id,
                "core_drop_rate": definition.monster_core_drop_rate,
                "material_loot": definition.material_loot.serialize()
            }

        with open(file=file_path, mode="w", encoding="utf-8") as file:
            json.dump(serialized_form, fp=file, indent=4, ensure_ascii=False)

    async def dump_pets_to_file(self, file_path: str):
        serialized_form: dict[str, dict[str, Any]] = {}
        for name, definition in self._pet_definitions.items():
            serialized_pet: dict[str, Any] = {
                "parent_beast_name": definition.parent_beast_name,
                "rarity": definition.rarity,
                "initial_stage": {"major": definition.initial_stage.major, "minor": definition.initial_stage.minor},
                "growth_rate_range": [definition.growth_rate_range[0], definition.growth_rate_range[1]]
            }

            if definition.can_evolve:
                evolution: PetBeastEvolution = definition.next_evolution
                serialized_pet["evolution"] = {
                    "target_name": evolution.target_pet_name,
                    "required_stage": {"major": evolution.required_stage.major, "minor": evolution.required_stage.minor},
                    "required_items": evolution.required_items
                }

            serialized_form[name] = serialized_pet

        with open(file=file_path, mode="w", encoding="utf-8") as file:
            json.dump(serialized_form, fp=file, indent=4, ensure_ascii=False)

    def exp_range(self, rank: int) -> tuple[int, int]:
        beasts: list[BeastDefinition] = self.find(rank=rank)
        if len(beasts) == 0:
            return 0, 0

        exp_values: list[int] = [b.exp_value for b in beasts]

        return min(exp_values), max(exp_values)

    def filter(self,
               name: Optional[str] = None,
               rank: Optional[int] = None,
               rank__gt: Optional[int] = None,
               rank__ge: Optional[int] = None,
               rank__lt: Optional[int] = None,
               rank__le: Optional[int] = None,
               rank__in: Optional[set[int]] = None,
               affinity: Optional[str] = None,
               affinity__in: Optional[set[str]] = None,
               tameable: Optional[bool] = None,
               criteria: Optional[Callable[[BeastDefinition], bool]] = None) -> list[BeastDefinition]:
        return self.find(name, rank, rank__gt, rank__ge, rank__lt, rank__le, rank__in, affinity, affinity__in, tameable, criteria)

    def find(self,
             name: Optional[str] = None,
             rank: Optional[int] = None,
             rank__gt: Optional[int] = None,
             rank__ge: Optional[int] = None,
             rank__lt: Optional[int] = None,
             rank__le: Optional[int] = None,
             rank__in: Optional[set[int]] = None,
             affinity: Optional[str] = None,
             affinity__in: Optional[set[str]] = None,
             tameable: Optional[bool] = None,
             criteria: Optional[Callable[[BeastDefinition], bool]] = None) -> list[BeastDefinition]:
        # Using successive filtering because I don't know Python well enough to do otherwise, in Java I would have used Predicate.and between the criteria
        result: list[BeastDefinition] = self.beast_list
        if name is not None:
            result = [beast for beast in result if beast.name == name]

        if rank is not None:
            result = [beast for beast in result if beast.rank == rank]

        if rank__gt is not None:
            result = [beast for beast in result if beast.rank > rank__gt]

        if rank__ge is not None:
            result = [beast for beast in result if beast.rank >= rank__ge]

        if rank__lt is not None:
            result = [beast for beast in result if beast.rank < rank__lt]

        if rank__le is not None:
            result = [beast for beast in result if beast.rank <= rank__le]

        if rank__in is not None and len(rank__in) > 0:
            result = [beast for beast in result if beast.rank in rank__in]

        if affinity is not None:
            result = [beast for beast in result if affinity in beast.affinities]

        if affinity__in is not None and len(affinity__in) > 0:
            result = [beast for beast in result if len(beast.affinities.intersection(affinity__in)) > 0]

        if tameable is not None:
            result = [beast for beast in result if beast.tameable == tameable]

        if criteria is not None:
            result = [beast for beast in result if criteria(beast)]

        return result

    def get(self, name: str) -> Optional[BeastDefinition]:
        return self._beasts.get(name, None)

    def get_variant(self, name: str) -> Optional[BeastVariant]:
        return self._variants.get(name, None) if name is not None else None

    def get_pet_definition(self, name: str) -> Optional[PetBeastDefinition]:
        return self._pet_definitions.get(name, None)

    def list(self, sort: bool = False) -> list[BeastDefinition]:
        beast_list: list[BeastDefinition] = [beast for beast in self._beasts.values()]
        if sort:
            beast_list.sort(key=cmp_to_key(compare_beasts))

        return beast_list

    def register_variant(self, name: str, variant: BeastVariant) -> bool:
        if name not in self._variants:
            self._variants[name] = variant
            return True

        return False

    async def update_beast_database(self) -> tuple[int, int, int]:
        existing_name_data: list[tuple[str]] = await AllBeasts.all().values_list("name")
        existing_names: set[str] = set()
        for row_data in existing_name_data:
            existing_names.add(row_data[0])

        created_count: int = 0
        updated_count: int = 0
        deleted_count: int = 0
        for definition in self._beasts.values():
            name: str = definition.name
            if name in existing_names:
                # Update
                await AllBeasts.filter(name=name).update(rank=definition.rank, health=definition.health, affinity=compute_affinity_str(definition.affinities), exp_given=definition.exp_value, drop_rate=definition.monster_core_drop_rate,
                                                         mat_drop_types=definition.material_loot.serialize())
                existing_names.remove(name)
                updated_count += 1
            else:
                # Create
                await AllBeasts.create(name=name, rank=definition.rank, health=definition.health, affinity=compute_affinity_str(definition.affinities), exp_given=definition.exp_value, drop_rate=definition.monster_core_drop_rate,
                                       mat_drop_types=definition.material_loot.serialize())
                created_count += 1

        for name in existing_names:
            # Delete
            await AllBeasts.filter(name=name).delete()
            deleted_count += 1

        return created_count, updated_count, deleted_count

    async def update_pet_database(self) -> tuple[int, int, int]:
        existing_name_data: list[tuple[str]] = await AllPets.all().values_list("name")
        existing_names: set[str] = set()
        for row_data in existing_name_data:
            existing_names.add(row_data[0])

        created_count: int = 0
        updated_count: int = 0
        deleted_count: int = 0
        for definition in self._pet_definitions.values():
            name: str = definition.name
            evolution: PetBeastEvolution = definition.next_evolution
            if name in existing_names:
                # Update
                await AllPets.filter(name=name).update(rarity=definition.rarity, growth_rate=[definition.growth_rate_range[0], definition.growth_rate_range[0]],
                                                       start_stage={"major": definition.initial_stage.major, "minor": definition.initial_stage.minor},
                                                       evolution={"name": evolution.target_pet_name, "stage": [evolution.required_stage.major, evolution.required_stage.minor], "requirements": evolution.required_items})
                existing_names.remove(name)
                updated_count += 1
            else:
                # Create
                await AllPets.create(name=name, rarity=definition.rarity, growth_rate=[definition.growth_rate_range[0], definition.growth_rate_range[0]],
                                     start_stage={"major": definition.initial_stage.major, "minor": definition.initial_stage.minor},
                                     evolution={"name": evolution.target_pet_name, "stage": [evolution.required_stage.major, evolution.required_stage.minor], "requirements": evolution.required_items})
                created_count += 1

        for name in existing_names:
            # Delete
            await AllPets.filter(name=name).delete()
            deleted_count += 1

        return created_count, updated_count, deleted_count


class BeastDefinitionEmbed(disnake.Embed):
    def __init__(self, beast: BeastDefinition):
        super().__init__()
        self.title = beast.name
        self.color = disnake.Color(0x2e3135)
        self.add_field("Rank", f"`{beast.rank}`")
        self.add_field("EXP Value", f"`{beast.exp_value:,}`")
        self.add_field("Affinity", f"`{compute_affinity_str(beast.affinities)}`")
        if beast.name in BEAST_FLAME_DROP:
            _, drop_chance = BEAST_FLAME_DROP[beast.name]
            self.add_field("Flame Drop Rate", f"`{drop_chance}%`")

        image = beast.image
        if image:
            self.set_image(file=image)


class PetBeastDefinitionEmbed(disnake.Embed):
    def __init__(self, pet: PetBeastDefinition, item_catalog: ItemCompendium):
        super().__init__()
        self.title = pet.name
        self.color = disnake.Color(0x2e3135)

        prev_evol: PetBeastEvolution = pet.source_evolution
        if prev_evol is not None:
            self.add_field("Evolved From", f"`{prev_evol.source_pet_name}`", inline=False)

        self.add_field("Rarity", f"`Rank {pet.rank} - {pet.rarity.capitalize()}`")
        self.add_field("Growth Rate", f"`{pet.growth_rate_range[0]:.3f} - {pet.growth_rate_range[1]:.3f}`")
        self.add_field("Affinity", f"`{compute_affinity_str(pet.parent_beast.affinities)}`")

        self.add_field("Starts At", f"`{pet.initial_stage.name}`")

        next_evol: PetBeastEvolution = pet.next_evolution
        if next_evol is not None:
            self.add_field("Evolves At", f"`{next_evol.required_stage.name}`")

        if next_evol is not None:
            self.add_field("Evolves To", f"`{next_evol.target_pet_name}`")
            items = next_evol.required_items
            if items is not None and len(items) > 0:
                self.add_field("Requires", item_catalog.describe_dict(next_evol.required_items))

        image = pet.image
        if image:
            self.set_image(file=image)


def compare_beasts(beast_1: BeastDefinition, beast_2: BeastDefinition) -> int:
    if beast_1 == beast_2:
        # Easy equal case first
        return 0

    # We do Energy Ratio > Energy Flat > Exp Ratio > Exp Flat > Stars > Gold > Arena Coins > Items by tier lowest to highest then alpha
    difference: int = beast_1.rank - beast_2.rank
    if difference == 0:
        if beast_1.name < beast_2.name:
            difference = -1
        elif beast_1.name > beast_2.name:
            difference = 1

    return difference


def _log(user_id: Union[int, str], message: str, level: str = "INFO"):
    log_event(user_id, "bestiary", message, level)

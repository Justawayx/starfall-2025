# Move to module to a config package/folder once the configuration is no longer dependent on the database (nor cogs)
from typing import Optional, Union, Callable

from utils.InventoryUtils import ITEM_TYPE_MONSTER_PART, ITEM_TYPE_PILL, ITEM_TYPE_MAP_FRAGMENT, ITEM_TYPE_MONSTER_CORE
from utils.LoggingUtils import log_event
from utils.base import singleton
from utils.loot import ChoiceLoot, EmptyLoot, FixedItemLoot, FixedLoot, FixedQuantityLoot, FlatExperienceLoot, GoldLoot, Loot, RandomLoot, RelativeExperienceLoot, RepeatedLoot, uniform_distribution, uniform_quantity, ArenaCoinLoot, FlatEnergyLoot
from world.compendium import ItemCompendium, ItemDefinition
from world.bestiary import Bestiary

MAX_CHEST_RANK = 9
MAX_CHEST_TIER = 5

CHEST_TYPE_ARENA_COINS = "arena_coin"
CHEST_TYPE_ENERGY = "energy"
CHEST_TYPE_EXPERIENCE = "exp"
CHEST_TYPE_GOLD = "gold"
CHEST_TYPE_MIXED = "mixed"

CHEST_TYPES = [CHEST_TYPE_ARENA_COINS, CHEST_TYPE_ENERGY, CHEST_TYPE_EXPERIENCE, CHEST_TYPE_GOLD, CHEST_TYPE_MIXED]

_CHEST_TIER_WEIGHTS = [58, 24, 12, 5, 1]

_SHORT_NAME = "chests"


def _uniform_item_distribution(item_catalog: ItemCompendium, criteria: Callable[[ItemDefinition], bool]) -> list[dict[str, int]]:
    items_per_rank: list[dict[str, int]] = []
    for t in range(1, item_catalog.max_tier + 1):
        items: list[ItemDefinition] = item_catalog.filter(tier=t, criteria=criteria)
        items_per_rank.append(uniform_distribution([item.id for item in items]))

    return items_per_rank


class _ChestTypeLootConfig:
    def __init__(self, loot_matrix: list[list[Loot]]):
        self._loot_matrix: list[list[Loot]] = loot_matrix  # The matrix[rank][tier] containing the Loot for a given rank-tier combination
        self._loot_per_rank = [ChoiceLoot(loots, _CHEST_TIER_WEIGHTS) for loots in loot_matrix]  # The tier choice loot per rank. Index is the rank

    # ============================================== "Real" methods =============================================

    def loot(self, rank: int, tier: Optional[int] = None) -> Loot:
        if tier is None:
            return self._loot_per_rank[rank - 1] if 0 < rank <= len(self._loot_per_rank) else EmptyLoot()
        else:
            rank_loot: Optional[list[Loot]] = self._loot_matrix[rank - 1] if 0 < rank <= len(self._loot_matrix) else None
            if rank_loot is None:
                return EmptyLoot()
            else:
                return rank_loot[tier - 1] if 0 < tier <= len(rank_loot) else EmptyLoot()


@singleton
class ChestLootConfig:
    def __init__(self):
        self._loot_per_type: dict[str, _ChestTypeLootConfig] = {}

    # ============================================= Special methods =============================================

    def __getitem__(self, rank: int) -> Loot:
        mixed_chest_config: _ChestTypeLootConfig = self._loot_per_type[CHEST_TYPE_MIXED]
        return mixed_chest_config.loot(rank)

    # ========================================= Disnake lifecycle methods ========================================

    async def load(self):
        bestiary: Bestiary = Bestiary()
        item_catalog: ItemCompendium = ItemCompendium()

        self._loot_per_type[CHEST_TYPE_ARENA_COINS] = _build_arena_coin_loot_config()
        self._loot_per_type[CHEST_TYPE_ENERGY] = _build_energy_loot_config()
        self._loot_per_type[CHEST_TYPE_EXPERIENCE] = _build_experience_loot_config()
        self._loot_per_type[CHEST_TYPE_GOLD] = _build_gold_loot_config()
        self._loot_per_type[CHEST_TYPE_MIXED] = _build_mixed_loot_config(item_catalog, bestiary)

    # ============================================== "Real" methods =============================================

    def loot(self, chest_type: str, rank: int, tier: Optional[int] = None) -> Loot:
        return self._loot_per_type[chest_type].loot(rank, tier)


def _log(user_id: Union[int, str], message: str):
    log_event(user_id, _SHORT_NAME, message)


def _build_arena_coin_loot_config() -> _ChestTypeLootConfig:
    return _ChestTypeLootConfig([
        [  # Rank 1
            ArenaCoinLoot(0, 0),
            ArenaCoinLoot(0, 0),
            ArenaCoinLoot(0, 0),
            ArenaCoinLoot(0, 1),
            ArenaCoinLoot(1, 1)
        ],
        [  # Rank 2
            ArenaCoinLoot(0, 0),
            ArenaCoinLoot(0, 1),
            ArenaCoinLoot(1, 1),
            ArenaCoinLoot(2, 3),
            ArenaCoinLoot(3, 6)
        ],
        [  # Rank 3
            ArenaCoinLoot(1, 2),
            ArenaCoinLoot(2, 3),
            ArenaCoinLoot(4, 7),
            ArenaCoinLoot(8, 15),
            ArenaCoinLoot(16, 32)
        ],
        [  # Rank 4
            ArenaCoinLoot(4, 8),
            ArenaCoinLoot(9, 17),
            ArenaCoinLoot(18, 36),
            ArenaCoinLoot(38, 76),
            ArenaCoinLoot(80, 160)
        ],
        [  # Rank 5
            ArenaCoinLoot(22, 41),
            ArenaCoinLoot(43, 86),
            ArenaCoinLoot(91, 181),
            ArenaCoinLoot(191, 381),
            ArenaCoinLoot(400, 800)
        ],
        [  # Rank 6
            ArenaCoinLoot(108, 205),
            ArenaCoinLoot(216, 432),
            ArenaCoinLoot(454, 907),
            ArenaCoinLoot(953, 1_905),
            ArenaCoinLoot(2_000, 4_001)
        ],
        [  # Rank 7
            ArenaCoinLoot(540, 1_026),
            ArenaCoinLoot(1_080, 2_160),
            ArenaCoinLoot(2_268, 4_536),
            ArenaCoinLoot(4_763, 9_526),
            ArenaCoinLoot(10_002, 20_004)
        ],
        [  # Rank 8
            ArenaCoinLoot(2_700, 5_130),
            ArenaCoinLoot(5_400, 10_800),
            ArenaCoinLoot(11_340, 22_680),
            ArenaCoinLoot(23_814, 47_628),
            ArenaCoinLoot(50_009, 100_019)
        ],
        [  # Rank 9
            ArenaCoinLoot(13_500, 25_650),
            ArenaCoinLoot(27_000, 54_000),
            ArenaCoinLoot(56_700, 113_400),
            ArenaCoinLoot(119_070, 238_140),
            ArenaCoinLoot(250_047, 500_094)
        ]
    ])


def _build_energy_loot_config() -> _ChestTypeLootConfig:
    return _ChestTypeLootConfig([
        [  # Rank 1
            FlatEnergyLoot(10, 13),
            FlatEnergyLoot(12, 15),
            FlatEnergyLoot(14, 17),
            FlatEnergyLoot(17, 20),
            FlatEnergyLoot(21, 24)
        ],
        [  # Rank 2
            FlatEnergyLoot(20, 23),
            FlatEnergyLoot(24, 27),
            FlatEnergyLoot(29, 32),
            FlatEnergyLoot(35, 38),
            FlatEnergyLoot(41, 46)
        ],
        [  # Rank 3
            FlatEnergyLoot(30, 34),
            FlatEnergyLoot(36, 40),
            FlatEnergyLoot(43, 47),
            FlatEnergyLoot(52, 56),
            FlatEnergyLoot(62, 67)
        ],
        [  # Rank 4
            FlatEnergyLoot(40, 44),
            FlatEnergyLoot(48, 52),
            FlatEnergyLoot(58, 62),
            FlatEnergyLoot(69, 75),
            FlatEnergyLoot(83, 89)
        ],
        [  # Rank 5
            FlatEnergyLoot(50, 55),
            FlatEnergyLoot(60, 65),
            FlatEnergyLoot(72, 78),
            FlatEnergyLoot(86, 93),
            FlatEnergyLoot(104, 111)
        ],
        [  # Rank 6
            FlatEnergyLoot(60, 65),
            FlatEnergyLoot(72, 78),
            FlatEnergyLoot(86, 93),
            FlatEnergyLoot(104, 111),
            FlatEnergyLoot(124, 133)
        ],
        [  # Rank 7
            FlatEnergyLoot(70, 76),
            FlatEnergyLoot(84, 90),
            FlatEnergyLoot(101, 108),
            FlatEnergyLoot(121, 129),
            FlatEnergyLoot(145, 154)
        ],
        [  # Rank 8
            FlatEnergyLoot(80, 86),
            FlatEnergyLoot(96, 103),
            FlatEnergyLoot(115, 123),
            FlatEnergyLoot(138, 147),
            FlatEnergyLoot(166, 176)
        ],
        [  # Rank 9
            FlatEnergyLoot(90, 97),
            FlatEnergyLoot(108, 115),
            FlatEnergyLoot(130, 138),
            FlatEnergyLoot(156, 165),
            FlatEnergyLoot(187, 198)
        ]
    ])


def _build_experience_loot_config() -> _ChestTypeLootConfig:
    return _ChestTypeLootConfig([
        [  # Rank 1
            FlatExperienceLoot(15, 30),
            FlatExperienceLoot(32, 63),
            FlatExperienceLoot(66, 132),
            FlatExperienceLoot(139, 278),
            FlatExperienceLoot(292, 583)
        ],
        [  # Rank 2
            FlatExperienceLoot(50, 100),
            FlatExperienceLoot(105, 210),
            FlatExperienceLoot(221, 441),
            FlatExperienceLoot(463, 926),
            FlatExperienceLoot(972, 1_945)
        ],
        [  # Rank 3
            FlatExperienceLoot(150, 300),
            FlatExperienceLoot(315, 630),
            FlatExperienceLoot(662, 1_323),
            FlatExperienceLoot(1_389, 2_778),
            FlatExperienceLoot(2_917, 5_834)
        ],
        [  # Rank 4
            FlatExperienceLoot(500, 1_000),
            FlatExperienceLoot(1_050, 2_100),
            FlatExperienceLoot(2_205, 4_410),
            FlatExperienceLoot(4_631, 9_261),
            FlatExperienceLoot(9_724, 19_448)
        ],
        [  # Rank 5
            FlatExperienceLoot(1_000, 2_000),
            FlatExperienceLoot(2_100, 4_200),
            FlatExperienceLoot(4_410, 8_820),
            FlatExperienceLoot(9_261, 18_522),
            FlatExperienceLoot(19_448, 38_896)
        ],
        [  # Rank 6
            FlatExperienceLoot(2_000, 4_000),
            FlatExperienceLoot(4_200, 8_400),
            FlatExperienceLoot(8_820, 17_640),
            FlatExperienceLoot(18_522, 37_044),
            FlatExperienceLoot(38_896, 77_792)
        ],
        [  # Rank 7
            FlatExperienceLoot(5_000, 10_000),
            FlatExperienceLoot(10_500, 21_000),
            FlatExperienceLoot(22_050, 44_100),
            FlatExperienceLoot(46_305, 92_610),
            FlatExperienceLoot(97_241, 194_481)
        ],
        [  # Rank 8
            FlatExperienceLoot(10_000, 20_000),
            FlatExperienceLoot(21_000, 42_000),
            FlatExperienceLoot(44_100, 88_200),
            FlatExperienceLoot(92_610, 185_220),
            FlatExperienceLoot(194_481, 388_962)
        ],
        [  # Rank 9
            FlatExperienceLoot(15_000, 30_000),
            FlatExperienceLoot(31_500, 63_000),
            FlatExperienceLoot(66_150, 132_300),
            FlatExperienceLoot(138_915, 277_830),
            FlatExperienceLoot(291_722, 583_443)
        ]
    ])


def _build_gold_loot_config() -> _ChestTypeLootConfig:
    return _ChestTypeLootConfig([
        [  # Rank 1
            GoldLoot(5, 10),
            GoldLoot(10, 20),
            GoldLoot(22, 43),
            GoldLoot(45, 90),
            GoldLoot(95, 190)
        ],
        [  # Rank 2
            GoldLoot(26, 49),
            GoldLoot(51, 102),
            GoldLoot(108, 215),
            GoldLoot(226, 452),
            GoldLoot(474, 948)
        ],
        [  # Rank 3
            GoldLoot(128, 243),
            GoldLoot(256, 512),
            GoldLoot(538, 1075),
            GoldLoot(1129, 2_258),
            GoldLoot(2_371, 4_742)
        ],
        [  # Rank 4
            GoldLoot(640, 1_216),
            GoldLoot(1_280, 2_560),
            GoldLoot(2_688, 5_376),
            GoldLoot(5_645, 11_290),
            GoldLoot(11_854, 23_708)
        ],
        [  # Rank 5
            GoldLoot(3_200, 6_080),
            GoldLoot(6_400, 12_800),
            GoldLoot(13_440, 26_880),
            GoldLoot(28_224, 56_448),
            GoldLoot(59_270, 118_541)
        ],
        [  # Rank 6
            GoldLoot(16_000, 30_400),
            GoldLoot(32_000, 64_000),
            GoldLoot(67_200, 134_400),
            GoldLoot(141_120, 282_240),
            GoldLoot(296_352, 592_704)
        ],
        [  # Rank 7
            GoldLoot(80_000, 152_000),
            GoldLoot(160_000, 320_000),
            GoldLoot(336_000, 672_000),
            GoldLoot(705_600, 1_411_200),
            GoldLoot(1_481_760, 2_963_520)
        ],
        [  # Rank 8
            GoldLoot(400_000, 760_000),
            GoldLoot(800_000, 1_600_000),
            GoldLoot(1_680_000, 3_360_000),
            GoldLoot(3_528_000, 7_056_000),
            GoldLoot(7_408_800, 14_817_600)
        ],
        [  # Rank 9
            GoldLoot(2_000_000, 3_800_000),
            GoldLoot(4_000_000, 8_000_000),
            GoldLoot(8_400_000, 16_800_000),
            GoldLoot(17_640_000, 35_280_000),
            GoldLoot(37_044_000, 74_088_000)
        ]
    ])


def _build_mixed_loot_config(compendium: ItemCompendium, bestiary: Bestiary) -> _ChestTypeLootConfig:
    # Create the base loot structure
    loot_matrix: list[list[ChoiceLoot]] = _build_mixed_loot_structure()

    exp_range_per_rank: list[tuple[int, int]] = [bestiary.exp_range(r) for r in range(1, bestiary.max_rank + 1)]
    exp: list[FlatExperienceLoot] = [FlatExperienceLoot(min_exp, max_exp) for min_exp, max_exp in exp_range_per_rank]
    monster_parts: list[dict[str, int]] = _uniform_item_distribution(compendium, lambda i: i.type == ITEM_TYPE_MONSTER_PART or i.type == ITEM_TYPE_MONSTER_CORE)
    pills: list[dict[str, int]] = _uniform_item_distribution(compendium, lambda i: i.type == ITEM_TYPE_PILL)
    fragments: list[Loot] = [EmptyLoot() if f is None or len(f) == 0 else FixedQuantityLoot(f) for f in _uniform_item_distribution(compendium, lambda i: i.type == ITEM_TYPE_MAP_FRAGMENT)]

    for rank in range(0, MAX_CHEST_RANK):
        part_index: int = min(rank, len(monster_parts) - 1)
        pill_index: int = min(rank, len(pills) - 1)
        exp_index: int = min(rank, len(exp) - 1)
        fragment_index: int = min(rank, len(fragments) - 1)

        rank_loot: list[ChoiceLoot] = loot_matrix[rank]
        loot_matrix[rank] = [
            rank_loot[0].append([exp[exp_index]]),
            rank_loot[1].append([exp[exp_index], RandomLoot(monster_parts[part_index], uniform_quantity(1, 2))]),
            rank_loot[2].append([exp[exp_index], RepeatedLoot(RandomLoot(monster_parts[part_index], uniform_quantity(3, 4), single_item_id=True), 2)]),
            rank_loot[3].append([exp[exp_index], RepeatedLoot(RandomLoot(monster_parts[part_index], uniform_quantity(3, 4), single_item_id=True), 3), FixedQuantityLoot(pills[pill_index], 1)]),
            rank_loot[4].append([RelativeExperienceLoot(RelativeExperienceLoot.percent_to_param(0.005 * (1 + (rank - 1) / 2)), RelativeExperienceLoot.percent_to_param(0.01 * (1 + (rank - 1) / 2))), fragments[fragment_index]])
        ]

    return _ChestTypeLootConfig(loot_matrix)


def _build_mixed_loot_structure() -> list[list[ChoiceLoot]]:
    return [
        [  # Rank 1
            ChoiceLoot([GoldLoot(10, 100), FixedItemLoot("cherb", uniform_quantity(1, 2))]),
            ChoiceLoot([GoldLoot(100, 200), FixedItemLoot("cherb", uniform_quantity(4, 6)), FixedItemLoot("rherb", uniform_quantity(1, 2))]),
            ChoiceLoot([GoldLoot(200, 400), FixedItemLoot("cherb", uniform_quantity(5, 9)), FixedItemLoot("rherb", uniform_quantity(2, 3))]),
            ChoiceLoot([GoldLoot(400, 600)]),
            ChoiceLoot([GoldLoot(600, 800)])
        ],
        [  # Rank 2
            ChoiceLoot([GoldLoot(800, 1_000), FixedItemLoot("cherb", uniform_quantity(4, 6))]),
            ChoiceLoot([GoldLoot(1_000, 1_200), FixedItemLoot("cherb", uniform_quantity(7, 9)), FixedItemLoot("rherb", uniform_quantity(3, 4))]),
            ChoiceLoot([GoldLoot(1_200, 1_400), FixedItemLoot("cherb", uniform_quantity(10, 13)), FixedItemLoot("rherb", uniform_quantity(5, 6))]),
            ChoiceLoot([GoldLoot(1_600, 1_800)]),
            ChoiceLoot([GoldLoot(1_800, 2_000)])
        ],
        [  # Rank 3
            ChoiceLoot([GoldLoot(2_000, 4_000), FixedItemLoot("rherb", uniform_quantity(4, 6))]),
            ChoiceLoot([GoldLoot(4_000, 6_000), FixedItemLoot("rherb", uniform_quantity(7, 9)), FixedItemLoot("uherb", uniform_quantity(3, 4))]),
            ChoiceLoot([GoldLoot(6_000, 8_000), FixedItemLoot("rherb", uniform_quantity(10, 13)), FixedItemLoot("uherb", uniform_quantity(5, 6))]),
            ChoiceLoot([GoldLoot(8_000, 10_000)]),
            ChoiceLoot([GoldLoot(10_000, 15_000)])
        ],
        [  # Rank 4
            ChoiceLoot([GoldLoot(15_000, 20_000), FixedItemLoot("rherb", uniform_quantity(7, 9))]),
            ChoiceLoot([GoldLoot(15_000, 20_000), FixedItemLoot("rherb", uniform_quantity(10, 12)), FixedItemLoot("uherb", uniform_quantity(5, 6))]),
            ChoiceLoot([GoldLoot(20_000, 25_000), FixedItemLoot("rherb", uniform_quantity(13, 14)), FixedItemLoot("uherb", uniform_quantity(7, 8))]),
            ChoiceLoot([GoldLoot(25_000, 30_000)]),
            ChoiceLoot([GoldLoot(30_000, 35_000)])
        ],
        [  # Rank 5
            ChoiceLoot([GoldLoot(35_000, 40_000), FixedItemLoot("uherb", uniform_quantity(7, 9))]),
            ChoiceLoot([GoldLoot(40_000, 45_000), FixedItemLoot("uherb", uniform_quantity(10, 12)), FixedItemLoot("lherb", uniform_quantity(5, 6))]),
            ChoiceLoot([GoldLoot(45_000, 50_000), FixedItemLoot("uherb", uniform_quantity(13, 14)), FixedItemLoot("lherb", uniform_quantity(7, 8))]),
            ChoiceLoot([GoldLoot(50_000, 55_000)]),
            ChoiceLoot([GoldLoot(55_000, 60_000)])
        ],
        [  # Rank 6
            ChoiceLoot([GoldLoot(60_000, 70_000), FixedItemLoot("uherb", uniform_quantity(7, 8))]),
            ChoiceLoot([GoldLoot(70_000, 80_000), FixedItemLoot("uherb", uniform_quantity(9, 10)), FixedItemLoot("lherb", uniform_quantity(3, 4))]),
            ChoiceLoot([GoldLoot(80_000, 90_000), FixedItemLoot("uherb", uniform_quantity(11, 12)), FixedItemLoot("lherb", uniform_quantity(5, 6))]),
            ChoiceLoot([GoldLoot(90_000, 100_000)]),
            ChoiceLoot([GoldLoot(100_000, 110_000)])
        ],
        [  # Rank 7
            ChoiceLoot([GoldLoot(110_000, 120_000), FixedItemLoot("lherb", uniform_quantity(4, 6))]),
            ChoiceLoot([GoldLoot(120_000, 130_000), FixedItemLoot("lherb", uniform_quantity(7, 9)), FixedLoot("mherb", 1)]),
            ChoiceLoot([GoldLoot(130_000, 140_000), FixedItemLoot("lherb", uniform_quantity(10, 12)), FixedLoot("mherb", 2)]),
            ChoiceLoot([GoldLoot(140_000, 150_000)]),
            ChoiceLoot([GoldLoot(150_000, 200_000)])
        ],
        [  # Rank 8
            ChoiceLoot([GoldLoot(200_000, 250_000), FixedItemLoot("lherb", uniform_quantity(6, 7))]),
            ChoiceLoot([GoldLoot(250_000, 300_000), FixedItemLoot("lherb", uniform_quantity(8, 9)), FixedItemLoot("mherb", uniform_quantity(1, 2))]),
            ChoiceLoot([GoldLoot(300_000, 350_000), FixedItemLoot("lherb", uniform_quantity(10, 12)), FixedItemLoot("mherb", uniform_quantity(2, 3))]),
            ChoiceLoot([GoldLoot(350_000, 400_000)]),
            ChoiceLoot([GoldLoot(500_000, 1_000_000)])
        ],
        [  # Rank 9
            ChoiceLoot([GoldLoot(250_000, 300_000), FixedItemLoot("lherb", uniform_quantity(6, 7))]),
            ChoiceLoot([GoldLoot(300_000, 350_000), FixedItemLoot("lherb", uniform_quantity(8, 9)), FixedItemLoot("mherb", uniform_quantity(1, 2))]),
            ChoiceLoot([GoldLoot(350_000, 400_000), FixedItemLoot("lherb", uniform_quantity(10, 12)), FixedItemLoot("mherb", uniform_quantity(2, 3))]),
            ChoiceLoot([GoldLoot(400_000, 450_000)]),
            ChoiceLoot([GoldLoot(1_500_000, 2_000_000)])
        ]
    ]

import random
from abc import ABC, abstractmethod
from datetime import timedelta, datetime
from typing import Optional, TypeVar, Union, Callable, Any

import disnake
from disnake import User

from adventure.battle import BeastBattle, BattleManager, BattleRound
from adventure.chests import ChestLootConfig
from character.player import Player
from utils import ParamsUtils
from utils.Database import RuinsDao, ID_UNCREATED
from utils.LoggingUtils import log_event
from utils.base import PrerequisiteNotMetException, singleton, BaseStarfallEmbed
from utils.loot import WeightedChoice, Loot, EmptyLoot, PossibleLoot, RepeatedLoot, uniform_choice, recalibrate_probability, uniform_distribution, roll_from_weighted_dict, merge_loot
from world.bestiary import Bestiary, BeastDefinition, AFFINITY_FIRE, VARIANT_ELITE, VARIANT_BOSS
from world.compendium import ItemCompendium

R = TypeVar("R", bound="Ruins")
T = TypeVar("T")

ENERGY_TO_START: int = 10

BASE_ENERGY_COST_PER_ACTION: int = 12
BASE_ENERGY_COST_EXPLORE: int = 8
BASE_ENERGY_COST_FIGHT: int = 12
BASE_ENERGY_COST_SEARCH: int = 6
BASE_ENERGY_COST_SNEAK: int = 8

BASE_ELITE_CHANCE: int = 15  # In %
MIN_DEPTH_BEFORE_FINAL: int = 5  # In %, per depth
BASE_FINAL_ROOM_CHANCE: float = 3.5  # In %, per depth
BASE_SNEAK_CHANCE: int = 50  # In %
SNEAK_CHANCE_INCREMENT: int = 5  # In %, per rank
MAX_ROUND_NORMAL: int = 3
MAX_ROUND_ELITE: int = 6
MAX_ROUND_BOSS: int = 9

DEFAULT_COLOR: disnake.Color = disnake.Color.gold()

ROOM_ID_BEAST_YARD: str = "beast_yard"
ROOM_ID_BEDROOM: str = "bedroom"
ROOM_ID_CORRIDOR: str = "corridor"
ROOM_ID_COURTYARD: str = "courtyard"
ROOM_ID_ENTRANCE: str = "entrance"
ROOM_ID_GARDEN: str = "garden"
ROOM_ID_HALL: str = "hall"
ROOM_ID_HALLWAY: str = "hallway"
ROOM_ID_LIBRARY: str = "library"
ROOM_ID_MAIN_HALL: str = "main_hall"
ROOM_ID_PILL_ROOM: str = "pill_room"
ROOM_ID_SECLUSION_CHAMBER: str = "seclusion_chamber"
ROOM_ID_SIDE_ROOM: str = "side_room"
ROOM_ID_STABLE: str = "stable"
ROOM_ID_STORAGE_ROOM: str = "storage_room"

_ALL_ROOM_IDS: list[str] = [
    ROOM_ID_ENTRANCE,
    ROOM_ID_HALL,
    ROOM_ID_HALLWAY,
    ROOM_ID_MAIN_HALL,
    ROOM_ID_CORRIDOR,
    ROOM_ID_STORAGE_ROOM,
    ROOM_ID_BEDROOM,
    ROOM_ID_COURTYARD,
    ROOM_ID_GARDEN,
    ROOM_ID_SIDE_ROOM,
    ROOM_ID_SECLUSION_CHAMBER,
    ROOM_ID_PILL_ROOM,
    ROOM_ID_LIBRARY,
    ROOM_ID_STABLE,
    ROOM_ID_BEAST_YARD
]

_MAXIMUM_RUINS_AGE: timedelta = timedelta(days=40)
_SHORT_NAME: str = "ruins"
_VOWELS: str = "aeio"


# TODO: Add ruins modifiers


class ExplorationNotStartedException(PrerequisiteNotMetException):
    def __init__(self, system_message: str, player_message: Optional[str] = None, player_embed: Optional[disnake.Embed] = None, ephemeral: bool = False):
        super().__init__(system_message, player_message, player_embed, ephemeral)


class GuardianAlreadyKilledException(PrerequisiteNotMetException):
    def __init__(self, system_message: str, player_message: Optional[str] = None, player_embed: Optional[disnake.Embed] = None, ephemeral: bool = False):
        super().__init__(system_message, player_message, player_embed, ephemeral)


class NotEnoughEnergyException(PrerequisiteNotMetException):
    def __init__(self, system_message: str, player_message: Optional[str] = None, player_embed: Optional[disnake.Embed] = None, ephemeral: bool = False):
        super().__init__(system_message, player_message, player_embed, ephemeral)


class RoomAlreadySearchedException(PrerequisiteNotMetException):
    def __init__(self, system_message: str, player_message: Optional[str] = None, player_embed: Optional[disnake.Embed] = None, ephemeral: bool = False):
        super().__init__(system_message, player_message, player_embed, ephemeral)


class UnguardedRoomException(PrerequisiteNotMetException):
    def __init__(self, system_message: str, player_message: Optional[str] = None, player_embed: Optional[disnake.Embed] = None, ephemeral: bool = False):
        super().__init__(system_message, player_message, player_embed, ephemeral)


# =======================================================================================================================
# =================================================== RoomDefinition ====================================================
# =======================================================================================================================
class RoomDefinition:
    def __init__(self, room_id: str, name: str, description: str,
                 search_loots: list[PossibleLoot],
                 possible_guardians: list[WeightedChoice[Optional[BeastDefinition]]],
                 sneak_chance_mod: int = 0, final_room: bool = False):
        super().__init__()
        self._id: str = room_id
        self._name: str = name
        self._description: str = description
        self._search_loots: list[PossibleLoot] = search_loots
        self._possible_guardians: list[WeightedChoice[Optional[BeastDefinition]]] = possible_guardians
        self._sneak_chance_mod: int = sneak_chance_mod
        self._final_room: bool = final_room

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"RoomDefinition {self._id}, name: {self._name}, description: {self._description}"

    def __str__(self) -> str:
        return self._name

    def __hash__(self) -> int:
        return hash(self._id)

    def __eq__(self, other):
        return other is not None and isinstance(other, RoomDefinition) and self._id == other._id

    def __ne__(self, other):
        return not self.__eq__(other)

    # ================================================ Properties ===============================================

    @property
    def description(self) -> str:
        return self._description

    @property
    def final_room(self) -> bool:
        return self._final_room

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def possible_guardians(self) -> list[WeightedChoice[BeastDefinition]]:
        return self._possible_guardians.copy()

    @property
    def search_loots(self) -> list[PossibleLoot]:
        return self._search_loots.copy()

    @property
    def sneak_chance_mod(self) -> int:
        return self._sneak_chance_mod

    # ================================================= Methods =================================================

    def generate_boss(self, depth: int = 0, criteria: Callable[[BeastDefinition], bool] = lambda b: True) -> BeastDefinition:
        bestiary: Bestiary = Bestiary()
        index: int = _compute_index(self._possible_guardians, depth)
        if index < 0:
            # Force a random boss if one cannot be found from the possible guardians
            beast: BeastDefinition = self._select_boss_outside_configuration(bestiary, depth, criteria)
        else:
            beast: Optional[BeastDefinition] = self.generate_guardian_choice(depth, 100, criteria).choose()
            if beast is None:
                selector: WeightedChoice[Optional[BeastDefinition]] = self._possible_guardians[index]
                choices: dict[BeastDefinition, int] = {definition: chance for definition, chance in selector.possible_choices.items() if definition is not None}
                if len(choices) > 0:
                    beast = roll_from_weighted_dict(choices)
                else:
                    # Force a random boss if one cannot be found from the possible guardians
                    beast: BeastDefinition = self._select_boss_outside_configuration(bestiary, depth, criteria)

        return beast.mutate(bestiary.get_variant(VARIANT_BOSS))

    def generate_guardian(self, depth: int = 0, probability_mod: int = 0, criteria: Callable[[BeastDefinition], bool] = lambda b: True, elite_chance_mod: int = 0, final_boss: bool = False) -> Optional[BeastDefinition]:
        if self._final_room or final_boss:
            return self.generate_boss(depth, criteria)

        guardian: Optional[BeastDefinition] = self.generate_guardian_choice(depth, probability_mod, criteria).choose()
        if guardian is not None:
            elite_chance: int = BASE_ELITE_CHANCE + elite_chance_mod
            if random.randint(1, 100) <= elite_chance:
                guardian = guardian.mutate(Bestiary().get_variant(VARIANT_ELITE))

        return guardian

    def generate_guardian_choice(self, depth: int = 0, probability_mod: int = 0, criteria: Callable[[BeastDefinition], bool] = lambda b: True) -> WeightedChoice[Optional[BeastDefinition]]:
        index: int = _compute_index(self._possible_guardians, depth)
        if index < 0:
            return WeightedChoice(None)

        return WeightedChoice(recalibrate_probability(weighted_values=self._possible_guardians[index].possible_choices, probability_mod=probability_mod, criteria=criteria))

    def search_loot(self, depth: int) -> PossibleLoot:
        index: int = _compute_index(self._search_loots, depth)
        return self._search_loots[index] if index >= 0 else PossibleLoot(EmptyLoot(), 0)

    @staticmethod
    def _select_boss_outside_configuration(bestiary: Bestiary, depth: int, criteria: Callable[[BeastDefinition], bool]) -> BeastDefinition:
        # Force a random boss if one cannot be found from the possible guardians
        beast: Optional[BeastDefinition] = bestiary.choose_random(rank=min(depth, bestiary.max_rank), criteria=criteria)
        if beast is None:
            # Generate a boss even if one cannot pass the filter, but only as a last ditch option
            beast: BeastDefinition = bestiary.choose_random(rank=min(depth, bestiary.max_rank))

        return beast


# =======================================================================================================================
# =================================================== RuinType ==========================================================
# =======================================================================================================================
class RuinsType:
    def __init__(self, ruins_type_id: str, name: str, description: str, color: Optional[disnake.Color] = None, affinities: Optional[set[str]] = None,
                 search_rate_mod: int = 0, guardian_rate_mod: int = 0, elite_guardian_rate_mod: int = 0, sneak_chance_mod: int = 0,
                 energy_consumption_rate: int = 100, experience_rate: int = 100):
        super().__init__()
        self._id: str = ruins_type_id
        self._name: str = name
        self._description: str = description
        self._color: Optional[disnake.Color] = color if color is not None else DEFAULT_COLOR
        self._affinities: set[str] = affinities.copy() if affinities is not None else {}
        self._search_rate_mod: int = search_rate_mod
        self._guardian_rate_mod: int = guardian_rate_mod
        self._elite_guardian_rate_mod: int = elite_guardian_rate_mod
        self._sneak_chance_mod: int = sneak_chance_mod
        self._energy_consumption_rate: int = energy_consumption_rate
        self._experience_rate: int = experience_rate

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"RuinType {self._name}"

    def __str__(self) -> str:
        return self._name

    def __hash__(self) -> int:
        return hash(self._id)

    def __eq__(self, other):
        return other is not None and isinstance(other, RuinsType) and self._id == other._id

    def __ne__(self, other):
        return not self.__eq__(other)

    # ================================================ Properties ===============================================

    @property
    def affinities(self) -> set[str]:
        return self._affinities.copy()

    @property
    def color(self) -> disnake.Color:
        return self._color

    @property
    def description(self) -> str:
        return self._description

    @property
    def elite_guardian_rate_mod(self) -> int:
        return self._elite_guardian_rate_mod

    @property
    def energy_consumption_rate(self) -> int:
        return self._energy_consumption_rate

    @property
    def experience_rate(self) -> int:
        return self._experience_rate

    @property
    def guardian_filter(self) -> Callable[[BeastDefinition], bool]:
        if len(self._affinities) == 0:
            return lambda _: True
        else:
            return lambda b: b.has_affinity(AFFINITY_FIRE)

    @property
    def guardian_rate_mod(self) -> int:
        return self._guardian_rate_mod

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def search_rate_mod(self) -> int:
        return self._search_rate_mod

    @property
    def sneak_chance_mod(self) -> int:
        return self._sneak_chance_mod


# =======================================================================================================================
# ================================================== RuinsStructure =====================================================
# =======================================================================================================================
class RuinsStructure(ABC):
    def __init__(self, ruins_structure_id: str, name: str, description: str):
        super().__init__()
        self._id: str = ruins_structure_id
        self._name: str = name
        self._description: str = description

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"RuinType {self._name}"

    def __str__(self) -> str:
        return self._name

    def __hash__(self) -> int:
        return hash(self._id)

    def __eq__(self, other):
        return other is not None and isinstance(other, RuinsStructure) and self._id == other._id

    def __ne__(self, other):
        return not self.__eq__(other)

    # ================================================ Properties ===============================================

    @property
    def description(self) -> str:
        return self._description

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def starting_room(self) -> str:
        return ROOM_ID_ENTRANCE

    # ============================================== "Real" methods =============================================

    @abstractmethod
    def generate_next_room_id(self, ruins_type: RuinsType, current_room: str, depth: int = 0) -> Optional[tuple[str, bool]]:
        pass


class SimpleRuinsStructure(RuinsStructure):
    def __init__(self, ruins_structure_id: str, name: str, description: str, room_selectors: dict[Optional[str], list[WeightedChoice[str]]]):
        super().__init__(ruins_structure_id, name, description)
        self._id: str = ruins_structure_id
        self._name: str = name
        self._description: str = description
        self._room_selectors: dict[Optional[str], list[WeightedChoice[str]]] = room_selectors

    # ================================================ Properties ===============================================

    @property
    def room_selectors(self) -> dict[Optional[str], list[WeightedChoice[str]]]:
        return self._room_selectors.copy()

    # ============================================== "Real" methods =============================================

    def generate_next_room_id(self, ruins_type: RuinsType, current_room: str, current_depth: int = 0) -> Optional[tuple[str, bool]]:
        selector_by_depth: list[WeightedChoice[str]] = self._room_selectors[current_room] if current_room in self._room_selectors else self._room_selectors[None]
        index: int = _compute_index(selector_by_depth, current_depth)
        if index < 0:
            return None

        selector = selector_by_depth[index]
        room_id: Optional[str] = selector.choose()
        if room_id is None:
            return None

        if current_depth >= MIN_DEPTH_BEFORE_FINAL:
            final_room_chance: int = round(BASE_FINAL_ROOM_CHANCE * current_depth)
            final_room: bool = random.randint(1, 100) <= final_room_chance
        else:
            final_room: bool = False

        return room_id, final_room


# =======================================================================================================================
# =================================================== Room ==============================================================
# =======================================================================================================================
class Room:
    def __init__(self, definition: RoomDefinition, depth: int, final: bool, guardian: Optional[BeastDefinition], search_loot: Loot,
                 sneak_failed: bool = False, guardian_battle: Optional[BeastBattle] = None, search_result: Optional[dict[str, int]] = None):
        super().__init__()
        self._definition: RoomDefinition = definition
        self._depth: int = depth
        self._final: bool = final or definition.final_room

        self._guardian: Optional[BeastDefinition] = guardian
        self._search_loot: Loot = search_loot

        self._sneak_failed: bool = sneak_failed
        self._guardian_battle: Optional[BeastBattle] = guardian_battle
        self._search_result: Optional[dict[str, int]] = search_result

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"Room {self._definition.name}, guardian: {self._guardian}, search_loots: {self._search_loot}"

    def __str__(self) -> str:
        return self._definition.name

    # ================================================ Properties ===============================================

    @property
    def definition(self) -> RoomDefinition:
        return self._definition

    @property
    def depth(self) -> int:
        return self._depth

    @property
    def final_room(self) -> bool:
        return self._final

    @property
    def guarded(self) -> bool:
        return self._guardian is not None and not self.guardian_killed

    @property
    def guardian(self) -> Optional[BeastDefinition]:
        return self._guardian

    @property
    def guardian_battle(self) -> Optional[BeastBattle]:
        return self._guardian_battle

    @property
    def guardian_battle_finished(self) -> bool:
        return self._guardian_battle is not None and self._guardian_battle.finished

    @property
    def guardian_battle_started(self) -> bool:
        return self._guardian_battle is not None and not self._guardian_battle.finished

    @property
    def guardian_drop(self) -> Optional[dict[str, int]]:
        return self._guardian_battle.loot if self.guardian_battle_finished else None

    @property
    def guardian_killed(self) -> bool:
        return self._guardian is not None and self._guardian_battle is not None and self._guardian_battle.beast_killed

    @property
    def name(self) -> str:
        return self._definition.name

    @property
    def search_loot(self) -> Loot:
        return self._search_loot

    @property
    def search_result(self) -> Optional[dict[str, int]]:
        return self._search_result.copy() if self._search_result is not None else None

    @property
    def searched(self) -> bool:
        return self._search_result is not None

    @property
    def sneak_failed(self) -> bool:
        return self._sneak_failed

    @sneak_failed.setter
    def sneak_failed(self, failed: bool) -> None:
        if not self.guarded:
            raise UnguardedRoomException("You don't have to sneak by unguarded rooms")

        self._sneak_failed = failed

    # ================================================= Methods =================================================

    async def do_fight_guardian(self, player: Player) -> BeastBattle:
        if not self.guarded:
            raise UnguardedRoomException("There's no guardian to kill in this room")
        elif self.guardian_killed:
            raise GuardianAlreadyKilledException("You already searched this place")

        if self._guardian_battle is None:
            await self._start_guardian_battle(player)

        await self._guardian_battle.process_round(player)

        return self._guardian_battle

    async def do_search(self, player: Player) -> dict[str, int]:
        if self.searched:
            raise RoomAlreadySearchedException("You already searched this place")

        self._search_result: dict[str, int] = self._search_loot.roll()
        if len(self._search_result) > 0:
            async with player:
                await player.acquire_loot(self._search_result)

        return self._search_result.copy()

    def do_sneak(self, player: Player, ruins_type: RuinsType) -> bool:
        success: bool = random.randint(1, 100) <= self._compute_sneak_chance(player, ruins_type)
        self.sneak_failed = not success
        return success

    def _compute_sneak_chance(self, player: Player, ruins_type: RuinsType):
        guardian_rank: int = self.guardian.rank
        player_rank: int = player.cultivation.major
        rank_delta: int = player_rank - guardian_rank
        sneak_chance: int = min(max(BASE_SNEAK_CHANCE + rank_delta * SNEAK_CHANCE_INCREMENT + self.definition.sneak_chance_mod + ruins_type.sneak_chance_mod, 0), 100)

        return sneak_chance

    async def _start_guardian_battle(self, player: Player) -> BeastBattle:
        # Start the battle
        if self.final_room:
            max_rounds: int = MAX_ROUND_BOSS
        elif self.guardian.has_variant(VARIANT_ELITE):
            max_rounds: int = MAX_ROUND_ELITE
        else:
            max_rounds: int = MAX_ROUND_NORMAL

        self._guardian_battle: BeastBattle = await BattleManager().start_solo_battle(player, self._guardian, max_rounds)

        return self._guardian_battle


# =======================================================================================================================
# =================================================== Ruins =============================================================
# =======================================================================================================================
class Ruins:
    def __init__(self, ruins_id: int, user_id: int, msg_id: int, ruins_type: RuinsType, ruins_structure: RuinsStructure,
                 started: bool = False, ended: bool = False, spent_energy: int = 0, distributed_exp: int = 0, distributed_loot: Optional[dict[str, int]] = None, current_room: Optional[Room] = None, previous_room: Optional[Room] = None,
                 created_at: datetime = datetime.now(), updated_at: datetime = datetime.now()):
        self._id: int = ruins_id
        self._user_id: int = user_id
        self._msg_id: int = msg_id
        self._type: RuinsType = ruins_type
        self._structure: RuinsStructure = ruins_structure
        self._started: bool = started
        self._ended: bool = ended
        self._spent_energy: int = spent_energy
        self._distributed_exp: int = distributed_exp
        self._distributed_loot: dict[str, int] = distributed_loot if distributed_loot is not None else {}
        self._current_room: Optional[Room] = current_room
        self._previous_room: Optional[Room] = previous_room
        self._created_at: datetime = created_at
        self._updated_at: datetime = updated_at

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"Ruins {self._id}, type: {self._type}, structure: {self._structure}"

    def __str__(self) -> str:
        return self.__repr__()

    def __hash__(self) -> int:
        return hash(self._msg_id) * 11

    def __eq__(self, other):
        return other is not None and isinstance(other, Ruins) and self._msg_id == other._msg_id

    def __ne__(self, other):
        return not self.__eq__(other)

    # ================================================ Properties ===============================================

    @property
    def id(self) -> int:
        return self._id

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def updated_at(self) -> datetime:
        return self._updated_at

    @property
    def completed(self) -> bool:
        return self._ended and self._previous_room is not None and self._previous_room.final_room

    @property
    def current_depth(self) -> int:
        if self._started:
            if self._ended:
                return self._previous_room.depth if self._previous_room is not None else -1
            else:
                return self._current_room.depth
        else:
            return -1

    @property
    def current_room(self) -> Optional[Room]:
        return self._current_room

    @property
    def distributed_exp(self) -> int:
        return self._distributed_exp

    @property
    def distributed_loot(self) -> dict[str, int]:
        return self._distributed_loot.copy()

    @property
    def ended(self) -> bool:
        return self._ended

    @property
    def msg_id(self) -> int:
        return self._msg_id

    @property
    def name(self) -> str:
        return self._type.name

    @property
    def previous_room(self) -> Optional[Room]:
        return self._previous_room

    @property
    def spent_energy(self) -> int:
        return self._spent_energy

    @property
    def started(self) -> bool:
        return self._started

    @property
    def structure(self) -> RuinsStructure:
        return self._structure

    @property
    def type(self) -> RuinsType:
        return self._type

    @property
    def user_id(self) -> int:
        return self._user_id

    # ============================================== "Real" methods =============================================
    async def end(self):
        if not self._ended:
            self._ended = True
            self._previous_room = self._current_room
            self._current_room = None
            await self.persist()

    async def explore(self) -> Optional[Room]:
        if not self._started:
            await self.start()
            return self._current_room

        current_depth: int = self._current_room.depth
        next_room_data: tuple[str, bool] = self._structure.generate_next_room_id(self._type, self._current_room.definition.id, current_depth)
        if next_room_data is None:
            await self.end()
            return None

        next_room_id, final_room = next_room_data
        next_room: Room = self._replace_current_room(next_room_id, current_depth + 1, final_room)
        await self.persist()

        return next_room

    async def persist(self, msg_id: Optional[int] = None):
        if msg_id is not None:
            self._msg_id = msg_id

        self._updated_at = datetime.now()
        if self.id == ID_UNCREATED:
            self._created_at = self._updated_at
            dto: RuinsDao = await RuinsDao.create(msg_id=self._msg_id, user_id=self._user_id, data=self._serialize_data(), created_at=self._created_at, updated_at=self._updated_at)
            self._id = dto.id
        elif msg_id is not None:
            await RuinsDao.filter(id=self._id).update(msg_id=self._msg_id, updated_at=self._updated_at)
        else:
            await RuinsDao.filter(id=self._id).update(ended=self._ended, data=self._serialize_data(), updated_at=self._updated_at)

    async def fight(self, player: Player) -> None:
        room: Room = self._valid_current_room()
        await room.do_fight_guardian(player)
        if room.guardian_killed:
            self._distributed_loot = merge_loot(self._distributed_loot, room.guardian_drop)
            self._distributed_exp += room.guardian.exp_value

        await self.persist()

    def register_energy_consumption(self, consumption: int) -> None:
        """
        Register an energy consumption by the player used to explore this ruins. This method does NOT persist the new state in database, it rather waits for the action to complete to do so

        Parameters
        ----------
        consumption: int
                     The energy consumed by the player to performa an action on this ruins

        Returns
        -------
        None
        """
        if consumption < 0:
            raise ValueError(f"Energy consumption should be positive, found {consumption}")

        self._spent_energy += consumption

    async def search(self, player: Player) -> None:
        room: Room = self._valid_current_room()
        room_loot: Optional[dict[str, int]] = await room.do_search(player)
        self._distributed_loot = merge_loot(self._distributed_loot, room_loot)
        await self.persist()

    async def sneak(self, player: Player) -> None:
        room: Room = self._valid_current_room()
        if room.do_sneak(player, self.type):
            await self.explore()
        else:
            await self.persist()

    async def start(self):
        if not self._started:
            self._started = True
            self._replace_current_room(self._structure.starting_room, 0)
            await self.persist()

        print("Failed to start ruins error")

    @staticmethod
    def deserialize(row_data: dict[str, Any]) -> R:
        manager: RuinsManager = RuinsManager()

        ruins_id: int = row_data["id"]
        msg_id: int = row_data["msg_id"]
        user_id: int = row_data["user_id"]
        ended: bool = row_data["ended"]
        created_at: datetime = row_data["created_at"]
        updated_at: datetime = row_data["updated_at"]

        data: dict[str, Any] = row_data["data"]
        ruins_type: RuinsType = manager.ruin_type(data["type_id"])
        ruins_structure: RuinsStructure = manager.ruin_structure(data["structure_id"])
        started: bool = data["started"]
        spent_energy: int = data.get("spent_energy", 0)
        distributed_exp: int = data.get("distributed_exp", 0)
        distributed_loot: dict[str, int] = data["distributed_loot"]

        current_room: Optional[Room] = Ruins._deserialize_room(ruins_type, data.get("current_room"))
        previous_room: Optional[Room] = Ruins._deserialize_room(ruins_type, data.get("previous_room"))

        ruins: Ruins = Ruins(ruins_id=ruins_id, user_id=user_id, msg_id=msg_id, ruins_type=ruins_type, ruins_structure=ruins_structure, started=started, ended=ended, spent_energy=spent_energy, distributed_exp=distributed_exp,
                             distributed_loot=distributed_loot, current_room=current_room, previous_room=previous_room, created_at=created_at, updated_at=updated_at)

        return ruins

    def _replace_current_room(self, room_id: str, depth: int, final_room: bool = False) -> Room:
        definition: RoomDefinition = RuinsManager().room_definition(room_id)
        final: bool = final_room or definition.final_room
        guardian: Optional[BeastDefinition] = definition.generate_guardian(depth=depth, probability_mod=self._type.guardian_rate_mod, criteria=self._type.guardian_filter, elite_chance_mod=self._type.elite_guardian_rate_mod, final_boss=final)
        search_loot: Loot = definition.search_loot(depth).alter_probability(self._type.search_rate_mod)
        new_room: Room = Room(definition=definition, depth=depth, final=final, guardian=guardian, search_loot=search_loot)
        self._previous_room: Optional[Room] = self._current_room
        self._current_room: Room = new_room
        return new_room

    def _valid_current_room(self) -> Room:
        room: Optional[Room] = self.current_room
        if room is None:
            raise ExplorationNotStartedException(f"Ruins {self.msg_id} doesn't have a current room")

        return room

    @staticmethod
    def _deserialize_room(ruins_type: RuinsType, room_data: Optional[dict[str, Optional[Union[bool, int, str, dict[str, int]]]]]) -> Optional[Room]:
        if room_data is None:
            return None

        manager: RuinsManager = RuinsManager()
        definition: RoomDefinition = manager.room_definition(room_data["definition_id"])
        depth: int = room_data["depth"]
        final: bool = room_data["final_room"]
        sneak_failed: bool = room_data["sneak_failed"]
        search_result: Optional[dict[str, int]] = room_data.get("search_result")

        # Use guardian_battle_id first instead of guardian_name since the battle also hold a BeastDefinition instance so let not create it twice for nothing
        guardian_battle_id: Optional[int] = room_data.get("guardian_battle_id")
        if guardian_battle_id is None:
            # No active battle, but the fight could simply not be started, so fallback on the guardian_name
            guardian: Optional[BeastDefinition] = Ruins._deserialize_room_guardian(room_data)
            guardian_battle: Optional[BeastBattle] = None
        else:
            # Use the battle to load everything
            guardian_battle: Optional[BeastBattle] = BattleManager().get(guardian_battle_id)
            if guardian_battle is None:
                # Can happen if a ruin has not expired but the battle did, in which case the player can redo the battle over, but oh well
                guardian: Optional[BeastDefinition] = Ruins._deserialize_room_guardian(room_data)
            else:
                guardian: BeastDefinition = guardian_battle.beast

        search_loot: Loot = definition.search_loot(depth).alter_probability(ruins_type.search_rate_mod)

        return Room(definition, depth, final, guardian, search_loot, sneak_failed, guardian_battle, search_result)

    @staticmethod
    def _deserialize_room_guardian(room_data: Optional[dict[str, Optional[Union[bool, int, str, dict[str, int]]]]]) -> Optional[BeastDefinition]:
        guardian_name: Optional[str] = room_data.get("guardian_name")
        if guardian_name is None:
            # Unguarded
            guardian: Optional[BeastDefinition] = None
        else:
            bestiary: Bestiary = Bestiary()
            guardian: BeastDefinition = bestiary.get(guardian_name).mutate(bestiary.get_variant(room_data.get("guardian_variant")))

        return guardian

    def _serialize_data(self) -> dict[str, Any]:
        data: dict[str, Optional[Union[bool, int, str, dict[str, Union[bool, int, str]]]]] = {
            "type_id": self._type.id,
            "structure_id": self._structure.id,
            "started": self._started,
            "spent_energy": self._spent_energy,
            "distributed_exp": self._distributed_exp,
            "distributed_loot": self._distributed_loot,
            "current_room": self._serialize_room(self._current_room),
            "previous_room": self._serialize_room(self._previous_room)
        }

        return data

    @staticmethod
    def _serialize_room(room: Optional[Room]) -> Optional[dict[str, Optional[Union[bool, int, str, dict[str, int]]]]]:
        if room is None:
            return None

        room_data: dict[str, Optional[Union[bool, int, str]]] = {
            "definition_id": room.definition.id,
            "depth": room.depth,
            "final_room": room.final_room,
            "sneak_failed": room.sneak_failed,
            "search_result": room.search_result
        }

        if room.guardian is not None:
            room_data["guardian_name"] = room.guardian.name
            room_data["guardian_variant"] = room.guardian.variant.name
            room_data["guardian_battle_id"] = room.guardian_battle.id if room.guardian_battle is not None else None
        else:
            room_data["guardian_name"] = None
            room_data["guardian_variant"] = None
            room_data["guardian_battle_id"] = None

        return room_data


# =======================================================================================================================
# =================================================== RuinsManager ======================================================
# =======================================================================================================================
@singleton
class RuinsManager:
    def __init__(self):
        self._room_definitions: list[RoomDefinition] = []
        self._room_definitions_dict: dict[str, RoomDefinition] = {}

        self._ruins_types: list[RuinsType] = [
            RuinsType(ruins_type_id="basic_ruins",
                      name="Ruins",
                      description="You discovered old ruins"),

            RuinsType(ruins_type_id="underground_ruins",
                      name="Underground Ruins",
                      color=disnake.Color.darker_grey(),
                      description="You discovered a cave leading to an underground ruins. The air is damp, the light is dim, and shadows come to life as torches sporadically light up when you pass near them. "
                                  "You can hear each of your steps echoes deep within the seemingly abandoned structures.Hiding from creatures used to this place will be challenging"
                                  "\n\n**Modifiers**"
                                  "\n- Sneak Chance: `-20%`",
                      sneak_chance_mod=-20),

            RuinsType(ruins_type_id="fire_ruins",
                      name="Fire Ruins",
                      color=disnake.Color.dark_red(),
                      description="After hearing rumors of a volcanic eruption scaring villagers away from their home, you went to a remote village by a mountain range to investigate. "
                                  "Upon your arrival, you were met with the gruesome sight or charred bodies beside rivers of magma flowing from the nearby mountain's top. Peering from the sky as you flew to the top, "
                                  "you were surprised to see a resplendent ancestral city remaining intact in the middle of the caldera. "
                                  "A place able to withstand such heat ought to have been owned by a very powerful individual that most likely left valuable treasures behind when they disappeared, "
                                  "but resisting the heat is going to consume your dou qi faster than usual."
                                  "\n\n**Modifiers**"
                                  "\n- Affinity: `Fire`"
                                  "\n- Energy Consumption: `+25%`",
                      affinities={AFFINITY_FIRE}, energy_consumption_rate=125)
        ]

        self._ruins_types_dict: dict[str, RuinsType] = {ruins_type.id: ruins_type for ruins_type in self._ruins_types}
        self._ruin_type_choice: WeightedChoice[RuinsType] = WeightedChoice({self._ruins_types_dict.get("basic_ruins"): 60, self._ruins_types_dict.get("underground_ruins"): 30, self._ruins_types_dict.get("fire_ruins"): 10})

        all_but_entrance: list[str] = [room_id for room_id in _ALL_ROOM_IDS if room_id != ROOM_ID_ENTRANCE]
        go_anywhere: list[WeightedChoice[str]] = [WeightedChoice(uniform_distribution(all_but_entrance))]

        self._ruins_structures: list[RuinsStructure] = [SimpleRuinsStructure("uniform_random", "city", "Blah blah", {None: go_anywhere})]
        self._ruins_structures_dict: dict[str, RuinsStructure] = {ruins_structure.id: ruins_structure for ruins_structure in self._ruins_structures}
        self._active_ruins: dict[int, Ruins] = dict()

    async def load(self):
        beasts: Bestiary = Bestiary()
        chests: ChestLootConfig = ChestLootConfig()

        standard_search_loots: list[PossibleLoot] = [
            PossibleLoot(chests[1], 60),  # Depth = 1
            PossibleLoot(chests[2], 60),  # Depth = 2
            PossibleLoot(chests[3], 60),  # Depth = 3
            PossibleLoot(chests[4], 65),  # Depth = 4
            PossibleLoot(chests[5], 65),  # Depth = 5
            PossibleLoot(chests[6], 65),  # Depth = 6
            PossibleLoot(chests[7], 65),  # Depth = 7
            PossibleLoot(chests[7], 70),  # Depth = 8
            PossibleLoot(chests[8], 75),  # Depth = 9
            PossibleLoot(chests[8], 80),  # Depth = 10
            PossibleLoot(chests[9], 80)   # Depth = 11
        ]

        standard_guardians: list[WeightedChoice[BeastDefinition]] = [
            uniform_choice(beasts.filter(rank__le=3), 50),  # Depth 1
            uniform_choice(beasts.filter(rank__le=4), 50),  # Depth 2
            uniform_choice(beasts.filter(rank__le=5), 60),  # Depth 3
            uniform_choice(beasts.filter(rank__ge=2, rank__le=6), 60),  # Depth 4
            uniform_choice(beasts.filter(rank__ge=3, rank__le=7), 65),  # Depth 5
            uniform_choice(beasts.filter(rank__ge=4, rank__le=8), 65),  # Depth 6
            uniform_choice(beasts.filter(rank__ge=5), 70),  # Depth 7
            uniform_choice(beasts.filter(rank__ge=6), 70),  # Depth 8
            uniform_choice(beasts.filter(rank__ge=7), 75),  # Depth 9
            uniform_choice(beasts.filter(rank__ge=8), 75),  # Depth 10
            uniform_choice(beasts.filter(rank__ge=8), 80)  # Depth 11, never freeze at R9 because there's only one mob and really not he best drop for fire ruins
        ]

        self._room_definitions: list[RoomDefinition] = [
            RoomDefinition(ROOM_ID_ENTRANCE, "entrance", "", standard_search_loots, standard_guardians),
            RoomDefinition(ROOM_ID_HALL, "hall", "", standard_search_loots, standard_guardians),
            RoomDefinition(ROOM_ID_HALLWAY, "hallway", "", standard_search_loots, standard_guardians),
            RoomDefinition(ROOM_ID_MAIN_HALL, "main hall", "", standard_search_loots, standard_guardians),
            RoomDefinition(ROOM_ID_CORRIDOR, "corridor", "", standard_search_loots, standard_guardians),
            RoomDefinition(ROOM_ID_STORAGE_ROOM, "storage room", "", standard_search_loots, standard_guardians),
            RoomDefinition(ROOM_ID_BEDROOM, "bedroom", "", standard_search_loots, standard_guardians),
            RoomDefinition(ROOM_ID_COURTYARD, "courtyard", "", standard_search_loots, standard_guardians),
            RoomDefinition(ROOM_ID_GARDEN, "garden", "", standard_search_loots, standard_guardians),
            RoomDefinition(ROOM_ID_SIDE_ROOM, "side room", "", standard_search_loots, standard_guardians),
            RoomDefinition(ROOM_ID_SECLUSION_CHAMBER, "seclusion chamber", "", standard_search_loots, standard_guardians),
            RoomDefinition(ROOM_ID_PILL_ROOM, "pill room", "", standard_search_loots, standard_guardians),
            RoomDefinition(ROOM_ID_LIBRARY, "library", "", standard_search_loots, standard_guardians),
            RoomDefinition(ROOM_ID_STABLE, "stable", "", standard_search_loots, standard_guardians),
            RoomDefinition(ROOM_ID_BEAST_YARD, "beast yard", "", standard_search_loots, standard_guardians)
        ]

        self._room_definitions_dict: dict[str, RoomDefinition] = {room.id: room for room in self._room_definitions}
        await self._load_active_ruins()

    async def _load_active_ruins(self):
        active_ruins: dict[int, Ruins] = {}

        ruins_data: list[dict[str, Any]] = await RuinsDao.filter(ended=False).values()
        for row_data in ruins_data:
            ruins: Ruins = Ruins.deserialize(row_data)
            active_ruins[ruins.msg_id] = ruins

        self._active_ruins: dict[int, Ruins] = active_ruins

    # ============================================= Special methods =============================================

    def __getitem__(self, msg_id: int) -> Optional[Ruins]:
        ruins: Optional[Ruins] = self._active_ruins.get(msg_id, None)
        if ruins is not None:
            return ruins

        # Attempt a search by id instead
        for active_ruins in self._active_ruins.values():
            if msg_id == active_ruins.id:
                return active_ruins

        return None

    # ================================================ Properties ===============================================

    @property
    def active_ruins(self) -> dict[int, Ruins]:
        return self._active_ruins.copy()

    @property
    def room_definitions(self) -> list[RoomDefinition]:
        return self._room_definitions.copy()

    @property
    def ruin_structures(self) -> list[RuinsStructure]:
        return self._ruins_structures.copy()

    @property
    def ruin_types(self) -> list[RuinsType]:
        return self._ruins_types.copy()

    # ============================================== "Real" methods =============================================

    async def generate_ruins(self, inter: disnake.CommandInteraction, player: Player, welcome_view: disnake.ui.View) -> Ruins:
        ruins: Ruins = Ruins(ruins_id=ID_UNCREATED, user_id=player.id, msg_id=0, ruins_type=self._ruin_type_choice.choose(), ruins_structure=random.choice(self._ruins_structures))
        msg: disnake.message.Message = await inter.edit_original_message(embed=RuinsWelcomeEmbed(inter.user, ruins), view=welcome_view)
        await ruins.persist(msg.id)
        self._active_ruins[msg.id] = ruins
        return ruins

    async def purge_irrelevant_ruins(self) -> None:
        now = datetime.now()
        limit = now - _MAXIMUM_RUINS_AGE
        delete_candidate_ids: set[int] = {ruins.msg_id for ruins in self._active_ruins.values() if ruins.updated_at.timestamp() < limit.timestamp()}
        for ruins_id in delete_candidate_ids:
            self._active_ruins.pop(ruins_id)

        await RuinsDao.filter(updated_at__lt=limit).delete()

    def ruins(self, msg_id: int) -> Optional[Ruins]:
        return self.__getitem__(msg_id)

    def room_definition(self, room_id: str) -> RoomDefinition:
        return self._room_definitions_dict[room_id]

    def ruin_structure(self, ruin_structure_id: str) -> RuinsStructure:
        return self._ruins_structures_dict[ruin_structure_id]

    def ruin_type(self, ruin_type_id: str) -> RuinsType:
        return self._ruins_types_dict[ruin_type_id]

    def unregister(self, ruins: Ruins) -> bool:
        msg_id: int = ruins.msg_id
        if msg_id in self._active_ruins:
            self._active_ruins.pop(msg_id)
            return True

        return False


class BaseRuinEmbed(BaseStarfallEmbed):
    def __init__(self, user: User, ruins: Ruins):
        super().__init__()
        self._user = user
        self._ruins = ruins
        self.title = ruins.type.name
        self.color = ruins.type.color
        if ruins.current_depth > 0:
            self.set_footer(text=f"Ruins exploration started by {user.name}, current depth: {ruins.current_depth}. Ruins id: {ruins.id}")
        else:
            self.set_footer(text=f"Ruins exploration started by {user.name}. Ruins id: {ruins.id}")

    @property
    def ruins(self) -> Ruins:
        return self._ruins

    @property
    def user(self) -> User:
        return self._user


class RuinsWelcomeEmbed(BaseRuinEmbed):
    def __init__(self, user: User, ruins: Ruins):
        super().__init__(user, ruins)
        self.description = ruins.type.description


class RuinsLeftEmbed(BaseRuinEmbed):
    def __init__(self, user: User, ruins: Ruins):
        super().__init__(user, ruins)
        self.set_footer(text=f"Ruins explored by {user.name}. Ruins id: {ruins.id}")

        result_summary: str = f"You completely explored the {ruins.type.name.lower()}." if ruins.completed else f"You left the {ruins.type.name.lower()} before completely exploring it."

        self.description = (f"{result_summary}"
                            f"\n\nYour little expedition took `{ruins.spent_energy:,} energy`, but earned you `{ruins.distributed_exp:,} exp` (plus bonus)")

        loot: dict[str, int] = ruins.distributed_loot
        if loot is not None and len(loot) > 0:
            self.description = (f"{self.description}, as well as:"
                                f"\n{ItemCompendium().describe_dict(loot)}")


class RoomEmbed(BaseRuinEmbed):
    def __init__(self, user: User, ruins: Ruins):
        super().__init__(user, ruins)
        room: Optional[Room] = self._ruins.current_room
        self._room: Optional[Room] = ruins.current_room
        if room is None:
            self.description = f"The {self._ruins.name} was fully explored."
        else:
            multiple_options: bool = True
            if room.searched:
                multiple_options: bool = not room.final_room
                search_result: Optional[dict[str, int]] = room.search_result
                if search_result is None or len(search_result) == 0:
                    contents_description: str = "After searching for 30 minutes without anything to show for, you had to resign yourself to the fact that the room didn't contain any treasure"
                else:
                    contents_description: str = (f"Searching thoroughly through the room you found:"
                                                 f"\n{ItemCompendium().describe_dict(search_result)}")

            elif room.guardian_battle is None:
                if room.guarded:
                    if room.sneak_failed:
                        contents_description: str = (f"You failed to sneak by the **{room.guardian.title}** guarding the room. "
                                                     f"\n\nYou have no choice but to fight it or flee now")
                    else:
                        contents_description: str = f"A **{room.guardian.title}** is guarding the room"
                else:
                    contents_description: str = "The room seems unguarded, you see some debris in a corner."
            else:
                # If there's a battle, then it's implicit that the room was guarded
                battle: BeastBattle = room.guardian_battle
                last_round: BattleRound = battle.last_round
                damage: int = last_round.damage_dealt
                dmg_description: str = f"You dealt `{ParamsUtils.format_num_abbr0(damage)}` dmg to the **{room.guardian.title}**"
                if room.guardian_battle_finished:
                    if room.guardian_killed:
                        guardian_loot: Optional[dict[str, int]] = room.guardian_drop
                        if guardian_loot is None or len(guardian_loot) == 0:
                            base_message: str = (f"{dmg_description}."
                                                 f"\n\nThe **{room.guardian.title}** body lays still after your gloriously vanquished it. You tried to salvage some materials from it, but could get anything usable from the whole mess.")
                        else:
                            base_message: str = (f"{dmg_description}."
                                                 f"\n\nThe **{room.guardian.title}** body lays still after your gloriously vanquished it. Searching it, you found:"
                                                 f"\n{ItemCompendium().describe_dict(room.guardian_drop)}")

                        contents_description: str = (f"{base_message}"
                                                     f"\n\nYou gained `{room.guardian.exp_value:,}` exp plus bonus."
                                                     f"\n\nYou see some debris in a corner.")
                    else:
                        # The room is still guarded, but the battle is finished
                        contents_description: str = f"{dmg_description}, but the beast is still alive and you're exhausted from the long fight, you can only escape..."
                        multiple_options: bool = False
                else:
                    # The battle is ongoing
                    contents_description: str = (f"{dmg_description}, but the beast is still alive."
                                                 f"\n\nYou have enough stamina to attack it {battle.remaining_rounds} times.")

            if room.guarded:
                image = room.guardian.image
                if image is not None:
                    self.set_image(file=image)

            if multiple_options:
                self.description = (f"{self.compute_enter_message()}"
                                    f"\n\n{contents_description}"
                                    f"\n\nWhat do you want to do next?")
            else:
                self.description = (f"{self.compute_enter_message()}"
                                    f"\n\n{contents_description}")

    def compute_enter_message(self) -> str:
        room: Room = self._room
        if room.definition.id == ROOM_ID_ENTRANCE:
            # Special case
            description: str = "You reached the ruin **entrance**."
        else:
            room_name: str = room.name
            description: str = f"You entered a{'n' if room_name[0] in _VOWELS else ''} **{room_name}**."

        return description


def _compute_index(list_by_rank: list[T], depth: int) -> int:
    length: int = len(list_by_rank)
    if length == 0:
        return -1

    if depth >= length:
        depth = length - 1

    return depth


def _log(user_id: Union[int, str], message: str):
    log_event(user_id, _SHORT_NAME, message)

from asyncio import Lock
from datetime import datetime, timedelta
from typing import Any, Optional, TypeVar, Union

from world.bestiary import Bestiary, BeastDefinition, VARIANT_NORMAL
from character.player import PlayerRoster, Player
from utils import DatabaseUtils, ParamsUtils
from utils.base import singleton
from utils.loot import LootDistributionLogic
from utils.Database import BeastBattleDao, ID_UNCREATED
from utils.LoggingUtils import log_event

SOURCE_ALLY: str = "ally"
SOURCE_PET: str = "pet"
SOURCE_PLAYER: str = "player"

NO_MAX_ROUND: int = -1

_SHORT_NAME: str = "battle"
_MAXIMUM_BATTLE_AGE: timedelta = timedelta(days=7)

A = TypeVar("A", bound="Attack")
B = TypeVar("B", bound="BeastBattle")
M = TypeVar("M", bound="BattleManager")
R = TypeVar("R", bound="BattleRound")


class Attack:
    def __init__(self, battle_round: R, player_id: int, damage_dealt: int, source: str, initiative: int, created_at: datetime = datetime.now(), player: Optional[Player] = None):
        self._round: R = battle_round
        self._player_id: int = player_id
        self._damage_dealt: int = damage_dealt
        self._source: str = source
        self._initiative: int = initiative
        self._player: Optional[Player] = player
        self._created_at: datetime = created_at

    # ============================================= Special methods =============================================

    def __repr__(self) -> str:
        return f"Attack from {self._player_id} the dealt {self._damage_dealt:,} damage on {self._round.battle.beast.name} through {self._source} at {self._created_at} during round {self._round.round_number}"

    def __str__(self) -> str:
        return self.__repr__()

    def __hash__(self) -> int:
        return hash(self._round) * 13 + hash(self._player_id) * 11 + hash(self._source) * 7 + hash(self._source) * 5 + hash(self._created_at) * 3

    def __eq__(self, other) -> bool:
        return (other is not None
                and isinstance(other, Attack)
                and self._round == other._round
                and self._player_id == other._player_id
                and self._source == other._source
                and self._initiative == other._initiative
                and self._created_at == other._created_at)

    def __ne__(self, other) -> bool:
        return not self.__eq__(other)

    def __ge__(self, other) -> bool:
        return self.__eq__(other) or self.__gt__(other)

    def __gt__(self, other) -> bool:
        if other is None or not isinstance(other, Attack):
            return False

        if self._initiative > other._initiative:
            return True
        elif self._initiative < other._initiative:
            return False
        else:
            # Same initiative and same created_at
            if self._created_at > other._created_at:
                return True
            elif self._created_at < other._created_at:
                return False
            else:
                # Same initiative and same created_at, fallback on source
                return self._source > other._source

    def __le__(self, other) -> bool:
        return self.__eq__(other) or self.__lt__(other)

    def __lt__(self, other) -> bool:
        return not self.__ge__(other)

    # ================================================ Properties ===============================================

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def damage_dealt(self) -> int:
        return self._damage_dealt

    @property
    def initiative(self) -> int:
        return self._initiative

    @property
    def player(self) -> Optional[Player]:
        return self._player

    @property
    def player_id(self) -> int:
        return self._player_id

    @property
    def source(self) -> str:
        return self._source

    # ============================================== "Real" methods =============================================

    @staticmethod
    def deserialize(battle_round: R, roster: PlayerRoster, data: dict[str, Union[datetime, int, str]]) -> A:
        player_id: int = data["player_id"]
        damage_dealt: int = data["damage_dealt"]
        source: str = data["source"]
        initiative: int = data["initiative"]
        created_at: datetime = datetime.utcfromtimestamp(int(data["created_at"]))
        player: Optional[Player] = roster.get(player_id)

        return Attack(battle_round, player_id, damage_dealt, source, initiative, created_at, player)

    def serialize(self) -> dict[str, Union[datetime, int, str]]:
        return {
            "player_id": self._player_id,
            "damage_dealt": self._damage_dealt,
            "source": self._source,
            "initiative": self._initiative,
            "created_at": self._created_at.timestamp()
        }


class BattleRound:
    def __init__(self, battle: B, round_number: int, player_id: int, player: Optional[Player], raw_attack_data: Optional[list[tuple[int, int, str, int, datetime, Optional[Player]]]] = None):
        self._battle: B = battle
        self._round_number: int = round_number
        self._player_id: int = player_id
        self._player: Optional[Player] = player
        self._attacks: list[Attack] = [Attack(self, p_id, dmg, src, ini, created_at, p) for p_id, dmg, src, ini, created_at, p in raw_attack_data if p_id == player_id] if raw_attack_data is not None else []
        self._attacks.sort()

    # ============================================= Special methods =============================================

    def __repr__(self) -> str:
        return f"Round {self._round_number} of battler at {self._battle.id}"

    def __str__(self) -> str:
        return self.__repr__()

    def __hash__(self) -> int:
        return hash(self._battle.id) * 5 + hash(self._round_number) * 3

    def __eq__(self, other) -> bool:
        return other is not None and isinstance(other, BattleRound) and self._battle == other._battle and self._round_number == other._round_number

    def __ne__(self, other) -> bool:
        return not self.__eq__(other)

    def __ge__(self, other) -> bool:
        return self.__eq__(other) or self.__gt__(other)

    def __gt__(self, other) -> bool:
        if other is None or not isinstance(other, BattleRound):
            return False

        return self._round_number > other._round_number

    def __le__(self, other) -> bool:
        return self.__eq__(other) or self.__lt__(other)

    def __lt__(self, other) -> bool:
        return not self.__ge__(other)

    # ================================================ Properties ===============================================

    @property
    def attacks(self) -> list[Attack]:
        return self._attacks.copy()

    @property
    def battle(self) -> B:
        return self._battle

    @property
    def player(self) -> Optional[Player]:
        return self._player

    @property
    def player_id(self) -> int:
        return self._player_id

    @property
    def round_number(self) -> int:
        return self._round_number

    @property
    def damage_dealt(self) -> int:
        return sum([atk.damage_dealt for atk in self._attacks])

    # ============================================== "Real" methods =============================================

    @staticmethod
    def deserialize(battle: B, roster: PlayerRoster, data: dict[str, Union[int, list[dict[str, Union[datetime, int, str]]]]]) -> R:
        round_number: int = data["round_number"]
        player_id: int = data["player_id"]
        battle_round: BattleRound = BattleRound(battle, round_number, player_id, roster.get(player_id))
        attacks: list[Attack] = [Attack.deserialize(battle_round, roster, attack_data) for attack_data in data["attacks"]]
        attacks.sort()
        battle_round._attacks = attacks

        return battle_round

    def serialize(self) -> dict[str, Union[int, list[dict[str, Union[datetime, int, str]]]]]:
        attack_data: list[dict[str, Union[datetime, int, str]]] = [attack.serialize() for attack in self._attacks]
        serialized: dict[str, Union[int, list[dict[str, Union[datetime, int, str]]]]] = {
            "round_number": self._round_number,
            "player_id": self._player_id,
            "attacks": attack_data
        }

        return serialized


class BeastBattle:
    def __init__(self, manager: M, beast: BeastDefinition, battle_id: int = ID_UNCREATED, max_rounds: int = NO_MAX_ROUND, unlimited_health: bool = False, valid_attacker_ids: Optional[set[int]] = None, finished: bool = False,
                 loot_distribution_logic: Optional[LootDistributionLogic] = None, loot: Optional[dict[str, int]] = None, loot_distribution: Optional[dict[int, dict[str, int]]] = None,
                 created_at: datetime = datetime.now(), updated_at: datetime = datetime.now()):
        super().__init__()
        # Ideally we'd want two Character instances, attacker and defender or something around those lines instead of a class per fight type
        self._manager: M = manager
        self._beast: BeastDefinition = beast
        self._id: int = battle_id
        self._max_rounds: int = max_rounds
        self._unlimited_health: bool = unlimited_health
        self._valid_attackers: Optional[set[int]] = None if valid_attacker_ids is None or len(valid_attacker_ids) == 0 else valid_attacker_ids.copy()
        self._rounds: list[BattleRound] = []
        self._finished: bool = finished
        self._loot_distribution_logic: LootDistributionLogic = loot_distribution_logic if loot_distribution_logic is not None else LootDistributionLogic()
        self._loot: Optional[dict[str, int]] = None if loot is None else loot
        self._loot_distribution: Optional[dict[int, dict[str, int]]] = None if loot_distribution is None else loot_distribution
        self._created_at: datetime = created_at
        self._updated_at: datetime = updated_at
        self._changed: bool = False
        self._lock: Lock = Lock()
        self._rounds.sort()

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"Player {{user_id: {self._id}}}"

    def __str__(self):
        return self.__repr__()

    def __hash__(self) -> int:
        return hash(self._id) * 17

    def __eq__(self, other):
        return other is not None and isinstance(other, BeastBattle) and self._id == other._id

    def __ne__(self, other):
        return not self.__eq__(other)

    # ================================================ Properties ===============================================

    @property
    def battle_manager(self) -> M:
        return self._manager

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
    def beast(self) -> BeastDefinition:
        return self._beast

    @property
    def beast_killed(self) -> bool:
        return not self._unlimited_health and self.total_damage >= self.total_health

    @property
    def completed_rounds(self) -> int:
        return len(self._rounds)

    @property
    def current_round_number(self) -> int:
        return len(self._rounds) + 1

    @property
    def experience_reward(self) -> int:
        return self._beast.exp_value if self.beast_killed else 0

    @property
    def finished(self) -> bool:
        return self._finished or self.max_rounds_reached or self.beast_killed

    @property
    def last_round(self) -> Optional[BattleRound]:
        round_count: int = len(self._rounds)
        return None if round_count == 0 else self._rounds[round_count - 1]

    @property
    def loot(self) -> Optional[dict[str, int]]:
        if self._loot is None and self.finished:
            self._loot = {}

        return self._loot.copy() if self._loot is not None else None

    @property
    def loot_distribution(self) -> Optional[dict[int, dict[str, int]]]:
        if self._loot_distribution is None and self.finished:
            self._loot_distribution: dict[int, dict[str, int]] = {}

        return self._loot_distribution.copy() if self._loot_distribution is not None else None

    @property
    def loot_distribution_logic(self) -> LootDistributionLogic:
        return self._loot_distribution_logic

    @property
    def max_rounds(self) -> int:
        return self._max_rounds

    @property
    def max_rounds_reached(self) -> bool:
        return 0 < self._max_rounds <= self.completed_rounds

    @property
    def remaining_health(self) -> int:
        return max(self.total_health - self.total_damage, 0)

    @property
    def remaining_rounds(self) -> int:
        if self._max_rounds == NO_MAX_ROUND:
            return 9999

        return self._max_rounds - len(self._rounds)

    @property
    def rounds(self) -> list[BattleRound]:
        return self._rounds.copy()

    @property
    def restrict_attackers(self) -> bool:
        return self._valid_attackers is not None

    @property
    def total_damage(self) -> int:
        return sum([r.damage_dealt for r in self._rounds])

    @property
    def total_health(self) -> int:
        return self._beast.health if not self._unlimited_health else -1

    @property
    def unlimited_health_mode(self) -> bool:
        return self._unlimited_health

    @property
    def valid_attacker(self) -> Optional[set[Player]]:
        return None if self._valid_attackers is None else self._valid_attackers.copy()

    # ============================================== "Real" methods =============================================

    async def finish(self) -> bool:
        requires_loot_distribution: bool = False
        async with self._lock:
            if not self.finished:
                self._finished = True
                if self.beast_killed or self._unlimited_health:
                    # Generate loot after explicit finish in unlimited health/punching bag mode
                    self._loot = self._beast.loot.roll()
                    requires_loot_distribution = True

                self._changed = True

        if requires_loot_distribution:
            await self._distribute_loot()

        await self.persist()

        return requires_loot_distribution

    def is_valid_attacker(self, player: Player) -> bool:
        return not self.restrict_attackers or player.id in self._valid_attackers

    async def process_round(self, player: Player) -> bool:
        if not self.is_valid_attacker(player):
            raise ValueError(f"Player {player.id} is not allowed to participate to battle {self.id}")

        requires_loot_distribution: bool = False
        async with self._lock:
            active: bool = not self.finished
            round_number: int = self.current_round_number
            if active:
                _, _, battle_boost, _ = await DatabaseUtils.compute_pill_bonus(player.id, battle=1)
                display_cp: int = await player.compute_total_cp()
                display_cp = display_cp + display_cp * battle_boost // 100
                internal_cp = ParamsUtils.display_to_internal_cp(display_cp)
                inflicted_damage = round(ParamsUtils.internal_cp_to_attack(internal_cp))
                self._rounds.append(BattleRound(self, round_number, player.id, player, [(player.id, inflicted_damage, SOURCE_PLAYER, 1, datetime.now(), player)]))
                if self.beast_killed:
                    self._finished = True
                    self._loot = self._beast.loot.roll()
                    requires_loot_distribution = True
                elif self.max_rounds_reached:
                    self._finished = True
                    if self._unlimited_health:
                        # Punching bag mode always generates loot when finished
                        self._loot = self._beast.loot.roll()
                        requires_loot_distribution = True
                    else:
                        self._loot = {}

                self._changed = True

        if active:
            if requires_loot_distribution:
                await self._distribute_loot()

            await self.persist()

        return requires_loot_distribution

    async def persist(self):
        if self.id == ID_UNCREATED:
            self._created_at = datetime.now()
            self._updated_at = self._created_at
            dto: BeastBattleDao = await BeastBattleDao.create(data=self._serialize_data(), created_at=self._created_at, updated_at=self._updated_at)
            self._id = dto.id
            self._changed = False
        elif self._changed:
            self._updated_at = datetime.now()
            await BeastBattleDao.filter(id=self._id).update(data=self._serialize_data(), created_at=self._created_at, updated_at=self._updated_at)
            self._changed = False

    async def _distribute_loot(self) -> None:
        if self._loot_distribution is None:
            if self.experience_reward > 0 or (self._loot is not None and len(self._loot) > 0):
                contributions: dict[int, int] = {}
                for battle_round in self._rounds:
                    player_id: int = battle_round.player_id
                    contributions[player_id] = contributions.get(player_id, 0) + battle_round.damage_dealt

                self._loot_distribution = self._loot_distribution_logic.distribute(loot=self._loot, contributions=contributions, flat_experience=self.experience_reward)
                await PlayerRoster().distribute_loot(self._loot_distribution)
            else:
                self._loot_distribution = {}

            self._changed = True

    @staticmethod
    def deserialize(manager: M, bestiary: Bestiary, roster: PlayerRoster, row_data: dict[str, Any]) -> B:
        battle_id: int = row_data["id"]
        created_at: datetime = row_data["created_at"]
        updated_at: datetime = row_data["updated_at"]
        data: dict[str, Any] = row_data["data"]

        beast_name: str = data["beast_name"]
        beast_variant_name: str = data["beast_variant"]
        max_rounds: int = data["max_rounds"]
        unlimited_health: bool = data["unlimited_health"]
        valid_attackers: Optional[list[int]] = data["valid_attackers"]
        finished: bool = data["finished"]
        loot_distribution_logic: LootDistributionLogic = LootDistributionLogic.deserialize(data["loot_distribution_logic"])
        loot: Optional[dict[str, int]] = data["loot"]
        loot_distribution: Optional[dict[int, dict[str, int]]] = data["loot_distribution"]
        rounds_data: list[dict[str, Union[int, list[dict[str, Union[datetime, int, str]]]]]] = data["rounds"]

        beast: BeastDefinition = bestiary[beast_name]
        if beast_variant_name != VARIANT_NORMAL:
            beast = beast.mutate(bestiary.get_variant(beast_variant_name))

        battle: BeastBattle = BeastBattle(manager, beast, battle_id, max_rounds, unlimited_health, set(valid_attackers) if valid_attackers is not None else None, finished, loot_distribution_logic, loot, loot_distribution, created_at, updated_at)
        rounds: list[BattleRound] = [BattleRound.deserialize(battle, roster, round_data) for round_data in rounds_data]
        rounds.sort()
        battle._rounds = rounds

        return battle

    def _serialize_data(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "beast_name": self._beast.name,
            "beast_variant": self._beast.variant.name,
            "max_rounds": self._max_rounds,
            "unlimited_health": self._unlimited_health,
            "valid_attackers": list(self._valid_attackers) if self._valid_attackers is not None else None,
            "finished": self._finished,
            "loot_distribution_logic": self._loot_distribution_logic.serialize(),
            "loot": self._loot,
            "loot_distribution": self._loot_distribution,
            "rounds": self._serialize_round_data(),
        }

        return data

    def _serialize_round_data(self) -> list[dict[str, Union[int, list[dict[str, Union[datetime, int, str]]]]]]:
        round_data: list[dict[str, Union[int, list[dict[str, Union[datetime, int, str]]]]]] = [battle_round.serialize() for battle_round in self._rounds]
        return round_data


@singleton
class BattleManager:
    def __init__(self):
        self._beast_battles: dict[int, BeastBattle] = {}

    async def load(self):
        bestiary: Bestiary = Bestiary()
        roster: PlayerRoster = PlayerRoster()
        beast_battles: dict[int, BeastBattle] = {}

        battles: list[dict[str, Any]] = await BeastBattleDao.all().values()
        for battle_data in battles:
            battle: BeastBattle = BeastBattle.deserialize(self, bestiary, roster, battle_data)
            beast_battles[battle.id] = battle

        self._beast_battles: dict[int, BeastBattle] = beast_battles

    # ============================================= Special methods =============================================

    def __repr__(self):
        return "BattleManager"

    def __str__(self) -> str:
        return "Battle Manager"

    def __getitem__(self, battle_id: int) -> BeastBattle:
        return self._beast_battles[battle_id]

    # ============================================== "Real" methods =============================================
    async def purge_irrelevant_battles(self) -> None:
        now = datetime.now()
        limit = now - _MAXIMUM_BATTLE_AGE
        delete_candidate_ids: set[int] = {battle.id for battle in self._beast_battles.values() if battle.updated_at.timestamp() < limit.timestamp()}
        for battle_id in delete_candidate_ids:
            self._beast_battles.pop(battle_id)

        await BeastBattleDao.filter(updated_at__lt=limit).delete()

    async def start_open_battle(self, beast: BeastDefinition, max_rounds: int = NO_MAX_ROUND, unlimited_health: bool = False) -> BeastBattle:
        return await self._register(BeastBattle(manager=self, beast=beast, max_rounds=max_rounds, unlimited_health=unlimited_health))

    async def start_solo_battle(self, player: Player, beast: BeastDefinition, max_rounds: int = NO_MAX_ROUND, unlimited_health: bool = False) -> BeastBattle:
        return await self._register(BeastBattle(manager=self, beast=beast, max_rounds=max_rounds, unlimited_health=unlimited_health, valid_attacker_ids={player.id}))

    def get(self, battle_id: int) -> Optional[BeastBattle]:
        return self._beast_battles.get(battle_id)

    async def _register(self, battle: BeastBattle) -> BeastBattle:
        await battle.persist()
        self._beast_battles[battle.id] = battle

        return battle


def _log(user_id: Union[int, str], message: str):
    log_event(user_id, _SHORT_NAME, message)

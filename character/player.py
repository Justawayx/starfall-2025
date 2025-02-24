from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from time import mktime
from typing import Optional, Union, Any, TypeVar, cast

import disnake
from tortoise.exceptions import MultipleObjectsReturned

from character.character import Character
from utils import ParamsUtils
from utils.Database import Alchemy, Cultivation, Users, Pvp, RingInventory, Pet, Temp, Factions, Inventory, AllRings
from utils.InventoryUtils import check_item_in_inv, remove_from_inventory, add_to_inventory, get_equipped_ring_id
from utils.LoggingUtils import log_event
from utils.ParamsUtils import CURRENCY_NAME_ARENA_COIN, CURRENCY_NAME_GOLD, CURRENCY_NAME_STAR, format_num_abbr1, mention
from utils.Styles import PLUS, EXCLAMATION, CROSS, TICK, MINUS
from utils.base import CogNotLoadedError, singleton, BaseStarfallButton
from character.inventory import PlayerInventory, BaseInventory, Item, StorageRing
from utils.loot import PSEUDO_ITEM_ID_EXP_FLAT, PSEUDO_ITEM_ID_EXP_RATIO, RelativeExperienceLoot, filter_item_loot, PSEUDO_ITEM_ID_GOLD, PSEUDO_ITEM_ID_ARENA_COIN, PSEUDO_ITEM_ID_STAR, filter_pseudo_item_loot, PSEUDO_ITEM_ID_ENERGY_FLAT, \
    PSEUDO_ITEM_ID_ENERGY_RATIO
from world.bestiary import Bestiary, PetBeastDefinition
from world.continent import Continent
from world.cultivation import PlayerCultivationStage, generate_player_cultivation_stage_matrix, BeastCultivationStage
from world.compendium import ItemCompendium, ItemDefinition, FlameDefinition, QiMethodManualDefinition

MESSAGE_EXP_COUNT_LIMIT: int = 100
MESSAGE_EXP_COOLDOWN: timedelta = timedelta(minutes=1)
MESSAGE_EXP_RANGE: tuple[int, int] = (10, 15)
ENERGY_RECOVERY_RATE_MINUTES: int = 2

VALID_CURRENCY = ['gold', 'ac']
PVP_REWARDS = {
    "High Tian": [5000000, 500000],
    "Middle Tian": [2500000, 250000],
    "Low Tian": [1000000, 100000],
    "High Di": [600000, 60000],
    "Middle Di": [400000, 40000],
    "Low Di": [200000, 20000],
    "High Xuan": [100000, 10000],
    "Middle Xuan": [75000, 7500],
    "Low Xuan": [50000, 5000],
    "High Huang": [20000, 2000],
    "Middle Huang": [10000, 1000],
    "Low Huang": [5000, 500],
    " Unranked": [0, 0]  # Keep the space
}

BUFF_TYPE_COMBAT_POWER: str = "CP"
BUFF_TYPE_EXPERIENCE: str = "EXP"

R = TypeVar("R", bound="PlayerRoster")  # the variable name must coincide with the string


class TemporaryBuff:
    def __init__(self, user_id: int, buff_type: str, value: int, expire_on_epoch: Optional[int] = None):
        super().__init__()
        self._user_id: int = user_id
        self._buff_type: str = buff_type
        self._value: int = value
        self._expire_on_epoch: Optional[int] = expire_on_epoch

    # ============================================= Special methods =============================================

    def __repr__(self):
        expiration_desc: str = f"{datetime.fromtimestamp(self._expire_on_epoch, timezone.utc)}" if self._expire_on_epoch is not None else "Until dispelled"
        return f"TemporaryBuff {{user_id: {self._user_id}, type: {self._buff_type}, value: {self._value}, expire_on: {expiration_desc}}}"

    def __str__(self):
        return self.__repr__()

    def __hash__(self) -> int:
        return hash(self._user_id) * 19 + hash(self._buff_type) * 3 + hash(self._value) * 5

    def __eq__(self, other):
        return other is not None and isinstance(other, TemporaryBuff) and self._user_id == other._user_id and self._buff_type == other._buff_type and self._value == other._value and self._expire_on_epoch == other._expire_on_epoch


class PlayerWallet:
    def __init__(self, user_id: int, gold: int, arena_coins: int, stars: int):
        super().__init__()
        self._user_id: int = user_id
        self._gold: int = gold
        self._arena_coins: int = arena_coins
        self._stars: int = stars

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"PlayerWallet {{user_id: {self._user_id}, gold: {self._gold}, arena_coins: {self._arena_coins}, stars: {self._stars}}}"

    def __str__(self):
        return self.__repr__()

    def __hash__(self) -> int:
        return hash(self._user_id) * 19

    def __eq__(self, other):
        return other is not None and isinstance(other, PlayerWallet) and self._user_id == other._user_id

    # ================================================ Properties ===============================================

    @property
    def arena_coins(self) -> int:
        return self._arena_coins

    @arena_coins.setter
    def arena_coins(self, new_amount: int) -> None:
        self._arena_coins = new_amount

    def copy(self) -> PlayerWallet:
        return PlayerWallet(self._user_id, self._gold, self._arena_coins, self._stars)

    @property
    def gold(self) -> int:
        return self._gold

    @gold.setter
    def gold(self, new_amount: int) -> None:
        self._gold = new_amount

    @property
    def stars(self) -> int:
        return self._stars

    @stars.setter
    def stars(self, new_amount: int) -> None:
        self._stars = new_amount

    @property
    def user_id(self) -> int:
        return self._user_id

    # ============================================== "Real" methods =============================================


class Player(Character):
    def __init__(self, roster: R, user_id: int, energy: int, wallet: PlayerWallet,
                 cultivation_stage: PlayerCultivationStage, current_experience: int, cultivation_cooldown: Optional[datetime] = None,
                 daily_message_count: int = 0, daily_message_cooldown: Optional[datetime] = None,
                 claimed_daily: bool = False, inventory: PlayerInventory = None):
        super().__init__()
        self._roster: R = roster
        self._id: int = user_id
        self._energy: int = energy
        self._wallet: PlayerWallet = wallet
        self._cultivation_stage: PlayerCultivationStage = cultivation_stage
        self._current_experience: int = int(current_experience)
        self._cultivation_cooldown: Optional[datetime] = datetime.fromtimestamp(cultivation_cooldown.timestamp()) if cultivation_cooldown is not None else None
        self._daily_message_count: int = daily_message_count
        self._daily_message_cooldown: Optional[datetime] = datetime.fromtimestamp(daily_message_cooldown.timestamp()) if daily_message_cooldown is not None else None
        self._claimed_daily: bool = claimed_daily
        self._buffs: dict[str, list[TemporaryBuff]] = {}
        self._member: Optional[disnake.Member] = None
        self._core_altered: bool = False
        self._cultivation_altered: bool = False
        self._pvp_altered: bool = False
        self._inventory: PlayerInventory = inventory

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"Player {{user_id: {self._id}}}"

    def __str__(self):
        return self.__repr__()

    def __hash__(self) -> int:
        return hash(self._id) * 17

    def __eq__(self, other):
        return other is not None and isinstance(other, Player) and self._id == other._id

    def __ne__(self, other):
        return not self.__eq__(other)

    # ================================================ Properties ===============================================

    @property
    def claimed_daily(self) -> bool:
        return self._claimed_daily

    @claimed_daily.setter
    def claimed_daily(self, claimed: bool) -> None:
        if self._claimed_daily != claimed:
            self._claimed_daily = claimed
            self._core_altered = True

    @property
    def cultivation(self) -> PlayerCultivationStage:
        return self._cultivation_stage

    @cultivation.setter
    def cultivation(self, new_cultivation: PlayerCultivationStage) -> None:
        if new_cultivation != self._cultivation_stage:
            self._cultivation_stage = new_cultivation
            self._cultivation_altered = True

    @property
    def cultivation_cooldown(self) -> Optional[datetime]:
        return self._cultivation_cooldown

    @cultivation_cooldown.setter
    def cultivation_cooldown(self, new_cooldown: Optional[datetime]) -> None:
        if self._cultivation_cooldown != new_cooldown:
            self._cultivation_altered = True
            self._cultivation_cooldown = new_cooldown

    @property
    def current_experience(self) -> int:
        return self._current_experience

    @property
    def current_arena_coins(self) -> int:
        return self.get_funds(CURRENCY_NAME_ARENA_COIN)

    @property
    def current_gold(self) -> int:
        return self.get_funds()

    @property
    def current_stars(self) -> int:
        return self.get_funds(CURRENCY_NAME_STAR)

    @property
    def daily_message_count(self) -> int:
        return self._daily_message_count

    @daily_message_count.setter
    def daily_message_count(self, new_count: int) -> None:
        if new_count < 0:
            raise ValueError(f"message count should be positive, found {new_count:,}")
        elif new_count > MESSAGE_EXP_COUNT_LIMIT:
            raise ValueError(f"message count should be lower or equal than {MESSAGE_EXP_COUNT_LIMIT}, found {new_count:,}")

        if new_count != self._daily_message_count:
            self._daily_message_count: int = new_count
            self._cultivation_altered = True

    @property
    def daily_message_cooldown(self) -> Optional[datetime]:
        return self._daily_message_cooldown

    @daily_message_cooldown.setter
    def daily_message_cooldown(self, new_cooldown: Optional[datetime]) -> None:
        if new_cooldown != self._daily_message_cooldown:
            self._daily_message_cooldown: Optional[datetime] = new_cooldown
            self._cultivation_altered = True

    @property
    def daily_message_cooldown_elapsed(self) -> bool:
        if self._daily_message_cooldown is None:
            return True

        return datetime.now().timestamp() > self._daily_message_cooldown.timestamp()

    @property
    def energy(self) -> int:
        return self._energy

    @property
    def id(self) -> int:
        return self._id

    @property
    def inventory(self) -> PlayerInventory:
        return self._inventory

    @property
    def is_missing_energy(self) -> bool:
        return self.missing_energy > 0

    @property
    def maximum_energy(self) -> int:
        return self._cultivation_stage.maximum_energy

    @property
    def mention_str(self):
        return mention(self._id)

    @property
    def missing_energy(self) -> int:
        current: int = self._energy
        maximum: int = self.maximum_energy
        return maximum - current if current < maximum else 0

    @property
    def roster(self) -> R:
        return self._roster

    @property
    def total_experience(self) -> int:
        return self._cultivation_stage.required_total_experience + self._current_experience

    # ============================================== "Real" methods =============================================

    async def acquire_loot(self, loot: dict[str, int]) -> None:
        pseudo_item_loot: dict[str, int] = filter_pseudo_item_loot(loot)
        if len(pseudo_item_loot) > 0:
            experience: int = loot.get(PSEUDO_ITEM_ID_EXP_FLAT, 0)
            experience_ratio: int = loot.get(PSEUDO_ITEM_ID_EXP_RATIO, 0)
            if experience_ratio > 0:
                experience += math.ceil(self.cultivation.breakthrough_experience * RelativeExperienceLoot.as_percentage(experience_ratio))

            await self.add_experience(experience)

            energy: int = loot.get(PSEUDO_ITEM_ID_ENERGY_FLAT, 0)
            energy_ratio: int = loot.get(PSEUDO_ITEM_ID_ENERGY_RATIO, 0)
            if energy_ratio > 0:
                energy += math.ceil(self.cultivation.maximum_energy * energy_ratio // 100)

            self.add_energy(energy)
            self.add_funds(loot.get(PSEUDO_ITEM_ID_GOLD, 0), CURRENCY_NAME_GOLD)
            self.add_funds(loot.get(PSEUDO_ITEM_ID_ARENA_COIN, 0), CURRENCY_NAME_ARENA_COIN)
            self.add_funds(loot.get(PSEUDO_ITEM_ID_STAR, 0), CURRENCY_NAME_STAR)

        item_loot: dict[str, int] = filter_item_loot(loot)
        if len(item_loot) > 0:
            ring_id = await get_equipped_ring_id(self.id)
            for item_id, count in item_loot.items():
                await add_to_inventory(self.id, item_id, count, ring_id)

        return

    def add_energy(self, amount: int, ignore_cap: bool = True) -> tuple[int, bool]:
        return self.alter_energy_by(amount, ignore_cap)

    async def add_experience(self, base_amount: int, apply_bonus: bool = True, message_cooldown: Optional[timedelta] = None) -> tuple[int, int]:
        if base_amount < 0:
            raise ValueError(f"Experience amount to add must be positive, found {base_amount:,}")

        if base_amount == 0:
            return 0, 0

        if apply_bonus:
            exp_bonus_percent: int = await compute_user_exp_bonus(self._id)
            bonus_amount: int = int(base_amount * exp_bonus_percent // 100)
            effective_amount: int = int(base_amount + bonus_amount)
        else:
            bonus_amount: int = 0
            effective_amount: int = int(base_amount)

        if message_cooldown is not None:
            self.daily_message_cooldown = self.daily_message_cooldown + message_cooldown

        effective_amount = self.set_current_experience(self.current_experience + effective_amount)
        _log(self._id, f"Gained {effective_amount:,}, Current: {self.current_experience:,} EXP")

        return effective_amount, bonus_amount

    def add_funds(self, amount: int, currency: str = CURRENCY_NAME_GOLD) -> None:
        if amount < 0:
            raise ValueError(f"Funds amount to add must be positive, found {amount:,}")

        if amount > 0:
            if currency == CURRENCY_NAME_ARENA_COIN:
                self._wallet.arena_coins += amount
                self._pvp_altered = True
            elif currency == CURRENCY_NAME_STAR:
                self._wallet.stars += amount
                self._core_altered = True
            else:
                self._wallet.gold += amount
                self._core_altered = True

    async def add_message_experience(self) -> None:
        async with self:
            if self.daily_message_cooldown_elapsed and self.daily_message_count < MESSAGE_EXP_COUNT_LIMIT:
                experience = random.randint(MESSAGE_EXP_RANGE[0], MESSAGE_EXP_RANGE[1])
                experience -= min(self.cultivation.minor, MESSAGE_EXP_RANGE[0])

                self.daily_message_count += 1
                self.daily_message_cooldown = datetime.now() + MESSAGE_EXP_COOLDOWN
                awarded, _ = await self.add_experience(experience)

                if awarded > 0:
                    _log(self.id, f"Chat or command EXP +{awarded:,}", "DEBUG")

    def alter_energy_by(self, amount: int, ignore_cap: bool = False) -> tuple[int, bool]:
        return self.set_energy(self._energy + amount, ignore_cap)

    def as_member(self) -> disnake.Member:
        if self._member is None:
            member: Optional[disnake.Member] = Continent().guild.get_member(self.id)
            if member is None:
                # Shouldn't really happen
                raise ValueError(f"Couldn't locate any member with id {self.id}")

            self._member: disnake.Member = member

        return self._member

    def balance(self, currency: str = CURRENCY_NAME_GOLD) -> int:
        return self.get_funds(currency)

    async def change_realm(self, amount, change_type="promote", guild=None, ignore_oqi=False, maintain_major: bool = True) -> tuple[str, str]:
        content = ""
        embed_content = ""

        author: disnake.Member = self.as_member()
        initial_stage: PlayerCultivationStage = self.cultivation
        initial_rank_cp = initial_stage.displayed_combat_power

        total_energy_given = 0
        log_event(self.id, "breakthrough", f"Started {change_type}, {amount} times", "DEBUG")

        target_stage: PlayerCultivationStage = initial_stage
        from utils.ExpSystem import upgrade_qi_flame, update_role
        if change_type == "demote":
            target_stage: PlayerCultivationStage = initial_stage.advance_by(-amount, maintain_major)

            content = f"{MINUS} **Demoted {author.mention}!**"
            embed_content = f"{MINUS} {author.name} have been demoted to **`{target_stage}`**"

            cp_lost = initial_rank_cp - target_stage.displayed_combat_power
            embed_content += f"\n\n{EXCLAMATION} You lost **`{format_num_abbr1(cp_lost)}` base CP**!"

            log_event(author.id, "breakthrough", f"Got Demoted to {target_stage}")

        elif change_type == "promote":
            effective_count: int = 0
            for i in range(0, amount):
                current_stage: PlayerCultivationStage = target_stage
                target_stage = target_stage.next_stage
                if target_stage is None:
                    target_stage = current_stage
                else:
                    effective_count += 1
                    content = f"{TICK} **Congratulations {author.mention}!**"
                    embed_content = f"{EXCLAMATION} You broke through from **{initial_stage}** to **{target_stage}**"
                    if target_stage.major == current_stage.major:
                        total_energy_given += 30
                        content = f"{TICK} **Congratulations {author.mention}!**"
                        embed_content = f"{EXCLAMATION} You broke through to **{target_stage}**"
                        log_event(author.id, "breakthrough", f"+minor {target_stage}", "DEBUG")
                    else:
                        log_event(author.id, "breakthrough", f"+MAJOR {target_stage}", "DEBUG")
                        if not ignore_oqi and target_stage.major == 12:
                            check = await check_item_in_inv(author.id, "originqi", 1)
                            if not check:
                                log_event(author.id, "breakthrough", f"Failed to breakthrough because of Origin Qi")
                                content = f"{CROSS} Failed to Breakthrough"
                                embed_content = f"{EXCLAMATION} You need Origin Qi to breakthrough to Fight God! It have a very low chances to drop from `/search` and `/beast hunt`"
                                return content, embed_content

                            await remove_from_inventory(author.id, "originqi", 1)
                        total_energy_given += 60

            if effective_count > 1:
                content = f"{TICK} **Successfully promoted {author.mention}!**"
                embed_content = f"{PLUS} {author.name} have continuously broken through `{effective_count}` times, reaching **`{target_stage}`**"

            flame_check, f = await upgrade_qi_flame(author.id, target_stage.major, target_stage.minor)
            if flame_check:
                if f == "new":
                    embed_content += f"\n\n{PLUS} You are now able to condense a flame using Dou Qi!"
                else:
                    embed_content += f"\n\n{PLUS} Your Dou Qi flame evolved to a higher level!"

            if total_energy_given > 0:
                embed_content += f"\n\n{PLUS} You recovered {total_energy_given} energy."

            cp_gained = target_stage.displayed_combat_power - initial_rank_cp
            embed_content += f"\n\n{PLUS} You gained **`{format_num_abbr1(cp_gained)}` base CP**!"
            log_event(author.id, "breakthrough", f"Broke through to {target_stage}")

        self.cultivation = target_stage
        self.add_energy(total_energy_given)

        if guild:
            await update_role(author, guild, target_stage.major)

        old_max_energy = initial_stage.maximum_energy
        new_max_energy = target_stage.maximum_energy
        if old_max_energy != new_max_energy:
            self._core_altered = True
            embed_content += f"\n\n{MINUS}Your max energy set to {new_max_energy}"

        return content, embed_content

    async def get_equipped_items(self):
        equipped, bonuses = await Users.get_or_none(user_id=self.id).values_list("equipped", "bonuses")
        return equipped
    
    def get_stats_dict(self):
        # Just base stats for now (later change to async)
        stats_dict = self.cultivation.base_stats
        stats_dict['Elemental Affinities'] = [] # TODO
        return stats_dict

    async def compute_total_cp(self) -> int:
        major: int = self.cultivation.major
        equipped, bonuses = await Users.get_or_none(user_id=self.id).values_list("equipped", "bonuses")

        base_cp = self.cultivation.displayed_combat_power
        relative_cp_boost: int = 0  # Percent boost
        flat_cp_bonus: int = 0  # Flat bonus

        # Get TempBoost CP bonus
        _, _, temp_boost_cp_boost, _ = await compute_temp_status(self.id)
        relative_cp_boost += temp_boost_cp_boost

        # Get flame CP bonus
        _, flame_cp_boost, _ = await compute_flame_bonus(self.id)
        relative_cp_boost += flame_cp_boost

        pet_cp = await compute_pet_cp(self.id)

        # Get method CP bonus
        method = equipped["method"]
        if method:
            compendium: ItemCompendium = ItemCompendium()
            method_id: str = method[0]
            item: ItemDefinition = compendium.get(method_id)
            if item is not None and isinstance(item, QiMethodManualDefinition):
                method_definition: QiMethodManualDefinition = cast(QiMethodManualDefinition, item)
                relative_cp_boost += method_definition.combat_power_boost

        # Get other CP bonuses tied to user
        relative_cp_boost += bonuses["cp"]

        # Get technique CP bonus
        all_techniques = equipped["techniques"]
        for tech_id in all_techniques:
            cp, tier, name = all_techniques[tech_id]
            increase_cp = ParamsUtils.compute_technique_cp_bonus(int(cp), int(tier), major)
            flat_cp_bonus += increase_cp

        # Final calculation
        total_cp = math.ceil((base_cp + flat_cp_bonus) * (1 + relative_cp_boost / 100))
        total_cp = math.ceil(total_cp + pet_cp)
        return total_cp

    def consume_energy(self, amount: int, force: bool = False) -> bool:
        if amount <= 0:
            return True

        if amount > self._energy:
            if force:
                amount = self._energy
            else:
                return False

        self._energy = max(self._energy - amount, 0)
        self._core_altered = True

        return True

    def demote(self, times: int) -> PlayerCultivationStage:
        if times > 0:
            target_stage: PlayerCultivationStage = self.cultivation
            for i in range(times):
                previous_stage: Optional[PlayerCultivationStage] = target_stage.previous_stage
                if previous_stage is None:
                    break

                target_stage = previous_stage

            self.cultivation = target_stage

        return self.cultivation

    def get_funds(self, currency: str = CURRENCY_NAME_GOLD) -> int:
        if currency == CURRENCY_NAME_GOLD:
            return self._wallet.gold
        elif currency == CURRENCY_NAME_ARENA_COIN:
            return self._wallet.arena_coins
        elif currency == CURRENCY_NAME_STAR:
            return self._wallet.stars
        else:
            return self._wallet.gold

    def promote(self, times: int) -> PlayerCultivationStage:
        if times > 0:
            target_stage: PlayerCultivationStage = self.cultivation
            for i in range(times):
                next_stage: Optional[PlayerCultivationStage] = target_stage.next_stage
                if next_stage is None:
                    break

                target_stage = next_stage

            self.cultivation = target_stage

        return self.cultivation

    def regen_energy(self, amount: int = 1) -> tuple[int, bool]:
        # We don't want to reduce the energy as a result of not ignoring the cap
        if self.energy >= self.maximum_energy:
            return 0, False

        return self.alter_energy_by(amount, False)

    def remove_funds(self, amount: int, currency: str = CURRENCY_NAME_GOLD) -> bool:
        return self.spend_funds(amount, currency)

    def spend_funds(self, amount: int, currency: str = CURRENCY_NAME_GOLD) -> bool:
        if amount < 0:
            raise ValueError(f"Funds amount to spend must be positive, found {amount:,}")

        if amount == 0:
            return True

        if currency == CURRENCY_NAME_ARENA_COIN:
            if self._wallet.arena_coins < amount:
                return False

            self._wallet.arena_coins = max(self._wallet.arena_coins - amount, 0)
            self._pvp_altered = True
        elif currency == CURRENCY_NAME_STAR:
            if self._wallet.stars < amount:
                return False

            self._wallet.stars = max(self._wallet.stars - amount, 0)
            self._core_altered = True
        else:
            if self._wallet.gold < amount:
                return False

            self._wallet.gold = max(self._wallet.gold - amount, 0)
            self._core_altered = True

        return True

    def remove_experience(self, amount: int) -> int:
        if amount < 0:
            raise ValueError(f"Experience amount to remove must be positive, found {amount:,}")

        if amount >= self._current_experience:
            amount = self._current_experience - 1

        effective_amount = self.set_current_experience(max(self._current_experience - amount, 0))

        _log(self.id, f"Lost {effective_amount:,} EXP, Current {self.current_experience} EXP")

        return amount

    def set_current_experience(self, amount: int) -> int:
        if amount < 0:
            raise ValueError(f"Experience amount must be positive, found {amount:,}")

        current_exp: int = int(self._current_experience)
        target_exp: int = amount
        cultivation: PlayerCultivationStage = self._cultivation_stage
        if cultivation.has_experience_cap:
            target_exp = min(target_exp, cultivation.experience_cap)

        if target_exp == current_exp:
            return 0
        else:
            self._current_experience = target_exp
            self._cultivation_altered = True

            effective_amount: int = target_exp - current_exp
            return effective_amount

    def set_energy(self, new_energy: int, ignore_cap: bool = False) -> tuple[int, bool]:
        effective_new_energy: int = new_energy
        if effective_new_energy < 0:
            effective_new_energy = 0
        elif not ignore_cap and effective_new_energy > self.maximum_energy:
            effective_new_energy = self.maximum_energy

        just_reached_max: bool = False
        if self._energy != effective_new_energy:
            old_energy = self._energy
            self._energy = effective_new_energy
            self._core_altered = True
            just_reached_max = old_energy < self.maximum_energy <= effective_new_energy

        return effective_new_energy, just_reached_max

    async def start_cultivating_exp(self) -> tuple[bool, Optional[str]]:
        now: datetime = datetime.now()
        now_epoch_seconds: int = int(mktime(now.timetuple()))

        cooldown: Optional[datetime] = self._cultivation_cooldown
        cooldown_epoch_seconds: int = int(mktime(cooldown.timetuple())) if cooldown is not None else 0

        waiting_time_seconds: int = cooldown_epoch_seconds - now_epoch_seconds
        if cooldown and waiting_time_seconds > 0:
            return False, f"Command under cooldown, try again <t:{cooldown_epoch_seconds}:R>"
        elif not self.consume_energy(1):
            return False, "You don't have enough energy to cultivate"

        self.cultivation_cooldown: datetime = now + timedelta(minutes=1)
        await self.persist()

        return True, None

    async def persist(self):
        if self._core_altered:
            await self.persist_core()

        if self._cultivation_altered:
            await self.persist_cultivation()

        if self._pvp_altered:
            await self.persist_pvp()

    async def persist_all(self):
        await self.persist_core()
        await self.persist_cultivation()
        await self.persist_pvp()

    async def persist_core(self):
        await Users.filter(user_id=self._id).update(energy=self._energy, max_energy=self._cultivation_stage.maximum_energy,
                                                    money=self._wallet.gold, star=self._wallet.stars, money_cooldown=1 if self._claimed_daily else 0)
        self._core_altered: bool = False

    async def persist_cultivation(self):
        cultivate_cd: Optional[datetime] = datetime.utcfromtimestamp(self._cultivation_cooldown.timestamp()) if self._cultivation_cooldown is not None else None
        message_cd: Optional[datetime] = datetime.utcfromtimestamp(self._daily_message_cooldown.timestamp()) if self._daily_message_cooldown is not None else None
        await Cultivation.filter(user_id=self._id).update(major=self._cultivation_stage.major, minor=self._cultivation_stage.minor, current_exp=self._current_experience, total_exp=self.total_experience,
                                                          cultivate_cooldown=cultivate_cd, msg_limit=self.daily_message_count, cooldown=message_cd)
        self._cultivation_altered: bool = False

    async def persist_pvp(self):
        await Pvp.filter(user_id=self._id).update(pvp_coins=self._wallet.arena_coins)
        self._pvp_altered: bool = False


@singleton
class PlayerRoster:
    def __init__(self):
        self._cultivation_stages: list[list[PlayerCultivationStage]] = generate_player_cultivation_stage_matrix()
        self._players: dict[int, Player] = {}

    async def load(self):
        all_users: list[dict[str, Any]] = await Users.all().values()
        all_cultivations: list[dict[str, Any]] = await Cultivation.all().values()
        all_pvp: list[dict[str, Any]] = await Pvp.all().values()
        all_base_inv: list[dict[str, Any]] = await Inventory.all().values()
        all_ring_inv: list[dict[str, Any]] = await RingInventory.all().values()

        user_by_user_id: dict[int, dict[str, Any]] = {item["user_id"]: item for item in all_users}
        pvp_by_user_id: dict[int, dict[str, Any]] = {item["user_id"]: item for item in all_pvp}
        cultivation_by_user_id: dict[int, dict[str, Any]] = {item["user_id"]: item for item in all_cultivations}
        user_ids: list[int] = [user_id for user_id in user_by_user_id.keys()]
        user_ids = sorted(user_ids)

        for user_id in user_ids:
            user_data: dict[str, Any] = user_by_user_id[user_id]
            pvp_data: Optional[dict[str, Any]] = pvp_by_user_id.get(user_id, None)
            cultivation_data: Optional[dict[str, Any]] = cultivation_by_user_id.get(user_id, None)
            base_inv: BaseInventory = BaseInventory()
            compendium: ItemCompendium = ItemCompendium()
            for i in all_base_inv:
                if user_id == i['user_id']:
                    item_def = compendium.get(i["item_id"])

                    if item_def.type == "ring":
                        item = StorageRing(item_def, i["unique_id"])
                        for r in all_ring_inv:
                            if i["unique_id"] == r["ring_id"]:
                                ring_item_def = compendium.get(r["item_id"])
                                r_item = Item(ring_item_def, r["unique_id"], r["count"])
                                item.add(r_item)

                    else:
                        item = Item(item_def, i["unique_id"], i["count"])

                    base_inv.add(item)

            equipped_ring_id: Optional[int] = await get_equipped_ring_id(user_id)
            if equipped_ring_id is not None:
                ring_details = await AllRings.get_or_none(id=equipped_ring_id).values_list("ring", flat=True)
                ring_def = compendium.get(str(ring_details))
                equipped_ring = StorageRing(ring_def, equipped_ring_id)
            else:
                equipped_ring = None

            player_inventory = PlayerInventory(user_id, base_inventory=base_inv, equipped_ring=equipped_ring)

            if cultivation_data is not None:
                major: int = cultivation_data["major"]
                minor: int = cultivation_data["minor"]
                current_exp: int = cultivation_data["current_exp"]
                cultivate_cooldown: Optional[datetime] = cultivation_data["cultivate_cooldown"]
                message_limit: int = cultivation_data["msg_limit"]
                message_cooldown: Optional[datetime] = cultivation_data["cooldown"]
            else:
                major: int = 0
                minor: int = 0
                current_exp: int = 0
                cultivate_cooldown: Optional[datetime] = None
                message_limit: int = 0
                message_cooldown: Optional[datetime] = None

            wallet: PlayerWallet = PlayerWallet(user_id=user_id, gold=user_data["money"], arena_coins=pvp_data["pvp_coins"] if pvp_data is not None else 0, stars=user_data["star"])
            player: Player = Player(roster=self, user_id=user_id, energy=user_data["energy"], wallet=wallet,
                                    cultivation_stage=self._cultivation_stages[major][minor], current_experience=current_exp, cultivation_cooldown=cultivate_cooldown,
                                    daily_message_count=message_limit, daily_message_cooldown=message_cooldown,
                                    claimed_daily=user_data["money_cooldown"] != 0, inventory=player_inventory)
            self._players[user_id] = player

    # ============================================= Special methods =============================================

    def __contains__(self, user_id: Union[str, int]) -> bool:
        player_id: int = self._as_player_id(user_id)
        return player_id in self._players

    def __getitem__(self, user_id: Union[str, int]) -> Optional[Player]:
        return self.get(self._as_player_id(user_id))

    # =============================================== "Real" methods ==============================================

    async def distribute_loot(self, loot_distribution: dict[int, dict[str, int]]) -> None:
        if len(loot_distribution) == 0:
            return

        for player_id, loot in loot_distribution.items():
            player: Optional[Player] = self.get(player_id)
            if player is not None:
                async with player:
                    await player.acquire_loot(loot)

    async def ensure_player(self, user_id: Union[str, int]) -> Player:
        player_id: int = self._as_player_id(user_id)
        player: Optional[Player] = self.get(player_id)
        if player is None:
            player: Player = await self._create_player(player_id)

        return player

    async def find_cultivator_or_warn(self, inter: disnake.CommandInteraction, user_id: int) -> Optional[Player]:
        player: Optional[Player] = self.get(user_id)
        if player is None:
            await inter.response.send_message("You could nod find any information about this cultivator")
            raise ValueError(f"No player row for player {user_id}")

        return player

    def find_player_for(self, inter: Union[disnake.CommandInteraction, disnake.MessageInteraction], member: Optional[disnake.Member] = None):
        user_id: int = inter.author.id if member is None else member.id
        return self.get(user_id)

    def get(self, user_id: Union[int, str]) -> Optional[Player]:
        player_id: int = self._as_player_id(user_id)
        player: Optional[Player] = self._players.get(player_id, None)

        return player

    def list(self) -> list[Player]:
        return list(self._players.values())

    def reset_local_daily_values(self):
        for player in self._players.values():
            player.daily_message_count = 0
            player.claimed_daily = False

    @staticmethod
    def _as_player_id(user_id: Union[int, str]) -> int:
        if isinstance(user_id, str):
            user_id: int = int(user_id)

        return user_id

    async def _create_player(self, user_id: int) -> Player:
        cooldown: datetime = datetime.now()
        player: Player = Player(roster=self, user_id=user_id, energy=0, wallet=PlayerWallet(user_id, 1, 0, 0),
                                cultivation_stage=self._cultivation_stages[0][0], current_experience=0, cultivation_cooldown=cooldown,
                                daily_message_count=0, daily_message_cooldown=cooldown,
                                claimed_daily=False)
        self._players[user_id] = player

        await Users.create(user_id=user_id)
        await Cultivation.create(user_id=user_id, cooldown=cooldown, cultivate_cooldown=cooldown)
        await Alchemy.create(user_id=user_id)
        await Pvp.create(user_id=user_id)
        _log(user_id, f"User {user_id} created")

        return player


class PlayerActionButton(BaseStarfallButton):
    def __init__(self, label: str, custom_id: str, style: disnake.ButtonStyle = disnake.ButtonStyle.primary, row: Optional[int] = None):
        super().__init__(label=label, custom_id=custom_id, style=style, row=row)

    @staticmethod
    def player(inter: disnake.MessageInteraction) -> Player:
        player: Player = PlayerRoster().find_player_for(inter)
        if player is None:
            raise ValueError(f"Could not find the player with id {inter.author.id}")

        return player


class PlayerRosterNotLoadedError(CogNotLoadedError):
    def __init__(self):
        super().__init__()


async def compute_flame_bonus(user_id, only_flame=False):
    exp_bonus, cp_bonus, pill_rate_bonus = 0, 0, 0

    flame_id: str = await Alchemy.get_or_none(user_id=user_id).values_list("flame", flat=True)
    if flame_id and isinstance(flame_id, str) and flame_id != 'conpillflame':
        compendium: ItemCompendium = ItemCompendium()
        item: ItemDefinition = compendium[flame_id]
        if isinstance(item, FlameDefinition):
            flame: FlameDefinition = item
            exp_bonus: float = flame.experience_boost
            cp_bonus: float = flame.combat_power_boost
            pill_rate_bonus: float = flame.refine_bonus

        if only_flame:
            return exp_bonus, cp_bonus, pill_rate_bonus

        equipped_stone = await Users.get_or_none(user_id=user_id).values_list("equipped", flat=True)
        stone = equipped_stone.get("stone", None)
        if stone:
            stone_flame = await RingInventory.filter(ring_id=int(stone)).values_list("item__properties", flat=True)
            if stone_flame:
                stone_bonuses = stone_flame[0]
                exp_bonus += stone_bonuses["xp_boost"] * 0.5
                cp_bonus += stone_bonuses["cp_boost"] * 0.5
                pill_rate_bonus += stone_bonuses["pill_rate_boost"] * 0.5

    return exp_bonus, cp_bonus, pill_rate_bonus


async def compute_pet_cp(user_id):
    pet_details = await Pet.get_or_none(user_id=user_id, main=1).values_list("pet_id", "p_cp", "p_major", "p_minor", "growth_rate")
    if pet_details is None:
        return 0

    pet_name, inherited_cp, pet_major, pet_minor, growth_rate = pet_details
    bestiary: Bestiary = Bestiary()
    definition: PetBeastDefinition = bestiary.get_pet_definition(pet_name)
    return definition.combat_power(BeastCultivationStage(pet_major, pet_minor, definition.rarity), growth_rate, inherited_cp)


async def compute_temp_status(user_id):
    all_data = await Temp.filter(user_id=user_id).values_list("role_id", "item_id", "cp", "exp", "event_cp", "event_exp")
    role_id, item_id, cp, exp, event_cp, event_exp = None, None, 0, 0, 0, 0
    for data in all_data:
        if data[0]:
            role_id = data[0]
        if data[1]:
            item_id = data[1]
        if data[2]:
            cp = data[2]
        if data[3]:
            exp = data[3]
        if data[4]:
            event_cp = data[4]
        if data[5]:
            event_exp = data[5]
    cp = cp + event_cp
    exp = exp + event_exp

    return role_id, item_id, cp, exp


async def compute_user_exp_bonus(user_id: int) -> int:
    user_data = await Users.get_or_none(user_id=user_id).values_list("pill_used", "bonuses")
    pill_used_list, bonuses = user_data
    exp_bonus: int = bonuses["exp"]

    # Get TempBoost EXP bonus
    _, _, _, temp_exp_boost = await compute_temp_status(user_id)
    exp_bonus += temp_exp_boost

    # Get flame EXP bonus
    flame_exp_boost, _, _ = await compute_flame_bonus(user_id)
    exp_bonus += flame_exp_boost

    # Get faction EXP bonus
    try:
        faction_exp_boost = await Factions.get_or_none(user_id=user_id).values_list("multiplier", flat=True)
    except MultipleObjectsReturned:
        faction_exp_boost = 0

    if faction_exp_boost:
        exp_bonus += faction_exp_boost

    return math.floor(exp_bonus)


def _log(user_id: Union[int, str], message: str, level: str = "INFO"):
    log_event(user_id, "roster", message, level)

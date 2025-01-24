from __future__ import annotations
import math
import random
from datetime import datetime, timedelta, timezone
from time import mktime
from typing import Optional, Union, Any, TypeVar, cast
from enum import Enum

from utils.Database import Character
from character.pvp_stats import PvPStats, Element
from tortoise.exceptions import MultipleObjectsReturned
import disnake
from utils import ParamsUtils
from utils.Database import Alchemy, Cultivation, Users, Pvp, RingInventory, Pet, Temp, Factions, Inventory, AllRings
from utils.InventoryUtils import check_item_in_inv, remove_from_inventory, add_to_inventory, get_equipped_ring_id
from utils.LoggingUtils import log_event
from utils.ParamsUtils import CURRENCY_NAME_ARENA_COIN, CURRENCY_NAME_GOLD, CURRENCY_NAME_STAR, format_num_abbr1, mention
from utils.Styles import PLUS, EXCLAMATION, CROSS, TICK, MINUS
from utils.base import CogNotLoadedError, singleton, BaseStarfallButton
from character.inventory import PlayerInventory, BaseInventory, Item, StorageRing
from utils.loot import PSEUDO_ITEM_ID_EXP_FLAT, PSEUDO_ITEM_ID_EXP_RATIO, RelativeExperienceLoot, filter_item_loot, PSEUDO_ITEM_ID_GOLD, PSEUDO_ITEM_ID_ARENA_COIN, PSEUDO_ITEM_ID_STAR, filter_pseudo_item_loot, PSEUDO_ITEM_ID_ENERGY_FLAT, PSEUDO_ITEM_ID_ENERGY_RATIO
from world.bestiary import Bestiary, PetBeastDefinition
from world.continent import Continent
from world.cultivation import PlayerCultivationStage, generate_player_cultivation_stage_matrix, BeastCultivationStage
from world.compendium import ItemCompendium, ItemDefinition, FlameDefinition, QiMethodManualDefinition

MESSAGE_EXP_COUNT_LIMIT: int = 100
MESSAGE_EXP_COOLDOWN: timedelta = timedelta(minutes=1)
MESSAGE_EXP_RANGE: tuple[int, int] = (10, 15)
ENERGY_RECOVERY_RATE_MINUTES: int = 2

class TechniqueType(Enum):
    ATTACK = "Attack"
    DEFENSE = "Defense"
    AGILITY = "Agility"
    FLYING = "Flying"
    SUMMON = "Summon"
    CONTROL = "Control"
    SUPPORT = "Support"

class StatusEffect(Enum):
    BURN = "Burn"
    POISON = "Poison"
    BLEED = "Bleed"
    CONFUSED = "Confused"
    WITHER = "Wither"
    STEALTH = "Stealth"
    STUN = "Stun"
    FREEZE = "Freeze"
    PARALYSIS = "Paralysis"
    ROOT = "Root"
    SLOW = "Slow"

class PlayerRoster:
    """Manages a collection of players"""
    def __init__(self):
        self.players = {}
        
    def add_player(self, player: Player):
        self.players[player._id] = player
        
    def get_player(self, user_id: int) -> Optional[Player]:
        return self.players.get(user_id)
        
    def remove_player(self, user_id: int):
        if user_id in self.players:
            del self.players[user_id]

class Player(Character):
    def __init__(self, roster: R, user_id: int, energy: int, wallet: PlayerWallet,
                 cultivation_stage: PlayerCultivationStage, current_experience: int, 
                 cultivation_cooldown: Optional[datetime] = None,
                 daily_message_count: int = 0, daily_message_cooldown: Optional[datetime] = None,
                 claimed_daily: bool = False, inventory: PlayerInventory = None,
                 pvp_stats: Optional[PvPStats] = None):
        super().__init__()
        self._roster: R = roster
        self._id: int = user_id
        self._energy: int = energy
        self._dou_qi: int = 100  # Mana system
        self._wallet: PlayerWallet = wallet
        self._cultivation_stage: PlayerCultivationStage = cultivation_stage
        self._current_experience: int = int(current_experience)
        self._cultivation_cooldown: Optional[datetime] = datetime.fromtimestamp(cultivation_cooldown.timestamp()) if cultivation_cooldown is not None else None
        self._daily_message_count: int = daily_message_count
        self._daily_message_cooldown: Optional[datetime] = datetime.fromtimestamp(daily_message_cooldown.timestamp()) if daily_message_cooldown is not None else None
        self._claimed_daily: bool = claimed_daily
        self._buffs: dict[str, list[TemporaryBuff]] = {}
        self._status_effects: dict[StatusEffect, int] = {}  # Status effects and their durations
        self._member: Optional[disnake.Member] = None
        self._core_altered: bool = False
        self._cultivation_altered: bool = False
        self._pvp_altered: bool = False
        self._inventory: PlayerInventory = inventory

    @property
    def dou_qi(self) -> int:
        return self._dou_qi

    @property
    def max_dou_qi(self) -> int:
        return self._cultivation_stage.max_dou_qi

    def add_dou_qi(self, amount: int) -> int:
        """Add Dou Qi (mana) to the player"""
        new_amount = min(self._dou_qi + amount, self.max_dou_qi)
        added = new_amount - self._dou_qi
        self._dou_qi = new_amount
        self._core_altered = True
        return added

    def consume_dou_qi(self, amount: int) -> bool:
        """Consume Dou Qi (mana) from the player"""
        if amount > self._dou_qi:
            return False
        self._dou_qi -= amount
        self._core_altered = True
        return True

    def add_status_effect(self, effect: StatusEffect, duration: int):
        """Add or refresh a status effect"""
        self._status_effects[effect] = duration
        self._core_altered = True

    def clear_status_effect(self, effect: StatusEffect):
        """Remove a status effect"""
        if effect in self._status_effects:
            del self._status_effects[effect]
            self._core_altered = True

    def process_status_effects(self):
        """Process status effects at the start of each turn"""
        for effect in list(self._status_effects.keys()):
            self._status_effects[effect] -= 1
            if self._status_effects[effect] <= 0:
                del self._status_effects[effect]
        
        # Apply effect consequences
        if StatusEffect.BURN in self._status_effects:
            self._energy = max(self._energy - 5, 0)
        if StatusEffect.POISON in self._status_effects:
            self._energy = max(self._energy - 3, 0)
        if StatusEffect.BLEED in self._status_effects:
            self._energy = max(self._energy - 2, 0)

        self._core_altered = True

    def get_elemental_multiplier(self, attack_element: Element) -> float:
        """Calculate elemental damage multiplier based on defender's elements"""
        if not self.pvp_stats.elements:
            return 1.0
            
        # TODO: Implement elemental strengths/weaknesses
        return 1.0

    # Rest of the Player class implementation remains the same...
    # [Previous methods like add_energy, add_experience, etc. would be here]

    async def persist(self):
        """Save stats to database"""
        if self._core_altered:
            await self.persist_core()

        if self._cultivation_altered:
            await self.persist_cultivation()

        if self._pvp_altered:
            await self.persist_pvp()

    async def persist_core(self):
        await Users.filter(user_id=self._id).update(
            energy=self._energy,
            dou_qi=self._dou_qi,
            max_energy=self._cultivation_stage.maximum_energy,
            max_dou_qi=self._cultivation_stage.max_dou_qi,
            money=self._wallet.gold,
            star=self._wallet.stars,
            money_cooldown=1 if self._claimed_daily else 0,
            status_effects={e.value: d for e, d in self._status_effects.items()}
        )
        self._core_altered = False

# Rest of the file remains the same...
# [Other classes like PlayerWallet, TemporaryBuff, etc. would be here]

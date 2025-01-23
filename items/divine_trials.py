from typing import TypedDict, Literal
from datetime import datetime
from tortoise import fields
from utils.Database import StarfallModel
from character.player import Player
from adventure.battle import BeastBattle, BattleManager, NO_MAX_ROUND

class TrialRequirement(TypedDict):
    cp_required: int
    weapon_level: int
    cultivation_realm: str

class BossStats(TypedDict):
    name: str
    hp: int
    cp: int
    abilities: list[dict[str, str | int]]

class DivineTrialDefinition(TypedDict):
    name: str
    description: str
    tier: Literal[0, 1, 2]  # 0 for initial divine weapon
    requirements: TrialRequirement
    rewards: dict[str, int]
    boss: BossStats

DIVINE_TRIALS = {
    "divine_weapon": {
        "name": "Divine Weapon Trial",
        "description": "Challenge the Divine Guardian to prove your worth of wielding a divine weapon",
        "tier": 0,
        "requirements": {
            "cp_required": 5_000_000_000_000_000,  # 5Q
            "weapon_level": 0,
            "cultivation_realm": "Ruler"
        },
        "rewards": {
            "weapon_selection_token": 1
        },
        "boss": {
            "name": "Divine Guardian",
            "cp": 7_500_000_000_000,  # 7.5T
         
        }
    },
    
    "tier1_ascension": {
        "name": "Sovereign Trial",
        "description": "Defeat the Sovereign Guardian to ascend your divine weapon to tier 2",
        "tier": 1,
        "requirements": {
            "cp_required": 100_000_000_000_000_000,  # 100Q
            "weapon_level": 5,
            "cultivation_realm": "Ruler"
        },
        "rewards": {
            "divine_essence": 1,
            "ascension_stone": 1
        },
        "boss": {
            "name": "Sovereign Guardian",
    
            "cp": 150_000_000_000_000_000,  # 150Q
        }
    },

    "tier2_ascension": {
        "name": "Emperor's Trial",
        "description": "Challenge the Emperor HolyGuardian to ascend your weapon to its ultimate form",
        "tier": 2,
        "requirements": {
            "cp_required": 500_000_000_000_000_000,  # 500Q
            "weapon_level": 5,
            "cultivation_realm": "Ruler"
        },
        "rewards": {
            "divine_essence": 2,
            "transcendence_stone": 1
        },
        "boss": {
            "name": "Emperor Holy Guardian",
            "cp": 750_000_000_000_000_000,  # 750Q
        }
    }
}

class DivineTrialCompletion(StarfallModel):
    user_id = fields.BigIntField()
    trial_id = fields.CharField(max_length=50)  # Unique identifier for the trial
    completed_at = fields.DatetimeField(default=datetime.now)
    
    class Meta:
        table = "divine_trial_completions"
        unique_together = (("user_id", "trial_id"),)

def can_attempt_trial(player_cp: int, weapon_level: int, cultivation_realm: str, current_time: datetime) -> bool:
    """Check if a player can attempt the divine trial"""
    # Check if current date is within first 7 days of month
    if current_time.day > 7:
        return False
        
    # Check trial requirements
    trial = DIVINE_TRIALS["tier1_ascension"]
    requirements = trial["requirements"]
    
    return (
        player_cp >= requirements["cp_required"] and
        weapon_level >= requirements["weapon_level"] and
        cultivation_realm >= requirements["cultivation_realm"]
    )

def get_active_challenges(trial_id: str) -> list[dict]:
    """Get list of active challenges for the trial"""
    if trial_id not in DIVINE_TRIALS:
        return []
    
    return DIVINE_TRIALS[trial_id]["challenges"]

def check_challenge_completion(challenge: dict, player_stats: dict) -> bool:
    """Check if a player has completed a specific challenge"""
    if challenge["name"] == "Divine Beast Hunt":
        return (
            player_stats["beasts_killed"] >= challenge["requirement"] and
            player_stats["current_hp"] >= player_stats["max_hp"] * 0.8
        )
    elif challenge["name"] == "Pill Refinement Challenge":
        return player_stats["pills_refined"] >= challenge["requirement"]
    elif challenge["name"] == "Cultivation Sprint":
        return player_stats["exp_gained"] >= challenge["requirement"]
    
    return False 

async def has_completed_trial(user_id: int, trial_id: str) -> bool:
    completion = await DivineTrialCompletion.get_or_none(
        user_id=user_id,
        trial_id=trial_id
    )
    return completion is not None

async def mark_trial_completed(user_id: int, trial_id: str) -> None:
    await DivineTrialCompletion.create(
        user_id=user_id,
        trial_id=trial_id
    )

async def start_divine_trial(player: Player, trial_id: str) -> BeastBattle:
    # Check if player has already completed this trial
    if await has_completed_trial(player.id, trial_id):
        raise ValueError("You have already completed this divine trial")
    
    # Get trial boss configuration
    trial_boss = DIVINE_TRIALS[trial_id]["boss"]
    trial_beast = {
        "name": trial_boss["name"],
        "cp": trial_boss["cp"]
    }
        
    # Create the trial battle
    battle = await BattleManager().start_solo_battle(
        player=player,
        beast=trial_beast,
        max_rounds=NO_MAX_ROUND
    )
    
    # When battle ends successfully, mark trial as completed
    if battle.finished and battle.beast_killed:
        await mark_trial_completed(player.id, trial_id)
        
    return battle
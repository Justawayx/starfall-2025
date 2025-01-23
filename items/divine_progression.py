from typing import TypedDict

class WeaponLevel(TypedDict):
    level: int
    name: str
    exp_required: int
    bonus: float  # Multiplier for weapon's base CP

# Tier 1 to Tier 2 Progression
TIER_1_PROGRESSION = {
    1: {
        "level": 1,
        "name": "Divine Resonance",
        "exp_required": 1_500_000, 
        "bonus": 1.2
    },
    2: {
        "level": 2,
        "name": "Divine Awakening",
        "exp_required": 4_500_000, 
        "bonus": 1.5
    },
    3: {
        "level": 3,
        "name": "Divine Enlightenment",
        "exp_required": 9_000_000, 
        "bonus": 2.0
    },
    4: {
        "level": 4,
        "name": "Divine Mastery",
        "exp_required": 15_000_000, 
        "bonus": 2.5
    },
    5: {
        "level": 5,
        "name": "Divine Transcendence",
        "exp_required": 24_000_000, 
        "bonus": 3.0
    }
}

# Tier 2 to Tier 3 Progression
TIER_2_PROGRESSION = {
    1: {
        "level": 1,
        "name": "Sovereign Resonance",
        "exp_required": 27_000_000, 
        "bonus": 1.2
    },
    2: {
        "level": 2,
        "name": "Sovereign Awakening",
        "exp_required": 33_000_000, 
        "bonus": 1.5
    },
    3: {
        "level": 3,
        "name": "Sovereign Enlightenment",
        "exp_required": 42_000_000, 
        "bonus": 2.0
    },
    4: {
        "level": 4,
        "name": "Sovereign Mastery",
        "exp_required": 54_000_000, 
        "bonus": 2.5
    },
    5: {
        "level": 5,
        "name": "Sovereign Transcendence",
        "exp_required": 72_000_000, 
        "bonus": 3.0
    }
}

def calculate_weapon_cp(base_cp: int, current_level: WeaponLevel) -> int:
    """Calculate the total CP of a weapon based on its level progression"""
    return int(base_cp * current_level["bonus"]) 
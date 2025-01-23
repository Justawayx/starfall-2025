from typing import TypedDict, Literal, Optional
from items.divine_trials import has_completed_trial
from character.player import PlayerRoster
from utils.InventoryUtils import remove_from_inventory

class WeaponEffect(TypedDict):
    name: str
    description: str
    cooldown: int
    bonus: float

class DivineWeaponDefinition(TypedDict):
    name: str
    tier: Literal[1, 2, 3]
    base_type: str
    cp: int
    level: int
    exp: int
    evolution_paths: list[str]
    active_effects: list[WeaponEffect]
    passive_effects: list[WeaponEffect]

# Base Divine Weapons (Tier 1)
TIER_1_WEAPONS: dict[str, DivineWeaponDefinition] = {
    "divine_sword": {
        "name": "Divine Sword",
        "tier": 1,
        "base_type": "sword",
        "cp": 5_000_000_000_000_000,
        "evolution_paths": ["sovereign_blade", "blood_saber", "void_blade"]
    },
    "divine_spear": {
        "name": "Divine Spear",
        "tier": 1,
        "base_type": "spear",
        "cp": 5_000_000_000_000_000,
        "evolution_paths": ["beast_hunter_spear", "lightning_spear", "dragon_piercer"]
    },
    "divine_staff": {
        "name": "Divine Staff",
        "tier": 1,
        "base_type": "staff",
        "cp": 5_000_000_000_000_000,
        "evolution_paths": ["mystic_staff", "soul_staff", "cosmic_staff"]
    },
    "divine_shield": {
        "name": "Divine Shield",
        "tier": 1,
        "base_type": "shield",
        "cp": 5_000_000_000_000_000,
        "evolution_paths": ["mountain_shield", "storm_shield", "void_shield"]
    },
    "divine_bow": {
        "name": "Divine Bow",
        "tier": 1,
        "base_type": "bow",
        "cp": 5_000_000_000_000_000,
        "evolution_paths": ["frost_bow", "storm_bow", "shadow_bow"]
    }
}

# Intermediate Forms (Tier 2)
TIER_2_WEAPONS: dict[str, DivineWeaponDefinition] = {
    # Sword paths
    "sovereign_blade": {
        "name": "Sovereign Blade",
        "tier": 2,
        "base_type": "sword",
        "cp": 15_000_000_000_000_000,
        "evolution_paths": ["world_ender", "blood_sovereign"],
        "active_effects": [{
            "name": "Royal Treasury",
            "description": "Convert 50% of your current gold into bonus CP for 1 hour",
            "cooldown": 24,
            "bonus": 50
        }],
        "passive_effects": [{
            "name": "Noble Collection",
            "description": "Gain 0.5% CP for each unique qi method owned",
            "cooldown": 0,
            "bonus": 0.5
        }]
    },

    "blood_saber": {
        "name": "Blood Saber", 
        "tier": 2,
        "base_type": "sword",
        "cp": 15_000_000_000_000_000,
        "evolution_paths": ["blood_sovereign", "shadow_emperor"],
        "active_effects": [{
            "name": "Blood Frenzy",
            "description": "Gain 30% bonus CP for 2 hours",
            "cooldown": 24,
            "bonus": 30
        }],
        "passive_effects": [{
            "name": "Blood Essence",
            "description": "Permanently increase CP by 7%",
            "cooldown": 0,
            "bonus": 7
        }]
    },

    "void_blade": {
        "name": "Void Blade",
        "tier": 2,
        "base_type": "sword",
        "cp": 15_000_000_000_000_000,
        "evolution_paths": ["void_walker", "shadow_emperor"],
        "active_effects": [{
            "name": "Void Strike",
            "description": "Gain 25% bonus CP for 3 hours",
            "cooldown": 24,
            "bonus": 25
        }],
        "passive_effects": [{
            "name": "Void Attunement",
            "description": "Permanently increase CP by 6%",
            "cooldown": 0,
            "bonus": 6
        }]
    },

    # Spear paths
    "beast_hunter_spear": {
        "name": "Beast Hunter Spear",
        "tier": 2,
        "base_type": "spear",
        "cp": 15_000_000_000_000_000,
        "evolution_paths": ["primal_sovereign", "inferno_king"],
        "active_effects": [{
            "name": "Beast Slayer",
            "description": "For 2 hours, gain 5% bonus CP for each unique beast type owned",
            "cooldown": 24,
            "bonus": 5
        }],
        "passive_effects": [{
            "name": "Hunter's Instinct",
            "description": "Each beast in inventory grants 0.2% CP",
            "cooldown": 0,
            "bonus": 0.2
        }]
    },

    "lightning_spear": {
        "name": "Lightning Spear",
        "tier": 2,
        "base_type": "spear",
        "cp": 15_000_000_000_000_000,
        "evolution_paths": ["storm_lord", "inferno_king"],
        "active_effects": [{
            "name": "Lightning Strike",
            "description": "For 1 hour, each active boost effect duration is increased by 30%",
            "cooldown": 24,
            "bonus": 30
        }],
        "passive_effects": [{
            "name": "Thunder Essence",
            "description": "Morning cultivation (8AM-12PM) grants 15% more EXP",
            "cooldown": 0,
            "bonus": 15
        }]
    },

    "dragon_piercer": {
        "name": "Dragon Piercer",
        "tier": 2,
        "base_type": "spear",
        "cp": 15_000_000_000_000_000,
        "evolution_paths": ["primal_sovereign", "storm_lord"],
        "active_effects": [{
            "name": "Dragon's Bane",
            "description": "For 1 hour, gain 100% more EXP from dragon-type beasts",
            "cooldown": 24,
            "bonus": 50
        }],
        "passive_effects": [{
            "name": "Dragon Essence",
            "description": "Each dragon-type beast owned grants 4% CP",
            "cooldown": 0,
            "bonus": 4
        }]
    },

    # Staff paths
    "mystic_staff": {
        "name": "Mystic Staff",
        "tier": 2,
        "base_type": "staff",
        "cp": 12_000_000_000_000_000,
        "evolution_paths": ["ancient_one", "transcendent"],
        "active_effects": [{
            "name": "Alchemical Insight",
            "description": "Double pill refinement success rate for 1 hour",
            "cooldown": 24,
            "bonus": 100
        }],
        "passive_effects": [{
            "name": "Mystic Understanding",
            "description": "Gain 1% CP for each tier 8+ flame owned",
            "cooldown": 0,
            "bonus": 1
        }]
    },

    "soul_staff": {
        "name": "Soul Staff",
        "tier": 2,
        "base_type": "staff",
        "cp": 12_000_000_000_000_000,
        "evolution_paths": ["transcendent", "shadow_emperor"],
        "active_effects": [{
            "name": "Soul Harvest",
            "description": "For 2 hours, each pill consumed grants 5% bonus CP (max 30%)",
            "cooldown": 24,
            "bonus": 10
        }],
        "passive_effects": [{
            "name": "Soul Resonance",
            "description": "Dawn cultivation (4-8AM) grants 15% more EXP",
            "cooldown": 0,
            "bonus": 15
        }]
    },

    "cosmic_staff": {
        "name": "Cosmic Staff",
        "tier": 2,
        "base_type": "staff",
        "cp": 12_000_000_000_000_000,
        "evolution_paths": ["ancient_one", "void_walker"],
        "active_effects": [{
            "name": "Stellar Alignment",
            "description": "Convert current pill refinement bonus into CP boost for 1 hour",
            "cooldown": 24,
            "bonus": 200
        }],
        "passive_effects": [{
            "name": "Cosmic Harmony",
            "description": "Each tier 9+ pill in inventory grants 0.1% CP",
            "cooldown": 0,
            "bonus": 0.1
        }]
    },

    # Shield paths
    "mountain_shield": {
        "name": "Mountain Shield",
        "tier": 2,
        "base_type": "shield",
        "cp": 12_000_000_000_000_000,
        "evolution_paths": ["ancient_one", "storm_lord"],
        "active_effects": [{
            "name": "Mountain's Bounty",
            "description": "Gain CP based on total inventory weight for 2 hours",
            "cooldown": 24,
            "bonus": 0.1
        }],
        "passive_effects": [{
            "name": "Earth's Blessing",
            "description": "Afternoon cultivation (2-6PM) grants 15% more EXP",
            "cooldown": 0,
            "bonus": 15
        }]
    },

    "storm_shield": {
        "name": "Storm Shield",
        "tier": 2,
        "base_type": "shield",
        "cp": 15_000_000_000_000_000,
        "evolution_paths": ["storm_lord", "frost_monarch"],
        "active_effects": [{
            "name": "Storm Barrier",
            "description": "Next 5 pills consumed have double effect duration",
            "cooldown": 24,
            "bonus": 100
        }],
        "passive_effects": [{
            "name": "Lightning Ward",
            "description": "Each active boost effect grants 3% EXP",
            "cooldown": 0,
            "bonus": 3
        }]
    },

    "void_shield": {
        "name": "Void Shield",
        "tier": 2,
        "base_type": "shield",
        "cp": 12_000_000_000_000_000,
        "evolution_paths": ["void_walker", "frost_monarch"],
        "active_effects": [{
            "name": "Void Barrier",
            "description": "Convert current defensive techniques into CP boost for 1 hour",
            "cooldown": 24,
            "bonus": 25
        }],
        "passive_effects": [{
            "name": "Void Protection",
            "description": "Evening cultivation (6-10PM) grants 15% more EXP",
            "cooldown": 0,
            "bonus": 15
        }]
    },

    # Bow paths
    "frost_bow": {
        "name": "Frost Bow",
        "tier": 2,
        "base_type": "bow",
        "cp": 15_000_000_000_000_000,
        "evolution_paths": ["frost_monarch", "void_walker"],
        "active_effects": [{
            "name": "Frost Arrow",
            "description": "Next 3 pills consumed have triple effect duration",
            "cooldown": 24,
            "bonus": 200
        }],
        "passive_effects": [{
            "name": "Winter's Embrace", 
            "description": "Morning cultivation (6-10AM) grants 15% more EXP",
            "cooldown": 0,
            "bonus": 15
        }]
    },

    "storm_bow": {
        "name": "Storm Bow",
        "tier": 2,
        "base_type": "bow",
        "cp": 15_000_000_000_000_000,
        "evolution_paths": ["storm_lord", "frost_monarch"],
        "active_effects": [{
            "name": "Lightning Arrow",
            "description": "For 1 hour, each active boost effect grants additional 5% CP",
            "cooldown": 24,
            "bonus": 5
        }],
        "passive_effects": [{
            "name": "Storm's Fury",
            "description": "Night cultivation (10PM-2AM) grants 15% more CP", 
            "cooldown": 0,
            "bonus": 15
        }]
    },

    "shadow_bow": {
        "name": "Shadow Bow",
        "tier": 2,
        "base_type": "bow",
        "cp": 15_000_000_000_000_000,
        "evolution_paths": ["shadow_emperor", "void_walker"],
        "active_effects": [{
            "name": "Shadow Arrow",
            "description": "Within 1 hour after activating, gain 30% more CP after a PVP win",
            "cooldown": 24,
            "bonus": 30
        }],
        "passive_effects": [{
            "name": "Shadow's Embrace",
            "description": "Dawn cultivation (2-6AM) grants 15% more EXP",
            "cooldown": 0,
            "bonus": 15
        }]
    }
}

# Ultimate Forms (Tier 3)
TIER_3_WEAPONS: dict[str, DivineWeaponDefinition] = {
    "world_ender": {
        "name": "World Ender",
        "tier": 3,
        "base_type": "sword",
        "cp": 50_000_000_000_000_000,
        "evolution_paths": [],
        "active_effects": [
            {
                "name": "World Ending Authority",
                "description": "If World Destroyer is active, leach 0.3% of EXP cultivated from each player until World Destroyer ends",
                "cooldown": 24,
                "bonus": 0.3
            },
            {
                "name": "Reality Fracture",
                "description": "For 30 minutes, cultivation costs are reduced by 75%",
                "cooldown": 24,
                "bonus": 75
            }
        ],
        "passive_effects": [
            {
                "name": "World Destroyer",
                "description": "During a random hour of the day, CP is increased by 250%",
                "cooldown": 0,
                "bonus": 250
            },
            {
                "name": "End Times Approaching",
                "description": "Gain 0.2% permanent bonus CP for each player defeated in PvP (max 50%)",
                "cooldown": 0,
                "bonus": 2
            }
        ]
    },

    "blood_sovereign": {
        "name": "Blood Sovereign",
        "tier": 3,
        "base_type": "sword",
        "cp": 49_000_000_000_000_000,
        "evolution_paths": [],
        "active_effects": [
            {
                "name": "Blood Domain",
                "description": "For 2 hours, each pill refined grants 5% bonus CP",
                "cooldown": 24,
                "bonus": 5
            },
            {
                "name": "Sovereign's Feast",
                "description": "Next 10 pills consumed have 50% stronger effects",
                "cooldown": 24,
                "bonus": 50
            }
        ],
        "passive_effects": [
            {
                "name": "Blood Empowerment",
                "description": "Gain 1% CP for each day of consecutive daily claims",
                "cooldown": 0,
                "bonus": 1
            },
            {
                "name": "Dusk Sovereign",
                "description": "Evening cultivation (6-10PM) grants 35% more EXP",
                "cooldown": 0,
                "bonus": 35
            }
        ]
    },

    "shadow_emperor": {
        "name": "Shadow Emperor",
        "tier": 3,
        "base_type": "sword",
        "cp": 47_000_000_000_000_000,
        "evolution_paths": [],
        "active_effects": [
            {
                "name": "Shadow Realm",
                "description": "Gain CP based on total inventory value for 1 hour",
                "cooldown": 24,
                "bonus": 0.01
            },
            {
                "name": "Emperor's Authority",
                "description": "All active time-based effects pause for 30 minutes",
                "cooldown": 24,
                "bonus": 100
            }
        ],
        "passive_effects": [
            {
                "name": "Shadow Collection",
                "description": "Each unique item type owned grants 0.5% CP",
                "cooldown": 0,
                "bonus": 0.5
            },
            {
                "name": "Midnight Emperor",
                "description": "Gain 50% more CP between midnight and dawn (12-4AM)",
                "cooldown": 0,
                "bonus": 50
            }
        ]
    },

    "void_walker": {
        "name": "Void Walker",
        "tier": 3,
        "base_type": "universal",
        "cp": 46_000_000_000_000_000,
        "evolution_paths": [],
        "active_effects": [
            {
                "name": "Dimensional Harvest",
                "description": "Convert all cultivation EXP gained in the next hour into CP",
                "cooldown": 24,
                "bonus": 100
            },
            {
                "name": "Void Meditation",
                "description": "Pills effects last twice as long if consumed within 2 hours",
                "cooldown": 24,
                "bonus": 200
            }
        ],
        "passive_effects": [
            {
                "name": "Void Collection",
                "description": "Gain 3% CP for each type of resource owned (gold, stars, etc)",
                "cooldown": 0,
                "bonus": 3
            },
            {
                "name": "Eternal Void",
                "description": "Midnight CP cultivation (12AM-3AM) grants 40% more EXP",
                "cooldown": 0,
                "bonus": 40
            }
        ]
    },

    "storm_lord": {
        "name": "Storm Lord",
        "tier": 3,
        "base_type": "universal",
        "cp": 48_000_000_000_000_000,
        "evolution_paths": [],
        "active_effects": [
            {
                "name": "Thunder Domain",
                "description": "For 1 hour, gain CP equal to 2% of your total gold spent",
                "cooldown": 24,
                "bonus": 2
            },
            {
                "name": "Storm Essence",
                "description": "Double the effect of all active CP boosts for 30 minutes",
                "cooldown": 24,
                "bonus": 100
            }
        ],
        "passive_effects": [
            {
                "name": "Lightning-Flame Mastery",
                "description": "Each active flame increases CP by 5%",
                "cooldown": 0,
                "bonus": 5
            },
            {
                "name": "Storm's Blessing",
                "description": "Gain 30% more EXP during peak hours (6-10PM)",
                "cooldown": 0,
                "bonus": 30
            }
        ]
    },

    "ancient_one": {
        "name": "Ancient One",
        "tier": 3,
        "base_type": "universal",
        "cp": 45_000_000_000_000_000,
        "evolution_paths": [],
        "active_effects": [
            {
                "name": "Time Acceleration",
                "description": "Pills and cultivation techniques complete 4x faster for 30 minutes",
                "cooldown": 24,
                "bonus": 400
            },
            {
                "name": "Ancient Wisdom",
                "description": "For 1 hour, gain CP equal to 20% of your total accumulated cultivation EXP",
                "cooldown": 24,
                "bonus": 20
            }
        ],
        "passive_effects": [
            {
                "name": "Technique Mastery",
                "description": "Gain 2% CP for each tier 7+ technique owned",
                "cooldown": 0,
                "bonus": 2
            },
            {
                "name": "Dawn Cultivation",
                "description": "Gain 25% more EXP between 6-9 AM server time",
                "cooldown": 0,
                "bonus": 25
            }
        ]
    },

    "frost_monarch": {
        "name": "Frost Monarch",
        "tier": 3,
        "base_type": "universal",
        "cp": 46_000_000_000_000_000,
        "evolution_paths": [],
        "active_effects": [
            {
                "name": "Frozen Domain",
                "description": "For 1 hour, gain CP equal to 1% of your total stars earned",
                "cooldown": 24,
                "bonus": 1
            },
            {
                "name": "Winter's Embrace",
                "description": "During the winter season, gain 100% more CP, otherwise 10%",
                "cooldown": 24,
                "bonus": 100
            }
        ],
        "passive_effects": [
            {
                "name": "Frost Mastery",
                "description": "Each unique qi method owned increases CP by 2%",
                "cooldown": 0,
                "bonus": 2
            },
            {
                "name": "Eternal Winter",
                "description": "Night cultivation (10PM-2AM) grants 35% more EXP",
                "cooldown": 0,
                "bonus": 35
            }
        ]
    },

    "inferno_king": {
        "name": "Inferno King",
        "tier": 3,
        "base_type": "universal",
        "cp": 48_000_000_000_000_000,
        "evolution_paths": [],
        "active_effects": [
            {
                "name": "Infernal Realm",
                "description": "Convert flames into CP boost for 2 hours",
                "cooldown": 24,
                "bonus": 100
            },
            {
                "name": "Phoenix Rebirth",
                "description": "Reset all daily cooldowns (except weapon abilities)",
                "cooldown": 24,
                "bonus": 100
            }
        ],
        "passive_effects": [
            {
                "name": "Flame Emperor",
                "description": "Each heavenly flame tier grants 1% CP (max 30%)",
                "cooldown": 0,
                "bonus": 1
            },
            {
                "name": "Solar Peak",
                "description": "Midday cultivation (11AM-3PM) grants 40% more EXP",
                "cooldown": 0,
                "bonus": 40
            }
        ]
    },

    "transcendent": {
        "name": "Transcendent",
        "tier": 3,
        "base_type": "universal",
        "cp": 45_000_000_000_000_000,
        "evolution_paths": [],
        "active_effects": [
            {
                "name": "Transcendent Realm",
                "description": "For 1 hour, gain 1CP based on your highest achieved cultivation",
                "cooldown": 24,
                "bonus": 10
            },
            {
                "name": "Soul Convergence",
                "description": "Triple pill refinement success rate for 30 minutes",
                "cooldown": 24,
                "bonus": 300
            }
        ],
        "passive_effects": [
            {
                "name": "Technique Transcendence",
                "description": "Each Tier 8+ technique grants 4% CP",
                "cooldown": 0,
                "bonus": 4
            },
            {
                "name": "Eternal Wisdom",
                "description": "Gain bonus CP based on account age (1% per month, max 24%)",
                "cooldown": 0,
                "bonus": 1
            }
        ]
    },

    "primal_sovereign": {
        "name": "Primal Sovereign",
        "tier": 3,
        "base_type": "spear",
        "cp": 48_000_000_000_000_000,
        "evolution_paths": [],
        "active_effects": [
            {
                "name": "Primal Domain",
                "description": "For 2 hours, gain CP equal to 100% of your total beast CP",
                "cooldown": 24,
                "bonus": 100
            },
            {
                "name": "Beast Emperor's Authority",
                "description": "For 1 hour, double EXP gained from all beast-related sources",
                "cooldown": 24,
                "bonus": 100
            }
        ],
        "passive_effects": [
            {
                "name": "Sovereign's Menagerie",
                "description": "Each unique beast type owned increases CP by 4%",
                "cooldown": 0,
                "bonus": 4
            },
            {
                "name": "Primal Awakening",
                "description": "Eggs have a 10% higher chance to hatch Exotic beasts",
                "cooldown": 0,
                "bonus": 10
            }
        ]
    }
}

def get_weapon_definition(weapon_id: str) -> Optional[DivineWeaponDefinition]:
    """Get the definition of a divine weapon by its ID"""
    return (TIER_1_WEAPONS.get(weapon_id) or 
            TIER_2_WEAPONS.get(weapon_id) or 
            TIER_3_WEAPONS.get(weapon_id))

async def ascend_divine_weapon(player_id: int, current_weapon_id: str, target_weapon_id: str) -> bool:
    """
    Ascend a divine weapon to its next evolution
    Returns True if successful, False otherwise
    """
    current_weapon = get_weapon_definition(current_weapon_id)
    target_weapon = get_weapon_definition(target_weapon_id)
    
    if not current_weapon or not target_weapon:
        raise ValueError("Invalid weapon IDs provided")
        
    # Check if target weapon is a valid evolution path
    if target_weapon_id not in current_weapon.get("evolution_paths", []):
        raise ValueError("Invalid evolution path")
    
    # Check if player has completed required trials
    if not await has_completed_trial(player_id, f"trial_{target_weapon_id}"):
        raise ValueError("Required trial not completed")
        
    # Get player's current weapon data
    async with PlayerRoster().get(player_id) as player:
        current_cp = player.divine_weapon.get("cp", current_weapon["cp"])
        current_base = player.divine_weapon.get("base_type", current_weapon["base_type"])
        current_effects = player.divine_weapon.get("effects", [])
        
        # Remove trial drops from inventory
        await remove_from_inventory(player_id, f"trial_{target_weapon_id}_drop", 1)
        
        # Create new weapon data maintaining CP and base type
        new_weapon_data = {
            "id": target_weapon_id,
            "name": target_weapon["name"],
            "tier": target_weapon["tier"],
            "base_type": current_base,
            "cp": current_cp,
            "active_effects": target_weapon.get("active_effects", []),
            "passive_effects": target_weapon.get("passive_effects", [])
        }
        
        # Merge previous weapon's effects with new ones
        if current_effects:
            new_weapon_data["effects"] = current_effects + new_weapon_data.get("effects", [])
            
        # Update player's divine weapon
        player.divine_weapon = new_weapon_data
        
    return True

async def evolve_weapon(player, current_weapon_id, chosen_evolution_id):
    try:
        success = await ascend_divine_weapon(player.id, current_weapon_id, chosen_evolution_id)
        if success:
            await player.send_message(f"Successfully ascended your weapon to {chosen_evolution_id}!")
        else:
            await player.send_message("Failed to ascend weapon")
    except ValueError as e:
        await player.send_message(str(e))
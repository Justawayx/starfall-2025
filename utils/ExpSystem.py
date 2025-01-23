import random

import disnake

from utils.Database import Alchemy, AllItems
from utils.LoggingUtils import log_event
from utils.ParamsUtils import ROLE_IDS
from world.cultivation import PlayerCultivationStage

# =====================================
# ExpSystem specific params
# =====================================
BREAKTHROUGH_ROLE = 1010445866483601458
MAX_MESSAGE_LIMIT = 50
REF_MEAT_MULT_BELOW = [1.0, 0.5, 0.16666667, 0.04166667, 0.00833333, 0.00138889, 0.00019841, 2.681e-05, 3.44e-06, 4.351270174e-07]
MEAT_EXP_REFERENCE = [10, 100, 1000, 10_000, 100_000, 1_000_000, 10_000_000, 100_000_000, 1_000_000_000, 10_000_000_000]


def calculate_meat_exp(pet_rank, meat_rank, ref_exp):
    meat_exp = ref_exp
    if pet_rank < meat_rank:
        meat_exp = ref_exp * REF_MEAT_MULT_BELOW[meat_rank - pet_rank]
    return round(meat_exp)


def calculate_egg_exp(egg_tier) -> int:
    ref_exp = MEAT_EXP_REFERENCE[egg_tier - 1]
    egg_exp = calculate_meat_exp(egg_tier, egg_tier, ref_exp)
    egg_exp = round(egg_exp * 8)
    return egg_exp


def calculate_hunt_exp(pet_rank, beast_rank):
    ref_exp = MEAT_EXP_REFERENCE[beast_rank - 1]
    hunt_exp = calculate_meat_exp(pet_rank, beast_rank, ref_exp)
    ran_percent = random.uniform(0.05, 0.10)
    hunt_exp = round(hunt_exp * ran_percent)
    return hunt_exp


def get_max_exp(major, minor):
    cultivation: PlayerCultivationStage = PlayerCultivationStage(major, minor)
    required_exp = cultivation.breakthrough_experience
    max_exp = required_exp * (1 + (50 / 100))
    return max_exp, required_exp


async def update_role(member: disnake.Member, guild: disnake.Guild, major: int):
    role = guild.get_role(ROLE_IDS[major])
    if role:
        role_id_list = [role.id for role in member.roles]

        for role_id in ROLE_IDS:
            if role_id in role_id_list and role_id != role.id:
                role_to_remove = guild.get_role(role_id)
                await member.remove_roles(role_to_remove)
                log_event(member.id, "breakthrough", f"Removed {role_to_remove}")

        if role.id not in role_id_list:
            await member.add_roles(role)
            log_event(member.id, "breakthrough", f"Added {role}")


async def upgrade_qi_flame(user_id, major, minor):
    old_flame_id = await Alchemy.get_or_none(user_id=user_id).values_list("flame", flat=True)
    if old_flame_id is None:
        old_flame_id = "qiflame_none"
    if old_flame_id.split("_")[0] == "qiflame":
        flames = await AllItems.filter(type="qi_flame").values_list("id", "tier", "properties")

        new_flame_id = old_flame_id
        for flame in sorted(flames, key=lambda x: int(x[1]), reverse=True):  # Sort by flame tier, reversed
            properties = flame[2]
            flame_id = flame[0]
            r_major = properties["major"]
            r_minor = properties["minor"]
            if major >= r_major and minor >= r_minor:
                new_flame_id = flame_id
                break

        if new_flame_id != old_flame_id:
            await Alchemy.filter(user_id=user_id).update(flame=new_flame_id)
            log_event(user_id, "breakthrough", f"Upgraded flame to {new_flame_id}")
            if old_flame_id is None:
                return True, "new"
            return True, "upgrade"

    return False, None


def compare_realms(major, minor, new_major, new_minor, compare="high"):
    if compare == "high":
        if major == new_major:
            if minor > new_minor:
                return False
        elif major > new_major:
            return False

    elif compare == "low":
        if major < new_major:
            return False
        elif major == new_major:
            if minor < new_minor:
                return False

    return True

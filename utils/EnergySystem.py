from tortoise.expressions import F
from utils.Database import Users


# =====================================
# EnergySystem specific params
# =====================================

# Returns base energy cap for given major, minor
def get_base_max_energy(major, minor):
    base = 60
    max_energy = base + (major * 15)
    if major == 11:  # Fight Saint
        max_energy += (minor // 3) * 10
    elif major == 12:  # Fight God
        max_energy = 330
    elif major == 13:
        max_energy = 330
    elif major == 14:
        max_energy = 350

    return max_energy


async def get_max_energy(user_id):
    max_energy = await Users.get_or_none(user_id=user_id).values_list("max_energy", flat=True)
    return max_energy


async def update_max_energy(user_id, new_max_energy):
    await Users.filter(user_id=user_id).update(max_energy=new_max_energy)


async def increase_max_energy(user_id, amount):
    await Users.filter(user_id=user_id).update(max_energy=F("max_energy") + amount)


async def show_energy(user_id) -> tuple[str, int]:
    user_data = await Users.get_or_none(user_id=user_id).values_list("energy", "max_energy")
    energy, max_energy = user_data

    if max_energy > energy:
        time_to_full = (max_energy - energy) * 2
    else:
        time_to_full = 0

    energy_str = f"Energy : `{energy}`/{max_energy}"
    if time_to_full > 0:
        energy_str += f"\nTime till full: {time_to_full} minute(s)"

    return energy_str, energy

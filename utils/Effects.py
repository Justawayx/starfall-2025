from utils.Database import Users
from utils.LoggingUtils import log_event
    
    
async def equip_technique(user_id: int, item_id: str, info: list, remove: str = None):
    equipped = await Users.get_or_none(user_id=user_id).values_list("equipped", flat=True)

    if remove:
        if remove in equipped["techniques"].keys():
            equipped["techniques"].pop(remove)

    equipped["techniques"][item_id] = info

    await Users.filter(user_id=user_id).update(equipped=equipped)
    log_event(user_id, "technique", f"Equipped {item_id}, Removed {remove} (extra info: {info})")


async def equip_qi_method(user_id: int, info: list):
    equipped = await Users.get_or_none(user_id=user_id).values_list("equipped", flat=True)
    equipped["method"] = info

    await Users.filter(user_id=user_id).update(equipped=equipped)
    log_event(user_id, "qi_method", f"Equipped {info}")

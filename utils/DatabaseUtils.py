# =====================================
# DatabaseUtils.py
# =====================================
# Contains helper functions for getting info from the database
from utils.Database import Crafted, Users, AllItems, Cultivation, Alchemy
from utils.LoggingUtils import log_event

MARKET_TIERS: dict[int, dict[str, int]] = {
    0: {"listing_tax": 5, "sell_tax": 10, "buy_tax": 5, "item_limit": 3, "user_tier": 1},
    30_000: {"listing_tax": 4, "sell_tax": 8, "buy_tax": 4, "item_limit": 5, "user_tier": 2},
    800_000: {"listing_tax": 3, "sell_tax": 6, "buy_tax": 3, "item_limit": 7, "user_tier": 3},
    26_000_000: {"listing_tax": 2, "sell_tax": 4, "buy_tax": 2, "item_limit": 9, "user_tier": 4},
    60_000_000: {"listing_tax": 0, "sell_tax": 2, "buy_tax": 0, "item_limit": 15, "user_tier": 5}
}


async def add_permanent_boost(author_id: int, cp: int = 0, exp: int = 0):
    bonuses = await Users.get_or_none(user_id=author_id).values_list("bonuses", flat=True)

    bonuses["cp"] += cp
    bonuses["exp"] += exp

    await Users.filter(user_id=author_id).update(bonuses=bonuses)
    log_event(author_id, "effects", f"Gained {cp}% CP and {exp}% EXP")


async def remove_permanent_boost(author_id: int, cp: int = 0, exp: int = 0):
    bonuses = await Users.get_or_none(user_id=author_id).values_list("bonuses", flat=True)

    bonuses["cp"] -= cp
    bonuses["exp"] -= exp

    await Users.filter(user_id=author_id).update(bonuses=bonuses)
    log_event(author_id, "effects", f"Lost {cp}% CP and {exp}% EXP")


async def check_for_great_ruler(user_id, top_3: list = None):
    if not top_3:
        top_3 = await Cultivation.filter(major__gte=1).order_by("-major", "-minor", "-current_exp").values_list("user_id")
    for data in top_3[:3]:
        if user_id == int(data[0]):
            return "The Great Ruler"

    return None


async def compute_cauldron_bonus(user_id):
    user_data = await Alchemy.get_or_none(user_id=user_id).values_list("cauldron", flat=True)

    if user_data:
        cauldron = await Crafted.get_or_none(id=user_data).values_list("stats", flat=True)

        if cauldron:
            alchemy_cdr = cauldron["alchemy_cdr"]
            refine_bonus_per_tier_above = cauldron["refine_bonus_per_tier_above"]

            return alchemy_cdr, refine_bonus_per_tier_above

    return 0, 0


async def compute_pill_bonus(user_id: int, battle: int = 0, refine_pill: bool = False, flame_remove: bool = False, beast_l_remove: bool = False):
    all_pills = await AllItems.filter(type="pill").values_list("id", "name", "properties")

    user_data = await Cultivation.get_or_none(user_id=user_id).values_list("user__pill_used", "user__bonuses", "user__battle_boost", "major", "minor")
    pill_used_list, bonuses, battle_boost, major, minor = user_data
    if battle_boost is None:
        battle_boost = [0, 0]
    pill_refine, flame_swallow, b_boost, beast_l = 0, 0, battle_boost[0], None

    for pill in all_pills:
        pill_id, pill_name, properties = pill

        if pill_id in pill_used_list:

            pill_effects = properties["effects"]
            refine_effect = pill_effects.get("PILL_REFINE")
            flame_effect = pill_effects.get("FLAME_SWALLOW")
            beast_lure_eff = pill_effects.get("BEAST_LURE")

            consumed = False

            if refine_effect:
                pill_refine += refine_effect
                if refine_pill is True:
                    pill_used_list.remove(pill_id)
                    consumed = True

            if flame_effect:
                if "icypill" in pill_used_list and "pathpill" in pill_used_list:
                    flame_swallow += 25
                    if flame_remove is True:
                        pill_used_list.remove("icypill")
                        pill_used_list.remove("pathpill")
                else:
                    flame_swallow += flame_effect

                    if pill_id != "bloodlotuspill":
                        if flame_remove is True:
                            pill_used_list.remove(pill_id)
                consumed = True

            if beast_lure_eff:
                if beast_l is None:
                    beast_l = beast_lure_eff
                    if beast_l_remove is True:
                        pill_used_list.remove(pill_id)
                    consumed = True

            if consumed is True:
                await Users.filter(user_id=user_id).update(pill_used=pill_used_list)

    if battle > 0:
        battle_boost[1] -= battle
        if battle_boost[1] <= 0:
            battle_boost = [0, 0]

        await Users.filter(user_id=user_id).update(battle_boost=battle_boost)

    return pill_refine, flame_swallow, b_boost, beast_l


async def compute_market_userinfo(user_id):
    points = await Users.get_or_none(user_id=user_id).values_list("market_points", flat=True)
    sell_tax = 0
    buy_tax = 0
    item_limit = 0
    listing_tax = 0
    user_tier = 0
    for tier in MARKET_TIERS.keys():
        if int(points) >= tier:
            sell_tax = MARKET_TIERS[tier]["sell_tax"]
            buy_tax = MARKET_TIERS[tier]["buy_tax"]
            item_limit = MARKET_TIERS[tier]["item_limit"]
            listing_tax = MARKET_TIERS[tier]["listing_tax"]
            user_tier = MARKET_TIERS[tier]["user_tier"]

    return listing_tax, sell_tax, buy_tax, item_limit, int(points), user_tier

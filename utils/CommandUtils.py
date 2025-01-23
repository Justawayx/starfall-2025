import random
from datetime import timedelta
from time import time

import disnake
from tortoise.expressions import F

from utils.Database import GuildOptions, Inventory, Market, RingInventory, Temp, Crafted, Users
from utils.InventoryUtils import ITEM_TYPE_ORIGIN_QI, add_to_inventory, check_item_everywhere, convert_id
from utils.LoggingUtils import log_event
from utils.ParamsUtils import PATREON_ROLES

MAX_CHOICE_ITEMS = 25

ORIGIN_QI_LIFESPAN = timedelta(hours=72)
ORIGIN_QI_BASE_CHANCE_DENOMINATOR: int = 10000
ORIGIN_QI_MIN_CHANCE_DENOMINATOR: int = 100
ORIGIN_QI_COUNTER_DENOMINATOR_VALUE: int = 400

MARKET_POINTS_PERCENT_GIVEN = 1

class VoteLinkButton(disnake.ui.Button):
    def __init__(self):
        super().__init__(label="Vote", style=disnake.ButtonStyle.link, url="https://top.gg/servers/352517656814813185/vote")


class PatreonLinkButton(disnake.ui.Button):
    def __init__(self):
        super().__init__(label="Patreon", style=disnake.ButtonStyle.link, url="https://www.patreon.com/fspavilion")


async def give_patron_role_bonus(member):
    role_bonus_dict = None
    role_id_list = [r.id for r in member.roles]
    for role_id in sorted(list(PATREON_ROLES.keys()), reverse=True):
        if role_id in role_id_list:
            role_bonus_dict = PATREON_ROLES[role_id]
            break

    return role_bonus_dict


async def add_market_points(user_id, points):
    await Users.filter(user_id=user_id).update(market_points=F("market_points") + points)
    log_event(user_id, "market", f"Gained {points} market points")


async def add_market_points_for_sale(user_id, sale_price):
    points = round((MARKET_POINTS_PERCENT_GIVEN / 100) * sale_price)
    await add_market_points(user_id, points)


async def remove_points(user_id, points):
    await Users.filter(user_id=user_id).update(market_points=F("market_points") - points)


async def destroy_crafted_item(item_id: str) -> bool:
    item_code, unique_id = convert_id(item_id)
    if unique_id:
        ret = await Crafted.filter(id=unique_id, item_id=item_code).delete()

        return ret > 0

    return False


async def drop_origin_qi(guild: disnake.Guild, user_id):
    qi_counter = await GuildOptions.get_or_none(name="qi_counter").values_list("value", flat=True)
    if qi_counter is None:
        await GuildOptions.create(name="qi_counter", value=1)
        qi_counter = 1

    qi_counter = int(qi_counter)

    qi_chance = ORIGIN_QI_BASE_CHANCE_DENOMINATOR
    qi_chance -= qi_counter * ORIGIN_QI_COUNTER_DENOMINATOR_VALUE
    if qi_chance < ORIGIN_QI_MIN_CHANCE_DENOMINATOR:
        qi_chance = ORIGIN_QI_MIN_CHANCE_DENOMINATOR

    chance = random.randint(1, qi_chance)

    if chance == 69:
        print("ORIGIN QIIIIIIII")
        all_inv_check = await check_item_everywhere(ITEM_TYPE_ORIGIN_QI)
        if all_inv_check is True:
            await add_to_inventory(user_id, ITEM_TYPE_ORIGIN_QI, 1)
            await add_temp_item(user_id, ITEM_TYPE_ORIGIN_QI, ORIGIN_QI_LIFESPAN)
            await announce_in_channel(user_id, guild, ORIGIN_QI_LIFESPAN.total_seconds() / 60, item_id=ITEM_TYPE_ORIGIN_QI, text=f"Congratulations! You found Origin Qi")
            user = await guild.getch_member(int(user_id))
            if user:
                await user.send("Congratulations! You found Origin Qi")
            log_event(user_id, ITEM_TYPE_ORIGIN_QI, f"Gave origin qi for 3 days (chance = 1/{qi_chance}, days = {qi_counter})")

        await GuildOptions.filter(name="qi_counter").update(value=0)


async def add_temp_item(user_id, item_id, duration: timedelta):
    till = round(time() + duration.total_seconds())
    check = await Temp.get_or_none(user_id=user_id, item_id=item_id)
    if check:
        await Temp.filter(user_id=user_id, item_id=item_id).update(till=till)
    else:
        await Temp.create(user_id=user_id, item_id=item_id, till=till)

    log_event(user_id, "temp", f"Added {item_id} item for {duration.total_seconds() / 60} minutes")


async def unregister_item_expiration(user_id, item_id) -> int:
    existing_entry = await Temp.get_or_none(user_id=user_id, item_id=item_id)
    if existing_entry is None:
        return -1

    deleted = await Temp.filter(user_id=user_id, item_id=item_id).delete() > 0
    if deleted:
        # deleted should always be true, unless there was a concurrent command
        return round(existing_entry.till / 60)

    return -1


async def add_temp_role(user_id, role_id, duration):
    till = round(time() + (duration * 60))
    check = await Temp.get_or_none(user_id=user_id, role_id=role_id)
    if check:
        await Temp.filter(user_id=user_id, role_id=role_id).update(till=till)
    else:
        await Temp.create(user_id=user_id, role_id=role_id, till=till)

    log_event(user_id, "temp", f"Added {role_id} role for {duration} minutes")


async def add_temp_cp(user_id, cp_percent, duration):
    till = round(time() + (duration * 60))

    await Temp.create(user_id=user_id, cp=cp_percent, till=till)
    log_event(user_id, "temp", f"Boosted {cp_percent}% CP for {duration} minutes")

    return f"Gained {cp_percent}% CP boost For {duration} minutes"


async def add_temp_exp(user_id, exp_percent, duration):
    till = round(time() + (duration * 60))

    await Temp.create(user_id=user_id, exp=exp_percent, till=till)
    log_event(user_id, "temp", f"Boosted {exp_percent}% EXP for {duration} minutes")

    return f"Gained {exp_percent}% EXP boost for {duration} minutes"


async def announce_in_channel(user_id, guild, duration, item_id=None, role_id=None, text=None):
    till = round(time() + (duration * 60))
    item_str = f"\n\n{item_id} will be removed <t:{int(till)}:R> (approx) from inventory"
    role_str = f"\n\n<@&{role_id}> will be removed <t:{int(till)}:R> (approx)"

    embed = disnake.Embed(
        description="",
        color=disnake.Color(0x2e3135)
    )
    if text:
        embed.description += text
    if item_id:
        embed.description += item_str
    if role_id:
        embed.description += role_str

    try:
        # channel = guild.get_channel(941630078452899881)
        channel = guild.get_channel(1010458217362509894)
    except:
        channel = guild.get_channel(998104630443651082)
    await channel.send(content=f"<@{user_id}>", embed=embed)


async def check_for_temp(bot):
    muted_users = await Temp.all().values_list("user_id", "role_id", "item_id", "till", "event_cp", "event_exp", "cp", "exp")
    for user_id, role_id, item_id, till, event_cp, event_exp, cp, exp in muted_users:
        if time() >= int(till):
            if role_id:
                guild: disnake.Guild = bot.get_guild(bot.main_guild)
                if guild:
                    member: disnake.Member = await guild.getch_member(user_id)
                    if member:
                        role = guild.get_role(int(role_id))
                        await remove_role(member, role)

            if item_id:
                if item_id == ITEM_TYPE_ORIGIN_QI:
                    await Inventory.filter(item_id=item_id).delete()
                    await RingInventory.filter(item_id=item_id).delete()
                    await Market.filter(item_id=item_id).delete()
                    log_event(user_id, "temp", f"Removed {item_id} from everywhere")

            await Temp.filter(user_id=user_id, role_id=role_id, item_id=item_id, event_cp=event_cp, event_exp=event_exp, cp=cp, exp=exp, till=till).delete()
            log_event(user_id, "temp", f"Removed temp effect {role_id}, {item_id}, {till}, {event_cp}, {event_exp}, {cp}, {exp}")


async def remove_role(member: disnake.Member, role):
    if role in member.roles:
        await member.remove_roles(role)
        log_event(member.id, "user", f"Removed {role.name} role")


async def add_role(member: disnake.Member, role):
    if role not in member.roles:
        await member.add_roles(role)
        log_event(member.id, "user", f"Added {role.name} role")

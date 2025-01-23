import random
from time import time
from typing import Optional

import disnake
from disnake.ext import commands

from character.player import PlayerRoster, compute_flame_bonus
from utils import DatabaseUtils
from utils.CommandUtils import drop_origin_qi
from utils.Database import Alchemy, AllItems, Crafted, Users
from utils.Embeds import BasicEmbeds
from utils.InventoryUtils import ConfirmDelete, check_inv_weight, check_item_in_inv, give_combined_inv, add_to_inventory, get_equipped_ring_id, remove_from_inventory, mass_check_items, give_custom_ring_inv
from utils.LoggingUtils import log_event
from utils.ParamsUtils import format_num_simple
from utils.Styles import TICK, PLUS, ITEM_EMOJIS

# =====================================
# Alchemy specific params
# =====================================

HERBS_IDS = ["cherb", "rherb", "uherb", "lherb", "mherb"]

SEARCH_CHANCES = {0: [97.5, 2.5, 0.0, 0.0, 0.0],
                  1: [93.0, 5.0, 1.5, 0.5, 0.0],
                  2: [88.5, 7.5, 3.0, 1.0, 0.0],
                  3: [84.0, 10.0, 4.5, 1.5, 0.0],
                  4: [79.5, 12.5, 6.0, 2.0, 0.0],
                  5: [75.0, 15.0, 7.5, 2.5, 0.0],
                  6: [70.3, 17.5, 9.0, 3.0, 0.2],
                  7: [65.6, 20.0, 10.5, 3.5, 0.4],
                  8: [60.9, 22.5, 12.0, 4.0, 0.6],
                  9: [56.2, 25.0, 13.5, 4.5, 0.8],
                  10: [34.50, 34.00, 20.00, 10.00, 1.50]
                  }

NUMBER_OF_DROPS = {
    0: {"min": 2, "max": 3},
    1: {"min": 3, "max": 5},
    2: {"min": 4, "max": 6},
    3: {"min": 5, "max": 6},
    4: {"min": 7, "max": 9},
    5: {"min": 10, "max": 15},
    6: {"min": 10, "max": 20},
    7: {"min": 20, "max": 30},
    8: {"min": 30, "max": 50},
    9: {"min": 50, "max": 100},
    10: {"min": 100, "max": 100}
}

PILL_COOLDOWN = {
    1: 1 * 60,
    2: 2 * 60,
    3: 4 * 60,
    4: 8 * 60,
    5: 15 * 60,
    6: 30 * 60,
    7: 1 * 60 * 60,
    8: 2 * 60 * 60,
    9: 4 * 60 * 60,
    10: 8 * 60 * 60
}


def pill_refine_check(pill_chance, pill_tier, user_tier, next_tier_chance, increase, pill_pity=0, cauldron_bonus=0) -> (bool, int):
    tier_diff = pill_tier - user_tier

    if tier_diff <= 0:
        base_chance = pill_chance + abs(tier_diff * 20) + (0.5 * cauldron_bonus)
    elif tier_diff == 1:
        base_chance = next_tier_chance + (10 * pill_pity) + cauldron_bonus  # 5% or 40%
    elif tier_diff == 2:
        base_chance = 1 + cauldron_bonus  # 1% + cauldron
    else:
        base_chance = 0 + cauldron_bonus

    chance = base_chance + (increase if tier_diff <= 0 else int((0.5 ** (tier_diff - 1)) * increase))  # Units are percentages

    if chance > 100:
        return True, 100
    elif chance < 0:
        return False, 0

    number = random.randint(1, 100)
    return number <= chance, chance


def calculate_chances(user_tier) -> list[str]:
    cherb_chance = SEARCH_CHANCES[user_tier][0]
    rherb_chance = SEARCH_CHANCES[user_tier][1] + cherb_chance
    uherb_chance = SEARCH_CHANCES[user_tier][2] + rherb_chance
    lherb_chance = SEARCH_CHANCES[user_tier][3] + uherb_chance
    mherb_chance = SEARCH_CHANCES[user_tier][4] + lherb_chance
    other_chance = 100

    max_drop = NUMBER_OF_DROPS[user_tier]["max"]
    min_drop = NUMBER_OF_DROPS[user_tier]["min"]

    drop_amount = random.randint(min_drop, max_drop)
    found_ids: list[str] = []

    for i in range(drop_amount):
        chance = random.random() * 100
        if chance <= cherb_chance:
            found_ids.append("cherb")

        elif chance <= rherb_chance:
            # values.append(f"Found {bot.ITEM_EMOJIS['rherb']} (rherb) x{drop_amount} while searching")
            found_ids.append("rherb")

        elif chance <= uherb_chance:
            found_ids.append("uherb")

        elif chance <= lherb_chance:
            found_ids.append("lherb")

        elif chance <= mherb_chance:
            found_ids.append("mherb")

        elif chance <= other_chance:
            found_ids.append("cauldron")

    return found_ids


def pill_embed(details):
    item, requirement_str, user_data, pill_bonus, cauldron_bonus = details
    alchemy_cdr, refine_above_tier_bonus = cauldron_bonus

    item_id, name, properties, e_description, tier, item_type = item

    base_chance = properties['make_chance']
    pill_exp_given = properties['exp_given']

    user_tier, user_exp, flame, refined_pills, pill_cooldown, next_tier_chance, pill_pity = user_data

    check, chance = pill_refine_check(base_chance, tier, user_tier, next_tier_chance, pill_bonus, pill_pity, refine_above_tier_bonus)
    chance_str = '%.02f' % chance

    # ID, tier and success rate
    embed = disnake.Embed(
        title=name,
        description=f"(**`{item_id}`**) \n\n**Tier : `{tier}`** | **Refinement success rate : `{chance_str}`%** \nExp Given: `{format_num_simple(pill_exp_given)}`",
        color=disnake.Color(0xe5fe88)
    )

    # Effect
    embed.add_field(name="Effect", value=e_description if e_description else "None", inline=False)

    # Picture
    try:
        path = f"./media/{item_type}/{item_id}.png"
        embed.set_thumbnail(file=disnake.File(path))
    except OSError:
        pass

    # Requirements
    embed.add_field(name="Requirements", value=requirement_str, inline=False)

    if time() < user_data[4]:
        embed.add_field(name="Next Refine Possible", value=f"<t:{int(user_data[4])}:R>")

    return embed


class AlchemyDropdown(disnake.ui.Select):

    def __init__(self, item_list):
        self.item_list = item_list
        item_list.reverse()
        options = [
            *(disnake.SelectOption(label=f"[T{item[4]}] {item[1]}", value=f"{item[0]}") for item, requirement_str, user_data, pill_bonus, cauldron_bonus in item_list[:24]),
        ]

        super().__init__(
            # custom_id=f"pill_{round(time(), 3)}",
            placeholder="Choose your pills",
            max_values=1,
            options=options,
        )

    async def callback(self, inter):
        for item in self.item_list:
            if item[0][0] == inter.values[0]:
                self.view.current_item = item
                await inter.response.edit_message(attachments=[])
                await inter.edit_original_message(embed=pill_embed(item), view=self.view)
                # await inter.message.edit(embed=embed)


class AlchemyMenu(disnake.ui.View):
    def __init__(self, item_list, author):
        super().__init__(timeout=None)
        self.item_list = item_list[:24]
        self.item_list_2 = item_list[24:]
        self.current_item = self.item_list[0]
        self.author = author

        self.add_item(AlchemyDropdown(self.item_list))
        if len(self.item_list_2) > 0:
            self.add_item(AlchemyDropdown(self.item_list_2))

    async def interaction_check(self, inter) -> bool:
        return inter.author == self.author

    async def user_flame_check(self, channel, user_flame):
        if user_flame is None:
            embed = BasicEmbeds.exclamation("You need a flame to refine the pill \n*Hint: Consume a Congeal Flame Pill to gain one-time flame*")
            await channel.send(embed=embed)
            return False

        if user_flame == 'conpillflame':  # Special case (one time use flame)
            pill_used_list = await Users.get(user_id=self.author.id).values_list("pill_used", flat=True)
            pill_used_list.remove("conpill")
            await Users.filter(user_id=self.author.id).update(pill_used=pill_used_list)
            await Alchemy.filter(user_id=self.author.id).update(flame=None)  # Flame disappears

        return True

    @disnake.ui.button(label="Refine", style=disnake.ButtonStyle.green)
    async def refine_pill(self, _: disnake.ui.Button, inter: disnake.MessageInteraction):

        self.clear_items()
        item, requirement_str, user_data, _, cauldron_bonus = self.current_item

        pill_id, pill_name, pill_properties, e_description, pill_tier, item_type = item
        # Get pill information
        pill_exp_given = pill_properties['exp_given']
        pill_make_chance = pill_properties['make_chance']

        await inter.response.edit_message(embed=BasicEmbeds.exclamation(f"Trying to refine {pill_name}"), attachments=[], view=self)

        # Get player alchemy information
        user_level, user_exp, flame, refined_pills, _, next_tier_chance, pill_pity = user_data
        pill_cooldown = await Alchemy.get(user_id=inter.author.id).values_list("pill_cooldown", flat=True)

        requirements = pill_properties["requirements"]
        mass_check, check_content = await mass_check_items(inter.author.id, requirements)
        if not mass_check:
            await inter.edit_original_message(embed=BasicEmbeds.exclamation(f"You dont have enough materials to refine {pill_name} \n{check_content}"))
            return

        alchemy_cdr, refine_above_tier_bonus = cauldron_bonus
        if user_level <= 7:
            if (alchemy_cdr + refine_above_tier_bonus) == 0:
                await inter.edit_original_message(embed=BasicEmbeds.exclamation("You dont have a cauldron to refine pills. \nEquip a cauldron first!"))
                return

        # Check if on pill cooldown
        if pill_cooldown is not None and time() < pill_cooldown:
            await inter.edit_original_message(embed=BasicEmbeds.exclamation(f"Pill refinement on cooldown, try again after <t:{pill_cooldown}:R>"))
            return

        continue_check, ring_id, add_check = await check_inv_weight(inter.channel, inter.author.id, pill_id, 1)
        if not continue_check:
            embed = BasicEmbeds.cmd_not_continued()
            await inter.edit_original_message(embed=embed)
            return

        # Check if there is enough energy
        async with PlayerRoster().find_player_for(inter) as player:
            energy_check = player.consume_energy(6 * int(pill_tier))

        if not energy_check:
            await inter.edit_original_message(embed=BasicEmbeds.exclamation("You don't have enough energy to refine a pill"))
            return

        # Check for flame (prerequisite for refining a pill)
        # WARNING: consumes one-time-use flame if present
        flame_check = await self.user_flame_check(inter.channel, flame)
        if not flame_check:
            await inter.edit_original_message(view=self)
            return

        # Calculate pill refinement bonus
        pill_bonus = 0

        # Flame bonus
        _, _, flame_pill_bonus = await compute_flame_bonus(inter.author.id)
        pill_bonus += flame_pill_bonus

        # Pill effect bonuses (one use)
        pill_bonus_raw, _, _, _ = await DatabaseUtils.compute_pill_bonus(user_id=inter.author.id, refine_pill=True)
        pill_bonus += pill_bonus_raw

        refined, chance = pill_refine_check(pill_make_chance, pill_tier, user_level, next_tier_chance, pill_bonus, pill_pity, refine_above_tier_bonus)
        chance_str = '%.01f' % chance

        pill_raw_cd = PILL_COOLDOWN[pill_tier]
        pill_cdr = (alchemy_cdr / 100) * pill_raw_cd
        pill_cooldown = int(time() + (pill_raw_cd - pill_cdr))

        # Remove herbs from inventory
        ring_id = await get_equipped_ring_id(inter.author.id)
        for herb, count in pill_properties["requirements"].items():
            await remove_from_inventory(inter.author.id, herb, count, ring_id)

        if refined:  # Successfully refined pill

            log_event(inter.author.id, "alchemy", f"Refined {pill_id} ({chance_str}%)")

            content = f"You have successfully refined {pill_name} ({chance_str}%)"
            await add_to_inventory(inter.author.id, pill_id, 1, ring_id, add_check)

            # Update refined_pills
            if pill_tier in refined_pills:
                refined_pills[pill_tier] += 1
            else:
                refined_pills[pill_tier] = 1

            # Alchemy exp given and tier upgrade check
            if pill_exp_given > 0:

                required_exp = (round(100 * (7 ** (user_level - 1)))) * 3  # EXP to get to next alchemy level

                if (user_exp + pill_exp_given) > required_exp:  # User about to break through

                    if pill_tier > user_level:  # User refined a higher tier pill, break through
                        user_level += 1
                        user_exp = 0

                        next_tier_chance = 5
                        pill_pity = 0  # Reset pill pity
                        content += f"\n\n**Congratulations you have reached Tier `{user_level}`!**"
                        log_event(inter.author.id, "alchemy", f"Leveled up to {user_level} Tier")
                    else:  # User did not refine a higher tier pill
                        user_exp = required_exp
                        next_tier_chance = 40 if user_level < 9 else 30
                        if user_level < 10:
                            content += f"\n\n*You have reached limit of your tier, refine a higher tier pill now to progress.*"

                    await Alchemy.filter(user_id=inter.author.id).update(next_tier_chance=next_tier_chance, pill_pity=pill_pity)

                else:  # User not about to break through
                    user_exp += pill_exp_given
                    log_event(inter.author.id, "alchemy", f"Increase the EXP by {pill_exp_given:,}, total {user_exp:,} EXP")
                await Alchemy.filter(user_id=inter.author.id).update(a_lvl=user_level, a_exp=user_exp)

            # Update pill refined dict
            await Alchemy.filter(user_id=inter.author.id).update(pill_refined=refined_pills)

            # Send message
            embed = BasicEmbeds.add_plus(content)
            await inter.edit_original_message(embed=embed)

        elif not refined:  # Fail to refine pill
            log_event(inter.author.id, "alchemy", f"Failed to refine {pill_id} ({chance}%)")
            # Increase pity if already at max EXP
            pity_str = ''
            required_exp = (round(100 * (7 ** (user_level - 1)))) * 3
            if user_exp == required_exp and (pill_tier - user_level) == 1:
                pill_pity += 1  # Update pill pity
                await Alchemy.filter(user_id=inter.author.id).update(pill_pity=pill_pity)
                pity_str = "\nYour pity has increased to %i." % pill_pity

            # Send message
            embed = BasicEmbeds.wrong_cross(f"{pill_name} failed to refine ({chance}% chance to refine){pity_str}")
            await inter.edit_original_message(embed=embed)

        # Update pill cooldown
        await Alchemy.filter(user_id=inter.author.id).update(pill_cooldown=pill_cooldown)
        log_event(inter.author.id, "alchemy", f"Cooldown added for {round((pill_cooldown - time()) / 60, 1)} minutes")


class AlchemySystem(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(name="alchemy", description="Shows your alchemy stats")
    async def slash_alchemy(self,
                            inter: disnake.CommandInteraction,
                            member: Optional[disnake.Member] = commands.Param(default=None, name="member", description="Mention a member to view their stats")):
        await inter.response.defer()

        if member is None:
            member = inter.author

        # Get user alchemy info
        user_check = await Alchemy.get_or_none(user_id=member.id).values_list("a_lvl", "a_exp", "cauldron", "flame", "pill_refined", "pill_cooldown", "next_tier_chance", "pill_pity")
        if user_check is None:
            return

        user_level, user_exp, cauldron, flame, _, _, _, _ = user_check
        required_exp = (round(100 * (7 ** (user_level - 1)))) * 3

        if flame == 'conpillflame':
            flame_string = "Congeal Flame Pill Flame"
        elif flame is not None:
            flame_name, flame_properties = await AllItems.get_or_none(id=flame).values_list("name", "properties")
            pill_rate_boost = flame_properties["pill_rate_boost"]
            flame_string = f"{flame_name} (+{pill_rate_boost}% pill refine boost)"
        else:
            flame_string = "*None*"

        equipped = await Users.get_or_none(user_id=member.id).values_list("equipped", flat=True)
        previous_stone = equipped.get("stone", None)
        second_flame = "None"
        if previous_stone is not None:
            stone_inv = await give_custom_ring_inv(previous_stone)
            if len(stone_inv) > 0:
                flame_name, flame_properties = await AllItems.get_or_none(id=list(stone_inv.keys())[0]).values_list("name", "properties")
                snd_pill_rate_boost = flame_properties["pill_rate_boost"]
                second_flame = flame_name + f" (+{snd_pill_rate_boost * 0.5}% pill refine boost)"

        if cauldron is not None:
            cauldron_id, stats = await Crafted.get_or_none(id=cauldron).values_list("item_id", "stats")
            stat_name = {
                "alchemy_cdr": "Alchemy Cooldown Reduction",
                "refine_bonus_per_tier_above": "Higher Tier Refine Bonus"
            }
            stat_str = '\n'.join(f'> {stat_name[stat]}: {value}%' for stat, value in stats.items())
            cauldron_str = f"{cauldron_id} \n{stat_str}"
        else:
            cauldron_str = "*None*"
        # Format alchemy profile
        values = [
            f"**Alchemy Tier** : `{user_level}`",
            f"**EXP to next tier** : `{user_exp:,}`/`{required_exp:,}`",
            f"\n**Flame** : {flame_string}",
            f"**Flame #2** : {second_flame}",
            f"\n**Cauldron** : {cauldron_str}",

        ]
        embed = disnake.Embed(
            description="\n".join(value for value in values),
            color=member.color
        )
        if member.avatar is not None:
            embed.set_author(name=member.name, icon_url=member.avatar.url)
        else:
            embed.set_author(name=member.name)
        await inter.edit_original_message(embed=embed)

    @commands.slash_command(name="pills", description="Check what pill you can make")
    async def slash_pills(self, inter: disnake.CommandInteraction):
        await inter.response.defer()

        all_pills = await AllItems.filter(type="pill").values_list("id", "name", "properties", "e_description", "tier", "type")
        alchemy_data = await Alchemy.get(user_id=inter.author.id).values_list("a_lvl", "a_exp", "flame", "pill_refined", "pill_cooldown", "next_tier_chance", "pill_pity")

        # Calculate pill refinement bonus
        pill_bonus = 0

        # Flame bonus
        _, _, flame_pill_bonus = await compute_flame_bonus(inter.author.id)
        pill_bonus += flame_pill_bonus

        # Pill effect bonuses (one use)
        pill_bonus_raw, _, _, _ = await DatabaseUtils.compute_pill_bonus(user_id=inter.author.id)
        pill_bonus += pill_bonus_raw

        if pill_bonus_raw < 1 and alchemy_data[0] >= 6:
            elem_heart_check = await check_item_in_inv(inter.author.id, "elemheartpill", 1)
            if not elem_heart_check:
                if alchemy_data[0] == 6 and alchemy_data[1] == 0:
                    await Alchemy.filter(user_id=inter.author.id).update(a_exp=1)
                    await add_to_inventory(inter.author.id, "elemheartpill", 1)

                    embed = BasicEmbeds.empty_embed()
                    embed.description = (f"I see you haven't managed to refine a pill as a tier 6 alchemist yet. Poor you :("
                                         f""
                                         f"\n\nBut dont worry! "
                                         f"\nI have given you a tasty pill (`elemheartpill`) which increase refine chance "
                                         f""
                                         f"\n\n### Consume it quick and do </pills:123> again to see the magic")
                    await inter.edit_original_message(embed=embed)
                    return
            else:
                view = ConfirmDelete(inter.author.id)
                await inter.channel.send(f"You haven't consumed Elemental Heart Pill to boost refine chance, continue?", view=view)

                await view.wait()
                if view.confirm is False:
                    embed = BasicEmbeds.exclamation(f"Refining stopped by the user")
                    await inter.edit_original_message(embed=embed)
                    return

        # Cauldron Bonus
        alchemy_cdr, refine_above_tier_bonus = await DatabaseUtils.compute_cauldron_bonus(inter.author.id)

        item_list = []
        combined_inv = await give_combined_inv(inter.author.id)

        for pill in all_pills:
            properties_dict = pill[2]
            requirements = properties_dict["requirements"]

            mass_check, check_content = await mass_check_items(inter.author.id, requirements, combined_inv)
            item_list.append((pill, check_content, alchemy_data, pill_bonus, (alchemy_cdr, refine_above_tier_bonus)))

        if len(item_list) > 0:
            view = AlchemyMenu(item_list, inter.author)
            if time() < alchemy_data[4]:
                view.refine_pill.disabled = True

            await inter.edit_original_message(embed=pill_embed(item_list[0]), view=view)
        else:
            embed = BasicEmbeds.exclamation("You don't have enough ingredients in your inventory")
            await inter.edit_original_message(embed=embed)

    @commands.slash_command(name="search", description="Search for the ingredients to refine pills")
    @commands.cooldown(1, 1800, commands.BucketType.user)
    async def slash_search(self, inter: disnake.CommandInteraction):
        await inter.response.defer()
        await drop_origin_qi(inter.guild, inter.author.id)

        user_info = await Alchemy.get_or_none(user_id=inter.author.id).values_list("a_lvl")
        all_herbs = await AllItems.filter(id__in=HERBS_IDS).order_by("-tier").values_list("id", "name", "properties", "e_description", "tier")

        embed = disnake.Embed(
            description="Found some herbs while searching ",
            color=disnake.Color(0x5bf27e)
        )

        id_list: list[str] = calculate_chances(user_info[0])
        max_drop = NUMBER_OF_DROPS[user_info[0]]["max"]

        if len(id_list) > 0:
            continue_check, ring_id, add_check = await check_inv_weight(inter.channel, inter.author.id, id_list[0],
                                                                        max_drop, confirm_text=f"Make sure you have at least {max_drop}wt worth of free space in your inventory/ring. You may lose some of the items, Continue?")
            if continue_check is False:
                embed = BasicEmbeds.cmd_not_continued()
                await inter.edit_original_message(embed=embed)
                return

            log_event(inter.author.id, "alchemy", f"Searched for herbs")
            details = []
            for herb in all_herbs:
                if herb[0] in id_list:
                    details.append(herb)

            for detail in details:
                embed.description += f"\n{PLUS} {ITEM_EMOJIS[detail[0]]} **{detail[1]}** x **`{id_list.count(detail[0])}`**"
                await add_to_inventory(inter.author.id, detail[0], id_list.count(detail[0]), ring_id, add_check)

            embed.description += f"\n{TICK} Successfully added to inventory"

        await inter.edit_original_message(embed=embed)


def setup(bot):
    bot.add_cog(AlchemySystem(bot))
    print("[Alchemy] Loaded")

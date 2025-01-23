import random

import disnake
from disnake.ext import commands
from time import time
from tortoise.expressions import F

from character.player import PlayerRoster
from utils.CommandUtils import add_temp_cp, add_temp_exp, VoteLinkButton, PatreonLinkButton
from utils.Database import AllItems, Temp, Users, Alchemy, Cultivation
from utils.Embeds import BasicEmbeds
from utils.ExpSystem import compare_realms
from utils.InventoryUtils import check_item_in_inv, remove_from_inventory
from utils.LoggingUtils import log_event
from utils.base import BaseStarfallCog

"""
properties = {
    "requirements": {"lherb": 3, "uherb": 9, "rherb": 18, "cherb": 27},
    "make_chance": 85,
    "exp_given": 11,
    "effects": {
        "MAX_COUNT": None or 1,2,3.., # Max number allowed in used list, None is infinite
        "PROMOTE": None or {"max_realm": [0,12], "min_realm":[0,0], "count": 1}, # [Minor, Major]
        "TEMPBOOST": None or {"cp": [20, 10], "exp": [15,10]}, # [Percent, Minutes]
        "ENERGY": None or 10,20.., # Gain Energy
        "PERMANENT": None or {"cp": 0, "exp": 0}, # Permanent CP AND EXP Boost (they get added)
        "FLAME_SWALLOW": None or 10%, 20%..,
        "PILL_REFINE": None or 10%..., 
        "BATTLE_BOOST": None or [10%, 10] # [CP boost, Number of battle]
        "BEAST_LURE": None or [min_rank, max_rank, limit]
    }
}
"""


class Pills(BaseStarfallCog):

    def __init__(self, bot):
        super().__init__(bot, "Pills", "pills")

    async def _do_load(self):
        pass

    def _do_unload(self):
        pass

    @commands.slash_command(name="consume", description="Consume a pill")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def slash_consume(self,
                            inter: disnake.CommandInteraction,
                            pill_id: str = commands.Param(name="pill_id", description="Type the item id to use it")):
        await inter.response.defer()
        pill_check = await AllItems.get_or_none(id=pill_id).values_list("id", "type", "name", "properties")

        # Checking if item exists
        if pill_check is None:
            embed = BasicEmbeds.item_not_found()
            await inter.edit_original_message(embed=embed)
            return

        _, item_type, pill_name, properties = pill_check

        # Checking if item is a pill
        if item_type != "pill":
            embed = BasicEmbeds.exclamation("Not a pill")
            await inter.edit_original_message(embed=embed)
            return

        pill_effects = properties["effects"]

        # Fetching user data
        consumed = False
        user_data = await Cultivation.get_or_none(user_id=inter.author.id).values_list("user__pill_used", "user__bonuses", "user__battle_boost", "major", "minor")
        pill_used_list, bonuses, battle_boost, major, minor = user_data
        if battle_boost is None:
            battle_boost = [0, 0]

        # Checking if player consumed the pill before
        max_allowed = pill_effects.get("MAX_COUNT")
        if max_allowed:
            if pill_used_list.count(pill_id) >= max_allowed > 0:
                embed = BasicEmbeds.exclamation("You have consumed maximum amount of this pill")
                await inter.edit_original_message(embed=embed)
                return

        # Removing the pill from inventory
        inv_check = await check_item_in_inv(inter.author.id, pill_id)
        if inv_check is False:
            embed = BasicEmbeds.not_enough_item(pill_name, "alchemy")
            await inter.edit_original_message(embed=embed)
            return

            # Add the pill to used list
        pill_used_list.append(pill_id)

        content = []  # A list to make a response later

        # All Effects
        # Immediate eff
        promotion_eff = pill_effects.get("PROMOTE")
        temp_boost_eff = pill_effects.get("TEMPBOOST")
        energy_eff = pill_effects.get("ENERGY")
        perm_eff = pill_effects.get("PERMANENT")
        battle_eff = pill_effects.get("BATTLE_BOOST")
        # Later effect
        refine_effect = pill_effects.get("PILL_REFINE")
        flame_effect = pill_effects.get("FLAME_SWALLOW")
        beast_lure_eff = pill_effects.get("BEAST_LURE")

        # Promotion effect
        if promotion_eff:
            # gspirit1pill, gspirit2pill, gspirit3pill
            max_major, max_minor = promotion_eff["max_realm"]
            min_major, min_minor = promotion_eff["min_realm"]
            amount = promotion_eff["count"]

            # Special pills effect
            if pill_id == "gspirit2pill":
                if major == 2:
                    # Fight Master consuming Two-Lined Green Spirit Pill have chances to lose cultivation
                    if random.randint(1, 100) <= 10:
                        amount = -1

            elif pill_id == "gspirit3pill":
                if major == 2:
                    # Fight Master consuming Three-Lined Green Spirit Pill have chances to lose cultivation
                    rand = random.randint(1, 100)
                    if rand <= 5:
                        amount = -2
                    elif rand <= 15:
                        amount = -1

            elif pill_id == "mightypill":
                if random.randint(1, 100) <= 20:
                    amount = 2

            min_check = compare_realms(major, minor, min_major, min_minor, "low")
            if min_check is True:
                max_check = compare_realms(major, minor, max_major, max_minor, "high")
                if max_check is True:
                    if pill_id == "zongpill":
                        async with PlayerRoster().find_player_for(inter) as player:
                            await player.add_experience(amount)

                        content.append(f"Exp increased by {amount}")
                    else:
                        if amount >= 0:
                            async with PlayerRoster().find_player_for(inter) as player:
                                await player.change_realm(amount, "promote", inter.guild, ignore_oqi=True)

                            content.append(f"Cultivation increased by {amount} level")
                        elif amount < 0:
                            async with PlayerRoster().find_player_for(inter) as player:
                                await player.change_realm(-amount, "demote", inter.guild, ignore_oqi=True)

                            content.append(f"Uh oh.. cultivation decreased by {-1 * amount} level")

                    log_event(inter.author.id, "pill", f"Promoted by {amount} levels")
                    consumed = True
                else:
                    consumed = True
                    content.append(f"but your realm is higher than required, so nothing happened :(")
            else:
                consumed = True
                content.append(f"but your realm is low, so nothing happened :(")
                log_event(inter.author.id, "pill", f"Failed to promote", "WARN")

        # Temp Boost effect
        if temp_boost_eff:
            # refpill
            give_cp = temp_boost_eff.get("cp")
            give_exp = temp_boost_eff.get("exp")

            tempboost = await Temp.filter(user_id=inter.author.id).values_list("cp", "exp")

            give_cp_boost = None
            give_exp_boost = None
            for t_boost in tempboost:
                cp_boost, exp_boost = t_boost

                if cp_boost:
                    give_cp_boost = cp_boost
                if exp_boost:
                    give_exp_boost = exp_boost

            if give_exp:
                percent_exp, duration = give_exp
                if not give_exp_boost:

                    text = await add_temp_exp(inter.author.id, percent_exp, duration)
                    consumed = True
                    content.append(text)
                    pill_used_list.remove(pill_id)

                else:
                    content.append("An effect is already boosting your **exp**, wait for it to end and try again!")
                    log_event(inter.author.id, "pill", f"Failed to gain EXP temp boost", "WARN")

            if give_cp:
                percent_cp, duration = give_cp
                if not give_cp_boost:
                    text = await add_temp_cp(inter.author.id, percent_cp, duration)
                    consumed = True
                    content.append(text)
                    pill_used_list.remove(pill_id)

                else:
                    content.append("An effect is already boosting your **cp**, wait for it to end and try again!")
                    log_event(inter.author.id, "pill", f"Failed to gain CP temp boost", "WARN")

        # increase energy effect
        if energy_eff:
            # recpill, 
            give_energy = energy_eff
            async with PlayerRoster().find_player_for(inter) as player:
                player.add_energy(give_energy)

            consumed = True
            content.append(f"Gained {give_energy} Energy!")
            log_event(inter.author.id, "pill", f"Gained {give_energy} Energy")

        # Permanent cp and exp increase 
        if perm_eff:
            # burnblood
            give_cp = perm_eff["cp"]
            give_exp = perm_eff["exp"]

            if pill_id == "flamedemonpill" and random.randint(1, 100) > 50:
                consumed = True
                content.append(f"Failed to increase CP! Try again")
                pill_used_list.remove(pill_id)
                log_event(inter.author.id, "pill", f"Failed to gain permanent cp boost", "WARN")
            else:
                bonuses["cp"] += give_cp
                bonuses["exp"] += give_exp

                await Users.filter(user_id=inter.author.id).update(bonuses=bonuses)
                consumed = True
                content.append(f"Gained {give_cp}% CP and {give_exp}% Exp boost!")
                log_event(inter.author.id, "pill", f"Gained {give_cp}% CP and {give_exp}% Exp, permanently")

        # Boost battle effect
        if battle_eff:
            # strpill, windpill
            give_boost = battle_eff
            if battle_boost[1] > 0:
                content.append(f"You already have a boost present for {battle_boost[1]} more battles")
                log_event(inter.author.id, "pill", f"Failed to gain battle boost", "WARN")
            else:
                if pill_id != "qimendpill" or (pill_id == "qimendpill" and major <= 7):
                    await Users.filter(user_id=inter.author.id).update(battle_boost=give_boost)
                    consumed = True
                    content.append(f"Gained {give_boost[0]}% CP boost for {give_boost[1]} battles")

                    log_event(inter.author.id, "pill", f"Gained {give_boost[0]}% CP boost for {give_boost[1]} battles")
                    pill_used_list.remove(pill_id)

        # Other late effects
        if refine_effect:
            consumed = True

        if flame_effect:
            # pathpill, icypill
            consumed = True

        if beast_lure_eff:
            consumed = True

        # Special pills with unique effects
        if pill_id in ["conpill", "groundpill"]:
            # conpill, 
            consumed = True
            if pill_id == "conpill":
                user_flame = await Alchemy.get_or_none(user_id=inter.author.id).values_list("flame", flat=True)
                if user_flame is None:
                    await Alchemy.filter(user_id=inter.author.id).update(flame="conpillflame")
                    content.append("Gained one-time use flame")
                else:
                    consumed = False
                    content.append("You already have a flame present!")

        # Check if the pill is consumed
        if consumed is True:
            main_content = f"Consumed {pill_name} successfully!\n"
            embed = BasicEmbeds.right_tick(main_content + "\n" + "\n".join(c for c in content))
            await Users.filter(user_id=inter.author.id).update(pill_used=pill_used_list)
            await remove_from_inventory(inter.author.id, pill_id, 1)
            log_event(inter.author.id, "pill", f"Consumed {pill_name}")
        else:
            # healpill, 
            main_content = f"{pill_name} not consumed!\n"
            embed = BasicEmbeds.exclamation(main_content + "\n" + "\n".join(c for c in content))
            log_event(inter.author.id, "pill", f"Failed to consume {pill_name}", "WARN")

        view = disnake.ui.View()
        view.add_item(VoteLinkButton())
        view.add_item(PatreonLinkButton())

        await inter.edit_original_message(embed=embed, view=view)



def setup(bot):
    bot.add_cog(Pills(bot))
    print("[Pills] Loaded")

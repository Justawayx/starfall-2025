from time import time

import disnake
from disnake.ext import commands
from tortoise.expressions import F

from character.player import PVP_REWARDS, PlayerRoster, Player
from cogs.timeflow import time_flow
from utils import InventoryUtils
from utils.Database import Pet, Temp, Users, Alchemy, Cultivation, Pvp, Crafting, GuildOptions
from utils.EconomyUtils import CURRENCY_NAME_GOLD, CURRENCY_NAME_ARENA_COIN, EVENT_SHOP
from utils.Embeds import BasicEmbeds
from utils.InventoryUtils import remove_from_inventory, inventory_view
from utils.LoggingUtils import log_event
from utils.ParamsUtils import elo_from_rank_points
from utils.base import BaseStarfallCog
from world.compendium import autocomplete_item_id
import logging

class RemoveButton(disnake.ui.Button):

    def __init__(self, label):
        super().__init__(label=str(label), style=disnake.ButtonStyle.grey, emoji="<:minus:987586651171725402>")
        self.label = label

    async def callback(self, inter):
        self.view.itemid = self.label
        self.view.clear_items()
        await inter.response.edit_message(view=self.view)
        self.view.stop()


class RemoveBonusView(disnake.ui.View):

    def __init__(self, ids):
        super().__init__()
        for _id in ids:
            self.add_item(RemoveButton(_id))
        self.itemid = ""


class Admin(BaseStarfallCog):

    def __init__(self, bot):
        super().__init__(bot, "Admin", "admin")

    async def _do_load(self):
        pass

    def _do_unload(self):
        pass

    # //////////////////////////////////////// #

    @commands.command(name="set_qi_counter")
    @commands.has_permissions(manage_guild=True)
    async def set_qi_counter(self, inter, count: int = 1):
        qi_counter = await GuildOptions.get_or_none(name="qi_counter").values_list("value", flat=True)
        if qi_counter is None:
            await GuildOptions.create(name="qi_counter", value=1)

        await GuildOptions.filter(name="qi_counter").update(value=count)
        await inter.send(f"Qi counter set to {count}")

    @commands.command(name="reset_daily_tax")
    @commands.has_permissions(manage_guild=True)
    async def reset_daily_tax(self, _, count: int = -1):
        if count < 0:
            qi_counter = await GuildOptions.get_or_none(name="qi_counter").values_list("value", flat=True)
            if qi_counter is None:
                await GuildOptions.create(name="qi_counter", value=1)
                qi_counter = 1

            count = int(qi_counter) + 1

        await GuildOptions.filter(name="qi_counter").update(value=count)

        all_users = await Pvp.all().values_list("user__pill_used", "rank_points", "user_id")
        for user in all_users:
            pill_used_list, rank_point, user_id = user
            pill_list_update = [pill_id for pill_id in pill_used_list if pill_id != 'recpill']

            elo_rank, elo_sub_rank, excess_points = elo_from_rank_points(rank_point)
            user_rank_reward = PVP_REWARDS[f"{elo_sub_rank} {elo_rank}"]
            money, coins = user_rank_reward
            await Users.filter(user_id=user_id).update(pill_used=pill_list_update, money=F("money") + money)
            await Pvp.filter(user_id=user_id).update(pvp_coins=F("pvp_coins") + coins)

    @commands.slash_command()
    @commands.default_member_permissions(manage_guild=True)
    async def admin(self, inter):
        """
        Parent Command
        """
        pass
    
    @commands.slash_command()
    @commands.default_member_permissions(manage_guild=True)
    async def adminreset(self, inter):
        """
        Parent Command
        """
        pass

    @admin.sub_command(name="promote_user", description="Promote a cultivator")
    async def promote_user(self,
                           inter: disnake.CommandInteraction,
                           member: disnake.Member = commands.Param(name="member", description="Choose a member to promote"),
                           amount: int = commands.Param(name="amount", description="How many times to promote?", default=1, gt=0)):
        async with PlayerRoster().find_player_for(inter, member) as player:
            content, embed_content = await player.change_realm(amount, "promote", inter.guild, ignore_oqi=True)

        embed = disnake.Embed(description=embed_content, color=disnake.Color(0x2e3135))

        await inter.response.send_message(content=content, embed=embed)

    @admin.sub_command(name="demote_user", description="Demote a cultivator")
    async def demote_user(self,
                          inter: disnake.CommandInteraction,
                          member: disnake.Member = commands.Param(name="member", description="Choose a member to promote"),
                          amount: int = commands.Param(name="amount", description="How many times to promote?", default=1, gt=0),
                          maintain_major: bool = commands.Param(default=False, name="maintain_major", description="Should the player's major rank be maintained (False by default)?")):
        async with PlayerRoster().find_player_for(inter, member) as player:
            content, embed_content = await player.change_realm(amount, "demote", inter.guild, ignore_oqi=True, maintain_major=maintain_major)

        embed = disnake.Embed(description=embed_content, color=disnake.Color(0x2e3135))

        await inter.response.send_message(content=content, embed=embed)

    @admin.sub_command(name="add_exp_effect", description="Add temporary EXP effect")
    async def add_exp_effect(self, inter: disnake.CommandInteraction, member: disnake.Member, exp_amount: int, hours: int):
        till = round(time() + (hours * 60 * 60))

        await Temp.create(user_id=member.id, event_exp=exp_amount, till=till)

        embed = BasicEmbeds.right_tick(f"Gave {member.mention} {exp_amount}% EXP boost For {hours} hours")
        await inter.response.send_message(embed=embed)
    
    @admin.sub_command(name="update_event_shop", description="Enable event shop")
    async def update_event_shop(self, inter: disnake.CommandInteraction, enable: bool, duration_hours: int, comma_sep_items: str, name: str):
        if enable:
            EVENT_SHOP.enable(duration_hours)
            EVENT_SHOP.set_name_and_items(name, comma_sep_items.split(','))
            embed = BasicEmbeds.right_tick(f"Enabled event shop named '{name}' for {duration_hours} hours with items `{comma_sep_items}`")
        else:
            EVENT_SHOP.disable()
            embed = BasicEmbeds.right_tick(f"Disabled event shop")
        
        await inter.response.send_message(embed=embed)

    @admin.sub_command(name="add_cp_effect", description="Add temporary CP effect")
    async def add_cp_effect(self, inter: disnake.CommandInteraction, member: disnake.Member, cp_amount: int, hours: int):
        till = round(time() + (hours * 60 * 60))

        await Temp.create(user_id=member.id, event_cp=cp_amount, till=till)

        embed = BasicEmbeds.right_tick(f"Gave {member.mention} {cp_amount}% CP boost For {hours} hours")
        await inter.response.send_message(embed=embed)

    @admin.sub_command(name="clear_flame", description="Remove flame")
    async def clear_flame(self, inter: disnake.CommandInteraction, member: disnake.Member):
        await Alchemy.filter(user_id=member.id).update(flame=None)
        await inter.response.send_message(embed=disnake.Embed(description="Cleared flame"))

    @admin.sub_command(name="show_alchemy_data", description="Show user alchemy data")
    async def show_alchemy_data(self, inter: disnake.CommandInteraction, member: disnake.Member):
        alchemy_data = await Alchemy.filter(user_id=member.id).values()
        embed = disnake.Embed(
            description=str(alchemy_data),
            color=inter.author.color
        )
        await inter.response.send_message(embed=embed)

    @admin.sub_command(name="clear_pill_used", description="Clear pill_used")
    async def clear_pill_used(self, inter: disnake.CommandInteraction, member: disnake.Member):
        await Users.filter(user_id=member.id).update(pill_used=[])
        embed = disnake.Embed(
            description=f"Cleared pill_used",
            color=inter.author.color
        )
        await inter.response.send_message(embed=embed)

    @adminreset.sub_command(name="pvp_reset", description="Reset all pvp stats to zero")
    async def pvp_reset(self, ctx):
        await Pvp.all().update(rank_points=0, pvp_promo=0, pvp_demote=0, rank_points_before_promo=0)
        embed = disnake.Embed(
            description=f"All users have been reset to 0 rank points (Unranked).",
            color=ctx.author.color
        )
        await ctx.response.send_message(embed=embed)

    @admin.sub_command(name="pvp_set", description="Sets rank points for a specific member")
    async def pvp_set(self, inter: disnake.CommandInteraction, member: disnake.Member, points: int):
        await Pvp.filter(user_id=member.id).update(rank_points=points)

        embed = disnake.Embed(
            description=f"Set rank points of {member.mention} to {points}.",
            color=inter.author.color
        )
        await inter.response.send_message(embed=embed)

    @admin.sub_command(name="invsee", description="See inventory of someone else")
    async def invsee(self, inter: disnake.CommandInteraction, member: disnake.Member):
        embed, view = await inventory_view(member, inter.author)
        if view:
            await inter.response.send_message(embed=embed, view=view)
        else:
            await inter.response.send_message(embed=embed)

    @admin.sub_command(name="invadd", description="Give item to someone")
    async def invadd(self,
                     inter:
                     disnake.CommandInteraction,
                     member: disnake.Member,
                     item_id: str = commands.Param(name="item_id", description="The item identifier", autocomplete=autocomplete_item_id),
                     quantity: int = commands.Param(name="quantity", default=1, ge=1, description="The item count")):
        await InventoryUtils.add_to_inventory(member.id, item_id, quantity, ignore_ring_weight=True)

        embed = BasicEmbeds.right_tick(f"Gave {quantity}x {item_id} to {member.mention}")

        await inter.response.send_message(embed=embed)

    @admin.sub_command(name="invremove", description="Take item from someone")
    async def invremove(self,
                        inter: disnake.CommandInteraction,
                        member: disnake.Member,
                        item_id: str = commands.Param(name="item_id", description="The item identifier", autocomplete=autocomplete_item_id),
                        quantity: int = commands.Param(name="quantity", default=1, ge=1, description="The item count")):
        await remove_from_inventory(member.id, item_id, quantity)
        embed = BasicEmbeds.right_tick(f"Removed {quantity}x {item_id} from {member.mention}")
        await inter.response.send_message(embed=embed)

    # TODO: FINALIZE HOW TO DO BONUSES
    @admin.sub_command(name="equippedmenu", description="Remove equipped item")
    async def equippedmenu(self, inter: disnake.CommandInteraction, member: disnake.Member):
        data = await Users.get_or_none(user_id=member.id).values("equipped")
        equipped = data['equipped']
        equipped_ids_list = [tup[0] for tup in equipped['techniques']]
        if equipped['method']:
            equipped_ids_list.append(equipped['method'][0])
        equipped_ids_list += [tup[0] for tup in equipped['weapons']]

        embed = BasicEmbeds.exclamation("Please choose an equipped item to remove")
        view = RemoveBonusView(equipped_ids_list)
        await inter.response.send_message(embed=embed, view=view)

        await view.wait()

        # Really tacky
        removed_item = view.itemid
        if removed_item == equipped['method']:
            equipped['method'] = None
        elif removed_item in equipped['techniques']:
            equipped['techniques'].pop(view.itemid)
        elif removed_item in equipped['weapons']:
            equipped['weapons'].pop(view.itemid)
        await Users.filter(user_id=member.id).update(equipped=equipped)
        embed = BasicEmbeds.right_tick("Removed the equipped item")

        await inter.edit_original_message(embed=embed)

    @admin.sub_command(name="boostshow", description="See boosts of someone else")
    async def boostshow(self, inter: disnake.CommandInteraction, member: disnake.Member):
        embed = disnake.Embed(
            color=disnake.Color(0x2e3135)
        )

        data = await Temp.filter(user_id=member.id).values_list("percent_cp", "percent_exp", "till")
        if data is None:
            embed.description = "No temp boosts"
        else:
            cp_m = []
            exp_m = []
            for boost in data:
                cp_boost, exp_boost, till = boost
                if cp_boost:
                    cp_m.append(f"CP Boost - `{boost[1]}%` - Ends <t:{round(float(till))}:R>")
                elif exp_boost:
                    exp_m.append(f"Exp Boost - `{boost[1]}%` - Ends <t:{round(float(till))}:R>")
            if len(cp_m) > 0:
                embed.add_field(name="CP Boosts", value="\n".join(m for m in cp_m), inline=False)
            if len(exp_m) > 0:
                embed.add_field(name="Exp Boosts", value="\n".join(m for m in exp_m), inline=False)
            embed.description = f"Currently showing **{len(cp_m) + len(exp_m)}** Boosts"

        await inter.response.send_message(embed=embed)

    @admin.sub_command(name="boostremove", description="Remove boosts of someone")
    async def boostremove(self, inter: disnake.CommandInteraction, member: disnake.Member):
        await Temp.filter(user_id=inter.author.id).delete()
        embed = BasicEmbeds.right_tick(f"Removed all the boost for {member.mention}")
        await inter.response.send_message(embed=embed)

    @admin.sub_command(name="remove_all_pets", description="Remove all the pets of someone")
    async def remove_all_pets(self, inter: disnake.CommandInteraction, member: disnake.Member):
        await Pet.filter(user_id=member.id).delete()
        embed = BasicEmbeds.right_tick(f"Removed all pets for {member.mention}")
        await inter.response.send_message(embed=embed)

    @admin.sub_command(name="energyadd", description="Give energy to a single player")
    async def energy_add(self, inter: disnake.CommandInteraction, member: disnake.Member, amount: int):
        embed = BasicEmbeds.exclamation(f"Giving energy to {member.name}")
        await inter.response.send_message(embed=embed)

        player: Player = PlayerRoster().find_player_for(inter, member)
        async with player:
            player.add_energy(amount, True)

        self._log(player.id, f"Gained {amount}")

        embed = BasicEmbeds.right_tick(f"Given the energy to the user")
        await inter.edit_original_message(embed=embed)

    @admin.sub_command(name="energyremove", description="Take energy from someone")
    async def energy_remove(self, inter: disnake.CommandInteraction, member: disnake.Member, amount: int):
        player: Player = PlayerRoster().find_player_for(inter, member)
        async with player:
            player.consume_energy(amount, True)

        embed = BasicEmbeds.right_tick(f"Removed {amount} energy from {member.name}")
        await inter.response.send_message(embed=embed)

    @adminreset.sub_command(name="reset_msg_limit", description="Reset message limit for a person")
    async def reset_msg_limit(self, inter: disnake.CommandInteraction, member: disnake.Member):
        player: Player = PlayerRoster().find_player_for(inter, member)
        async with player:
            player.daily_message_count = 0

        await inter.response.send_message(embed=BasicEmbeds.right_tick(f"Limit Refreshed for `{member.name}`"))

    @admin.sub_command(name="alchemy_set", description="Set alchemy stats")
    async def alchemy_set(self, inter: disnake.CommandInteraction, member: disnake.Member, user_tier: int, user_exp: int = 0, tier_chance: int = 5):
        await Alchemy.filter(user_id=member.id).update(next_tier_chance=tier_chance, pill_refined={}, a_lvl=user_tier, a_exp=user_exp)
        embed = BasicEmbeds.right_tick(f"Tier Set to `{user_tier}` for `{member.name}`")
        await inter.response.send_message(embed=embed)

    @admin.sub_command(name="craft_set", description="Set craft stats")
    async def craft_set(self, inter: disnake.CommandInteraction, member: disnake.Member, user_tier: int, user_exp: int = 0):
        await Crafting.filter(user_id=member.id).update(c_lvl=user_tier, c_exp=user_exp)
        embed = BasicEmbeds.right_tick(f"Crafting tier set to `{user_tier}`, `{user_exp}` EXP for `{member.name}`")
        await inter.response.send_message(embed=embed)

    @admin.sub_command(name="mass_give", description="Command used to compensate all the users")
    @commands.is_owner()
    async def mass_give(self, inter: disnake.CommandInteraction, gold: int, exp: int, energy: int):
        roster: PlayerRoster = PlayerRoster()
        players: list[Player] = roster.list()
        if gold > 0 or energy > 0:
            await Users.all().update(money=F("money") + gold, energy=F("energy") + energy)
            for player in players:
                player.add_funds(gold)
                player.add_energy(energy, True)

        if exp > 0:
            await Cultivation.all().update(current_exp=F("current_exp") + exp)
            for player in players:
                await player.add_experience(exp, False)

        embed = BasicEmbeds.right_tick(f"Gave everyone {energy} energy, {gold} gold and {exp} exp")
        await inter.response.send_message(embed=embed)

    @adminreset.sub_command(name="daily_reset", description="Command used to compensate all the users")
    @commands.is_owner()
    async def daily_reset(self, inter: disnake.CommandInteraction):
        await time_flow(inter.bot).daily_reset()
        embed = BasicEmbeds.right_tick(f"Reset!")
        await inter.response.send_message(embed=embed)

    @adminreset.sub_command(name="daily_user_reset", description="Command used to compensate all the users")
    @commands.is_owner()
    async def daily_user_reset(self, inter: disnake.CommandInteraction, member: disnake.Member):
        player: Player = PlayerRoster().find_player_for(inter, member)
        async with player:
            player.daily_message_count = 0
            player.claimed_daily = False

        await Pvp.filter(user_id=member.id).update(pvp_cooldown=0)

        embed = BasicEmbeds.right_tick(f"Reset! for {member.name}")
        await inter.response.send_message(embed=embed)

    @adminreset.sub_command(name="daily_money_reset", description="Command used to give daily pvp rewards manually")
    @commands.is_owner()
    async def daily_pvp_reward(self, inter: disnake.CommandInteraction):
        all_users = await Pvp.all().values_list("rank_points", "user_id")
        roster: PlayerRoster = PlayerRoster()

        roster.reset_local_daily_cooldown()

        # for user in all_users:
        #     rank_point, user_id = user
        #
        #     elo_rank, elo_sub_rank, excess_points = elo_from_rank_points(rank_point)
        #     user_rank_reward = PVP_REWARDS[f"{elo_sub_rank} {elo_rank}"]
        #     money, coins = user_rank_reward
        #     player: Player = roster.get(user_id)
        #     async with player:
        #         player.add_funds(money, CURRENCY_NAME_GOLD)
        #         player.add_funds(coins, CURRENCY_NAME_ARENA_COIN)
        #
        embed = BasicEmbeds.right_tick(f"Reset!")
        await inter.response.send_message(embed=embed)

def setup(bot):
    cog: Admin = Admin(bot)
    bot.add_cog(cog)
    log_event("system", "admin", f"{cog.name} Created", "INFO")

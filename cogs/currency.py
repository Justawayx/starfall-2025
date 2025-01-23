import disnake
import random
import math

from disnake.ext import commands

from tortoise.expressions import F

from adventure.auction import AuctionHouse
from character.player import Player, PlayerRoster

from utils.Database import Pvp, Cultivation, Users
from utils.DatabaseUtils import compute_market_userinfo
from utils.CommandUtils import give_patron_role_bonus, VoteLinkButton, PatreonLinkButton


from utils.EconomyUtils import get_tax_details, CURRENCY_NAME_STAR, CURRENCY_NAME_ARENA_COIN, CURRENCY_NAME_GOLD
from utils.Embeds import BasicEmbeds
from utils.LoggingUtils import log_event

from utils.ParamsUtils import elo_from_rank_points, MONEY_CARD_LINES
from utils.Styles import EXCLAMATION
from utils.base import BaseStarfallCog

from cogs.eventshop import EVENT_CONFIG, EVENT_SHOP
from utils.InventoryUtils import add_to_inventory

# =====================================
# Currency specific params
# =====================================


DAILY_STIPEND = {
    0: {"min": 10, "max": 200},
    1: {"min": 200, "max": 1000},
    2: {"min": 1000, "max": 2000},
    3: {"min": 2000, "max": 10_000},
    4: {"min": 10_000, "max": 20_000},
    5: {"min": 20_000, "max": 100_000},
    6: {"min": 100_000, "max": 200_000},
    7: {"min": 200_000, "max": 1_000_000},
    8: {"min": 1_000_000, "max": 2_000_000},
    9: {"min": 1_000_000, "max": 2_000_000},
    10: {"min": 1_000_000, "max": 2_000_000},
    11: {"min": 2_000_000, "max": 10_000_000},
    12: {"min": 10_000_000, "max": 20_000_000},
    13: {"min": 10_000_000, "max": 20_000_000},
    14: {"min": 20_000_000, "max": 20_000_000},
}

PVP_REWARDS = {
    "High Tian": [5000000, 500000],
    "Middle Tian": [2500000, 250000],
    "Low Tian": [1000000, 100000],
    "High Di": [600000, 60000],
    "Middle Di": [400000, 40000],
    "Low Di": [200000, 20000],
    "High Xuan": [100000, 10000],
    "Middle Xuan": [75000, 7500],
    "Low Xuan": [50000, 5000],
    "High Huang": [20000, 2000],
    "Middle Huang": [10000, 1000],
    "Low Huang": [5000, 500],
    " Unranked": [0, 0]  # Don't fix the space
}


async def daily_market_income(user_id):
    listing_tax, sell_tax, buy_tax, item_limit, market_points, user_market_tier = await compute_market_userinfo(user_id)
    if user_market_tier == 3:
        return 500_000
    elif user_market_tier == 4:
        return 1_500_000
    elif user_market_tier == 5:
        return 5_000_000
    else:
        return 0


class Currency(BaseStarfallCog):
    def __init__(self, bot: commands.Bot):
        super().__init__(bot, "Currency", "currency")

    async def _do_load(self):
        pass

    def _do_unload(self):
        pass

    @commands.slash_command(name="daily", description="Earn daily income")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def slash_daily(self, inter: disnake.CommandInteraction):
        await inter.response.defer()

        view = disnake.ui.View()
        view.add_item(VoteLinkButton())
        view.add_item(PatreonLinkButton())

        player: Player = PlayerRoster().find_player_for(inter)
        if player.claimed_daily:
            embed = BasicEmbeds.exclamation(f"Daily limit reached, please come back tomorrow to claim!")
            await inter.edit_original_message(embed=embed)
            return

        user_id: int = inter.author.id
        major: int = player.cultivation.major

        user = await Cultivation.get_or_none(user_id=user_id).values_list("major", "minor", "user__money_cooldown", "user__patreon_cooldown")
        rank_points = await Pvp.get_or_none(user_id=user_id).values_list("rank_points", flat=True)

        min_stipend = DAILY_STIPEND[major]["min"]
        max_stipend = DAILY_STIPEND[major]["max"]
        money = random.randint(min_stipend, max_stipend)
        energy = 0

        tax_percent, tax_amount, total_tax = await get_tax_details(user_id)
        tax_increase = math.floor((tax_percent / 100) * money)

        excess_tax = tax_amount / (money + tax_increase)
        excess_tax_str = None
        excess_tax_return = 0
        if 4.4 > excess_tax > 2.3:
            excess_tax_return += math.floor(tax_amount * 0.44)
            excess_tax_str = f"\nYou got extra +{excess_tax_return:,} gold for paying high tax\n"
        elif 8.3 > excess_tax >= 4.4:
            excess_tax_return += math.floor(tax_amount * 0.35)
            excess_tax_str = f"\nYou got extra +{excess_tax_return:,} gold for paying very high taxes (||Need mooaar||)\n"
        elif excess_tax >= 8.3:
            excess_tax_return += math.floor(tax_amount * 0.25)
            excess_tax_str = f"\nYou got extra +{excess_tax_return:,} gold for paying enormously high taxes (||Let it rain baby||)\n"

        market_money = await daily_market_income(user_id)

        patreon_bonus = await give_patron_role_bonus(inter.author)
        patreon_cooldown = int(user[3])
        patreon_text = None
        if patreon_cooldown > 1:
            patreon_text = f"\n*Next patreon bonus after {patreon_cooldown - 1} days*"
        if patreon_bonus:
            patreon_text = f"\n\n{EXCLAMATION} Thank you for subscribing to a membership!"
            if patreon_cooldown <= 1:
                log_event(user_id, "patreon", f"Patreon bonus")

        booster_text = None
        if inter.author.premium_since is not None:
            booster_text = f"\n\n{EXCLAMATION} Thank you for boosting the server! You can claim 1x `Attribute point reset` once a month"

        elo_rank, elo_sub_rank, excess_points = elo_from_rank_points(rank_points)
        user_rank_reward = PVP_REWARDS[f"{elo_sub_rank} {elo_rank}"]
        pvp_money, pvp_coins = user_rank_reward

        pvp_text = f"Here is your reward for being ranked {elo_sub_rank} {elo_rank} in PvP arena: +{pvp_money:,} gold and +{pvp_coins:,} AC"

        money_income: int = money + tax_increase + market_money + pvp_money + excess_tax_return
        async with player:
            player.claimed_daily = True
            player.add_funds(money_income)
            player.add_funds(pvp_coins, CURRENCY_NAME_ARENA_COIN)
            if energy > 0:
                player.add_energy(energy)

        if patreon_cooldown <= 1 and patreon_bonus is not None:
            await Users.filter(user_id=user_id).update(patreon_cooldown=patreon_bonus["cooldown"])

        # Event token drops
        token_text = ""
        if EVENT_SHOP.is_active and hasattr(self.bot.get_cog("EventManager"), "current_event"):
            event_manager = self.bot.get_cog("EventManager")
            current_event = event_manager.current_event
            if current_event and EVENT_CONFIG[current_event]["sources"]["daily_bonus"]:
                drop_config = EVENT_CONFIG[current_event]["drop_rates"]["daily"]
                if random.randint(1, 100) <= drop_config["chance"]:
                    token_amount = random.randint(drop_config["min"], drop_config["max"])
                    token_id = EVENT_CONFIG[current_event]["token_id"]
                    await add_to_inventory(inter.author.id, token_id, token_amount)
                    token_text = f"\n\nReceived {token_amount}x {token_id} from the event!"
                    log_event(inter.author.id, "event", f"Gained {token_amount}x {token_id} from daily")

        # Add token_text to the embed description
        embed = BasicEmbeds.add_plus(
            f"You've claimed {money:,} (+{tax_increase:,}) gold {excess_tax_str if excess_tax_str else ''}"
            f"\n{f'Here is a little bonus for being a vip in market.. Hope you like it! (+{market_money:,} gold)' if market_money > 1 else ''} {patreon_text if patreon_text else ''} {booster_text if booster_text else ''}"
            f"\n\n{pvp_text}"
            f"{token_text}"
            f"\n\nYou have paid a total of {tax_amount:,} gold as tax, contributed {tax_percent}% to total tax")

        embed.set_footer(text=f"A total of {total_tax:,} was collected yesterday")

        log_event(inter.author.id, "economy", f"Gained {money:,} (tax+{tax_increase:,}) (market+{market_money:,}) from daily")

        await inter.edit_original_message(content="*Want to help the developer team? check out our patreon by tapping the button below*", embed=embed, view=view)

    CurrencyTypes = commands.option_enum([
        CURRENCY_NAME_GOLD, CURRENCY_NAME_ARENA_COIN, CURRENCY_NAME_STAR
    ])

    @commands.slash_command(name="balance", description="Shows your balance")
    async def slash_balance(self, inter: disnake.CommandInteraction,
                            currency: CurrencyTypes = commands.Param(default=CURRENCY_NAME_GOLD, description="Defaults to Gold, type 'ac' to use PVP Arena Coins instead"),
                            member: disnake.Member = None):

        if not member:
            member = inter.author

        balance_str = self.show_balance(member.id, currency, member == inter.author)
        await inter.send(embed=disnake.Embed(description=balance_str, color=member.color), ephemeral=True)

    @commands.slash_command(name="money")
    @commands.default_member_permissions(manage_messages=True)
    async def slash_money(self, inter):
        """
        Parent Command
        """
        pass

    @slash_money.sub_command(name="add", description="Give money to someone")
    async def slash_money_add(self, inter: disnake.CommandInteraction,
                              member: disnake.Member,
                              amount: int = commands.Param(1, gt=0),
                              currency: CurrencyTypes = commands.Param(default=CURRENCY_NAME_GOLD, description="Defaults to Gold, type 'ac' to use PVP Arena Coins instead")):

        async with PlayerRoster().find_player_for(inter, member) as player:
            player.add_funds(amount, currency)

        embed = disnake.Embed(
            description=f"Gave `{amount:,}` {self.get_currency_str(currency)} to {member.mention}",
            color=disnake.Color(0x2e3135)
        )
        await inter.response.send_message(embed=embed)

    @slash_money.sub_command(name="remove", description="Take money from someone")
    async def remove(self, inter: disnake.CommandInteraction,
                     member: disnake.Member,
                     amount: int = commands.Param(1, gt=0),
                     currency: CurrencyTypes = commands.Param(default=CURRENCY_NAME_GOLD, description="Defaults to Gold, type 'ac' to use PVP Arena Coins instead")):

        async with PlayerRoster().find_player_for(inter, member) as player:
            if player.spend_funds(amount, currency):
                embed = disnake.Embed(
                    description=f"Took `{amount:,}` {self.get_currency_str(currency)} from {member.mention}",
                    color=disnake.Color(0x2e3135)
                )
                await inter.response.send_message(embed=embed)
            else:
                await inter.response.send_message("No don't steal", ephemeral=True)

    @staticmethod
    def get_currency_str(currency: str) -> str:
        if currency == CURRENCY_NAME_GOLD:
            return 'Gold'
        elif currency == CURRENCY_NAME_ARENA_COIN:
            return 'Arena Coins'
        elif currency == CURRENCY_NAME_STAR:
            return 'Stars'
        else:
            return 'Gold'

    @staticmethod
    def show_balance(user_id: int, currency: str = 'gold', split_escrow: bool = False):
        roster: PlayerRoster = PlayerRoster()
        player: Player = roster.get(user_id)
        if currency == "gold":
            currency_str = 'Gold'
            funds: int = player.current_gold
            escrow: int = AuctionHouse().get_escrow(user_id)
        elif currency == "ac":
            currency_str = 'Arena Coins'
            funds = player.current_arena_coins
            escrow: int = 0
        else:
            currency_str = "Stars"
            funds = player.current_stars
            escrow: int = 0

        if split_escrow and escrow > 0:
            money_str = f"`{funds:,}` (`+{escrow:,}` in auction escrow)"
        else:
            money_str = f"`{funds + escrow:,}`"

        if currency == 'gold':
            card = "ten"
            for value in MONEY_CARD_LINES.keys():
                if funds + escrow <= value:
                    card = MONEY_CARD_LINES[value]
                    break
            balance_str = f"Purple card lines: **{card}**\n{currency_str}: {money_str}"
        else:
            balance_str = f"{currency_str}: {money_str}"

        return balance_str


def setup(bot):
    bot.add_cog(Currency(bot))
    print("[Currency] Loaded")

from datetime import datetime, timedelta
from typing import Union, Optional

import disnake
from disnake.ext import commands, tasks
from tortoise.expressions import F

from world.continent import Continent
from character.player import PlayerRoster, Player, ENERGY_RECOVERY_RATE_MINUTES
from utils.CommandUtils import check_for_temp

from utils.DatabaseUtils import add_permanent_boost, remove_permanent_boost
from utils.Embeds import BasicEmbeds
from utils.LoggingUtils import log_event
from utils.ParamsUtils import PATREON_ROLES
from utils.base import BaseStarfallCog, CogNotLoadedError

from utils.EconomyUtils import check_for_tax
from utils.Database import Cultivation, Users, Pvp, GuildOptionsDict


class TimeFlow(BaseStarfallCog):
    def __init__(self, bot: commands.Bot):
        super().__init__(bot, "Time Flow Cog", "timeflow")
        self._daily_reset_time = datetime.strptime("05:00:00", "%H:%M:%S").time()

    # ========================================= Disnake lifecycle methods ========================================

    async def _do_load(self):
        if not self.refresh_cooldown.is_running():
            self.refresh_cooldown.start()
        if not self.recharge_energy.is_running():
            self.recharge_energy.start()

    def _do_unload(self):
        self.refresh_cooldown.cancel()
        self.recharge_energy.cancel()

    @tasks.loop(minutes=1)
    async def refresh_cooldown(self):
        now: datetime = datetime.utcnow()  # We really want utcnow here
        today_reset_time: datetime = datetime.combine(now.date(), self._daily_reset_time)
        since_reset: timedelta = now - today_reset_time

        if 0 <= since_reset.total_seconds() < 60:
            await self.daily_reset()

        # TODO: Declare 4 to 8 oqi increase times and divide the oqi counter drop chance value by the same factor (4 times per day but worth 100, or 8 times a day worth 50)

        await check_for_temp(self.bot)

    @tasks.loop(minutes=ENERGY_RECOVERY_RATE_MINUTES)
    async def recharge_energy(self):
        to_notify: list[int] = []
        await Users.filter(energy__lt=F("max_energy")).update(energy=F("energy") + 1)
        for player in PlayerRoster().list():
            _, capped = player.regen_energy()
            if capped:
                to_notify.append(player.id)

        if len(to_notify) > 0:
            world: Continent = Continent()
            embed = BasicEmbeds.exclamation(f"You just capped your energy")
            for user_id in to_notify:
                await world.whisper(user_id, embed)

    @refresh_cooldown.before_loop
    @recharge_energy.before_loop
    async def before_number(self):
        await self.bot.wait_until_ready()

    async def daily_reset(self):
        await Cultivation.all().update(msg_limit=0)
        await Users.all().update(money_cooldown=0, patreon_cooldown=F("patreon_cooldown") - 1)
        await Pvp.all().update(pvp_cooldown=0)

        PlayerRoster().reset_local_daily_values()
        _log("ALL", "Reset Message limit, daily command, and pvp command")

        new_tax, old_tax = await check_for_tax()
        await GuildOptionsDict.filter(name="old_tax_details").update(value=new_tax)
        await GuildOptionsDict.filter(name="new_tax_details").update(value='{}')
        _log("ALL", "Reset New tax and updated Old Tax")

        await self._increase_qi_chance()

        all_users = await Users.all().values_list("pill_used", "user_id")
        for user in all_users:
            pill_used_list, user_id = user
            pill_list_update = [pill_id for pill_id in pill_used_list if pill_id != 'recpill']
            if len(pill_list_update) < len(pill_used_list):
                await Users.filter(user_id=user_id).update(pill_used=pill_list_update)

        _log("ALL", "Upgraded pill list (recpill) and added pvp rewards")

        await Users.filter(money__lt=1).update(money=1)

    @commands.Cog.listener()
    async def on_member_update(self, before: disnake.Member, after: disnake.Member):
        old_role_ids: set[int] = {role.id for role in before.roles}
        new_role_ids: set[int] = {role.id for role in after.roles}

        added_role_ids: set[int] = new_role_ids.difference(old_role_ids)
        removed_role_ids: set[int] = old_role_ids.difference(new_role_ids)

        for role_id in sorted(list(PATREON_ROLES.keys()), reverse=True):
            if role_id in added_role_ids:  # Added role
                patreon_bonus = PATREON_ROLES[role_id]
                cp, exp = patreon_bonus["cp"], patreon_bonus["exp"]
                if cp > 0 or exp > 0:
                    await add_permanent_boost(after.id, cp, exp)
                break

            elif role_id in removed_role_ids:  # Removed role
                patreon_bonus = PATREON_ROLES[role_id]
                cp, exp = patreon_bonus["cp"], patreon_bonus["exp"]
                if cp > 0 or exp > 0:
                    await remove_permanent_boost(before.id, cp, exp)
                break

    @commands.Cog.listener()
    async def on_message(self, message: disnake.Message):
        author: Union[disnake.User, disnake.Member] = message.author
        if not author.bot:
            if message.guild is None:
                print(f"{author}: {message.content}")
            else:
                await self._add_message_experience_if_possible(message)

    @commands.Cog.listener()
    async def on_slash_command(self, inter: disnake.ApplicationCommandInteraction):
        user_id: int = inter.author.id
        await PlayerRoster().ensure_player(user_id)
        _log(user_id, f"About to invoke /{inter.application_command.qualified_name}", "DEBUG")

    @commands.Cog.listener()
    async def on_slash_command_completion(self, inter: disnake.ApplicationCommandInteraction):
        if await self._add_message_experience_if_possible(inter):
            _log(inter.author.id, f"Completed /{inter.application_command.qualified_name}", "DEBUG")

    async def _add_message_experience_if_possible(self, event: Union[disnake.ApplicationCommandInteraction, disnake.Message]) -> bool:
        if self._check_command_cooldown(event):
            user_id: int = event.author.id
            player: Player = await PlayerRoster().ensure_player(user_id)
            if player is not None:
                await player.add_message_experience()

            return True

        return False

    @staticmethod
    def _check_command_cooldown(event: Union[disnake.ApplicationCommandInteraction, disnake.Message]) -> bool:
        author: Union[disnake.User, disnake.Member] = event.author
        role: disnake.Role = Continent().breakthrough_role

        return role not in author.roles

    @staticmethod
    async def _increase_qi_chance() -> None:
        world: Continent = Continent()
        initial_counter: int = world.origin_qi_counter
        await world.increase_origin_qi_counter()
        _log("ALL", f"Upgrade Qi Counter from {initial_counter} to {world.origin_qi_counter}")


class TimeFlowNotLoadedError(CogNotLoadedError):
    def __init__(self):
        super().__init__()


def _log(user_id: Union[int, str], message: str, level: str = "INFO"):
    log_event(user_id, "timeflow", message, level)


# The bootstrap code
def setup(bot: commands.Bot):
    cog = TimeFlow(bot)
    bot.add_cog(cog)
    _log("system", f"{cog.name} Created")


def time_flow(bot: commands.Bot) -> TimeFlow:
    flow: Optional[TimeFlow] = bot.get_cog("TimeFlow")
    if flow is None:
        raise TimeFlowNotLoadedError()

    return flow

from typing import Union

from disnake.ext import commands, tasks

from adventure.battle import BattleManager
from utils.LoggingUtils import log_event
from utils.base import BaseStarfallCog

_SHORT_NAME: str = "battle"


class BattleManagerCog(BaseStarfallCog):
    def __init__(self, bot: commands.Bot):
        super().__init__(bot, "Battle Manager Cog", _SHORT_NAME)

    # ========================================= Disnake lifecycle methods ========================================

    async def _do_load(self):
        if not self.periodic_purge.is_running():
            self.periodic_purge.start()

    def _do_unload(self):
        if self.periodic_purge.is_running():
            self.periodic_purge.cancel()

    @tasks.loop(hours=12)
    async def periodic_purge(self):
        await BattleManager().purge_irrelevant_battles()


def _log(user_id: Union[int, str], message: str):
    log_event(user_id, _SHORT_NAME, message)


# The bootstrap code
def setup(bot: commands.Bot):
    cog = BattleManagerCog(bot)
    bot.add_cog(cog)
    _log("system", f"{cog.name} Created")

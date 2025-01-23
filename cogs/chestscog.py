from typing import Union

import disnake
from disnake.ext import commands

from adventure.chests import CHEST_TYPE_MIXED, CHEST_TYPES, MAX_CHEST_RANK, MAX_CHEST_TIER, ChestLootConfig
from world.compendium import ItemCompendium
from utils.LoggingUtils import log_event
from utils.base import BaseStarfallCog
from utils.loot import Loot

_SHORT_NAME = "chests"


class ChestCog(BaseStarfallCog):
    def __init__(self, bot: commands.Bot):
        super().__init__(bot, "Chest Loot Configuration Cog", _SHORT_NAME)

    # ============================================= Discord commands ============================================

    @commands.slash_command(name="chest_admin")
    @commands.default_member_permissions(manage_guild=True)
    async def slash_chest_admin(self, _: disnake.CommandInteraction):
        pass

    @slash_chest_admin.sub_command(name="loot_test", description="Test chest loot")
    async def slash_chest_admin_loot_test(
            self,
            inter: disnake.CommandInteraction,
            chest_type: str = commands.Param(CHEST_TYPE_MIXED, choices=CHEST_TYPES, name="type", description="The chest type"),
            rank: int = commands.Param(1, ge=1, le=MAX_CHEST_RANK, description=f"The chest rank [1, {MAX_CHEST_RANK}]"),
            tier: int = commands.Param(0, ge=0, le=MAX_CHEST_TIER, description=f"The chest tier [0, {MAX_CHEST_TIER}]. 0 means random tier"),
            times: int = commands.Param(1, ge=1, le=10000, description=f"The number of times the test should be ran [1, 10,000]")
    ):
        await inter.response.defer()

        loot: Loot = ChestLootConfig().loot(chest_type, rank, None if tier == 0 else tier)
        looted: dict[str, int] = loot.roll(times)
        chest_desc: str = f"rank {rank} {chest_type} chest" if tier == 0 else f"rank {rank} tier {tier} {chest_type} chest"
        loot_desc: str = ItemCompendium().describe_dict(looted)

        await inter.followup.send(f"Rolling the loot {times:,} times for a {chest_desc} yielded:\n{loot_desc}")


def _log(user_id: Union[int, str], message: str):
    log_event(user_id, _SHORT_NAME, message)


# The bootstrap code
def setup(bot: commands.Bot):
    cog = ChestCog(bot)
    bot.add_cog(cog)
    _log("system", f"{cog.name} Created")

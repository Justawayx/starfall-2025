import random
from typing import Union, Callable, Optional

import disnake
from disnake.ext import commands, tasks

from character.player import PlayerRoster
from gaming.catalog import GameCatalog
from gaming.game import Game
from gaming.gaminghouse import GamingHouse
from utils.LoggingUtils import log_event
from utils.base import BaseStarfallCog

_SHORT_NAME = "gaming"

DICE_MIN_RESULT: int = 1
DICE_MAX_RESULT: int = 6


def _format_list(values: list[str]) -> str:
    if len(values) == 0:
        return "<nothing>"
    elif len(values) == 1:
        return values[0]
    else:
        return ", ".join(values)


async def _roll_internal(inter: disnake.CommandInteraction, min_value: int, max_value: int, times: int, verb: str = "rolled", value_replacer: Callable[[int], str] = lambda n: f"{n:,}"):
    if times <= 1:
        times = 1

    if max_value <= min_value:
        max_value = min_value

    if times <= 1:
        await inter.response.send_message(f"You {verb} {value_replacer(random.randint(min_value, max_value))}")
    else:
        await inter.response.send_message(f"You {verb} {_format_list([value_replacer(random.randint(min_value, max_value)) for _ in range(0, times)])}")


class GamingCog(BaseStarfallCog):
    def __init__(self, bot: commands.Bot):
        super().__init__(bot, "Gaming House Cog", _SHORT_NAME)

    async def _initialize_views(self) -> list[disnake.ui.View]:
        return GamingHouse().persistent_views

    # ============================================== Discord tasks ==============================================

    @tasks.loop(seconds=20)
    async def check_expiration(self):
        pass

    # ============================================= Discord commands ============================================

    @commands.slash_command(name="random")
    async def slash_random(self, _: disnake.CommandInteraction):
        pass

    @slash_random.sub_command(name="dice", description="Roll a 6-faced dice up to 10 times")
    async def slash_random_dice(
            self,
            inter: disnake.CommandInteraction,
            times: int = commands.Param(default=1, name="times", description=f"The number of times the dice should be rolled [1, 10]", ge=1, le=10)
    ):
        await _roll_internal(inter, DICE_MIN_RESULT, DICE_MAX_RESULT, times)

    @slash_random.sub_command(name="number", description="Roll random number between [min, max] up to 10 times")
    async def slash_random_number(
            self,
            inter: disnake.CommandInteraction,
            min_value: int = commands.Param(default=1, name="min", description=f"The maximum number. Default: 1", ge=-1_000_000, le=1_000_000),
            max_value: int = commands.Param(default=100, name="max", description=f"The maximum number. Default: 100", ge=-1_000_000, le=1_000_000),
            times: int = commands.Param(default=1, name="times", description=f"The number of times the roll should be made [1, 10]", ge=1, le=10)
    ):
        await _roll_internal(inter, min_value, max_value, times)

    @slash_random.sub_command(name="toss", description="Toss a coin up to 10 times")
    async def slash_random_dice(
            self,
            inter: disnake.CommandInteraction,
            times: int = commands.Param(default=1, name="times", description=f"The number of times the toss should be made [1, 10]", ge=1, le=10)
    ):
        await _roll_internal(inter, 0, 1, times, "tossed", lambda v: "Tail" if v == 0 else "Head")

    @commands.slash_command(name="game_admin")
    @commands.default_member_permissions(manage_guild=True)
    async def slash_game_admin(self, _: disnake.CommandInteraction):
        pass

    @slash_game_admin.sub_command(name="setup", description="Setup a new game table")
    async def slash_game_admin_setup(
            self,
            inter: disnake.CommandInteraction,
            game_name: str = commands.Param(default=None, name="game", description="The game to start between various players", choices=GameCatalog().game_names)
    ):
        catalog: GameCatalog = GameCatalog()
        game: Optional[Game] = catalog.get_by_name(game_name)
        if game is not None:
            await GamingHouse().prepare_new_table(game, PlayerRoster().find_player_for(inter), inter)
            await inter.send("Launched the gaming table setup wizard", ephemeral=True)
        else:
            await inter.send(f"Could not locate {game_name}", ephemeral=True)


def _log(user_id: Union[int, str], message: str):
    log_event(user_id, _SHORT_NAME, message)


# The bootstrap code
def setup(bot: commands.Bot):
    cog = GamingCog(bot)
    bot.add_cog(cog)
    _log("system", f"{cog.name} Created")

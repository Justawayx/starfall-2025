import disnake
import os

import disnake
from disnake.ext import commands
from disnake.ext.commands import CommandSyncFlags
from dotenv import load_dotenv
import topgg

from adventure.auction import AuctionHouse
from adventure.battle import BattleManager
from world.bestiary import Bestiary
from adventure.chests import ChestLootConfig
from adventure.ruins import RuinsManager
from world.compendium import ItemCompendium
from character.player import PlayerRoster
from world.continent import Continent
from utils.Database import init_database
from character.inventory import RingStorage

load_dotenv()

VERSION = "1.1.1"
TOKEN = os.getenv("MAIN_TOKEN")

INTENTS = disnake.Intents.default()
INTENTS.members = True
INTENTS.message_content = True

GUILD_ID_PROD: int = 352517656814813185
GUILD_ID_BETA: int = 779435063678861383


class MyBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.main_guild = GUILD_ID_PROD
        self.breakthrough_role = 1010445866483601458


bot = MyBot(command_prefix="s!", intents=INTENTS, test_guilds=[GUILD_ID_BETA], help_command=None)

# This example uses topggpy's webhook system.
bot.topgg_webhook = topgg.WebhookManager(bot).dsl_webhook("/dslwebhook", "starfallone")

# The port must be a number between 1024 and 49151.
bot.topgg_webhook.run(65518)
print("Started Topgg webhook")


@bot.event
async def on_ready():
    print("Main Ready!")


@bot.command()
@commands.has_permissions(manage_guild=True)
async def reload(ctx, extension):
    """Reload the extension"""
    bot.reload_extension(f"cogs.{extension}")
    await ctx.send(embed=disnake.Embed(
        description=f"`{extension.upper()}` reloaded!",
        color=disnake.Color.dark_gold()))


@bot.command()
@commands.has_permissions(manage_guild=True)
async def load(ctx, extension):
    """load the extension"""
    bot.load_extension(f"cogs.{extension}")
    await ctx.send(embed=disnake.Embed(
        description=f"`{extension.upper()}` loaded!",
        color=disnake.Color.dark_gold()))


async def load_all():
    await Continent().load(bot)
    await ItemCompendium().load()
    await Bestiary().load()
    await ChestLootConfig().load()
    await RingStorage().load()
    await PlayerRoster().load()
    await AuctionHouse().load()
    await BattleManager().load()
    await RuinsManager().load()
    # await GamingHouse().load()


# Load the database before loaded the modules since module initialization may depend on the database
bot.loop.run_until_complete(init_database())
bot.loop.run_until_complete(load_all())

# Load the module
for file in os.listdir(f"./cogs"):
    if not file.startswith("!") and file.endswith(".py") and file != "__init__.py":
        bot.load_extension(f"cogs.{file[:-3]}")

# Main loop
bot.run(TOKEN)

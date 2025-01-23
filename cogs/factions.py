import disnake
import json

from disnake.ext import commands

from character.player import PlayerRoster, Player
from utils.ParamsUtils import get_major_rank_role_id
from utils.Database import Factions
from world.cultivation import PlayerCultivationStage

with open("factions.json", "r") as f:
    FACTIONS = json.load(f)


class FactionsDropdown(disnake.ui.Select):
    def __init__(self, roles, bot):
        self.bot = bot
        options = [
            *(disnake.SelectOption(label=f"{roles[i].name}", value=f"{roles[i].id}") for i in range(len(roles))),
        ]

        super().__init__(
            custom_id="main_role_menu",
            placeholder="Choose a role to toggle",
            max_values=1,
            options=options,
        )


class FactionsView(disnake.ui.View):
    def __init__(self, roles, bot):
        super().__init__(timeout=None)

        self.add_item(FactionsDropdown(roles, bot))


class FactionsMenu(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command()
    @commands.default_member_permissions(manage_messages=True)
    async def factionsmenu(self, ctx):
        """
        Create a Faction RoleMenu
        """
        roles = []
        values = []

        for faction in FACTIONS["factions"]:
            role = ctx.guild.get_role(faction["role"])
            roles.append(role)
            values.append((faction["name"],
                           f"({role.mention})"
                           f"\n **Tier :** **`{faction['tier']}`**"
                           f"\n **Class Required to join :** <@&{get_major_rank_role_id(faction['condition']['major'])}> "
                           f"\n **Xp Bonus :** **`{faction['multiplier']}`%**"
                           f"\n **Description :** "
                           f"\n{faction['description']}"))

        view = FactionsView(roles, self.bot)
        embed = disnake.Embed(
            title="Factions-",
            color=disnake.Color(0x20aca0)
        )
        for name, value in values:
            embed.add_field(name=name, value=value, inline=False)

        await ctx.response.send_message(embed=embed, view=view)

    @commands.Cog.listener()
    async def on_dropdown(self, inter):
        if inter.component.custom_id == "main_role_menu":
            user_check = await Factions.get_or_none(user_id=inter.author.id).values_list("user_id", "name", "role_id", "multiplier")

            final_roles = inter.author.roles
            role = inter.guild.get_role(int(inter.values[0]))

            if user_check is not None and user_check[2] != role.id:
                await inter.response.send_message(f"You have already joined {user_check[1]}, please leave it before joining another faction.", ephemeral=True)
                return

            for faction in FACTIONS["factions"]:
                if faction['role'] == role.id:
                    realm = faction['condition']['name']
                    multiplier = faction['multiplier']
                    major = faction['condition']['major']
                    minor = faction['condition']['minor']

            player: Player = PlayerRoster().find_player_for(inter)
            cultivation: PlayerCultivationStage = player.cultivation

            if cultivation.major >= major and cultivation.minor >= minor:
                if role not in final_roles:
                    try:
                        final_roles.append(role)
                        content = f"Joined {role.mention}"
                        if user_check is None:
                            await Factions.create(user_id=inter.author.id, name=role.name, multiplier=multiplier, role_id=role.id)
                    except disnake.Forbidden:
                        content = f"**Bot does not have permissions to give** {role.mention}"
                else:
                    try:
                        final_roles.remove(role)
                        content = f"Left {role.mention}"
                        await Factions.filter(user_id=inter.author.id).delete()

                    except disnake.Forbidden:
                        content = f"**Bot does not have permissions to take** {role.mention}"

                await inter.author.edit(roles=final_roles)
                await inter.response.send_message(content=content, ephemeral=True)
            else:
                await inter.response.send_message(f"You must be {realm} to join this faction", ephemeral=True)


def setup(bot):
    bot.add_cog(FactionsMenu(bot))
    print("[Factions] Loaded")

import disnake
from disnake.ext import commands

role_name_id_dict = {
    "Starfall Updates": 1052537377324797982,
    "Starfall Events": 1078987851892539462
}

role_name_desc_dict = {
    "Starfall Updates": "Get notified about Starfall bot updates (patches, hotfixes and downtime; does NOT include events).",
    "Starfall Events": "Get notified about Starfall events."
}

ordered_role_names = sorted(role_name_id_dict.keys())


class RolesDropdown(disnake.ui.Select):
    def __init__(self, bot):
        self.bot = bot
        options = [*(disnake.SelectOption(label=f"{role}", value=f"{role_name_id_dict[role]}") for role in ordered_role_names), ]
        super().__init__(
            custom_id="general_role_menu",
            placeholder="Choose a role to toggle",
            max_values=len(ordered_role_names),
            options=options,
        )


class RolesView(disnake.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.add_item(RolesDropdown(bot))


class RolesMenu(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(name="rolesmenu", description="Create a menu for picking general roles")
    @commands.default_member_permissions(manage_messages=True)
    async def rolesmenu(self, ctx):
        view = RolesView(self.bot)
        embed = disnake.Embed(title="Server Roles -", color=disnake.Color(0x20aca0))
        for role_name in ordered_role_names:
            role = ctx.guild.get_role(role_name_id_dict[role_name])
            embed.add_field(name=f"{role_name}", value=f"({role.mention})\n{role_name_desc_dict[role_name]}", inline=False)
        await ctx.response.send_message(embed=embed, view=view)

    @commands.Cog.listener()
    async def on_dropdown(self, inter):
        if inter.component.custom_id == "general_role_menu":
            final_roles = inter.author.roles  # User's current roles
            role = inter.guild.get_role(int(inter.values[0]))  # Role to add/remove

            if role not in final_roles:  # Do not have role, therefore add
                try:
                    final_roles.append(role)
                    content = f"Joined {role.mention}"
                except disnake.Forbidden:
                    content = f"**Bot does not have permissions to give** {role.mention}"
            else:  # Have role, therefore remove
                try:
                    final_roles.remove(role)
                    content = f"Left {role.mention}"
                except disnake.Forbidden:
                    content = f"**Bot does not have permissions to take** {role.mention}"

            await inter.author.edit(roles=final_roles)
            await inter.response.send_message(content=content, ephemeral=True)


def setup(bot):
    bot.add_cog(RolesMenu(bot))
    print("[Roles] Loaded")

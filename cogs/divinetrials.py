import disnake
from disnake.ext import commands
from disnake.ui import Button, View
from disnake import ApplicationCommandInteraction

class DivineWeapons(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
    @commands.slash_command(
        name="divinetree",
        description="Shows the divine weapons evolution tree"
    )
    async def show_divine_tree(self, inter: ApplicationCommandInteraction):
        await inter.response.send_message("This command is currently under maintenance.")

class DivineTrialsSystem(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(name="divinetrials", description="Shows divine trials")
    async def slash_divinetrials(self, inter: disnake.CommandInteraction):
        
        embed1 = disnake.Embed(title="First Image", color=disnake.Color.blue()).set_image(url='https://cdn.discordapp.com/attachments/948305640227504198/1331874525188591629/image.png?ex=6793344f&is=6791e2cf&hm=93f5ce219fced4de8fc5414af45a7eec28711758fc0e8e3f0abc2a9b4e4f61bf&')
        embed1.add_field(name="Divine Weapon Trial", value="Challenge the Divine Guardian to prove your worth of wielding a divine weapon", inline=True)
        embed1.add_field(name="Sovereign Trial (Tier 1 Ascension)", value="Defeat the Sovereign Guardian to ascend your divine weapon to tier 2", inline=True)
        embed1.add_field(name="Emperor's Trial (Tier 2 Ascension)", value="Challenge the Emperor HolyGuardian to ascend your weapon to its ultimate form", inline=True)
        
        # Create an instance of the custom View
        view = DivineTrialsView()
        
        # Send all three embeds and the view (buttons) in one response
        await inter.response.send_message(embed=embed1, view=view)

class DivineTrialsView(View):
    def __init__(self):
        super().__init__(timeout=None)  # No timeout for persistent buttons

    @disnake.ui.button(label="Enter", style=disnake.ButtonStyle.primary, custom_id="enter_divinetrial")
    async def enter_divinetrial(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.send_message("Enter divine trial 1", ephemeral=True)

def setup(bot):
    bot.add_cog(DivineWeapons(bot))
    bot.add_cog(DivineTrialsSystem(bot))
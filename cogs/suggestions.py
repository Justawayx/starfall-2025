import disnake
from disnake.ext import commands

SUGGESTION_CHANNEL = 941564654310785045
APPROVE_CHANNEL = 941564693779206164


class Suggestion(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

# //////////////////////////////////////// #

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.channel_id == SUGGESTION_CHANNEL:
            if payload.emoji.name == "✅":
                channel = self.bot.get_channel(SUGGESTION_CHANNEL)
                message = await channel.fetch_message(payload.message_id)
                r_count = message.reactions[0].count
                if r_count >= 3:
                    embed = message.embeds[0]
                    content = f"A channel for '{embed.description}' needs to be created. \n\nBy- {embed.footer.text}"
                    send_channel = self.bot.get_channel(APPROVE_CHANNEL)
                    await send_channel.send(content)
                    await message.delete()

# //////////////////////////////////////// #

    @commands.slash_command(name="suggest", description="Suggest a title")
    async def slash_suggest(self, ctx,
                            donghua_title: str = commands.Param(name="donghua_title", description="Type the title you want to suggest")):
        s_channel = ctx.guild.get_channel(SUGGESTION_CHANNEL)

        embed = disnake.Embed(
            title="Donghua Suggestion",
            description=donghua_title,
            color=disnake.Color(0x62d7cf),
        )
        if ctx.author.avatar:
            embed.set_footer(text=ctx.author.name, icon_url=ctx.author.avatar.url)
        else:
            embed.set_footer(text=ctx.author.name)

        msg = await s_channel.send(embed=embed)
        await ctx.response.send_message("Thank you for your suggestion")
        await msg.add_reaction('✅')


def setup(bot):
    bot.add_cog(Suggestion(bot))
    print("[Suggestion] Loaded")

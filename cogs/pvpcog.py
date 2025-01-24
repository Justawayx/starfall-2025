import disnake
from disnake.ext import commands
from disnake.ui import Button, View
from typing import List, Optional, Tuple
from character.player import Player, PlayerRoster
from adventure.pvp import start_pvp_battle
# from utils.Embeds import create_embed
from utils.Styles import EXCLAMATION
from utils.base import CogNotLoadedError
# from character.pvp_stats import PvPStats

class MainBattleView(View):

    # Store actions taken by the player
    def __init__(self, guild: disnake.Guild, channel: disnake.TextChannel, challenger: disnake.Member):
        super().__init__(timeout=None)  # No timeout for persistent buttons


class InitialChallengeView(View):
    def __init__(self, guild: disnake.Guild, channel: disnake.TextChannel, challenger: disnake.Member):
        super().__init__(timeout=None)  # No timeout for persistent buttons
        self.guild = guild  # Store the guild
        self.channel = channel  # Store the channel
        self.challenger = challenger  # Store the challenger

    @disnake.ui.button(label="Accept", style=disnake.ButtonStyle.primary, custom_id="accept_challenge")
    async def accept_challenge(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        try:
            # Send a DM to the challenger
            challenger_embed = disnake.Embed(
                title="Challenge Accepted!",
                description=f"{inter.author.mention} has accepted your challenge!",
                color=disnake.Color.green()
            )
            await self.challenger.send(embed=challenger_embed)

            # Send a message to the public channel
            if self.channel:
                public_embed = disnake.Embed(
                    title="Challenge Accepted!",
                    description=f"{inter.author.mention} has accepted {self.challenger.mention}'s challenge!",
                    color=disnake.Color.green()
                )
                await self.channel.send(embed=public_embed)
            else:
                print(f"Channel not found or inaccessible.")

            # Respond to the opponent
            await inter.response.send_message("You accepted the challenge!", ephemeral=True)
        except Exception as e:
            print(f"Error in accept_challenge: {e}")
            await inter.response.send_message("Something went wrong. Please try again.", ephemeral=True)

    @disnake.ui.button(label="Reject", style=disnake.ButtonStyle.primary, custom_id="reject_challenge")
    async def reject_challenge(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        try:
            # Send a DM to the challenger
            challenger_embed = disnake.Embed(
                title="Challenge Rejected",
                description=f"{inter.author.mention} has rejected your challenge.",
                color=disnake.Color.red()
            )
            await self.challenger.send(embed=challenger_embed)

            # Respond to the opponent
            await inter.response.send_message("You rejected the challenge.", ephemeral=True)
        except Exception as e:
            print(f"Error in reject_challenge: {e}")
            await inter.response.send_message("Something went wrong. Please try again.", ephemeral=True)


class PvPCog(commands.Cog):
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.slash_command(name="pvp")
    async def pvp(self, inter: disnake.ApplicationCommandInteraction):
        """Base PvP command"""
        pass
    
    @pvp.sub_command(name="challenge")
    async def challenge(
        self,
        inter: disnake.ApplicationCommandInteraction,
        opponent: disnake.Member
    ):
        """Challenge another player to a PvP battle"""
        await inter.response.defer()
        
        # Get both players
        challenger : Player = PlayerRoster().find_player_for(inter, inter.author)
        challenged : Player = PlayerRoster().find_player_for(inter, opponent)
        
        if challenger is None or challenged is None:
            await inter.send("Both players need to be registered cultivators!")
            return
            
        if challenger._id == challenged._id:
            await inter.send("You can't challenge yourself!")
            return
            
        # Start battle
        # winner, embed = await start_pvp_battle(challenger, challenged)
        embed = disnake.Embed(
            title="A new challenger approaches!",
            description=f"<@{challenger.id}> has challenged you to a duel! Would you like to accept?",
            color=disnake.Color.blue()
        )

        if inter.author.avatar:
            embed.set_thumbnail(url=inter.author.avatar.url)

        try:
            await opponent.send(embed=embed, view=InitialChallengeView(guild=inter.guild, channel=inter.channel, challenger=inter.author))
            await inter.followup.send(f"Challenge sent to {opponent.mention}!", ephemeral=True)

        except disnake.Forbidden:
            # Handle the case where the bot cannot send a DM to the opponent
            await inter.followup.send(f"I couldn't send a DM to {opponent.mention}. They might have DMs disabled.", ephemeral=True)

        # await inter.send(embed=embed)
        
        # Update rankings
        # await self.update_rankings(challenger, challenged, winner)
    
    async def update_rankings(self, player1: Player, player2: Player, winner: Optional[Player]):
        """Update player rankings after a battle"""
        if winner:
            loser = player2 if winner == player1 else player1
            await winner.pvp_stats.add_win()
            await loser.pvp_stats.add_loss()
        else:
            await player1.pvp_stats.add_draw()
            await player2.pvp_stats.add_draw()
    
    @pvp.sub_command(name="stats")
    async def stats(
        self,
        inter: disnake.ApplicationCommandInteraction,
        player: disnake.Member = None
    ):
        """View your or another player's PvP stats"""
        target = player or inter.author
        stats = {'wins': 5, 'losses': 3, 'draws': 2, 'win_rate': 0.5}# await PvPStats.get(target.id)
        
        if stats is None:
            await inter.send(f"{target.mention} doesn't have any PvP stats yet!")
            return
            
        embed = disnake.Embed(
            title=f"⚔️ {target.display_name}'s PvP Stats",
            description=(
                f"**Wins:** {stats.wins}\n"
                f"**Losses:** {stats.losses}\n"
                f"**Draws:** {stats.draws}\n"
                f"**Win Rate:** {stats.win_rate:.1f}%\n"
                f"**Last Match:** {stats.last_match.strftime('%Y-%m-%d %H:%M') if stats.last_match else 'Never'}"
            ),
            color=0x00ff00
        )
        
        await inter.send(embed=embed)
    
    @pvp.sub_command(name="leaderboard")
    async def leaderboard(self, inter: disnake.ApplicationCommandInteraction):
        """View the PvP leaderboard"""
        # TODO: Implement leaderboard
        await inter.send("Leaderboard coming soon!", ephemeral=True)

def setup(bot):
    bot.add_cog(PvPCog(bot))
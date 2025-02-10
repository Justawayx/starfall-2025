import disnake
from disnake.ext import commands
from disnake.ui import Button, View
from typing import List, Optional, Tuple
from character.player import Player, PlayerRoster
from adventure.pvp import start_pvp_battle
# from utils.Embeds import create_embed
from utils.Database import Users, PvpMatches
from utils.Styles import EXCLAMATION
from utils.base import CogNotLoadedError
import random, asyncio
# from character.pvp_stats import PvPStats

# TODO: Add action logs to public channel, address win/loss when health goes to 0
'''
{'id': 417239126849355776, 'Member': <Member id=417239126849355776 name='justawayx' global_name='Daisy' discriminator='0' bot=False nick=None guild=<Guild id=779435063678861383 name='Starfall PBE' shard_id=0 chunked=True member_count=25>>, 'Player': Player {user_id: 417239126849355776}, 'HP': 36, 'Max HP': 41, 'Qi': 100, 'Max Qi': 100, 'action': 'None'} {'id': 224668599409704961, 'Member': <Member id=224668599409704961 name='neutralizinq' global_name='Neutralizinq' discriminator='0' bot=False nick=None guild=<Guild id=779435063678861383 name='Starfall PBE' shard_id=0 chunked=True member_count=25>>, 'Player': Player {user_id: 224668599409704961}, 'HP': 10, 'Max HP': 10, 'Qi': 100, 'Max Qi': 100, 'action': '<@224668599409704961> used "basic_attack", dealing 4.92 damage to <@417239126849355776>'}
'''

def simple_embed(title: str, description: str, color: int = 0x00ff00) -> disnake.Embed:
    return disnake.Embed(
        title=title,
        description=description,
        color=color
    )

class MainBattleView(View):

    def __init__(self, guild: disnake.Guild, channel: disnake.TextChannel, match_id: int, user_id: int):
        
        ACTION_TIMEOUT = 30 # seconds
        super().__init__(timeout=None)  # Handle timeout manually
        self.countdown = ACTION_TIMEOUT
        self.message = None  # Store this user's message (for updating)
        self.opponent_message = None  # Store the opponent's message (for updating)
        self.guild = guild  # Store the guild
        self.channel = channel  # Store the channel
        self._id = match_id  # Store the match ID
        self.user_id = user_id  # Store this user's ID

        # Start the countdown task
        self.countdown_task = asyncio.create_task(self.update_countdown())
    
    async def get_match_data(self) -> Tuple[dict, dict, int, bool]:

        match_data = await PvpMatches.get_or_none(id=self._id).values_list("challenger_id", "defender_id", "status", "turn", "challenger_HP", "defender_HP", "challenger_Qi", "defender_Qi", "challenger_action", "defender_action")
        
        challenger_id, defender_id, status, turn, challenger_HP, defender_HP, challenger_Qi, defender_Qi, challenger_action, defender_action = match_data

        challenger = self.guild.get_member(challenger_id)
        defender = self.guild.get_member(defender_id)
        
        challengerPlayer: Player = PlayerRoster().get(challenger_id)
        defenderPlayer: Player = PlayerRoster().get(defender_id)

        # Get stats
        challengerCP = await challengerPlayer.compute_total_cp()
        challengerMaxHP = 10 + challengerCP
        challengerMaxQi = 100

        defenderCP = await defenderPlayer.compute_total_cp()
        defenderMaxHP = 10 + defenderCP
        defenderMaxQi = 100
        
        # Updated stats
        challenger_info = {
            'id': challenger_id,
            'Member': challenger,
            'Player': challengerPlayer,
            'HP': challenger_HP,
            'Max HP': challengerMaxHP,
            'Qi': challenger_Qi,
            'Max Qi': challengerMaxQi,
            'action': challenger_action
        }

        defender_info = {
            'id': defender_id,
            'Member': defender,
            'Player': defenderPlayer,
            'HP': defender_HP,
            'Max HP': defenderMaxHP,
            'Qi': defender_Qi,
            'Max Qi': defenderMaxQi,
            'action': defender_action
        }

        # Determine whether interacting user is challenger or defender
        am_challenger = (self.user_id == challenger_id)

        return challenger_info, defender_info, turn, am_challenger
    

    async def display_next_turn(self, challenger_info: dict, defender_info: dict, turn: int):
        
        # Generate updated embeds
        battle_embed = generate_battle_embed(challenger_info, defender_info, turn)
        action_embed = disnake.Embed(
            description=f"{challenger_info['action']}\n{defender_info['action']}",
            color=disnake.Color.red()
        )
        initial_countdown_embed = simple_embed('', "Starting turn...", color=disnake.Color.blue())

        # Send updated battle embed to public channel
        await self.channel.send(embeds=[battle_embed])
        
        # Send updated embeds to the challenger and store the message object
        challengerBattleView = MainBattleView(guild=self.guild, channel=self.channel, match_id=self._id, user_id=challenger_info['id'])
        challenger_message = await challenger_info['Member'].send(embeds=[action_embed, battle_embed, initial_countdown_embed], view=challengerBattleView)
        challengerBattleView.message = challenger_message  # Store the message for dynamic updates

        # Send updated embeds to the defender and store the message object
        defenderBattleView = MainBattleView(guild=self.guild, channel=self.channel, match_id=self._id, user_id=defender_info['id'])
        defender_message = await defender_info['Member'].send(embeds=[action_embed, battle_embed, initial_countdown_embed], view=defenderBattleView)
        defenderBattleView.message = defender_message  # Store the message for dynamic updates

        # Store references to the other player's message
        challengerBattleView.opponent_message = defender_message
        defenderBattleView.opponent_message = challenger_message

        self.stop()
    
    # Handle timeout (when the user doesn't click a button in time)
    async def on_timeout(self):
        
        # self.countdown_task.cancel()

        timeout_embed = disnake.Embed(description="⏰ Time's up! You didn't respond in time.")
        await self.message.edit(embeds=[*self.message.embeds[:-1], timeout_embed], view=None)

        # For now, do nothing and move on to next turn
        challenger_info, defender_info, turn, am_challenger = await self.get_match_data()

        if am_challenger:
            challenger_info['action'] = f'<@{challenger_info['id']}> did nothing.'
        else:
            defender_info['action'] = f'<@{defender_info['id']}> did nothing.'

        # Challenger side sends message if both players timed out, otherwise defender side sends message
        if challenger_info['action'] != 'None' or am_challenger:

            turn += 1
            await PvpMatches.filter(id=self._id).update(turn=turn, challenger_action='None', defender_action='None')
            await self.display_next_turn(challenger_info, defender_info, turn)
            
            # Delete original messages for both players
            await self.message.delete()
            await self.opponent_message.delete()


    async def update_countdown(self):
        # Update the countdown every second
        while self.countdown > 0:
            # Create the countdown embed
            countdown_embed = disnake.Embed(
                description=f"⏳ Time remaining: **{self.countdown} sec**",
                color=disnake.Color.blue()
            )

            # Edit the original message to update the countdown
            if self.message:
                await self.message.edit(embeds=[*self.message.embeds[:-1], countdown_embed])

            await asyncio.sleep(1)  # Wait 1 second
            self.countdown -= 1
        
        await self.on_timeout()


    @disnake.ui.button(label="Basic Attack", style=disnake.ButtonStyle.primary, custom_id="basic_attack")
    async def basic_attack(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        
        await inter.response.defer()
        self.countdown_task.cancel() # Stop the countdown
        self.stop() # Remove the buttons
        
        try:
            challenger_info, defender_info, turn, am_challenger = await self.get_match_data()

            if am_challenger: # Challenger submitted attack
                # Perform basic attack
                attack_damage = (random.randint(5, 15)/100.0)*defender_info['HP']
                action = f'<@{challenger_info['id']}> used "basic_attack", dealing {attack_damage} damage to <@{defender_info['id']}>'

                await PvpMatches.filter(id=self._id).update(defender_HP=(defender_info['HP'] - attack_damage), challenger_action=action)

                defender_info['HP'] -= attack_damage
                challenger_info['action'] = action

            else: # Defender submitted attack
                # Perform basic attack
                attack_damage = (random.randint(5, 15)/100.0)*challenger_info['HP']
                action = f'<@{defender_info['id']}> used "basic_attack", dealing {attack_damage} damage to <@{challenger_info['id']}>'
                
                await PvpMatches.filter(id=self._id).update(challenger_HP=(challenger_info['HP'] - attack_damage), defender_action=action)

                challenger_info['HP'] -= attack_damage
                defender_info['action'] = action
            
            if challenger_info['action'] != 'None' and defender_info['action'] != 'None': # Both players have submitted moves, move on to next turn
                turn += 1
                await PvpMatches.filter(id=self._id).update(turn=turn, challenger_action='None', defender_action='None')
                await self.display_next_turn(challenger_info, defender_info, turn)
                
                # Delete original messages for both players
                await self.message.delete()
                await self.opponent_message.delete()
            
            else: # Waiting for opponent to submit move
                waiting_embed = disnake.Embed(description=f'Waiting for opponent...')
                await inter.edit_original_message(embeds=[*self.message.embeds[:-1], waiting_embed], view=None)
        
        except Exception as e:
            print(f"Error in basic_attack: {e}")
            await inter.send("An error occurred while processing your request.", ephemeral=True)
    
    @disnake.ui.button(label="Use Technique", style=disnake.ButtonStyle.primary, custom_id="use_technique")
    async def use_technique_turn(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        pass

def generate_battle_embed(challenger_info: dict, defender_info: dict, turn: int) -> disnake.Embed:
    """Generate an embed for the battle"""
    embed = disnake.Embed(
        title=f"⚔️ PvP Battle: Turn {turn}",
        color=disnake.Color.blue()
    )
    embed.add_field(
        name=f"{challenger_info['Member'].display_name}",
        value=f"""HP: `{challenger_info['HP']}`/`{challenger_info['Max HP']}`
        Qi: `{challenger_info['Qi']}`/`{challenger_info['Max Qi']}`""",
        inline=True
    )
    embed.add_field(
        name=f"{defender_info['Member'].display_name}",
        value=f"""HP: `{defender_info['HP']}`/`{defender_info['Max HP']}`
        Qi: `{defender_info['Qi']}`/`{defender_info['Max Qi']}`""",
        inline=True
    )
    return embed

class InitialChallengeView(View):
    def __init__(self, guild: disnake.Guild, channel: disnake.TextChannel, challenger: disnake.Member, defender: disnake.Member):
        super().__init__(timeout=None)  # No timeout for persistent buttons
        self.guild = guild  # Store the guild
        self.channel = channel  # Store the channel
        self.challenger = challenger  # Store the challenger
        self.defender = defender # Store the defender

        self.challengerPlayer: Player = PlayerRoster().get(challenger.id)
        self.defenderPlayer: Player = PlayerRoster().get(defender.id)

    @disnake.ui.button(label="Accept", style=disnake.ButtonStyle.success, custom_id="accept_challenge")
    async def accept_challenge(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        try:
            # Get initial stats
            challengerCP = await self.challengerPlayer.compute_total_cp()
            challengerMaxHP = 10 + challengerCP
            challengerMaxQi = 100

            defenderCP = await self.defenderPlayer.compute_total_cp()
            defenderMaxHP = 10 + defenderCP
            defenderMaxQi = 100
            
            challenger_info = {
                'id': self.challenger.id,
                'Member': self.challenger,
                'Player': self.challengerPlayer,
                'HP': challengerMaxHP,
                'Max HP': challengerMaxHP,
                'Qi': challengerMaxQi,
                'Max Qi': challengerMaxQi,
                'action': 'None'
            }

            defender_info = {
                'id': self.defender.id,
                'Member': self.defender,
                'Player': self.defenderPlayer,
                'HP': defenderMaxHP,
                'Max HP': defenderMaxHP,
                'Qi': defenderMaxQi,
                'Max Qi': defenderMaxQi,
                'action': 'None'
            }

            turn = 1

            # Create a new PvP match and add to database
            pvpmatch = await PvpMatches.create(challenger_id=self.challengerPlayer.id, defender_id=self.defenderPlayer.id, 
                challenger_HP=challengerMaxHP, defender_HP=defenderMaxHP,
                challenger_Qi=challengerMaxQi, defender_Qi=defenderMaxQi,
                created_at=disnake.utils.utcnow(), updated_at=disnake.utils.utcnow(), turn=turn)
            
            self._id = pvpmatch.id # Match ID
            
            if self.channel:
                
                # Send a message to the public channel
                accept_embed = disnake.Embed(
                    title="Challenge Accepted!",
                    description=f"{inter.author.mention} has accepted {self.challenger.mention}'s challenge!",
                    color=disnake.Color.green()
                )

                battle_embed = generate_battle_embed(challenger_info, defender_info, turn)

                await self.channel.send(embeds=[accept_embed, battle_embed])

                # Notify both players / initiate the match

                defender_accept_DM_embed = simple_embed("Challenge Accepted!", f"You accepted the challenge from {self.challenger.mention}!", disnake.Color.green())
                challenger_accept_DM_embed = simple_embed("Challenge Accepted!", f"Your challenge has been accepted by {inter.author.mention}!", disnake.Color.green())
                
                challengerBattleView = MainBattleView(guild=self.guild, channel=self.channel, match_id=pvpmatch.id, user_id=self.challenger.id)
                defenderBattleView = MainBattleView(guild=self.guild, channel=self.channel, match_id=pvpmatch.id, user_id=self.defender.id)
                
                initial_countdown_embed = simple_embed('', "Starting turn...", color=disnake.Color.blue())

                # Send the initial message to the challenger and store the message object
                await self.challenger.send(embed=challenger_accept_DM_embed)
                challenger_message = await self.challenger.send(embeds=[battle_embed, initial_countdown_embed], view=challengerBattleView)
                challengerBattleView.message = challenger_message  # Store the message for dynamic updates

                # Send the initial message to the defender and store the message object
                await inter.response.send_message(embed=defender_accept_DM_embed)
                defender_message = await self.defender.send(embeds=[battle_embed, initial_countdown_embed], view=defenderBattleView)
                defenderBattleView.message = defender_message  # Store the message for dynamic updates

                # Store references to the other player's message
                challengerBattleView.opponent_message = defender_message
                defenderBattleView.opponent_message = challenger_message
                
            else:
                # Respond to the opponent
                await inter.response.send_message(f"Challenged failed due to invalid channel", ephemeral=True)
                print(f"Channel not found or inaccessible.")

        except Exception as e:
            print(f"Error in accept_challenge: {e}")
            await inter.response.send_message("Something went wrong. Please try again.", ephemeral=True)

    @disnake.ui.button(label="Reject", style=disnake.ButtonStyle.danger, custom_id="reject_challenge")
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
            await opponent.send(embed=embed, view=InitialChallengeView(guild=inter.guild, channel=inter.channel, challenger=inter.author, defender=opponent))
            await inter.followup.send(f"Challenge sent to {opponent.mention}!", ephemeral=True)

        except disnake.Forbidden:
            # Handle the case where the bot cannot send a DM to the opponent
            await inter.followup.send(f"I couldn't send a DM to {opponent.mention}. They might have DMs disabled.", ephemeral=True)
    
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
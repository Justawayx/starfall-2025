import disnake
from disnake.ext import commands
from disnake.ui import Button, View
from typing import List, Optional, Tuple
from character.player import Player, PlayerRoster
from adventure.pvp import start_pvp_battle
from tortoise.expressions import Q
# from utils.Embeds import create_embed
from utils.Database import Users, PvpMatches
from utils.Styles import EXCLAMATION
from utils.base import CogNotLoadedError
from utils.ParamsUtils import format_num_abbr1
import random, asyncio, json, math
# from character.pvp_stats import PvPStats

# TODO: remove bruv from shop

def simple_embed(title: str, description: str, color: int = 0x00ff00) -> disnake.Embed:
    return disnake.Embed(
        title=title,
        description=description,
        color=color
    )

def to_nonneg(number):
    return max(0, number)

class BattleAction():
    def __init__(self, name: str, player_id: int, target_id: int, damage: int):
        self.name = name
        self.player_id = player_id
        self.target_id = target_id
        self.damage = damage
        self.description = self.__str__()
    
    def __str__(self):
        return f'<@{self.player_id}> used `{self.name}`, dealing {format_num_abbr1(self.damage)} damage to <@{self.target_id}>'

class TechniqueDropdown(disnake.ui.Select):
    """Dropdown for selecting a technique."""

    def __init__(self, techniques: list, battle_view):
        options = [
            disnake.SelectOption(label=tech, description='Cooldown: x | Qi Cost: x', value=tech)
            for index, tech in enumerate(techniques)
        ]
        super().__init__(placeholder="Choose a technique...", min_values=1, max_values=1, options=options)
        self.battle_view = battle_view
        self.techniques = techniques

    async def callback(self, inter: disnake.MessageInteraction):
        """Handles when a technique is selected."""
        await inter.response.defer()
        self.battle_view.countdown_task.cancel() # Stop the countdown
        self.battle_view.toggle_buttons(enabled=False) # Disable the buttons
        self.battle_view.clear_items()  # Remove dropdown
        await self.battle_view.message.edit(view=self.battle_view)

        # Get selected technique
        selected_technique = self.values[0]

        # Store the action (modify this according to your action logic)
        action = {
            "name": selected_technique,
            "description": f"<@{inter.user.id}> used `{selected_technique}`!",
            "damage": 0
        }

        # Identify if the user is the challenger or defender
        challenger_info, defender_info, turn, am_challenger = await self.battle_view.get_match_data()
        if am_challenger:
            challenger_info['action'] = action
            await PvpMatches.filter(id=self.battle_view._id).update(challenger_action=action)
        else:
            defender_info['action'] = action
            await PvpMatches.filter(id=self.battle_view._id).update(defender_action=action)

        # Check if both players have chosen their actions
        if challenger_info["action"] and defender_info["action"]:
            if challenger_info['stats']['HP'] <= 0 or defender_info['stats']['HP'] <= 0:
                await self.battle_view.display_final_turn(challenger_info, defender_info, turn)
            else:
                turn += 1
                await PvpMatches.filter(id=self.battle_view._id).update(turn=turn, challenger_action={}, defender_action={})
                await self.battle_view.display_next_turn(challenger_info, defender_info, turn)
        else:
            waiting_embed = disnake.Embed(description=f'Waiting for opponent...')
            await self.battle_view.message.edit_message(embeds=[*self.message.embeds[:-1], waiting_embed])


class MainBattleView(View):

    def __init__(self, guild: disnake.Guild, channel: disnake.TextChannel, match_id: int, user_id: int, opponent_user_id: int,
        message: disnake.Message = None, opponent_message: disnake.Message = None, public_message: disnake.Message = None):
        super().__init__(timeout=None)  # Handle timeout manually
        self.countdown = 30
        self.message = message  # Store this user's message (for updating)
        self.opponent_message = opponent_message  # Store the opponent's message (for updating)
        self.public_message = public_message # Store the public message (for updating)
        self.guild = guild  # Store the guild
        self.channel = channel  # Store the channel
        self._id = match_id  # Store the match ID
        self.user_id = user_id  # Store this user's ID
        self.opponent_user_id = opponent_user_id # Store the opponent's view (for updating)
        
        # Start the countdown task
        self.countdown_task = asyncio.create_task(self.update_countdown())
    
    def toggle_buttons(self, enabled: bool):
        """Enable or disable all buttons dynamically."""
        for child in self.children:
            if isinstance(child, disnake.ui.Button):
                child.disabled = (not enabled)
    
    def restart_countdown_task(self):
        # Cancel the existing task if it exists and is not already done
        if self.countdown_task and not self.countdown_task.done():
            self.countdown_task.cancel()
        # Reset the countdown and create a new task
        self.countdown_task = asyncio.create_task(self.update_countdown())

    async def get_match_data(self) -> Tuple[dict, dict, int, bool]:
        
        match_data = await PvpMatches.get_or_none(id=self._id).values_list("challenger_id", "defender_id", "turn", "challenger_stats", "defender_stats", "challenger_action", "defender_action")
        challenger_id, defender_id, turn, challenger_stats, defender_stats, challenger_action, defender_action = match_data
        
        # Current player info
        challenger_info = {
            'id': challenger_id,
            'Member': self.guild.get_member(challenger_id),
            'Player': PlayerRoster().get(challenger_id),
            'action': challenger_action,
            'stats': challenger_stats
        }

        defender_info = {
            'id': defender_id,
            'Member': self.guild.get_member(defender_id),
            'Player': PlayerRoster().get(defender_id),
            'action': defender_action,
            'stats': defender_stats
        }

        # Determine whether interacting user is challenger or defender
        am_challenger = (self.user_id == challenger_id)

        return challenger_info, defender_info, turn, am_challenger
    
    async def display_final_turn(self, challenger_info: dict, defender_info: dict, turn: int):
        
        self.stop() # Stop the view
        winner_info, loser_info = (challenger_info, defender_info) if defender_info['stats']['HP'] <= 0 else (defender_info, challenger_info)

        # Generate updated embeds
        battle_embed = generate_battle_embed(challenger_info, defender_info, turn)
        action_embed = disnake.Embed(
            description=f"{challenger_info['action']['description']}\n{defender_info['action']['description']}",
            color=disnake.Color.red()
        )

        victory_title_options = ["Fate Sealed!", "A Decisive Blow!", "The Final Strike!", "Victory!", f"The End of <@{loser_info['Member'].display_name}>!", f"<@{winner_info['Member'].display_name}>'s Triumph!", "The Battle's Turning Point!", f"<@{loser_info['Member'].display_name}> Falls!", "The Ultimate Move!", "Destiny Fulfilled!", f"<@{winner_info['Member'].display_name}> Reigns Supreme!", "The Last Stand!"]
        victory_title = random.choice(victory_title_options)
        victory_description = f"<@{winner_info['id']}>'s `{winner_info['action']['name']}` sealed the fate of <@{loser_info['id']}>!"

        result_embed = simple_embed(victory_title, victory_description)

        # Updates embeds in public channel and for both players
        await self.public_message.edit(embeds=[action_embed, battle_embed, result_embed])
        await self.message.edit(embeds=[action_embed, battle_embed, result_embed])
        await self.opponent_message.edit(embeds=[action_embed, battle_embed, result_embed])

        # Set match status to 'completed'
        await PvpMatches.filter(id=self._id).update(status="completed")

    async def display_next_turn(self, challenger_info: dict, defender_info: dict, turn: int):
        
        # Generate updated embeds
        battle_embed = generate_battle_embed(challenger_info, defender_info, turn)
        action_embed = disnake.Embed(
            description=f"{challenger_info['action']['description']}\n{defender_info['action']['description']}",
            color=disnake.Color.red()
        )
        initial_countdown_embed = simple_embed('', "Starting turn...", color=disnake.Color.blue())

        # Updates embed in public channel
        await self.public_message.edit(embeds=[action_embed, battle_embed])
        
        # Send updated embeds to the challenger and store the message object
        challengerBattleView = MainBattleView(guild=self.guild, channel=self.channel, match_id=self._id, user_id=challenger_info['id'], opponent_user_id=defender_info['id'], public_message=self.public_message)
        challenger_message = await challenger_info['Member'].send(embeds=[action_embed, battle_embed, initial_countdown_embed], view=challengerBattleView)
        challengerBattleView.message = challenger_message  # Store the message for dynamic updates

        # Send updated embeds to the defender and store the message object
        defenderBattleView = MainBattleView(guild=self.guild, channel=self.channel, match_id=self._id, user_id=defender_info['id'], opponent_user_id=challenger_info['id'], public_message=self.public_message)
        defender_message = await defender_info['Member'].send(embeds=[action_embed, battle_embed, initial_countdown_embed], view=defenderBattleView)
        defenderBattleView.message = defender_message  # Store the message for dynamic updates

        # Store references to the other player's message
        challengerBattleView.opponent_message = defender_message
        defenderBattleView.opponent_message = challenger_message
        
        # Delete original messages for both players
        await self.message.delete()
        await self.opponent_message.delete()
    
    # Handle timeout (when the user doesn't click a button in time)
    async def on_timeout(self):

        timeout_embed = disnake.Embed(description="⏰ Time's up! You didn't respond in time.")
        self.toggle_buttons(enabled=False) # Disable the buttons
        await self.message.edit(embeds=[*self.message.embeds[:-1], timeout_embed], view=self)

        # For now, do nothing and move on to next turn
        challenger_info, defender_info, turn, am_challenger = await self.get_match_data()

        if am_challenger:
            challenger_info['action'] = BattleAction(name="nothing", player_id=challenger_info['id'], target_id=defender_info['id'], damage=0).__dict__
        else:
            defender_info['action'] = BattleAction(name="nothing", player_id=defender_info['id'], target_id=challenger_info['id'], damage=0).__dict__

        # Challenger side sends message if both players timed out, otherwise defender side sends message
        if (challenger_info['action']) or am_challenger:
            turn += 1
            await PvpMatches.filter(id=self._id).update(turn=turn, challenger_action={}, defender_action={})
            await self.display_next_turn(challenger_info, defender_info, turn)

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
        self.toggle_buttons(enabled=False) # Disable the buttons
        await self.message.edit(view=self)
        
        try:
            challenger_info, defender_info, turn, am_challenger = await self.get_match_data()
            challenger_stats = challenger_info['stats']; defender_stats = defender_info['stats']

            if am_challenger: # Challenger submitted attack
                # Perform basic attack
                attack_damage = math.ceil(challenger_stats['pATK']*(random.randint(80,100)/100.0))
                action = BattleAction(name="basic_attack", player_id=challenger_info['id'], target_id=defender_info['id'], damage=attack_damage).__dict__
                
                defender_stats['HP'] = to_nonneg(defender_stats['HP'] - attack_damage)
                challenger_info['action'] = action

                await PvpMatches.filter(id=self._id).update(defender_stats=(defender_stats), challenger_action=action)

            else: # Defender submitted attack
                # Perform basic attack
                attack_damage = math.ceil(defender_stats['pATK']*(random.randint(80,100)/100.0))
                action = BattleAction(name="basic_attack", player_id=defender_info['id'], target_id=challenger_info['id'], damage=attack_damage).__dict__
                
                challenger_stats['HP'] = to_nonneg(challenger_stats['HP'] - attack_damage)
                defender_info['action'] = action

                await PvpMatches.filter(id=self._id).update(challenger_stats=(challenger_stats), defender_action=action)
            
            if challenger_info['action'] and defender_info['action']: # Both players have submitted moves, move on to next turn
                
                if challenger_stats['HP'] <= 0 or defender_stats['HP'] <= 0: # Handle end of match
                    await self.display_final_turn(challenger_info, defender_info, turn)
                else:
                    turn += 1
                    await PvpMatches.filter(id=self._id).update(turn=turn, challenger_action={}, defender_action={})
                    await self.display_next_turn(challenger_info, defender_info, turn)
            
            else: # Waiting for opponent to submit move
                waiting_embed = disnake.Embed(description=f'Waiting for opponent...')
                await inter.edit_original_message(embeds=[*self.message.embeds[:-1], waiting_embed])
        
        except Exception as e:
            print(f"Error in basic_attack: {e}")
            await inter.send("An error occurred while processing your request.", ephemeral=True)
    
    @disnake.ui.button(label="Use Technique", style=disnake.ButtonStyle.primary, custom_id="use_technique")
    async def use_technique(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.defer()

        # Fetch techniques for this player
        challenger_info, defender_info, turn, am_challenger = await self.get_match_data()
        player = challenger_info['Player'] if am_challenger else defender_info['Player']
        equipped_items = await player.get_equipped_items()
        techniques = equipped_items['techniques']

        if len(techniques) > 0:
            # Create a dropdown for technique selection
            technique_dropdown = TechniqueDropdown(techniques, self)
            self.add_item(technique_dropdown)

            # Update message with dropdown
            button.disabled = True
            await self.message.edit(view=self)
        else:
            await inter.followup.send(f"You have not learned any Fight Techniques!", ephemeral=True)


def generate_battle_embed(challenger_info: dict, defender_info: dict, turn: int) -> disnake.Embed:
    challenger_stats = challenger_info['stats']; defender_stats = defender_info['stats']
    embed = disnake.Embed(
        title=f"⚔️ PvP Battle: Turn {turn}",
        color=disnake.Color.blue()
    )
    embed.add_field(
        name=f"{challenger_info['Member'].display_name}",
        value=f"""HP: `{challenger_stats['HP']}`/`{challenger_stats['Max HP']}`
        Qi: `{challenger_stats['Qi']}`/`{challenger_stats['Max Qi']}`""",
        inline=True
    )
    embed.add_field(
        name=f"{defender_info['Member'].display_name}",
        value=f"""HP: `{defender_stats['HP']}`/`{defender_stats['Max HP']}`
        Qi: `{defender_stats['Qi']}`/`{defender_stats['Max Qi']}`""",
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

    def toggle_buttons(self, enabled: bool):
        """Enable or disable all buttons dynamically."""
        for child in self.children:
            if isinstance(child, disnake.ui.Button):
                child.disabled = (not enabled)

    @disnake.ui.button(label="Accept", style=disnake.ButtonStyle.success, custom_id="accept_challenge")
    async def accept_challenge(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        
        await inter.response.defer()
        self.toggle_buttons(enabled=False) # Disable the buttons
        await inter.message.edit(view=self)
        
        try:
            # Get initial stats
            challenger_stats = {
                'pATK': 225, # Physical Attack
                'mATK': 225, # Magical Attack
                'pDEF': 225, # Physical Defense
                'mDEF': 225, # Magical Defense
                'pPEN': 45, # Physical Penetration
                'mPEN': 45, # Magical Penetration
                'SPD': 100, # Speed
                'ACC': 0.95, # Accuracy
                'EVA': 0.05, # Evasion (dodge)
                'CRIT': 0.05, # Critical rate
                'CRIT DMG': 1.50, # Critical damage multiplier
                'HP': 2250, 
                'Max HP': 2250, 
                'Qi': 100, 
                'Max Qi': 100
            }

            defender_stats = {
                'pATK': 225, # Physical Attack
                'mATK': 225, # Magical Attack
                'pDEF': 225, # Physical Defense
                'mDEF': 225, # Magical Defense
                'pPEN': 45, # Physical Penetration
                'mPEN': 45, # Magical Penetration
                'SPD': 100, # Speed
                'ACC': 0.95, # Accuracy
                'EVA': 0.05, # Evasion (dodge)
                'CRIT': 0.05, # Critical rate
                'CRIT DMG': 1.50, # Critical damage multiplier
                'HP': 2250, 
                'Max HP': 2250, 
                'Qi': 100, 
                'Max Qi': 100
            }

            # Current player info
            challenger_info = {
                'id': self.challengerPlayer.id,
                'Member': self.guild.get_member(self.challengerPlayer.id),
                'Player': PlayerRoster().get(self.challengerPlayer.id),
                'action': '',
                'stats': challenger_stats
            }

            defender_info = {
                'id': self.defenderPlayer.id,
                'Member': self.guild.get_member(self.defenderPlayer.id),
                'Player': PlayerRoster().get(self.defenderPlayer.id),
                'action': '',
                'stats': defender_stats
            }

            turn = 1
            
            # Create a new PvP match and add to database
            pvpmatch = await PvpMatches.create(challenger_id=self.challengerPlayer.id, defender_id=self.defenderPlayer.id, 
                challenger_stats=challenger_stats, defender_stats=defender_stats, created_at=disnake.utils.utcnow(), updated_at=disnake.utils.utcnow(), turn=turn)
            
            self._id = pvpmatch.id # Match ID
            
            if self.channel:
                
                # Generate battle and countdown embeds
                battle_embed = generate_battle_embed(challenger_info, defender_info, turn)
                initial_countdown_embed = simple_embed('', "Starting turn...", color=disnake.Color.blue())
                
                # Send messages to the public channel
                accept_embed = simple_embed("Challenge Accepted!", f"{inter.author.mention} has accepted {self.challenger.mention}'s challenge!", disnake.Color.green())
                initial_action_embed = simple_embed('', 'The battle has begun!', disnake.Color.red())
                public_message = await self.channel.send(embeds=[accept_embed, battle_embed])

                # Send messages with MainBattleViews to both players
                player_messages = []; player_views = [] # Order is challenger, defender
                for player, other_player in ((self.challenger, self.defender), (self.defender, self.challenger)):
                    acceptance_message = f"Your challenge has been accepted by {other_player.mention}!" if player == self.challenger else f"You accepted the challenge from {other_player.mention}!"
                    await player.send(embed=simple_embed("Challenge Accepted!", acceptance_message, disnake.Color.green()))
                    
                    playerBattleView = MainBattleView(guild=self.guild, channel=self.channel, match_id=pvpmatch.id, user_id=player.id, opponent_user_id=other_player.id)
                    player_message = await player.send(embeds=[initial_action_embed, battle_embed, initial_countdown_embed], view=playerBattleView)
                    playerBattleView.message = player_message; playerBattleView.public_message = public_message
                    player_messages.append(player_message); player_views.append(playerBattleView)
                
                player_views[0].opponent_message = player_messages[1]
                player_views[0].opponent_view = player_views[1]
                player_views[1].opponent_message = player_messages[0]
                player_views[1].opponent_view = player_views[0]
                
            else:
                # Respond to the opponent
                await inter.response.send_message(f"Challenged failed due to invalid channel", ephemeral=True)
                print(f"Channel not found or inaccessible.")

        except Exception as e:
            print(f"Error in accept_challenge: {e}")
            await inter.response.send_message("Something went wrong. Please try again.", ephemeral=True)

    @disnake.ui.button(label="Decline", style=disnake.ButtonStyle.danger, custom_id="decline_challenge")
    async def decline_challenge(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        
        self.toggle_buttons(enabled=False) # Disable the buttons
        await inter.message.edit(view=self)

        try:
            # Send a DM to the challenger
            challenger_embed = disnake.Embed(
                title="Challenge Declined",
                description=f"{inter.author.mention} has declined your challenge.",
                color=disnake.Color.red()
            )
            await self.challenger.send(embed=challenger_embed)

            # Respond to the opponent
            await inter.response.send_message("You declined the challenge.", ephemeral=True)
        except Exception as e:
            print(f"Error in decline_challenge: {e}")
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
        
        challenger_latest_match = await PvpMatches.filter(
            (Q(challenger_id=challenger._id) | Q(defender_id=challenger._id))
        ).order_by("-created_at").first()
        challenged_latest_match = await PvpMatches.filter(
            (Q(challenger_id=challenged._id) | Q(defender_id=challenged._id))
        ).order_by("-created_at").first()
        
        challenger_in_match = (challenger_latest_match and challenger_latest_match.status != "completed")
        challenged_in_match = (challenged_latest_match and challenged_latest_match.status != "completed")

        if challenger_in_match and challenged_in_match:
            await inter.send("Both players are currently unable to participate in a new match.")
            return
        elif challenger_in_match:
            await inter.send(f"<@{challenger._id}> is unable to participate in a new match.")
            return
        elif challenged_in_match:
            await inter.send(f"<@{challenged._id}> is unable to participate in a new match.")
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
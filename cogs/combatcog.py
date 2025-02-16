import disnake
from disnake.ext import commands
from disnake.ui import Button, View
from typing import List, Optional, Tuple
from character.player import Player, PlayerRoster
from adventure.pvp import start_pvp_battle
from tortoise.expressions import Q
# from utils.Embeds import create_embed
from utils.Database import Users, PvpMatches, AllItems
from utils.Styles import EXCLAMATION
from utils.base import CogNotLoadedError
from utils.ParamsUtils import format_num_abbr1
import random, asyncio, json, math
# from character.pvp_stats import PvPStats

# TODO: remove bruv from shop
# Action descriptions
# - dealing x magical damage, dealing x physical damage, dealing x mixed damage, dealing x true damage
# Mention status effects applied
# Speed
# Elements
# Put technique code in a separate file
# Cooldowns
# Status effects
# A player who is dead cannot attack
# Lock in techniques for the duration of a match (cannot learn/unlearn)
# Process turns at once rather than by the person who last clicked

def simple_embed(title: str, description: str, color: int = 0x00ff00) -> disnake.Embed:
    return disnake.Embed(
        title=title,
        description=description,
        color=color
    )

def to_nonneg(number):
    return max(0, number)

def random_success(chance):
    return (random.random() < chance)

def construct_player_info(player_stats, player_action, player_status, guild, user_id):
    player_info = {
        'id': user_id,
        'Member': guild.get_member(user_id),
        'Player': PlayerRoster().get(user_id),
        'action': player_action[str(user_id)],
        'stats': player_stats[str(user_id)],
        'status': player_status[str(user_id)]           
    }
    return player_info

class AttackComponent():
    def __init__(self, player_stats: dict, target_stats: dict,
        scaling_stat: str,
        scaling_stat_source: str,
        damage_type: str,
        multiplier: float = 1,
        true_damage: bool = False
    ):
        self.player_stats = player_stats
        self.target_stats = target_stats
        self.scaling_stat = scaling_stat # Stat to scale off of (pATK, mATK, HP, ...)
        self.scaling_stat_source = scaling_stat_source # Whose stat to use (player or target)
        self.damage_type = damage_type # Damage type (physical, magical, or true)
        self.multiplier = multiplier # Multiplier for the scaling value
        self.true_damage = true_damage # True / False
    
    def randomize_damage(self, damage: int): # Introduces random variability
        return math.ceil(damage*(random.randint(80,100)/100.0))
    
    def damage_dealt(self):
        # Damage = multiplier * scaling stat
        # Defense-adjusted damage = DMG * (DMG / (DMG + (DEF * (1-PEN))))
        # Final damage (not account for crit) = randomization of defense-adjusted damage

        source_stats = self.player_stats if self.scaling_stat_source == 'player' else self.target_stats
        original_DMG = source_stats[self.scaling_stat] * self.multiplier

        print(self.scaling_stat, "multiplier", self.multiplier, 'original DMG', original_DMG)
        
        DMG = 1
        if self.damage_type == "physical":
            defense_adjusted_DMG = original_DMG * (original_DMG / (original_DMG + (self.target_stats['pDEF'] * (1 - self.player_stats['pPEN']))))
            DMG = max(0, self.randomize_damage(defense_adjusted_DMG))
            print("Opponent pDEF", self.target_stats['pDEF'], "player pPEN", self.player_stats['pPEN'], 'defense adjusted DMG', defense_adjusted_DMG, 'randomized DMG', DMG)
        elif self.damage_type == "magical":
            defense_adjusted_DMG = original_DMG * (original_DMG / (original_DMG + (self.target_stats['mDEF'] * (1 - self.player_stats['mPEN']))))
            DMG = max(0, self.randomize_damage(defense_adjusted_DMG))
        elif self.damage_type == "true":
            DMG = original_DMG
        
        return DMG

class BattleAction():
    def __init__(self, name: str, player_info: dict, target_info: dict,
        attack_components: list[AttackComponent],
        base_accuracy: float = 0,
        player_status_effects: dict = {},
        target_status_effects: dict = {},
        no_crit: bool = False,
        qi_cost: int = 0,
    ):
        self.name = name
        self.player_info = player_info
        self.target_info = target_info
        self.attack_components = attack_components
        self.base_accuracy = base_accuracy
        self.player_status_effects = player_status_effects
        self.target_status_effects = target_status_effects
        self.no_crit = no_crit
        self.qi_cost = qi_cost
        self.description = 'This action has not yet been taken.'
        
    def determine_dodge(self):
        # Hit Chance = Move Accuracy * ((Attacker's ACC) / (Defender's EVA))
        hit_chance = min(1, self.base_accuracy * (self.player_info['stats']['ACC'] / self.target_info['stats']['EVA']))
        return (random.random() < hit_chance)
    
    def compute_damage(self): # Determines damage (assuming successful hit)
        player_stats = self.player_info['stats']; target_stats = self.target_info['stats']
        total_DMG = max(1, sum([attack_component.damage_dealt() for attack_component in self.attack_components]))
        print(self.player_info['Member'].display_name, "successful hit, chance", hit_chance, ", ", "orig DMG", total_DMG) # For debugging
        if self.no_crit:
            return total_DMG
        else:
            if random.random() < player_stats['CRIT']: # Critical hit
                return math.ceil(total_DMG * player_stats['CRIT DMG'])
                print("Critical hit!", player_stats['CRIT DMG'], math.ceil(total_DMG * player_stats['CRIT DMG'])) # For debugging
            else:
                return total_DMG
    
    async def execute(self): # Executes the attack, taking into passives and status effects, and updates database

        # Apply passive technique effects
        equipped_items = await player_info['Player'].get_equipped_items()
        techniques = equipped_items['techniques']

        for technique in techniques:
            # For now, hardcode different passive technique effects
            if technique == 'windimages':
                player_stats['SPD'] += 25
                player_stats['EVA'] += 25
                if random_success(0.3):
                    self.target_status_effects = 
        
        # Potentially apply status to opponent based on 
        for effect in self.player_status_effects['chance_to_apply']:
            chance, remaining_duration = self.player_status_effects['chance_to_apply'][effect]
            if not remaining_duration == 0:
                if random_success(chance):
                    self.target_status_effects['status'][effect] = {
                        'source': self.player_info['id'],
                        'duration': 1,
                    } # For now, status is only applied for one turn
            if remaining_duration == -1: # Permanent/passive
                pass:
            else:
                remaining_duration -= 1
        
        if self.player_status_effects['Burn']:
        elif self.player_status_effects['Shock']:
        elif self.player_status_effects['Fear']:
        elif self.player_status_effects['Bleed']:
        elif self.player_status_effects['Confuse']:
            confusion_probability = self.player_status_effects['Confuse']
            if self.dodged:
                if random.random() < confusion_probability:

        elif self.player_status_effects['Silence']:
        elif self.player_status_effects['Poison']:
        elif self.player_status_effects['Chill']:
        elif self.player_status_effects['Freeze']:
        elif self.player_status_effects['Frostbite']:
        
        

        action_damage = action.damage
        target_stats['HP'] = to_nonneg(target_stats['HP'] - action_damage)
        player_stats['Qi'] = to_nonneg(player_stats['Qi'] - 0)
        player_info['action'] = { 'name': action.name, 'description': str(action) }

        await PvpMatches.filter(id=self._id).update(
            player_stats={ player_info['id']: player_stats, target_info['id']: target_stats }, 
            player_action={ player_info['id']: player_info['action'], target_info['id']: target_info['action'] }
        )

        self.descripton = f'<@{self.player_info['id']}> used `{self.name}`, dealing {format_num_abbr1(self.damage)} damage to <@{self.target_info['id']}>'
    

class TechniqueDropdown(disnake.ui.Select):
    """Dropdown for selecting a technique."""

    def __init__(self, techniques: list, technique_cooldown_dict: dict, battle_view):
        options = []
        for index, technique in enumerate(techniques):
            if technique in technique_cooldown_dict:
                description = f'Qi Cost: x | Cooldown: {technique_cooldown_dict[technique]}'
            else:
                description = f'Qi Cost: x'
            options.append(disnake.SelectOption(label=technique, description=description, value=technique))
        
        super().__init__(placeholder="Choose a technique...", min_values=1, max_values=1, options=options)
        self.battle_view = battle_view
        self.techniques = techniques

    async def callback(self, inter: disnake.MessageInteraction):
        """Handles when a technique is selected."""
        await inter.response.defer()

        # Get selected technique
        selected_technique = self.values[0]

        # Identify if the user is the challenger or defender
        challenger_info, defender_info, turn, am_challenger = await self.battle_view.get_match_data()
        player_info, target_info = (challenger_info, defender_info) if am_challenger else (defender_info, challenger_info)
        player_stats, target_stats = player_info['stats'], target_info['stats']
        
        # Check if technique is on cooldown
        if selected_technique in player_info['status']['cooldowns'] and player_info['status']['cooldowns'][selected_technique] > 0: # At least 1 turn cooldown left
            await inter.followup.send(f"This technique is still on cooldown.", ephemeral=True)
        else:
            self.battle_view.countdown_task.cancel() # Stop the countdown
            self.battle_view.toggle_buttons(enabled=False) # Disable the buttons
            self.battle_view.clear_items()  # Remove dropdown
            await self.battle_view.message.edit(view=self.battle_view)
            
            # TODO: should technique effects be stored in the database or hardcoded?
            tech_name, tech_properties = await AllItems.get_or_none(id=selected_technique).values_list("name", "properties")
            
            # Execute technique (custom code for each technique)
            if selected_technique == "flametsunami":
                
                qi_cost = 15
                cooldown = 2
                attack_components = [AttackComponent(player_stats=player_stats, target_stats=target_stats, scaling_stat='pATK', scaling_stat_source='player', damage_type='physical', multiplier=1.3, true_damage=False), AttackComponent(player_stats=player_stats, target_stats=target_stats, scaling_stat='mATK', scaling_stat_source='player', damage_type='magical', multiplier=1.3, true_damage=False)]
                
                action = BattleAction(selected_technique, player_info, target_info, attack_components, base_accuracy = 0.9, player_status_effects = {}, target_status_effects = {
                    'mDEF_shred': (0.2, 2),
                    'pDEF_shred': (0.2, 2)
                }, qi_cost = qi_cost)

                action_damage = action.damage
                
                target_stats['HP'] = to_nonneg(target_stats['HP'] - action_damage)
                player_stats['Qi'] = to_nonneg(player_stats['Qi'] - qi_cost)
                player_info['action'] = { 'name': action.name, 'description': str(action) }
                player_info['status']['cooldowns'][selected_technique] = cooldown + 1
            
            elif selected_technique == "starshatter":
                
                qi_cost = 20
                cooldown = 5

                # Temporarily halve the enemy's mDEF
                orig_mDEF = target_stats['mDEF']
                target_stats['mDEF'] = orig_mDEF / 2

                attack_components = [AttackComponent(player_stats=player_stats, target_stats=target_stats, scaling_stat='mATK', scaling_stat_source='player', damage_type='magical', multiplier=3.4, true_damage=False)]
                
                action = BattleAction(selected_technique, player_info, target_info, attack_components, base_accuracy = 0.9, player_status_effects = {}, target_status_effects = {}, qi_cost = qi_cost)

                action_damage = action.damage
                
                target_stats['HP'] = to_nonneg(target_stats['HP'] - action_damage)
                player_stats['Qi'] = to_nonneg(player_stats['Qi'] - qi_cost)
                player_info['action'] = { 'name': action.name, 'description': str(action) }
                player_info['status']['cooldowns'][selected_technique] = cooldown + 1
                
                # Restore enemy's mDEF
                target_stats['mDEF'] = orig_mDEF

            await PvpMatches.filter(id=self.battle_view._id).update(
                player_stats={ player_info['id']: player_stats, target_info['id']: target_stats }, 
                player_action={ player_info['id']: player_info['action'], target_info['id']: target_info['action'] },
                player_status={ player_info['id']: player_info['status'], target_info['id']: target_info['status'] }
            )

            # Check if both players have chosen their actions
            if challenger_info["action"] and defender_info["action"]:
                if challenger_info['stats']['HP'] <= 0 or defender_info['stats']['HP'] <= 0:
                    await self.battle_view.display_final_turn(challenger_info, defender_info, turn)
                else:
                    turn += 1
                    await PvpMatches.filter(id=self.battle_view._id).update(turn=turn, player_action={ player_info['id']: None, target_info['id']: None })
                    await self.battle_view.display_next_turn(challenger_info, defender_info, turn)
            else:
                waiting_embed = disnake.Embed(description=f'Waiting for opponent...')
                await self.battle_view.message.edit(embeds=[*self.battle_view.message.embeds[:-1], waiting_embed])


def update_cooldowns(player_info):
    for technique in player_info['status']['cooldowns']:
        player_info['status']['cooldowns'][technique] = max(0, player_info['status']['cooldowns'][technique] - 1)

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
        match_data = await PvpMatches.get_or_none(id=self._id).values_list("challenger_id", "defender_id", "turn", "player_stats", "player_action", "player_status")
        challenger_id, defender_id, turn, player_stats, player_action, player_status = match_data
        
        challenger_info = construct_player_info(player_stats, player_action, player_status, self.guild, challenger_id)
        defender_info = construct_player_info(player_stats, player_action, player_status, self.guild, defender_id)
        am_challenger = (self.user_id == challenger_id) # Determine whether interacting user is challenger or defender
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

        victory_title_options = ["Fate Sealed!", "A Decisive Blow!", "The Final Strike!", "Victory!", f"The End of {loser_info['Member'].display_name}!", f"{winner_info['Member'].display_name}'s Triumph!", "The Battle's Turning Point!", f"{loser_info['Member'].display_name} Falls!", "The Ultimate Move!", "Destiny Fulfilled!", f"{winner_info['Member'].display_name} Reigns Supreme!", "The Last Stand!"]
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
        
        # Update cooldowns
        update_cooldowns(challenger_info); update_cooldowns(defender_info)
        await PvpMatches.filter(id=self._id).update(player_status={ challenger_info['id']: challenger_info['status'], defender_info['id']: defender_info['status'] })

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

        # For now, do basic attack and move on to next turn
        challenger_info, defender_info, turn, am_challenger = await self.get_match_data()
        player_info, target_info = (challenger_info, defender_info) if am_challenger else (defender_info, challenger_info)
        player_stats, target_stats = player_info['stats'], target_info['stats']

        # Basic attack
        attack_components = [AttackComponent(player_stats, target_stats, scaling_stat='pATK', scaling_stat_source='player', damage_type='physical', multiplier=1, true_damage=False)]
        action = BattleAction('basic_attack', player_info, target_info, attack_components, base_accuracy = 0.9, player_status_effects = {}, target_status_effects = {}, qi_cost = 0)
        
        action_damage = action.damage
        target_stats['HP'] = to_nonneg(target_stats['HP'] - action_damage)
        player_stats['Qi'] = to_nonneg(player_stats['Qi'] - 0)
        player_info['action'] = { 'name': action.name, 'description': str(action) }

        await PvpMatches.filter(id=self._id).update(
            player_stats={ player_info['id']: player_stats, target_info['id']: target_stats }, 
            player_action={ player_info['id']: player_info['action'], target_info['id']: target_info['action'] }
        )

        # Challenger side sends message if both players timed out, otherwise defender side sends message
        if (challenger_info['action']) or am_challenger:
            turn += 1
            await PvpMatches.filter(id=self._id).update(turn=turn, player_action={ player_info['id']: None, target_info['id']: None })
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
            player_info, target_info = (challenger_info, defender_info) if am_challenger else (defender_info, challenger_info)
            player_stats, target_stats = player_info['stats'], target_info['stats']

            # Basic attack
            attack_components = [AttackComponent(player_stats, target_stats, scaling_stat='pATK', scaling_stat_source='player', damage_type='physical', multiplier=1, true_damage=False)]
            action = BattleAction('basic_attack', player_info, target_info, attack_components, base_accuracy = 0.9, player_status_effects = {}, target_status_effects = {}, qi_cost = 0)
            action_damage = action.damage

            target_stats['HP'] = to_nonneg(target_stats['HP'] - action_damage)
            player_stats['Qi'] = to_nonneg(player_stats['Qi'] - 0)
            player_info['action'] = { 'name': action.name, 'description': str(action) }

            await PvpMatches.filter(id=self._id).update(
                player_stats={ player_info['id']: player_stats, target_info['id']: target_stats }, 
                player_action={ player_info['id']: player_info['action'], target_info['id']: target_info['action'] }
            )
            
            if challenger_info['action'] and defender_info['action']: # Both players have submitted moves, move on to next turn
                
                if player_stats['HP'] <= 0 or target_stats['HP'] <= 0: # Handle end of match
                    await self.display_final_turn(challenger_info, defender_info, turn)
                else:
                    turn += 1
                    await PvpMatches.filter(id=self._id).update(turn=turn, player_action={ challenger_info['id']: None, defender_info['id']: None })
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
        player_info = challenger_info if am_challenger else defender_info
        equipped_items = await player_info['Player'].get_equipped_items()
        techniques = equipped_items['techniques']
        
        # Create a dropdown for technique selection
        if len(techniques) > 0:
            
            # Get technique Qi costs and cooldowns
            technique_cooldown_dict = {}
            for technique in player_info['status']['cooldowns']:
                cooldown = player_info['status']['cooldowns'][technique]
                if cooldown > 0:
                    technique_cooldown_dict[technique] = cooldown
            
            technique_dropdown = TechniqueDropdown(techniques, technique_cooldown_dict, self)
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
            player_stats = {
                str(self.challengerPlayer.id): {
                    'pATK': 200, # Physical Attack
                    'mATK': 200, # Magical Attack
                    'pDEF': 200, # Physical Defense
                    'mDEF': 200, # Magical Defense
                    'pPEN': 0.1, # Physical Penetration
                    'mPEN': 0.1, # Magical Penetration
                    'SPD': 100, # Speed
                    'ACC': 0.95, # Accuracy
                    'EVA': 0.05, # Evasion (dodge)
                    'CRIT': 0.05, # Critical rate
                    'CRIT DMG': 1.50, # Critical damage multiplier
                    'HP': 2000, 
                    'Max HP': 2000, 
                    'Qi': 100,
                    'Max Qi': 100
                },
                str(self.defenderPlayer.id): {
                    'pATK': 200, # Physical Attack
                    'mATK': 200, # Magical Attack
                    'pDEF': 200, # Physical Defense
                    'mDEF': 200, # Magical Defense
                    'pPEN': 0.1, # Physical Penetration
                    'mPEN': 0.1, # Magical Penetration
                    'SPD': 100, # Speed
                    'ACC': 0.95, # Accuracy
                    'EVA': 0.05, # Evasion (dodge)
                    'CRIT': 0.05, # Critical rate
                    'CRIT DMG': 1.50, # Critical damage multiplier
                    'HP': 2000, 
                    'Max HP': 2000, 
                    'Qi': 100,
                    'Max Qi': 100
                }
            }

            player_action = {
                str(self.challengerPlayer.id): None,
                str(self.defenderPlayer.id): None
            }

            player_status = {
                str(self.challengerPlayer.id): {
                    'cooldowns': {}, # technique ID -> remaining cooldown
                    'debuffs': {}, # debuff type -> (value (if applicable), remaining cooldown)
                    'buffs': {} # buff type -> (value, remaining cooldown)
                },
                str(self.defenderPlayer.id): {
                    'cooldowns': {}, # technique ID -> remaining cooldown
                    'debuffs': {},
                    'buffs': {}
                },
            }

            # Current player info, start at turn 1
            challenger_info = construct_player_info(player_stats, player_action, player_status, self.guild, self.challengerPlayer.id)
            defender_info = construct_player_info(player_stats, player_action, player_status, self.guild, self.defenderPlayer.id)
            turn = 1
            
            # Create a new PvP match and add to database
            pvpmatch = await PvpMatches.create(challenger_id=self.challengerPlayer.id, defender_id=self.defenderPlayer.id, 
                player_stats=player_stats, player_action=player_action, player_status=player_status, created_at=disnake.utils.utcnow(), updated_at=disnake.utils.utcnow(), turn=turn)
            
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
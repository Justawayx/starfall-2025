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
import random, asyncio, json, math, copy
from rich import print
# from character.pvp_stats import PvPStats

# TODO: remove bruv from shop
# Action descriptions
# - dealing x magical damage, dealing x physical damage, dealing x mixed damage, dealing x true damage
# Mention status effects applied
# Elements
# Put technique code in a separate file
# Cooldowns
# Status effects
# A player who is dead cannot attack
# Lock in techniques for the duration of a match (cannot learn/unlearn)
# Process turns at once rather than by the person who last clicked
# Speed -> order of actions correspond
# Status effect levels

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

'''
Examples of player_stats_dict, player_action_dict, player_status_dict

example_player_stats_dict = {
    player1_user_ID: {
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
    player2_user_ID: { ... }
}

example_player_action_dict = { 
    player1_user_ID: { 
        'name': 'wopwop', 
        'description': 'Player1 used `wopwop`, dealing 3,455 damage to Player2'
    },
    player2_user_ID: None # Indicates player has not submitted an action yet
}

example_player_status_dict = {
    player1_user_ID: {
        'cooldowns': {}, # technique ID -> remaining cooldown
        'debuffs': {}, # debuff type -> {value, remaining cooldown}
        'buffs': {} # buff type -> {value, remaining cooldown}
        'status': { # status type -> {source, duration}
            'Confusion': {
                'source': player2_user_ID,
                'duration': 1,
            }
        }
    }
}
'''

class PvPMatch(): # In-memory representation of a match

    def __init__(self, match_id: int, challenger_id: int, defender_id: int,
        player_stats_dict: dict, player_action_dict: dict, player_status_dict: dict, player_techniques_dict: dict
    ):
        # Initialize match
        self._id = match_id  # Store the match ID (create database record first)
        self.challenger_id = challenger_id
        self.defender_id = defender_id
        self.status = "pending" # Match status
        self.turn = 1 # Turn number
        
        # Store player stats, actions, and status
        self.player_stats_dict = player_stats_dict # Dictionary: user ID -> stats dict
        self.player_action_dict = player_action_dict # Dictionary: user ID -> action dict
        self.player_status_dict = player_status_dict # Dictionary: user ID -> status dict
        self.player_techniques_dict = player_techniques_dict # Dictionary: user ID -> tech_id -> original cooldown

        # Apply permanent passive effects at the start of the match
        self.apply_all_passive_effects()

    # Apply technique permanent passive effect(s) to one player
    def apply_passive_effect(self, player_id, technique_id):
        # ================================================================================
        # HARDCODED TECHNIQUE EFFECTS PORTION
        # ================================================================================
        if technique_id == 'windimages':
            self.player_stats_dict[player_id]['SPD'] += 25
            self.player_stats_dict[player_id]['EVA'] += 25
        elif technique_id == 'ninewindsteps':
            self.player_stats_dict[player_id]['EVA'] += 20
        elif technique_id == 'skysteps':
            self.player_stats_dict[player_id]['SPD'] += 20
            self.player_stats_dict[player_id]['EVA'] += 20
        elif technique_id == 'cottonhand':
            self.player_stats_dict[player_id]['pATK'] += 15
            self.player_stats_dict[player_id]['mATK'] += 15
            self.player_stats_dict[player_id]['pDEF'] += 15
            self.player_stats_dict[player_id]['mDEF'] += 15

    # Apply all technique permanent passive effects to all players
    def apply_all_passive_effects(self):
        for player_id in self.player_techniques_dict:
            for technique_id in self.player_techniques_dict[player_id]:
                self.apply_passive_effect(player_id, technique_id)

    # Get a list of current player status effects
    def get_player_status_effects(self, player_id):
        active_effects = []

        for status_effect in self.player_status_dict[player_id]['status']:
            duration = self.player_status_dict[player_id]['status'][status_effect]['duration']
            if duration > 0:
                active_effects.append(status_effect)
        
        return active_effects

    # Access match data
    def get_match_data(self):
        return self.challenger_id, self.defender_id, self.turn, self.player_stats_dict, self.player_action_dict, self.player_status_dict

    # Update match information in database
    async def update_database_record(self):
        await PvpMatches.filter(id=self._id).update(status=self.status, turn=self.turn, player_stats=self.player_stats_dict)
    
    # Store one player's action
    def store_action(self, player_id: int, battle_action):
        self.player_action_dict[player_id] = battle_action

    # Clear player actions
    def clear_player_actions(self):
        for player_id in self.player_action_dict:
            self.player_action_dict[player_id] = None

    # Get player in list with highest current SPD
    def get_next_player(self, player_id_list: list[int]):
        player_SPD_dict = { player_id: self.player_stats_dict[player_id]['SPD'] for player_id in player_id_list }
        ordered_player_SPD_tups = sorted(player_SPD_dict.items(), key=lambda x: x[1], reverse=True)
        return ordered_player_SPD_tups[0][0]

    # Check if all players have submitted actions
    def all_players_ready(self):
        return all([(self.player_action_dict[player_id] != None) for player_id in self.player_action_dict])

    # Check if a player has won (currently only works for 1v1)
    def check_winner(self):
        end_of_match = False
        for player_id in self.player_stats_dict:
            if self.player_stats_dict[player_id]['HP'] <= 0:
                loser = player_id
                end_of_match = True
            else:
                alive_player = player_id
        if end_of_match:
            return alive_player
        else:
            return False # Nobody has died, match is not yet over

    # Update cooldowns
    def update_cooldowns(self):
        for player_id in self.player_status_dict:
            status_dict = self.player_status_dict[player_id]
            for technique in status_dict['cooldowns']: # Technique usage cooldowns
                status_dict['cooldowns'][technique] = max(0, status_dict['cooldowns'][technique] - 1)
            for status_effect in status_dict['status']: # Status effect durations
                status_dict['status'][status_effect]['duration'] = max(0, status_dict['status'][status_effect]['duration'] - 1)

    # Execute target response to attacker action
    async def execute_target_response(self, action):
        responder_id = action.target
        # ================================================================================
        # HARDCODED TECHNIQUE EFFECTS PORTION
        # ================================================================================
        if 'windimages' in self.player_techniques_dict[responder_id]:
            if action.dodged: # Target dodged this attack
                # 30% chance of confusing the attacker
                if random_success(0.3):
                    self.player_status_dict[action.player]['status']['Confusion'] = {
                        'source': responder_id,
                        'duration': 1+1
                    }
                    action.description += f'\n<@{responder_id}> confused <@{action.player}> for one turn!'
        elif 'skysteps' in self.player_techniques_dict[responder_id]:
            if action.dodged: # Target dodged this attack
                # Target counter-attacks the attacker with basic attack
                attack_components = [AttackComponent(player_stats=self.player_stats_dict[responder_id], target_stats=self.player_stats_dict[action.player], scaling_stat='pATK', scaling_stat_source='player', damage_type='physical', multiplier=1, true_damage=False)]
                counter_action = BattleAction(name='basic_attack', player=responder_id, target=action.player, match=self, attack_components=attack_components, base_accuracy = 0.9, player_status_effects = {}, target_status_effects = {}, qi_cost = 0, action_type='basic attack')
                
                await counter_action.execute()

                # Update the action description for the attacker
                action.description += f'<@{responder_id}> counter-attacked <@{action.player}>, dealing {format_num_abbr1(action.damage)} damage!'


    # Execute current turn actions for all players
    async def execute_turn(self):
        pending_players = copy.copy(list(self.player_action_dict.keys())) # List of players whose actions have not been executed yet

        while len(pending_players) > 0:
            current_player = self.get_next_player(pending_players) # Get next player
            action = await self.execute_action(current_player) # Execute this player's action
            await self.execute_target_response(action) # Execute target response
            pending_players.remove(current_player) # Remove player from pending list

            winner = self.check_winner() # Check for terminating condition
            if winner: # If there is a winner, do not execute remaining player actions
                self.status = "completed"
                for player_id in pending_players:
                    self.player_action_dict[player_id].description = ''
                break
        
        # Update database
        await self.update_database_record()

    # Update cooldowns and increment turn
    def next_turn(self):
        self.update_cooldowns()
        self.turn += 1
    
    # Clear player actions (run after displaying turn)
    def clear_actions(self):
        self.clear_player_actions()

    # Execute one player's action
    async def execute_action(self, player_id: int):
        action = self.player_action_dict[player_id]
        await action.execute()
        return action

def construct_player_info(match: PvPMatch, guild, user_id):
    player_info = {
        'id': user_id,
        'Member': guild.get_member(user_id),
        'Player': PlayerRoster().get(user_id),
        'action': match.player_action_dict[user_id],
        'stats': match.player_stats_dict[user_id],
        'status': match.player_status_dict[user_id],
        'active_effects': match.get_player_status_effects(user_id)
    }
    return player_info

class AttackComponent(): # Representation of a damage dealing component of an attack
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


class BattleAction(): # Representation of a player's action at a turn in battle
    def __init__(self, name: str, player: int, target: int, match: PvPMatch,
        action_type: str, # 'basic attack' or 'technique' for now
        attack_components: list[AttackComponent],
        base_accuracy: float = 0,
        player_status_effects: dict = {},
        target_status_effects: dict = {},
        no_crit: bool = False,
        qi_cost: int = 0,
        cooldown: int = 0,
    ):
        self.name = name; self.player = player; self.target = target; self.match = match
        self.action_type = action_type
        self.attack_components = attack_components
        self.base_accuracy = base_accuracy
        self.player_status_effects = player_status_effects
        self.target_status_effects = target_status_effects
        self.no_crit = no_crit
        self.qi_cost = qi_cost
        self.description = ''
        self.cooldown = cooldown
        
    def get_player_target_info(self):
        player_stats = self.match.player_stats_dict[self.player]; target_stats = self.match.player_stats_dict[self.target]
        player_status = self.match.player_status_dict[self.player]; target_status = self.match.player_status_dict[self.target]
        return player_stats, target_stats, player_status, target_status

    def determine_dodge(self):
        player_stats, target_stats, _, _ = self.get_player_target_info()
        
        # Hit Chance = Move Accuracy * ((Attacker's ACC) / (Defender's EVA))
        hit_chance = min(1, self.base_accuracy * (player_stats['ACC'] / target_stats['EVA']))
        return (random.random() < (1-hit_chance))
    
    def compute_damage(self): # Determines damage (assuming successful hit)
        player_stats, target_stats, _, _ = self.get_player_target_info()

        total_DMG = max(1, sum([attack_component.damage_dealt() for attack_component in self.attack_components]))
        if self.no_crit:
            return total_DMG
        else:
            if random.random() < player_stats['CRIT']: # Critical hit
                return math.ceil(total_DMG * player_stats['CRIT DMG'])
            else:
                return total_DMG
    
    async def execute(self): # Executes the attack, taking into account passives and status effects
        player_stats, target_stats, player_status, target_status = self.get_player_target_info()

        action_damage = self.compute_damage()
        opponent_dodged = self.determine_dodge()

        # Check for player status effects
        # ================================================================================
        # HARDCODED TECHNIQUE EFFECTS PORTION
        # ================================================================================
        for status_effect in self.match.get_player_status_effects(self.player):
            if status_effect == 'Confusion':
                # Retargets attack to user or an ally for 50% damage
                if random_success(0.3): # Confusion failed
                    pass
                else: # TODO: confusion cannot be critical hit
                    opponent_dodged = False
                    action_damage = math.ceil(action_damage * 0.5)
                    self.description = f'<@{self.player}> tried to attack <@{self.target}>, but was confused and attacked themselves instead!\n'
                    self.target = self.player; target_stats = player_stats; target_status = player_status

        if self.name == 'shatterclaw':
            target_stats['Qi'] = math.ceil(0.6*target_stats['Qi'])

        # Update player Qi based on Qi cost and target HP based on damage dealt
        player_stats['Qi'] = to_nonneg(player_stats['Qi'] - self.qi_cost)
        if opponent_dodged:
            self.description = f'<@{self.player}> used `{self.name}`, but <@{self.target}> dodged!'
        else:
            target_stats['HP'] = to_nonneg(target_stats['HP'] - action_damage)
            self.description += f'<@{self.player}> used `{self.name}`, dealing {format_num_abbr1(action_damage)} damage to <@{self.target}>'

        # If action type is technique, set cooldown
        if self.action_type == 'technique':
            self.match.player_status_dict[self.player]['cooldowns'][self.name] = self.cooldown + 1
        
        self.dodged = opponent_dodged
        self.damage = action_damage
        return self # Return information for opponent response
    

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
        challenger_info, defender_info, turn, am_challenger = self.battle_view.get_match_data()
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
                attack_components = [AttackComponent(player_stats=player_stats, target_stats=target_stats, scaling_stat='pATK', scaling_stat_source='player', damage_type='physical', multiplier=1.3, true_damage=False), AttackComponent(player_stats=player_stats, target_stats=target_stats, scaling_stat='mATK', scaling_stat_source='player', damage_type='magical', multiplier=1.3, true_damage=False)]
                action = BattleAction(selected_technique, player_info['id'], target_info['id'], self.battle_view.match, 'technique', attack_components, base_accuracy = 0.9, player_status_effects = {}, target_status_effects = {
                    'mDEF_shred': (0.2, 2),
                    'pDEF_shred': (0.2, 2)
                }, qi_cost = 15, cooldown=2)
            elif selected_technique == "starshatter":
                attack_components = [AttackComponent(player_stats=player_stats, target_stats=target_stats, scaling_stat='mATK', scaling_stat_source='player', damage_type='magical', multiplier=3.4, true_damage=False)]
                action = BattleAction(selected_technique, player_info['id'], target_info['id'], self.battle_view.match, 'technique', attack_components, base_accuracy = 0.9, player_status_effects = {}, target_status_effects = {}, qi_cost = 20, cooldown=5)
            elif selected_technique == 'windkillfinger':
                attack_components = [AttackComponent(player_stats=player_stats, target_stats=target_stats, 
                                                    scaling_stat='pATK', scaling_stat_source='player', 
                                                    damage_type='physical', multiplier=2.8, true_damage=False)]
                action = BattleAction(selected_technique, player_info['id'], target_info['id'], self.battle_view.match, 'technique', attack_components, 
                                    base_accuracy=0.9, player_status_effects={}, 
                                    target_status_effects={'pDEF_shred': (0.1, 99)},  # Lasts 99 turns
                                    qi_cost=20, cooldown=4)
            elif selected_technique == 'shatterclaw':
                attack_components = [AttackComponent(player_stats=player_stats, target_stats=target_stats, 
                                                    scaling_stat='pATK', scaling_stat_source='player', 
                                                    damage_type='physical', multiplier=2.9, true_damage=False)]
                action = BattleAction(selected_technique, player_info['id'], target_info['id'], self.battle_view.match, 'technique', attack_components, 
                                    base_accuracy=0.85, player_status_effects={}, 
                                    target_status_effects={}, qi_cost=25, cooldown=5)

            self.battle_view.match.store_action(player_info['id'], action)
            
            if self.battle_view.match.all_players_ready():
                await self.battle_view.match.execute_turn()
                if self.battle_view.match.status == 'completed': # Handle end of match
                    await self.battle_view.display_final_turn()
                else:
                    await self.battle_view.display_next_turn()
            else:
                waiting_embed = disnake.Embed(description=f'Waiting for opponent...')
                await self.battle_view.message.edit(embeds=[*self.battle_view.message.embeds[:-1], waiting_embed])

class MainBattleView(View):

    def __init__(self, guild: disnake.Guild, channel: disnake.TextChannel, match: PvPMatch, user_id: int, opponent_user_id: int,
        message: disnake.Message = None, opponent_message: disnake.Message = None, public_message: disnake.Message = None):
        super().__init__(timeout=None)  # Handle timeout manually
        self.countdown = 30
        self.message = message  # Store this user's message (for updating)
        self.opponent_message = opponent_message  # Store the opponent's message (for updating)
        self.public_message = public_message # Store the public message (for updating)
        self.guild = guild  # Store the guild
        self.channel = channel  # Store the channel
        self.match = match # Store the PvPMatch object
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

    def get_match_data(self) -> Tuple[dict, dict, int, bool]:
        challenger_id, defender_id, turn, player_stats, player_action, player_status = self.match.get_match_data()
        challenger_info = construct_player_info(self.match, self.guild, challenger_id)
        defender_info = construct_player_info(self.match, self.guild, defender_id)
        am_challenger = (self.user_id == challenger_id) # Determine whether interacting user is challenger or defender
        return challenger_info, defender_info, turn, am_challenger
    
    async def display_final_turn(self):
        self.stop() # Stop the view

        challenger_info, defender_info, turn, am_challenger = self.get_match_data()
        winner_info, loser_info = (challenger_info, defender_info) if defender_info['stats']['HP'] <= 0 else (defender_info, challenger_info)

        # Generate updated embeds
        battle_embed = generate_battle_embed(challenger_info, defender_info, turn)
        action_embed = disnake.Embed(
            description=f"{challenger_info['action'].description}\n{defender_info['action'].description}",
            color=disnake.Color.red()
        )

        victory_title_options = ["Fate Sealed!", "A Decisive Blow!", "The Final Strike!", "Victory!", f"The End of {loser_info['Member'].display_name}!", f"{winner_info['Member'].display_name}'s Triumph!", "The Battle's Turning Point!", f"{loser_info['Member'].display_name} Falls!", "The Ultimate Move!", "Destiny Fulfilled!", f"{winner_info['Member'].display_name} Reigns Supreme!", "The Last Stand!"]
        victory_title = random.choice(victory_title_options)
        victory_description = f"<@{winner_info['id']}>'s `{winner_info['action'].name}` sealed the fate of <@{loser_info['id']}>!"
        
        result_embed = simple_embed(victory_title, victory_description)

        # Updates embeds in public channel and for both players
        await self.public_message.edit(embeds=[action_embed, battle_embed, result_embed])
        await self.message.edit(embeds=[action_embed, battle_embed, result_embed])
        await self.opponent_message.edit(embeds=[action_embed, battle_embed, result_embed])

    async def display_next_turn(self):
        self.match.next_turn()
        challenger_info, defender_info, turn, am_challenger = self.get_match_data()
        print("================================\nData before embed for this turn:", turn)
        print("-------------------\nChallenger info:")
        print(challenger_info)
        print(challenger_info['action'].__dict__)
        print("-------------------\nDefender info:")
        print(defender_info)
        print(defender_info['action'].__dict__)
        # Generate updated embeds
        battle_embed = generate_battle_embed(challenger_info, defender_info, turn)
        action_embed = disnake.Embed(
            description=f"{challenger_info['action'].description}\n{defender_info['action'].description}",
            color=disnake.Color.red()
        )
        initial_countdown_embed = simple_embed('', "Starting turn...", color=disnake.Color.blue())

        # Updates embed in public channel
        await self.public_message.edit(embeds=[action_embed, battle_embed])
        
        # Send updated embeds to the challenger and store the message object
        challengerBattleView = MainBattleView(guild=self.guild, channel=self.channel, match=self.match, user_id=challenger_info['id'], opponent_user_id=defender_info['id'], public_message=self.public_message)
        challenger_message = await challenger_info['Member'].send(embeds=[action_embed, battle_embed, initial_countdown_embed], view=challengerBattleView)
        challengerBattleView.message = challenger_message  # Store the message for dynamic updates

        # Send updated embeds to the defender and store the message object
        defenderBattleView = MainBattleView(guild=self.guild, channel=self.channel, match=self.match, user_id=defender_info['id'], opponent_user_id=challenger_info['id'], public_message=self.public_message)
        defender_message = await defender_info['Member'].send(embeds=[action_embed, battle_embed, initial_countdown_embed], view=defenderBattleView)
        defenderBattleView.message = defender_message  # Store the message for dynamic updates

        # Store references to the other player's message
        challengerBattleView.opponent_message = defender_message
        defenderBattleView.opponent_message = challenger_message
        
        # Delete original messages for both players
        await self.message.delete()
        await self.opponent_message.delete()

        # Clear actions
        self.match.clear_actions()
    
    # Handle timeout (when the user doesn't click a button in time)
    async def on_timeout(self):
        timeout_embed = disnake.Embed(description="⏰ Time's up! You didn't respond in time.")
        self.toggle_buttons(enabled=False) # Disable the buttons
        await self.message.edit(embeds=[*self.message.embeds[:-1], timeout_embed], view=self)

        # For now, do basic attack and move on to next turn
        challenger_info, defender_info, turn, am_challenger = self.get_match_data()
        player_info, target_info = (challenger_info, defender_info) if am_challenger else (defender_info, challenger_info)
            
        # Basic attack
        action = BattleAction( name='basic_attack', player=player_info['id'], target=target_info['id'], match=self.match, attack_components=[ AttackComponent(player_info['stats'], target_info['stats'], scaling_stat='pATK', scaling_stat_source='player', damage_type='physical', multiplier=1, true_damage=False)], base_accuracy = 0.9, player_status_effects = {}, target_status_effects = {}, qi_cost = 0,action_type='basic attack')

        self.match.store_action(player_info['id'], action)
        
        if self.match.all_players_ready():
            await self.match.execute_turn()
            if self.match.status == 'completed': # Handle end of match
                await self.display_final_turn()
            else:
                await self.display_next_turn()

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

        challenger_info, defender_info, turn, am_challenger = self.get_match_data()
        player_info, target_info = (challenger_info, defender_info) if am_challenger else (defender_info, challenger_info)
        
        # Basic attack
        action = BattleAction(
            name='basic_attack', 
            player=player_info['id'], 
            target=target_info['id'], 
            match=self.match,
            attack_components=[
                AttackComponent(player_info['stats'], target_info['stats'], 
                    scaling_stat='pATK', 
                    scaling_stat_source='player', 
                    damage_type='physical', 
                    multiplier=1, 
                    true_damage=False
                )
            ], 
            base_accuracy = 0.9, 
            player_status_effects = {}, 
            target_status_effects = {}, 
            qi_cost = 0,
            action_type='basic attack'
        )

        self.match.store_action(player_info['id'], action)
        
        if self.match.all_players_ready():
            await self.match.execute_turn()
            if self.match.status == 'completed': # Handle end of match
                await self.display_final_turn()
            else:
                await self.display_next_turn()
        
        else: # Waiting for opponent to submit move
            waiting_embed = disnake.Embed(description=f'Waiting for opponent...')
            await inter.edit_original_message(embeds=[*self.message.embeds[:-1], waiting_embed])
    
    @disnake.ui.button(label="Use Technique", style=disnake.ButtonStyle.primary, custom_id="use_technique")
    async def use_technique(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.defer()

        # Fetch techniques for this player
        challenger_info, defender_info, turn, am_challenger = self.get_match_data()
        player_info = challenger_info if am_challenger else defender_info
        
        techniques_dict = self.match.player_techniques_dict[player_info['id']]
        techniques = sorted(techniques_dict.keys())
        
        # TODO: store elsewhere
        passive_only_techniques = ['skysteps', 'windimages']
        techniques = [technique for technique in techniques if technique not in passive_only_techniques]

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

# Generate battle embed
def generate_battle_embed(challenger_info: dict, defender_info: dict, turn: int) -> disnake.Embed:

    challenger_stats = challenger_info['stats']; defender_stats = defender_info['stats']

    challenger_effect_str = '*None*' if len(challenger_info['active_effects']) == 0 else ('\n'.join([f'- {effect}' for effect in challenger_info['active_effects']]))
    defender_effect_str = '*None*' if len(defender_info['active_effects']) == 0 else ('\n'.join([f'- {effect}' for effect in defender_info['active_effects']]))
    
    embed = disnake.Embed(
        title=f"⚔️ PvP Battle: Turn {turn}",
        color=disnake.Color.blue()
    )
    embed.add_field(
        name=f"{challenger_info['Member'].display_name}",
        value=f"""HP: `{challenger_stats['HP']}`/`{challenger_stats['Max HP']}`
        Qi: `{challenger_stats['Qi']}`/`{challenger_stats['Max Qi']}`
        Status Effects: {challenger_effect_str}""",
        inline=True
    )
    embed.add_field(
        name=f"{defender_info['Member'].display_name}",
        value=f"""HP: `{defender_stats['HP']}`/`{defender_stats['Max HP']}`
        Qi: `{defender_stats['Qi']}`/`{defender_stats['Max Qi']}`
        Status Effects: {defender_effect_str}""",
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
                self.challengerPlayer.id: {
                    'pATK': 200, # Physical Attack
                    'mATK': 200, # Magical Attack
                    'pDEF': 200, # Physical Defense
                    'mDEF': 200, # Magical Defense
                    'pPEN': 0.1, # Physical Penetration
                    'mPEN': 0.1, # Magical Penetration
                    'SPD': 120, # Speed
                    'ACC': 0.95, # Accuracy
                    'EVA': 0.50, # Evasion (dodge)
                    'CRIT': 0.05, # Critical rate
                    'CRIT DMG': 1.50, # Critical damage multiplier
                    'HP': 2000, 
                    'Max HP': 2000, 
                    'Qi': 100,
                    'Max Qi': 100
                },
                self.defenderPlayer.id: {
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
                self.challengerPlayer.id: None,
                self.defenderPlayer.id: None
            }

            player_status = {
                self.challengerPlayer.id: {
                    'cooldowns': {}, # technique ID -> remaining cooldown
                    'debuffs': {}, # debuff type -> (value (if applicable), remaining cooldown)
                    'buffs': {}, # buff type -> (value, remaining cooldown)
                    'status': {},
                },
                self.defenderPlayer.id: {
                    'cooldowns': {}, # technique ID -> remaining cooldown
                    'debuffs': {},
                    'buffs': {},
                    'status': {},
                },
            }

            turn = 1

            player_techniques_dict = {}
            for player in [self.challengerPlayer, self.defenderPlayer]:
                equipped_items = await player.get_equipped_items()
                techniques = equipped_items['techniques']
                player_techniques_dict[player.id] = { technique: 3 for technique in techniques }
            
            # Create a new PvP match and add to database
            pvpmatch = await PvpMatches.create(challenger_id=self.challengerPlayer.id, defender_id=self.defenderPlayer.id, 
                player_stats=player_stats, player_action=player_action, player_status=player_status, created_at=disnake.utils.utcnow(), updated_at=disnake.utils.utcnow(), turn=turn)
            
            self._id = pvpmatch.id # Match ID

            # Create the in-memory match object
            match = PvPMatch(pvpmatch.id, self.challengerPlayer.id, self.defenderPlayer.id, player_stats, player_action, player_status, player_techniques_dict)

            challenger_info = construct_player_info(match, self.guild, self.challengerPlayer.id)
            defender_info = construct_player_info(match, self.guild, self.defenderPlayer.id)
            
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
                    
                    playerBattleView = MainBattleView(guild=self.guild, channel=self.channel, match=match, user_id=player.id, opponent_user_id=other_player.id)
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
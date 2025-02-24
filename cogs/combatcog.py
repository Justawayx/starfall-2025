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
from collections import defaultdict
import roman
# from character.pvp_stats import PvPStats

# Elemental effectiveness
ELEMENT_EFFICACY_DICT = defaultdict(dict)

with open('./data/element_matrix.tsv', 'r') as f:
    defending_elements = f.readline().strip('\n').split('\t')[1:]
    for line in f:
        items = line.strip('\n').split('\t')
        attacking_element = items[0]
        multipliers = []
        for item in items[1:]:
            multiplier_str = item.lstrip('x')
            if '/' in multiplier_str:
                numerator, denominator = multiplier_str.split('/')
                multipliers.append(float(numerator)/float(denominator))
            else:
                multipliers.append(int(multiplier_str))
        for defending_element, multiplier in zip(defending_elements, multipliers):
            ELEMENT_EFFICACY_DICT[attacking_element][defending_element] = multiplier

# TODO: remove bruv from shop
# Action descriptions
# - dealing x magical damage, dealing x physical damage, dealing x mixed damage, dealing x true damage
# Mention status effects applied
# A player who is dead cannot attack
# Lock in techniques for the duration of a match (cannot learn/unlearn)
# Process turns at once rather than by the person who last clicked
# Speed -> order of actions correspond
# Status effect levels
# Elemental immunities
# Status effects should happen at end of turn
# Check if Skeleton king attacking another one is dark on dark damage (0.5 multiplier)
# Use full technique names [OK]
# Add debuffs to combat log [OK]
# Stun/silence should depend on speed [OK]
# +xx stat on an attack should be treated as permanent passive with conditional triggering (WL claw ACC+40) [OK-just don't announce]
# If it's 99 turns, say "for the rest of the battle" [OK]
# Dodging should also dodge technique's status effects/buffs and debuffs [OK]
# Someone with one star lower cultivation can only win through a lucky crit/dodge
# otherwise most of the time the person with higher cultivation wins
# basic attacks only

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
        'Max Qi': 100,
        'Elemental Affinities': ['Fire', 'Water', 'Earth'],
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
        'debuffs': [], # (debuff stat, value, remaining cooldown) list
        'buffs': [] # (buff stat, value, remaining cooldown) list
        'status': { # status type -> {source, duration}
            'Confusion': {
                'source': player2_user_ID,
                'duration': 1,
                'potency': 1
            }
            'Nine Turning Wind': {
                'source': player1_user_ID,
                'duration': 99,
                'potency': 1,
                'dodge_bonus': True,
            }
            'Freeze': False,
        },
        'summons': [{ # List of summons (retains summon after it dies)
            'name': 'Skeleton King',
            'HP': skeleton_hp,
            'Max HP': skeleton_hp,
            'SPD': skeleton_speed,
            'active': True,
            'Elemental Affinities': ['Dark'],
            'Elemental Immunities': ['Fire', 'Water'],
        }]
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
        self.player_techniques_dict = player_techniques_dict # Dictionary: user ID -> tech_id -> original cooldown, Qi cost
        self.player_summon_action_dict = defaultdict(dict) # Dictionary: user ID -> summon ID -> action dict
        
        # Store decriptions of all actions taken during this turn
        self.action_descriptions = []

        # Apply permanent passive effects at the start of the match
        self.apply_all_passive_effects()

    # Apply technique one-time permanent passive effect(s) to one player
    def apply_passive_effect(self, player_id, technique_id):
        # ================================================================================
        # HARDCODED TECHNIQUE EFFECTS PORTION
        # ================================================================================
        if technique_id == 'windimages':
            self.player_stats_dict[player_id]['SPD'] = math.ceil(1.25 * self.player_stats_dict[player_id]['SPD'])
            self.player_stats_dict[player_id]['EVA'] = math.ceil(1.25 * self.player_stats_dict[player_id]['EVA'])
        elif technique_id == 'ninewindsteps':
            self.player_stats_dict[player_id]['EVA'] = math.ceil(1.20 * self.player_stats_dict[player_id]['EVA'])
        elif technique_id == 'skysteps':
            self.player_stats_dict[player_id]['SPD'] = math.ceil(1.20 * self.player_stats_dict[player_id]['SPD'])
            self.player_stats_dict[player_id]['EVA'] = math.ceil(1.20 *  self.player_stats_dict[player_id]['EVA'])
        elif technique_id == 'cottonhand':
            self.player_stats_dict[player_id]['pATK'] = math.ceil(1.15 * self.player_stats_dict[player_id]['pATK'])
            self.player_stats_dict[player_id]['mATK'] = math.ceil(1.15 * self.player_stats_dict[player_id]['mATK'])
            self.player_stats_dict[player_id]['pDEF'] = math.ceil(1.15 * self.player_stats_dict[player_id]['pDEF'])
            self.player_stats_dict[player_id]['mDEF'] = math.ceil(1.15 * self.player_stats_dict[player_id]['mDEF'])
        elif technique_id == 'ninewindsteps':
            self.player_stats_dict[player_id]['EVA'] = math.ceil(1.20 * self.player_stats_dict[player_id]['EVA'])
            self.player_status_dict[player_id]['status']['Nine Turning Wind'] = {
                'source': player_id,
                'duration': 99,
                'potency': 1,
                'dodge_bonus': False,
            }
        elif technique_id == 'incinflame':
            self.player_status_dict[player_id]['status']['Freeze Immunity'] = {
                'source': player_id,
                'duration': 99,
                'potency': 1,
            }

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
    
    # Store one player's summon's action
    def store_summon_action(self, player_id: int, summon_id: int, battle_action):
        self.player_summon_action_dict[player_id][summon_id] = battle_action

    # Clear player (and summon) actions
    def clear_player_actions(self):
        for player_id in self.player_action_dict:
            self.player_action_dict[player_id] = None
        for player_id in self.player_summon_action_dict:
            for summon_id in self.player_summon_action_dict[player_id]:
                self.player_summon_action_dict[player_id][summon_id] = None

    # Get player in list with highest current SPD
    def get_next_player_or_summon(self, player_or_summon_list: list):
        
        player_summon_SPD_dict = {}
        for player_id in self.player_stats_dict:
            for summon in self.player_status_dict[player_id]['summons']:
                if summon['active']:
                    player_summon_SPD_dict[(player_id, summon['name'])] = summon['SPD']
        # print(player_summon_SPD_dict, "player_or_summon_list", player_or_summon_list)
        player_or_summon_SPD_dict = {}
        for player_or_summon in player_or_summon_list:
            if isinstance(player_or_summon, int):
                player_id = player_or_summon
                player_or_summon_SPD_dict[player_or_summon] = self.player_stats_dict[player_id]['SPD']
            else:
                player_or_summon_SPD_dict[player_or_summon] = player_summon_SPD_dict[player_or_summon]
        
        ordered_player_SPD_tups = sorted(player_or_summon_SPD_dict.items(), key=lambda x: x[1], reverse=True)
        return ordered_player_SPD_tups[0][0]

    # Get all players and active summons
    def get_all_players_and_summons(self):
        all_players_and_summons = []
        for player_id in self.player_action_dict:
            all_players_and_summons.append(player_id)
            for summon in self.player_status_dict[player_id]['summons']:
                if summon['active']:
                    all_players_and_summons.append((player_id, summon['name']))
        return all_players_and_summons

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

    # Get list of dead summons
    def get_dead_summons(self):
        dead_player_summon_tups = []
        for player_id in self.player_status_dict:
            for summon in self.player_status_dict[player_id]['summons']:
                if summon['HP'] <= 0:
                    dead_player_summon_tups.append((player_id, summon['name']))
        return dead_player_summon_tups
    
    # Update cooldowns for a specific player
    def update_cooldowns(self, player_id: int):
        status_dict = self.player_status_dict[player_id]
        
        for technique in status_dict['cooldowns']: # Technique usage cooldowns
            status_dict['cooldowns'][technique] = max(0, status_dict['cooldowns'][technique] - 1)
        
        for status_effect in status_dict['status']: # Status effect durations
            duration = status_dict['status'][status_effect]['duration']
            if status_effect == 'Chill' and duration == 1: # Special case
                SPD_reduction = status_dict['status'][status_effect]['potency'] * 0.1
                self.player_stats_dict[player_id]['SPD'] *= (1/(1 - SPD_reduction)) # Revert
            status_dict['status'][status_effect]['duration'] = max(0, (duration if duration == 99 else (duration - 1)))
        
        updated_buffs = []
        for buff_stat, buff_value, cooldown, buff_type in status_dict['buffs']: # Buff durations
            if cooldown == 1: # Buff will expire
                if buff_type == 'prop':
                    self.player_stats_dict[player_id][buff_stat] *= (1/(1 + buff_value)) # Revert
                    self.player_stats_dict[player_id][buff_stat] = math.ceil(self.player_stats_dict[player_id][buff_stat])
                elif buff_type == 'flat':
                    self.player_stats_dict[player_id][buff_stat] -= buff_value # Refert
            else:
                updated_buffs.append((buff_stat, buff_value, (cooldown if cooldown == 99 else (cooldown - 1)), buff_type))
        status_dict['buffs'] = updated_buffs

        updated_debuffs = []
        for debuff_stat, debuff_value, cooldown, debuff_type in status_dict['debuffs']: # Debuff durations
            if cooldown == 1: # Debuff will expire
                if debuff_type == 'prop':
                    self.player_stats_dict[player_id][debuff_stat] *= (1/(1 - debuff_value)) # Revert
                    self.player_stats_dict[player_id][debuff_stat] = math.ceil(self.player_stats_dict[player_id][debuff_stat])
                elif debuff_type == 'flat':
                    self.player_stats_dict[player_id][debuff_stat] += debuff_value # Revert
            else:
                updated_debuffs.append((debuff_stat, debuff_value, (cooldown if cooldown == 99 else (cooldown - 1)), debuff_type))
        status_dict['debuffs'] = updated_debuffs

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
                        'duration': 1+1,
                        'potency': 3,
                    }
                    action.description.append(f'\n<@{responder_id}> **confused** <@{action.player}> for one turn!')
        if 'skysteps' in self.player_techniques_dict[responder_id]:
            if action.dodged: # Target dodged this attack
                # Target counter-attacks the attacker with basic attack
                print('pATK', self.player_stats_dict[responder_id]['pATK'])
                attack_components = [AttackComponent(player_stats=self.player_stats_dict[responder_id], target_stats=self.player_stats_dict[action.player], scaling_stat='pATK', scaling_stat_source='player', damage_type='physical', multiplier=1, true_damage=False)]
                counter_action = BattleAction(name='basic_attack', player=responder_id, target=action.player, match=self, attack_components=attack_components, base_accuracy = 0.9, player_buffs = {}, target_debuffs = {}, qi_cost = 0, action_type='basic attack')
                
                await counter_action.execute()

                # Update the action description for the attacker
                action.description.append(f'<@{responder_id}> counter-attacked <@{action.player}>, dealing {format_num_abbr1(counter_action.damage)} damage!')
        if 'ninewindsteps' in self.player_techniques_dict[responder_id]:
            if action.dodged: # Target dodged this attack
                # Store this information for processing of speed buff status effect
                self.player_status_dict[responder_id]['status']['Nine Turning Wind']['dodge_bonus'] = True

    # Execute current turn actions for all players
    async def execute_turn(self):
        # Firstly store actions for alive summons
        for player_id in self.player_status_dict:
            for summon in self.player_status_dict[player_id]['summons']:
                if summon['active']:
                    # TODO: determine summon targeting
                    target = self.defender_id if player_id == self.challenger_id else self.challenger_id
                    summon_action = get_summon_action(player_id, target, self, summon['name'])
                    self.store_summon_action(player_id, summon['name'], summon_action)

        # Determine all players and player summons that get to move this turn
        all_players_and_summons = set(self.get_all_players_and_summons()) # Lock in at start of turn
        finished_players = set() # List of players whose actions have already been taken

        while finished_players != all_players_and_summons:
            
            pending_players = all_players_and_summons - finished_players # Get list of players who have not yet acted
            current_player = self.get_next_player_or_summon(pending_players) # Get next player (or summon)
            
            # Check if player cannot take action due to status effect
            skip_action = False
            if current_player in self.player_status_dict:
                action = self.player_action_dict[current_player]
                active_effects = self.get_player_status_effects(current_player)
                if 'Freeze' in active_effects:
                    if 'Freeze Immunity' in active_effects: # Check for immunity
                        self.action_descriptions += [f'<@{current_player}> is immune to **Freeze** and can still move.']
                    else:
                        skip_action = True; self.action_descriptions += [f'<@{current_player}> was frozen and is unable to move.']
                elif 'Stun' in active_effects:
                    skip_action = True; self.action_descriptions += [f'<@{current_player}> was stunned and is unable to move.']
                elif 'Silence' in active_effects and action.action_type == 'technique':
                    skip_action = True; self.action_descriptions += [f'<@{current_player}> was silenced and is unable to use abilities.']
            
            if not skip_action:
                action = await self.execute_action(current_player) # Execute this player (or summon)'s action

                winner = self.check_winner() # Check for terminating condition
                if winner: # If there is a winner, do not execute remaining player actions
                    self.action_descriptions += action.description # Add action descriptions to turn summary
                    self.status = "completed"
                    break
                else:
                    await self.execute_target_response(action) # Execute target response
                    self.action_descriptions += action.description # Add action descriptions to turn summary
                    winner = self.check_winner() # Check for terminating condition
                    if winner: # If there is a winner, do not execute remaining player actions
                        self.status = "completed"
                        break
            print(current_player, self.player_status_dict)
            if current_player in self.player_status_dict:
                self.update_cooldowns(current_player) # Update cooldowns for this player
            print(current_player, self.player_status_dict)
            finished_players.add(current_player) # Add player to finished list

            for player_summon_tup in self.get_dead_summons():
                pending_players.discard(player_summon_tup) # Remove dead summons from pending players
        
        if self.status != "completed":
            # Finally, apply per-turn status effects that do not affect actions during the turn
            for player_id in self.player_status_dict:
                for status_effect in self.get_player_status_effects(player_id):

                    if status_effect == 'Wither':
                        # Deals 5% max health true damage per turn to user
                        true_damage_taken = math.ceil(self.player_stats_dict[player_id]['Max HP'] * 0.05)
                        self.player_stats_dict[player_id]['HP'] -= true_damage_taken
                        self.action_descriptions.append(f'<@{player_id}> took {true_damage_taken} true damage from **Wither**.')
                    
                    elif status_effect in ['Burn', 'Shock', 'Bleed', 'Poison', 'Frostbite']:

                        source = self.player_status_dict[player_id]['status'][status_effect]['source']
                        ps = self.player_stats_dict[source]; ts = self.player_stats_dict[player_id] # Abbreviations
                        potency = self.player_status_dict[player_id]['status'][status_effect]['potency']
                        
                        effect_attack_parameters_dict = {
                            "Burn": (ps, ts, 'pATK', 'player', 'physical', "Fire", (0.05 * potency)),
                            "Shock": (ps, ts, 'mATK', 'player', 'magical', "Lightning", (0.05 * potency)),
                            "Bleed": (ps, ts, ('pATK' if ps['pATK'] > ps['mATK'] else 'mATK'), 'player', 'true', "none", (0.05 * potency)),
                            "Poison": (ps, ts, 'mATK', 'player', 'magical', "Poison", (0.05 * potency)),
                            "Frostbite": (ps, ts, 'pATK', 'player', 'physical', "Ice", (0.05 * potency)),
                        }

                        attack_parameters = effect_attack_parameters_dict[status_effect]
                        _, _, scaling_stat, _, damage_type, element, multiplier = attack_parameters
                        if element == "none":
                            damage_descriptor = f"{damage_type}"
                        else:
                            damage_descriptor = f"{element} {damage_type}"
                        damage_taken = AttackComponent(*attack_parameters).damage_dealt()
                        self.player_stats_dict[player_id]['HP'] -= damage_taken
                        self.action_descriptions.append(f'<@{player_id}> took {damage_taken} {damage_descriptor} damage from **{status_effect} {roman(potency)}**.')

                    elif status_effect == 'Nine Turning Wind':
                        # Ramping speed buff status effect associated with ninewindsteps
                        dodge_bonus = self.player_status_dict[player_id]['status']['Nine Turning Wind']['dodge_bonus']
                        SPD_increase = 20 if dodge_bonus else 10
                        self.player_stats_dict[player_id]['SPD'] += SPD_increase
                        self.action_descriptions.append(f'<@{player_id}> gained {SPD_increase} SPD from **{status_effect}**!')
                        # Reset dodge bonus
                        self.player_status_dict[player_id]['status']['Nine Turning Wind']['dodge_bonus'] = False


            winner = self.check_winner() # Check for terminating condition again
            if winner:
                self.status = "completed"
        
        # Update database
        await self.update_database_record()

    # Increment turn (call this BEFORE displaying battle embed)
    def next_turn(self):
        self.turn += 1
    
    # Clear player actions (run after displaying turn)
    def clear_actions(self):
        self.clear_player_actions()
        self.action_descriptions = []

    # Execute one player's action
    async def execute_action(self, player_or_summon):
        if isinstance(player_or_summon, int):
            action = self.player_action_dict[player_or_summon]
        else:  # (player_id, summon_name):
            action = self.player_summon_action_dict[player_or_summon[0]][player_or_summon[1]]
        await action.execute()
        return action

def construct_player_info(match: PvPMatch, guild, user_id):
    player_info = {
        'id': user_id,
        'Member': guild.get_member(user_id),
        'Player': PlayerRoster().get(user_id),
        'action': match.player_action_dict[user_id],
        'summon_action': match.player_summon_action_dict[user_id],
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
        element: str = 'none',
        multiplier: float = 1,
        true_damage: bool = False
    ):
        self.player_stats = player_stats
        self.target_stats = target_stats
        self.scaling_stat = scaling_stat # Stat to scale off of (pATK, mATK, HP, ...)
        self.scaling_stat_source = scaling_stat_source # Whose stat to use (player or target)
        self.damage_type = damage_type # Damage type (physical, magical, or true)
        self.element = element
        self.multiplier = multiplier # Multiplier for the scaling value
        self.true_damage = true_damage # True / False
    
    def randomize_damage(self, damage: int): # Introduces random variability
        return math.ceil(damage*(random.randint(80,100)/100.0))
    
    def get_elemental_multiplier(self):
        if self.element == 'none':
            return 1
        else:
            multiplier = 1
            for defender_element in self.target_stats['Elemental Affinities']:
                multiplier *= ELEMENT_EFFICACY_DICT[self.element][defender_element]
            return multiplier
    
    def damage_dealt(self):
        # Damage = multiplier * scaling stat
        # Defense-adjusted damage = DMG * (DMG / (DMG + (DEF * (1-PEN))))
        # Final damage (not account for crit) = randomization of defense-adjusted damage

        source_stats = self.player_stats if self.scaling_stat_source == 'player' else self.target_stats
        element_multiplier = self.get_elemental_multiplier()
        original_DMG = source_stats[self.scaling_stat] * self.multiplier
        
        DMG = 1
        if self.damage_type == "physical":
            defense_adjusted_DMG = original_DMG * (original_DMG / (original_DMG + (self.target_stats['pDEF'] * (1 - self.player_stats['pPEN']))))
            element_adjusted_DMG = defense_adjusted_DMG * element_multiplier
            DMG = max(0, self.randomize_damage(element_adjusted_DMG))
            # print("Opponent pDEF", self.target_stats['pDEF'], "player pPEN", self.player_stats['pPEN'], 'defense adjusted DMG', defense_adjusted_DMG, 'randomized DMG', DMG)
        elif self.damage_type == "magical":
            defense_adjusted_DMG = original_DMG * (original_DMG / (original_DMG + (self.target_stats['mDEF'] * (1 - self.player_stats['mPEN']))))
            element_adjusted_DMG = defense_adjusted_DMG * element_multiplier
            DMG = max(0, self.randomize_damage(element_adjusted_DMG))
        elif self.damage_type == "true":
            DMG = math.ceil(original_DMG)
        print(original_DMG, f"{self.target_stats['pDEF'] * (1 - self.player_stats['pPEN'])} = {self.target_stats['pDEF']} * (1 - {self.player_stats['pPEN']})")
        try:
            print("elemental multiplier", element_multiplier, "original DMG", original_DMG, "defense adjusted DMG", defense_adjusted_DMG, "element adjusted DMG", element_adjusted_DMG, "randomized DMG", DMG)
        except:
            print("elemental multiplier", element_multiplier, "original and final DMG", original_DMG)
        return DMG


class BattleAction(): # Representation of a player's action at a turn in battle
    def __init__(self, name: str, player: int, target: int, match: PvPMatch,
        action_type: str, # 'basic attack', 'technique', 'do_nothing', 'aftershock', or 'summon'
        attack_components: list[AttackComponent] = [],
        base_accuracy: float = 0,
        player_buffs: dict = {}, # { stat: (buff_value, duration, 'prop' or 'flat') }
        target_debuffs: dict = {}, # { stat: (debuff_value, duration, 'prop' or 'flat') }
        no_crit: bool = False,
        qi_cost: int = 0,
        cooldown: int = 0,
        aoe: bool = False, # Affects all enemies (ignores taunts) -- for now, affects summons
    ):
        self.name = name; self.player = player; self.target = target; self.match = match
        if action_type == 'technique':
            self.prettyname = match.player_techniques_dict[player][name]['name']
        elif action_type == 'basic attack':
            self.prettyname = 'basic attack'
        else:
            self.prettyname = name
        self.action_type = action_type
        self.attack_components = attack_components
        self.base_accuracy = base_accuracy
        self.player_buffs = player_buffs
        self.target_debuffs = target_debuffs
        self.no_crit = no_crit
        self.qi_cost = qi_cost
        self.description = []
        self.cooldown = cooldown
        self.aoe = aoe
        
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
        
        if self.action_type == 'do_nothing':
            self.description.append(f'<@{self.player}> could not act this turn due to **{self.name}**.')
            return self

        player_stats, target_stats, player_status, target_status = self.get_player_target_info()

        # Set player buffs introduced by this action
        buff_debuff_descriptions = [] # Append buff/debuff descriptions to description list, show after attack description
        for player_stat in self.player_buffs:
            buff_value, buff_cooldown, buff_type = self.player_buffs[player_stat]
            if buff_type == 'prop':
                buff_str = f'{int(buff_value * 100)}%'
                self.match.player_stats_dict[self.player][player_stat] = math.ceil((1 + buff_value) * self.match.player_stats_dict[self.player][player_stat])
            elif buff_type == 'flat':
                buff_str = f'{buff_value}'
                self.match.player_stats_dict[self.player][player_stat] += buff_value
            player_status['buffs'].append((player_stat, buff_value, buff_cooldown + 1, buff_type))
            
            if buff_cooldown == 1: # Do not announce
                pass
            else:
                if player_stat in ['Qi', 'HP']:
                    buff_cooldown_str = ''
                elif buff_cooldown == 99:
                    buff_cooldown_str = ' for the rest of the battle'
                else:
                    buff_cooldown_str = f' for {buff_cooldown} turns'
                buff_debuff_descriptions.append(f'<@{self.player}> increased their {player_stat} by {buff_str}{buff_cooldown_str}!')
        
        # Now determine whether opponent dodged
        opponent_dodged = self.determine_dodge()

        # Only set debuffs if opponent did not dodge
        if not opponent_dodged:
            for player_stat in self.target_debuffs:
                debuff_value, debuff_cooldown, debuff_type = self.target_debuffs[player_stat]
                if debuff_type == 'prop':
                    debuff_str = f'{int(debuff_value * 100)}%'
                    self.match.player_stats_dict[self.target][player_stat] = math.ceil((1 - debuff_value) * self.match.player_stats_dict[self.target][player_stat])
                elif debuff_type == 'flat':
                    debuff_str = f'{debuff_value}'
                    self.match.player_stats_dict[self.target][player_stat] -= debuff_value
                if debuff_cooldown > 1:
                    target_status['debuffs'].append((player_stat, debuff_value, debuff_cooldown + 1, debuff_type))
                
                if debuff_cooldown == 1: # Do not announce
                    pass
                else:
                    if player_stat in ['Qi', 'HP']:
                        debuff_cooldown_str = ''
                    elif debuff_cooldown == 99:
                        debuff_cooldown_str = ' for the rest of the battle'
                    else:
                        debuff_cooldown_str = f' for {debuff_cooldown} turns'
                    buff_debuff_descriptions.append(f'<@{self.target}> has their {player_stat} lowered by {debuff_str}{debuff_cooldown_str}!')

        # Now determine damage
        action_damage = self.compute_damage()
        
        # Check for and apply player status effects that affect turn AFTER action is submitted
        if self.action_type != 'summon': # Summons do not have status effects
            for status_effect in self.match.get_player_status_effects(self.player):
                potency = self.match.player_status_dict[self.player]['status'][status_effect]['potency']

                if status_effect == 'Confusion':
                    # (10 * potency) % chance of retargeting attack to user or an ally for 50% damage
                    if random_success(0.1 * potency):
                        opponent_dodged = False
                        action_damage = math.ceil(action_damage * 0.5)
                        self.description.append(f'<@{self.player}> tried to attack <@{self.target}>, but was **confused** and attacked themselves instead!')
                        self.target = self.player; target_stats = player_stats; target_status = player_status
                elif status_effect == 'Fear':
                    # (10 * potency) % chance of skipping turn
                    if random_success(0.1 * potency):
                        action_damage = 0
                        self.description.append(f'<@{self.player}> could not attack due to **Fear**!')
                        return self # Return information for opponent response
                elif status_effect == 'Nine Turning Wind':
                    pass
                # True damage attacks or abilities deal 20% more damage
                    # TODO
        
        # Check for target taunts
        # ================================================================================
        # HARDCODED TECHNIQUE EFFECTS PORTION
        # ================================================================================
        summon_taunt = False
        for summon in target_status['summons']:
            if summon['name'] == 'Skeleton King' and summon['active']:
                summon_taunt = summon

        # ================================================================================
        # HARDCODED TECHNIQUE EFFECTS PORTION
        # ================================================================================
        has_attack = True
        custom_description = False
        attacker_str = f'<@{self.player}>'
        defender_str = f'<@{self.target}>'
        attack_str = f'used **{self.prettyname}**'

        if self.name == 'skelking':
            has_attack = False

            # Compute summon stats and add summon to player's status
            skeleton_HP = math.ceil(0.8 * player_stats['Max HP']) # 80% of user max HP
            skeleton_ATK = math.ceil(0.35 * player_stats['mATK'])
            if 'Dark' in player_stats['Elemental Affinities']:
                skeleton_ATK *= 2 # Double damage if user is Dark type
            summon_name = 'Skeleton King'

            player_status['summons'].append({
                'name': summon_name,
                'active': True,
                'Elemental Affinities': ['Dark'], # Dark type
                'Elemental Immunities': ['Fire', 'Water'], # Immune to Fire and Water
                'pATK': skeleton_ATK,
                'pDEF': 0, 'mDEF': 0, 'pPEN': 0, 'mPEN': 0, # No DEF/PEN
                'SPD': math.ceil(player_stats['SPD'] * 0.2), # 20% of user SPD
                'ACC': 100, 'EVA': 0, # Cannot dodge
                'CRIT': 0, 'CRIT DMG': 1, # No crit
                'HP': skeleton_HP,
                'Max HP': skeleton_HP,
            })

            # Store summon's attack
            summon_action = get_summon_action(self.player, self.target, self.match, 'Skeleton King')
            self.match.store_summon_action(self.player, summon_name, summon_action)

             # Update action description
            self.description.append(f"<@{self.player}> used **{self.prettyname}**, summoning a Skeleton King with {format_num_abbr1(skeleton_HP)} HP!")
            self.description += summon_action.description
        
        elif self.name == 'phoenixbell': # TODO
            # Compute summon stats and add summon to player's status
            bell_HP = math.ceil(0.5 * player_stats['Max HP'])
            summon_name = "Demon Phoenix Bell"
            player_status['summons'].append({
                'name': summon_name,
                'active': True,
                'Elemental Affinities': [],
                'Elemental Immunities': [],
                'pATK': math.ceil(0.5 * player_stats['pATK']),
                'mATK': math.ceil(0.5 * player_stats['mATK']),
                'pDEF': 0, 'mDEF': 0, 'pPEN': 0, 'mPEN': 0, # No DEF/PEN
                'SPD': player_stats['SPD'],
                'ACC': 100, 'EVA': 0, # Cannot dodge
                'CRIT': 0, 'CRIT DMG': 1, # No crit
                'HP': bell_HP,
                'Max HP': bell_HP,
            })

        elif self.action_type == 'summon': # Summon attacked
            attacker_str = f"<@{self.player}>'s {self.name}"
            attack_str = "attacked"
        
        elif self.name == 'bloodagglom':
            opponent_dodged = False
            prop_increase = 0.6 if 'Blood' in player_stats['Elemental Affinities'] else 0.3
            # Do not treat as normal buff to avoid excessive action logs (TODO: group as 'all' if this will be reused)
            for combat_stat in ['pATK','mATK','pDEF','mDEF','pPEN','mPEN','SPD','ACC','EVA','CRIT','CRIT DMG']:
                player_stats[combat_stat] += math.ceil(player_stats[combat_stat] * prop_increase)
            self.description.append(f'{attacker_str} {attack_str} took {format_num_abbr1(action_damage)}{true_dmg_str} damage and amplified all stats by {int(100*prop_increase)}%!')
            custom_description = True
            # Add to status effect to keep track that this was already used
            player_status['status']['Blood Agglomeration'] = { 'source': self.player, 'duration': 99, 'potency': 1 }
        
        elif self.name == 'flamecreation':
            opponent_dodged = False
            prop_increase = 0.2
            # Do not treat as normal buff to avoid excessive action logs (TODO: group as 'all' if this will be reused)
            for combat_stat in ['pATK','mATK','pDEF','mDEF','pPEN','mPEN','SPD','ACC','EVA','CRIT','CRIT DMG']:
                player_stats[combat_stat] += math.ceil(player_stats[combat_stat] * prop_increase)
            self.description.append(f'{attacker_str} {attack_str} took {format_num_abbr1(action_damage)}{true_dmg_str} damage and amplified all stats by {int(100*prop_increase)}%!')
            custom_description = True
            # Add to status effect to keep track that this was already used
            player_status['status']['Flame Creation'] = { 'source': self.player, 'duration': 99, 'potency': 1 }

        if has_attack:
            
            if summon_taunt and (not self.aoe): # Player (or summon) attacked summon instead of target

                # Recompute damage based on target summon's stats
                for attack_component in self.attack_components:
                    attack_component.target_stats = summon_taunt
                action_damage = self.compute_damage()

                summon_taunt['HP'] = to_nonneg(summon_taunt['HP'] - action_damage)
                self.description.append(f"{attacker_str} {attack_str}, dealing {format_num_abbr1(action_damage)} damage to <@{self.target}>'s {summon_taunt['name']}")

                # If summon is dead, set it to inactive
                if summon_taunt['HP'] <= 0:
                    summon_taunt['active'] = False
                    self.description.append(f"\n<@{self.target}>'s {summon_taunt} has been defeated!")
                else:
                    # ================================================================================
                    # HARDCODED TECHNIQUE EFFECTS PORTION
                    # ================================================================================
                    if summon_taunt['name'] == 'Skeleton King' and self.action_type != 'summon':
                        # If player attacked target's Skeleton King, **Wither** the player for 2 turns (unless player is itself a summon)
                        player_status['status']['Wither'] = { 'source': self.target, 'duration': 2, 'potency': 1 }
                        self.description.append(f"<@{self.target}>'s {summon_taunt['name']} **withered** <@{self.player}> for 2 turns!")
            
            else: # Player attacked target (as normal)
                if opponent_dodged:
                    self.description.append(f'{attacker_str} {attack_str}, but {defender_str} dodged!')
                else:
                    target_stats['HP'] = to_nonneg(target_stats['HP'] - action_damage)
                    true_dmg_str = ' true' if self.attack_components[0].damage_type == 'true' else ''
                    if not custom_description:
                        self.description.append(f'{attacker_str} {attack_str}, dealing {format_num_abbr1(action_damage)}{true_dmg_str} damage to {defender_str}')
                
                if self.aoe: # AOE affects target's summons as well
                    for summon in target_status['summons']:
                        
                        # Recompute damage based on target summon's stats
                        for attack_component in self.attack_components:
                            attack_component.target_stats = summon
                        action_damage = self.compute_damage()

                        summon['HP'] = to_nonneg(summon['HP'] - action_damage)
                        self.description.append(f"The AOE attack also dealt {format_num_abbr1(action_damage)} damage to <@{self.target}>'s {summon['name']}")

                        # If summon is dead, set it to inactive
                        if summon['HP'] <= 0:
                            summon['active'] = False
                            self.description.append(f"\n<@{self.target}>'s {summon} has been defeated!")

                            # Trigger upon-defeat effects
                            if self.name == 'lightningcalamity':
                                self.match.store_action(self.player, BattleAction(
                                    name = "lightningcalamity_aftershock", player = self.player, target = self.target, match = self.match,
                                    action_type = "aftershock",
                                    attack_components = [
                                        AttackComponent(player_stats=player_stats, target_stats=target_stats, scaling_stat='mATK', scaling_stat_source='player', damage_type='magical', element='Lightning', multiplier=2.0, true_damage=False)
                                    ],
                                    base_accuracy = 0.8,
                                    player_buffs = {},
                                    target_debuffs = {},
                                    qi_cost = 0,
                                    cooldown = 0,
                                    aoe = True # Affects all enemies (ignores taunts)
                                ))
                        else:
                            if summon['name'] == 'Skeleton King' and self.action_type != 'summon':
                                # If player attacked target's Skeleton King, **Wither** the player for 2 turns (unless player is itself a summon)
                                player_status['status']['Wither'] = { 'source': self.target, 'duration': 2, 'potency': 1 }
                                self.description.append(f"<@{self.target}>'s {summon['name']} **withered** <@{self.player}> for 2 turns!")
        
        self.description += buff_debuff_descriptions
        
        # Apply effects that occur after attack
        # ================================================================================
        # HARDCODED TECHNIQUE EFFECTS PORTION
        # ================================================================================
        if self.name == 'wlclaw':
            # 40% chance of stunning enemy for one turn
            if random_success(0.4):
                self.match.player_status_dict[self.target]['status']['Stun'] = {
                    'source': self.player,
                    'duration': 1,
                    'potency': 1,
                }
                self.description.append(f"\n<@{self.player}>'s `{self.prettyname}` **stunned** <@{self.target}> for one turn!")

        # Update player Qi based on Qi cost
        player_stats['Qi'] = to_nonneg(player_stats['Qi'] - self.qi_cost)

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
        selected_technique_info_dict = self.battle_view.match.player_techniques_dict[self.battle_view.user_id][selected_technique]

        # Identify if the user is the challenger or defender
        challenger_info, defender_info, turn, am_challenger = self.battle_view.get_match_data()
        player_info, target_info = (challenger_info, defender_info) if am_challenger else (defender_info, challenger_info)
        player_stats, target_stats = player_info['stats'], target_info['stats']
        
        # ================================================================================
        # HARDCODED TECHNIQUE EFFECTS PORTION
        # ================================================================================
        # Check if technique is on cooldown
        if selected_technique in player_info['status']['cooldowns'] and player_info['status']['cooldowns'][selected_technique] > 0: # At least 1 turn cooldown left
            await inter.followup.send(f"This technique is still on cooldown.", ephemeral=True)
        
        # Check if player has enough Qi to use technique
        elif selected_technique_info_dict['Qi Cost'] > player_stats['Qi']:
            await inter.followup.send(f"You don't have enough Qi to use this technique.", ephemeral=True)
        
        # Check if Skeleton King has been previously summoned
        elif selected_technique == 'skelking' and any([summon['name'] == 'Skeleton King' for summon in player_info['status']['summons']]):
            await inter.followup.send(f"You can only summon the Skeleton King once per match.", ephemeral=True)
        
        # Check if one-time use techniques were already used
        elif 'Blood Agglomeration' in player_info['status']:
            await inter.followup.send(f"You can only use Great Blood Agglomeration Skill once per match.", ephemeral=True)
        
        elif 'Flame Creation' in player_info['status']:
            await inter.followup.send(f"You can only use True Flame Creation Skill once per match.", ephemeral=True)
        
        else:
            self.battle_view.countdown_task.cancel() # Stop the countdown
            self.battle_view.toggle_buttons(enabled=False) # Disable the buttons
            self.battle_view.clear_items()  # Remove dropdown
            await self.battle_view.message.edit(view=self.battle_view)
            
            # TODO: should technique effects be stored in the database or hardcoded?
            tech_name, tech_properties = await AllItems.get_or_none(id=selected_technique).values_list("name", "properties")
            
            action = get_technique_action(player_info['id'], target_info['id'], self.battle_view.match, selected_technique)

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
            description='\n'.join(self.match.action_descriptions),
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
        print("Challenger's action")
        print(challenger_info['action'].__dict__)
        print("-------------------\nDefender info:")
        print(defender_info)
        print("Defender's action")
        print(defender_info['action'].__dict__)
        
        # Generate updated embeds
        battle_embed = generate_battle_embed(challenger_info, defender_info, turn)
        
        action_embed = disnake.Embed(
            description='\n'.join(self.match.action_descriptions),
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

        # Check for disabling effect
        disabling_effect = False
        for status_effect in challenger_info['active_effects']:
            if status_effect == 'Freeze' and 'Freeze Immunity' not in challenger_info['active_effects']:
                disabling_effect = status_effect
            elif status_effect == 'Stun':
                disabling_effect = status_effect
            if status_effect == 'Silence' and not disabling_effect: # Lower priority than freeze/stun
                disabling_effect = status_effect
        
        if disabling_effect in ['Freeze', 'Stun']:
            challengerBattleView.countdown_task.cancel() # Stop the countdown
            challengerBattleView.toggle_buttons(enabled=False) # Disable the buttons
            await challenger_message.edit(embeds=[*challenger_message.embeds[:-1], simple_embed('', f"You are affected by **{disabling_effect}** and cannot act this turn.")], view=challengerBattleView)
            self.match.store_action(challenger_info['id'], BattleAction(disabling_effect, challenger_info['id'], defender_info['id'], self.match, 'do_nothing'))
        elif disabling_effect == 'Silence':
            challengerBattleView.toggle_buttons(enabled=False, disable_technique_only=True)
        
        disabling_effect = False
        for status_effect in defender_info['active_effects']:
            if status_effect in ['Freeze', 'Stun']:
                disabling_effect = status_effect
            if status_effect == 'Silence' and not disabling_effect: # Lower priority than freeze/stun
                disabling_effect = status_effect
        
        if disabling_effect in ['Freeze', 'Stun']:
            defenderBattleView.countdown_task.cancel() # Stop the countdown
            defenderBattleView.toggle_buttons(enabled=False) # Disable the buttons
            await defender_message.edit(embeds=[*defender_message.embeds[:-1], simple_embed('', f"You are affected by **{disabling_effect}** and cannot act this turn.")], view=defenderBattleView)
            self.match.store_action(defender_info['id'], BattleAction(disabling_effect, defender_info['id'], defender_info['id'], self.match, 'do_nothing'))
        elif disabling_effect == 'Silence':
            defenderBattleView.toggle_buttons(enabled=False, disable_technique_only=True)
    
    # Handle timeout (when the user doesn't click a button in time)
    async def on_timeout(self):
        timeout_embed = disnake.Embed(description="⏰ Time's up! You didn't respond in time.")
        self.toggle_buttons(enabled=False) # Disable the buttons
        await self.message.edit(embeds=[*self.message.embeds[:-1], timeout_embed], view=self)

        # For now, do basic attack and move on to next turn
        challenger_info, defender_info, turn, am_challenger = self.get_match_data()
        player_info, target_info = (challenger_info, defender_info) if am_challenger else (defender_info, challenger_info)
            
        # Basic attack
        action = BattleAction( name='basic_attack', player=player_info['id'], target=target_info['id'], match=self.match, attack_components=[ AttackComponent(player_info['stats'], target_info['stats'], scaling_stat='pATK', scaling_stat_source='player', damage_type='physical', multiplier=1, true_damage=False)], base_accuracy = 0.9, player_buffs = {}, target_debuffs = {}, qi_cost = 0,action_type='basic attack')

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
            player_buffs = {}, 
            target_debuffs = {}, 
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
        passive_only_techniques = ['skysteps', 'windimages', 'ninewindsteps', 'incinflame']
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

    challenger_elements_str = '*None*' if len(challenger_stats['Elemental Affinities']) == 0 else (' '.join([f'`{element}`' for element in challenger_stats['Elemental Affinities']]))
    defender_elements_str = '*None*' if len(defender_stats['Elemental Affinities']) == 0 else (' '.join([f'`{element}`' for element in defender_stats['Elemental Affinities']]))

    challenger_summons_str = ''
    challenger_active_summons = [ summon for summon in challenger_info['status']['summons'] if summon['active'] ]
    if len(challenger_active_summons) > 0:
        challenger_summons_str += 'Summons:\n'
        for summon in challenger_active_summons:
            challenger_summons_str += f"**{summon['name']}**: `{summon['HP']}`/`{summon['Max HP']}` HP\n"

    challenger_effect_str = '*None*' if len(challenger_info['active_effects']) == 0 else (' '.join([f'`{effect}`' for effect in challenger_info['active_effects']]))
    defender_effect_str = '*None*' if len(defender_info['active_effects']) == 0 else (' '.join([f'`{effect}`' for effect in defender_info['active_effects']]))
    defender_summons_str = ''
    defender_active_summons = [ summon for summon in defender_info['status']['summons'] if summon['active'] ]
    if len(defender_active_summons) > 0:
        defender_summons_str += 'Summons:\n'
        for summon in defender_active_summons:
            defender_summons_str += f"**{summon['name']}**: `{summon['HP']}`/`{summon['Max HP']}` HP\n"
    
    embed = disnake.Embed(
        title=f"⚔️ PvP Battle: Turn {turn}",
        color=disnake.Color.blue()
    )
    embed.add_field(
        name=f"{challenger_info['Member'].display_name}",
        value=f"""HP: `{challenger_stats['HP']}`/`{challenger_stats['Max HP']}`
        Qi: `{challenger_stats['Qi']}`/`{challenger_stats['Max Qi']}`
        Elements: {challenger_elements_str}
        Status Effects: {challenger_effect_str}
        {challenger_summons_str}""",
        inline=True
    )
    embed.add_field(
        name=f"{defender_info['Member'].display_name}",
        value=f"""HP: `{defender_stats['HP']}`/`{defender_stats['Max HP']}`
        Qi: `{defender_stats['Qi']}`/`{defender_stats['Max Qi']}`
        Elements: {defender_elements_str}
        Status Effects: {defender_effect_str}
        {defender_summons_str}""",
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

    def toggle_buttons(self, enabled: bool, disable_technique_only: bool = False):
        # Enable or disable all buttons dynamically, or just the technique button
        for child in self.children:
            if isinstance(child, disnake.ui.Button):
                if disable_technique_only and child.custom_id == "use_technique":
                    child.disabled = True
                else:
                    child.disabled = (not enabled)

    @disnake.ui.button(label="Accept", style=disnake.ButtonStyle.success, custom_id="accept_challenge")
    async def accept_challenge(self, button: disnake.ui.Button, inter: disnake.MessageInteraction):
        
        await inter.response.defer()
        self.toggle_buttons(enabled=False) # Disable the buttons
        await inter.message.edit(view=self)
        
        try:
            player_stats = {
                self.challengerPlayer.id: self.challengerPlayer.get_stats_dict(),
                self.defenderPlayer.id: self.defenderPlayer.get_stats_dict()
            }

            player_action = {
                self.challengerPlayer.id: None,
                self.defenderPlayer.id: None
            }

            player_status = {
                self.challengerPlayer.id: {
                    'cooldowns': {}, # technique ID -> remaining cooldown
                    'debuffs': [], # debuff type -> (value (if applicable), remaining cooldown)
                    'buffs': [], # buff type -> (value, remaining cooldown)
                    'status': {}, # status effect -> info dictionary
                    'summons': [],
                },
                self.defenderPlayer.id: {
                    'cooldowns': {}, # technique ID -> remaining cooldown
                    'debuffs': [],
                    'buffs': [],
                    'status': {},
                    'summons': [],
                },
            }
            
            turn = 1

            # Get technique ID-name mapping from AllItems
            technique_id_name_tups = await AllItems.filter(type='fight_technique').values_list('id', 'name')
            technique_id_name_dict = { tech_id: tech_name for tech_id, tech_name in technique_id_name_tups }

            player_techniques_dict = {}
            for player in [self.challengerPlayer, self.defenderPlayer]:
                equipped_items = await player.get_equipped_items()
                techniques = equipped_items['techniques']
                player_techniques_dict[player.id] = { technique: { 'Qi Cost': 20, 'name': technique_id_name_dict[technique] } for technique in techniques }
            
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
    
    @pvp.sub_command(name="profile")
    async def profile(self, inter: disnake.ApplicationCommandInteraction, member: disnake.Member = None):
        """
        Check your PVP combat stats
        """
        if member is None:
            member = inter.author

        selected_player : Player = PlayerRoster().find_player_for(inter, member)
        stats_dict = selected_player.get_stats_dict()
        # user_data = await Pvp.get_or_none(user_id=member.id).values_list("rank_points", "pvp_promo", "pvp_demote", "pvp_coins")
        # rank_points, promo_num, demote_status, pvp_coins = user_data  # Shouldn't be None...
        embed_desc_items = [f"**Username** : {member.name}"]
        for stat_name in stats_dict:
            embed_desc_items.append(f"**{stat_name}** : {stats_dict[stat_name]}")

        embed = disnake.Embed(
            title="Ranked Profile",
            description='\n'.join(embed_desc_items),
            color=disnake.Color(0x2e3135)
        )
        if member.avatar:
            embed.set_thumbnail(url=member.avatar.url)

        await inter.response.send_message(embed=embed)

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

# =================================================================================
# Define technique actions here
# =================================================================================

def get_technique_action(player: int, target: int, match: PvPMatch, technique_id: str):
    player_stats = match.player_stats_dict[player]
    target_stats = match.player_stats_dict[target]
    
    if technique_id == 'eightsplit':
        return BattleAction(
            # Deal 60% mATK as Earth Magic Damage, 60% mATK as Blood Magic Damage, 60% pATK as Earth Physical Damage and 60% pATK as Blood Physical Damage to all enemies
            # TODO: This technique deals 50% more damage for each additional enemy hit
            name = 'eightsplit', player = player, target = target, match = match,
            action_type = 'technique',
            attack_components = [
                AttackComponent(player_stats=player_stats, target_stats=target_stats, scaling_stat='mATK', scaling_stat_source='player', damage_type='magical', element='Earth', multiplier=0.6, true_damage=False),
                AttackComponent(player_stats=player_stats, target_stats=target_stats, scaling_stat='mATK', scaling_stat_source='player', damage_type='magical', element='Blood', multiplier=0.6, true_damage=False),
                AttackComponent(player_stats=player_stats, target_stats=target_stats, scaling_stat='pATK', scaling_stat_source='player', damage_type='physical', element='Earth', multiplier=0.6, true_damage=False),
                AttackComponent(player_stats=player_stats, target_stats=target_stats, scaling_stat='pATK', scaling_stat_source='player', damage_type='physical', element='Blood', multiplier=0.6, true_damage=False)
            ],
            base_accuracy = 0.9,
            player_buffs = {},
            target_debuffs = {},
            qi_cost = 20,
            cooldown = 7
        )
    elif technique_id == "flametsunami":
        return BattleAction(
            name = "flametsunami", player = player, target = target, match = match,
            action_type = 'technique',
            attack_components = [
                AttackComponent(player_stats=player_stats, target_stats=target_stats, scaling_stat='pATK', scaling_stat_source='player', damage_type='physical', multiplier=1.3, true_damage=False),
                AttackComponent(player_stats=player_stats, target_stats=target_stats, scaling_stat='mATK', scaling_stat_source='player', damage_type='magical', multiplier=1.3, true_damage=False)
            ],
            base_accuracy = 0.9,
            player_buffs = {},
            target_debuffs = {
                'mDEF': (0.2, 2, 'prop'),
                'pDEF': (0.2, 2, 'prop')
            },
            no_crit = False,
            qi_cost = 15,
            cooldown = 5
        )
    elif technique_id == "wlclaw":
        return BattleAction(
            # Deals 220% of mATK as 110% wind type damage and 110% lightning type damage
            name = "wlclaw", player = player, target = target, match = match,
            action_type = 'technique',
            attack_components = [
                AttackComponent(player_stats=player_stats, target_stats=target_stats, scaling_stat='mATK', scaling_stat_source='player', damage_type='magical', element='Wind', multiplier=1.1, true_damage=False),
                AttackComponent(player_stats=player_stats, target_stats=target_stats, scaling_stat='mATK', scaling_stat_source='player', damage_type='magical', element='Lightning', multiplier=1.1, true_damage=False)
            ],
            base_accuracy = 0.9,
            player_buffs = {
                'ACC': (40, 1, 'flat'),
            },
            target_debuffs = {},
            qi_cost = 20,
            cooldown = 5
        )
    elif technique_id == 'shocklightning':
        return BattleAction(
            # Deals 275% of mATK as Magic Damage
            name = 'shocklightning', player = player, target = target, match = match,
            action_type = 'technique',
            attack_components = [
                AttackComponent(player_stats=player_stats, target_stats=target_stats, scaling_stat='mATK', scaling_stat_source='player', damage_type='magical', multiplier=2.75, true_damage=False)
            ],
            base_accuracy = 0.9,
            player_buffs = {},
            target_debuffs = {},
            qi_cost = 20,
            cooldown = 1 # TODO
        )
    elif technique_id == "cottonhand":
        return BattleAction(
            # Deals 250% of mATK as true damage
            name = "cottonhand", player = player, target = target, match = match,
            action_type = 'technique',
            attack_components = [
                AttackComponent(player_stats=player_stats, target_stats=target_stats, scaling_stat='mATK', scaling_stat_source='player', damage_type='true', multiplier=2.5, true_damage=True)
            ],
            base_accuracy = 0.9,
            player_buffs = {},
            target_debuffs = {},
            qi_cost = 20,
            cooldown = 7
        )
    elif technique_id == "starshatter":
        return BattleAction(
            name = "starshatter", player = player, target = target, match = match,
            action_type = 'technique',
            attack_components = [
                AttackComponent(player_stats=player_stats, target_stats=target_stats, scaling_stat='mATK', scaling_stat_source='player', damage_type='magical', multiplier=3.4, true_damage=False)
            ],
            base_accuracy = 0.9,
            player_buffs = {},
            target_debuffs = {
                'mDEF': (0.5, 1, 'prop')
            },
            qi_cost = 20,
            cooldown = 5
        )
    elif technique_id == "windkillfinger":
        return BattleAction(
            name = "windkillfinger", player = player, target = target, match = match,
            action_type = 'technique',
            attack_components = [
                AttackComponent(player_stats=player_stats, target_stats=target_stats, scaling_stat='pATK', scaling_stat_source='player', damage_type='physical', multiplier=2.8, true_damage=False)
            ],
            base_accuracy = 0.9,
            player_buffs = {},
            target_debuffs = {
                'pDEF': (0.1, 99, 'prop')
            },
            qi_cost = 20,
            cooldown = 4
        )
    elif technique_id == "shatterclaw":
        return BattleAction(
            name = "shatterclaw", player = player, target = target, match = match,
            action_type = 'technique',
            attack_components = [
                AttackComponent(player_stats=player_stats, target_stats=target_stats, scaling_stat='pATK', scaling_stat_source='player', damage_type='physical', multiplier=2.9, true_damage=False)
            ],
            base_accuracy = 0.85,
            player_buffs = {},
            target_debuffs = {
                'Qi': (0.4, 99, 'prop')
            },
            qi_cost = 25,
            cooldown = 5
        )
    elif technique_id == "skelking":
        return BattleAction(
            name = "skelking", player = player, target = target, match = match,
            action_type = "technique",
            attack_components = [], # No attack component in and of itself
            base_accuracy = 1,
            player_buffs = {},
            target_debuffs = {},
            qi_cost = 20,
            cooldown = 0, # No cooldown, but can only be used once per match
        )
    elif technique_id == 'bloodagglom':
        return BattleAction(
            name = "bloodagglom", player = player, target = player, match = match,
            action_type = "technique",
            attack_components = [
                AttackComponent(player_stats=player_stats, target_stats=player_stats, scaling_stat='Max HP', scaling_stat_source='player', damage_type='true', multiplier=0.1, true_damage=True)
            ],
            base_accuracy = 1,
            player_buffs = {},
            target_debuffs = {},
            qi_cost = 20,
            cooldown = 0, # No cooldown, but can only be used once per match
        )
    elif technique_id == 'flamecreation':
        return BattleAction(
            name = "flamecreation", player = player, target = player, match = match,
            action_type = "technique",
            attack_components = [
                AttackComponent(player_stats=player_stats, target_stats=player_stats, scaling_stat='Max HP', scaling_stat_source='player', damage_type='true', multiplier=0.05, true_damage=True)
            ],
            base_accuracy = 1,
            player_buffs = {},
            target_debuffs = {},
            qi_cost = 20,
            cooldown = 0, # No cooldown, but can only be used once per match
        )
    elif technique_id == 'lightningcalamity':
        # Deal 800% of user's mATK as Lightning Damage to all enemies
        # Enemies struck by this technique have their Speed and Evasion reduced by 30% and their Defense by 20% for 5 turns.
        # If this technique defeats an enemy or entity, trigger a second explosion dealing 200% of the user's mATK as Lightning Damage to all remaining enemies.
        return BattleAction(
            name = "lightningcalamity", player = player, target = target, match = match,
            action_type = "technique",
            attack_components = [
                AttackComponent(player_stats=player_stats, target_stats=target_stats, scaling_stat='mATK', scaling_stat_source='player', damage_type='magical', element='Lightning', multiplier=8.0, true_damage=False)
            ],
            base_accuracy = 0.8,
            player_buffs = {},
            target_debuffs = {
                'SPD': (0.3, 5, 'prop'),
                'EVA': (0.3, 5, 'prop'),
                'pDEF': (0.2, 5, 'prop'),
                'mDEF': (0.2, 5, 'prop'),
            },
            qi_cost = 20,
            cooldown = 7,
            aoe = True # Affects all enemies (ignores taunts)
        )

def get_summon_action(player: int, target: int, match: PvPMatch, summon_name: str):
    player_stats = match.player_stats_dict[player]
    target_stats = match.player_stats_dict[target]
    
    if summon_name == "Skeleton King":
        return BattleAction(
            name = "Skeleton King",
            player = player,
            target = target,
            match = match,
            action_type = 'summon',
            attack_components = [
                AttackComponent(player_stats=player_stats, target_stats=target_stats, scaling_stat='pATK', scaling_stat_source='player', damage_type='physical', element='Dark', multiplier=1, true_damage=False),
            ],
            base_accuracy = 1,
            player_buffs = {},
            target_debuffs = {},
            no_crit = True,
            qi_cost = 0,
            cooldown = 0,
        )
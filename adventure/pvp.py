from __future__ import annotations
from typing import Optional, Dict, List, Tuple
from datetime import datetime
from enum import Enum
import random
import math
import disnake
from character.player import Player, StatusEffect, TechniqueType
from character.pvp_stats import PvPStats, Element
from utils.Embeds import create_embed
from utils.Styles import PLUS, MINUS, EXCLAMATION, TICK, CROSS
from utils.LoggingUtils import log_event

class BattlePhase(Enum):
    INITIALIZATION = "Initialization"
    TURN_START = "Turn Start"
    ACTION = "Action"
    TURN_END = "Turn End"
    COMPLETION = "Completion"

class PvPBattle:
    def __init__(self, player1: Player, player2: Player):
        self.players = [player1, player2]
        self.current_turn = 0
        self.turn_count = 0
        self.battle_log = []
        self.winner = None
        
    async def start_battle(self) -> Tuple[Optional[Player], List[str]]:
        """Start and run the PvP battle"""
        self.battle_log.append("⚔️ Battle started!")
        
        # Initialize battle state
        for player in self.players:
            player.process_status_effects()
            self.battle_log.append(f"{player.as_member().mention} enters the battle!")
        
        # Battle loop
        while not self.is_battle_over():
            self.turn_count += 1
            self.battle_log.append(f"\n**Turn {self.turn_count}**")
            
            # Process turn for current player
            current_player = self.players[self.current_turn]
            opponent = self.players[1 - self.current_turn]
            
            # Turn start phase
            self.battle_log.append(f"{current_player.as_member().mention}'s turn begins")
            current_player.process_status_effects()
            
            # Action phase
            action_result = await self.process_player_action(current_player, opponent)
            self.battle_log.extend(action_result)
            
            # Check if battle ended
            if self.is_battle_over():
                break
                
            # Turn end phase
            self.battle_log.append(f"{current_player.as_member().mention}'s turn ends")
            
            # Switch turns
            self.current_turn = 1 - self.current_turn
        
        # Determine winner
        self.winner = self.determine_winner()
        if self.winner:
            self.battle_log.append(f"\n🎉 {self.winner.as_member().mention} wins the battle!")
        else:
            self.battle_log.append("\n⚖️ The battle ended in a draw!")
            
        return self.winner, self.battle_log

    async def process_player_action(self, player: Player, opponent: Player) -> List[str]:
        """Process a player's action during their turn"""
        log = []
        
        # Randomly select an action type (attack, technique, etc.)
        action_type = random.choice(["attack", "technique"])
        
        if action_type == "attack":
            # Basic attack
            damage = self.calculate_damage(player, opponent)
            opponent._energy = max(opponent._energy - damage, 0)
            log.append(f"{player.as_member().mention} attacks for {damage} damage!")
            
            # Chance to apply status effect
            if random.random() < 0.2:  # 20% chance
                effect = random.choice(list(StatusEffect))
                duration = random.randint(1, 3)
                opponent.add_status_effect(effect, duration)
                log.append(f"{opponent.as_member().mention} is now {effect.value} for {duration} turns!")
                
        elif action_type == "technique":
            # Use a technique based on available Dou Qi
            if player.dou_qi >= 20:
                technique = self.select_technique(player)
                effect = self.apply_technique(player, opponent, technique)
                log.extend(effect)
                player.consume_dou_qi(20)
            else:
                log.append(f"{player.as_member().mention} doesn't have enough Dou Qi for a technique!")
                
        return log

    def calculate_damage(self, attacker: Player, defender: Player) -> int:
        """Calculate damage based on stats and elements"""
        base_damage = attacker.pvp_stats.pATK - defender.pvp_stats.pDEF
        base_damage = max(base_damage, 1)
        
        # Apply elemental multiplier
        element_mult = defender.get_elemental_multiplier(attacker.pvp_stats.elements[0])
        damage = math.floor(base_damage * element_mult)
        
        # Apply random variance
        damage = random.randint(math.floor(damage * 0.9), math.ceil(damage * 1.1))
        
        return damage

    def select_technique(self, player: Player) -> TechniqueType:
        """Select a technique based on player stats"""
        # Simple technique selection logic
        if player.pvp_stats.pATK > player.pvp_stats.mATK:
            return TechniqueType.ATTACK
        else:
            return TechniqueType.SUPPORT

    def apply_technique(self, player: Player, opponent: Player, technique: TechniqueType) -> List[str]:
        """Apply a technique's effects"""
        log = []
        if technique == TechniqueType.ATTACK:
            damage = self.calculate_damage(player, opponent) * 1.5
            opponent._energy = max(opponent._energy - damage, 0)
            log.append(f"{player.as_member().mention} uses a powerful {technique.value} technique for {damage} damage!")
        elif technique == TechniqueType.SUPPORT:
            heal_amount = math.floor(player.pvp_stats.mATK * 0.5)
            player._energy = min(player._energy + heal_amount, player.max_energy)
            log.append(f"{player.as_member().mention} uses a {technique.value} technique, healing for {heal_amount}!")
            
        return log

    def is_battle_over(self) -> bool:
        """Check if the battle should end"""
        # Battle ends if either player reaches 0 energy
        return any(player._energy <= 0 for player in self.players) or self.turn_count >= 20

    def determine_winner(self) -> Optional[Player]:
        """Determine the winner of the battle"""
        if self.players[0]._energy <= 0 and self.players[1]._energy <= 0:
            return None  # Draw
        elif self.players[0]._energy <= 0:
            return self.players[1]
        elif self.players[1]._energy <= 0:
            return self.players[0]
        elif self.turn_count >= 20:
            # If turn limit reached, player with most energy wins
            return max(self.players, key=lambda p: p._energy)
        return None

async def start_pvp_battle(player1: Player, player2: Player) -> Tuple[Optional[Player], disnake.Embed]:
    """Start a PvP battle between two players"""
    battle = PvPBattle(player1, player2)
    winner, log = await battle.start_battle()
    
    # Create battle result embed
    embed = create_embed(
        title="⚔️ PvP Battle Results",
        description="\n".join(log),
        color=0x00ff00 if winner else 0xffff00
    )
    
    # Update player stats
    if winner:
        await winner.pvp_stats.add_win()
        loser = player2 if winner == player1 else player1
        await loser.pvp_stats.add_loss()
    else:
        await player1.pvp_stats.add_draw()
        await player2.pvp_stats.add_draw()
        
    return winner, embed

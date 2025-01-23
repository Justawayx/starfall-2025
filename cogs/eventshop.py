import disnake
from disnake.ext import commands

from utils.EconomyUtils import EVENT_SHOP
from utils.Embeds import BasicEmbeds
from utils.base import BaseStarfallCog
from utils.LoggingUtils import log_event

EVENT_CONFIG = {
    "winter": {
        "token_id": "winter_token",
        "items": {
            "item_id1": {"cost": 5, "quantity": 1},
            "item_id2": {"cost": 10, "quantity": 1}
        },
        "sources": {
            "daily_bonus": True,
            "beast_drops": True,
            "cultivation": True,
            "breakthrough": True
        },
        "drop_rates": {
            "daily": {"min": 1, "max": 3, "chance": 100},  # Guaranteed 1-3 tokens
            "beast": {"min": 1, "max": 2, "chance": 25},   # 25% chance for 1-2 tokens
            "cultivation": {"min": 2, "max": 5, "chance": 15},  # 15% chance for 2-5 tokens
            "breakthrough": {"min": 3, "max": 6, "chance": 50}  # 50% chance for 3-6 tokens
        }
    },
    "spring": {
        "token_id": "spring_token",
        "items": {
            "item_id3": {"cost": 5, "quantity": 1},
            "item_id4": {"cost": 10, "quantity": 1}
        },
        "sources": {
            "daily_bonus": True,
            "beast_drops": True,
            "cultivation": True
        }
    },
    "summer": {
        "token_id": "summer_token",
        "items": {
            "item_id5": {"cost": 5, "quantity": 1},
            "item_id6": {"cost": 10, "quantity": 1}
        },
        "sources": {
            "daily_bonus": True,
            "beast_drops": False,
            "cultivation": False
        }
    }
}

class EventManager(BaseStarfallCog):
    def __init__(self, bot):
        super().__init__(bot, "EventManager", "event")
        self.current_event = None
        
    @commands.slash_command()
    @commands.default_member_permissions(manage_guild=True)
    async def event(self, inter):
        """Parent Command"""
        pass

    @event.sub_command(name="toggle", description="Toggle event status and token sources")
    @commands.is_owner()
    async def toggle_event(
        self, 
        inter: disnake.CommandInteraction,
        event_type: str = commands.Param(choices=["winter", "spring", "summer"]),
        duration_hours: int = commands.Param(default=168, description="Duration in hours"),
        daily_bonus: bool = commands.Param(default=True, description="Enable token drops from daily"),
        beast_drops: bool = commands.Param(default=True, description="Enable token drops from beast hunts"),
        breakthrough: bool = commands.Param(default=True, description="Enable token drops from breakthrough")
    ):
        if not EVENT_SHOP.is_active:
            self.current_event = event_type
            EVENT_SHOP.enable(duration_hours)
            
            # Update source configuration
            EVENT_CONFIG[event_type]["sources"].update({
                "daily_bonus": daily_bonus,
                "beast_drops": beast_drops,
                "breakthrough": breakthrough
            })
            
            sources = []
            if daily_bonus: sources.append("Daily Bonus")
            if beast_drops: sources.append("Beast Hunts")
            if breakthrough: sources.append("Breakthrough")
            
            await inter.response.send_message(
                embed=BasicEmbeds.right_tick(
                    f"{event_type.capitalize()} Festival enabled for {duration_hours} hours\n"
                    f"Token Sources: {', '.join(sources)}",
                    "Event Enabled"
                )
            )
        else:
            EVENT_SHOP.disable()
            self.current_event = None
            await inter.response.send_message(
                embed=BasicEmbeds.right_tick(
                    "Event disabled",
                    "Event Disabled"
                )
            )

def setup(bot):
    cog = EventManager(bot)
    bot.add_cog(cog)
    global EVENT_MANAGER
    EVENT_MANAGER = cog
    log_event("system", "event", f"{cog.name} Created", "INFO")
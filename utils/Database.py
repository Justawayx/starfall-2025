from typing import Optional, Any
from tortoise import fields
from tortoise.models import Model

# Special ID constants
ID_UNCREATED = "uncreated"  # Used to indicate an entity that hasn't been persisted yet

class RuinsDao(Model):
    """Database model for ruins exploration"""
    exploration_id = fields.UUIDField(pk=True)
    user_id = fields.BigIntField()
    ruin_id = fields.UUIDField()
    status = fields.CharField(max_length=20, default='exploring')
    progress = fields.IntField(default=0)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "ruins_explorations"

    @property
    def is_active(self) -> bool:
        """Check if exploration is still active"""
        return self.status == 'exploring'

    @classmethod
    async def get_active_explorations(cls, user_id: int) -> list['RuinsDao']:
        """Get all active explorations for a user"""
        return await cls.filter(user_id=user_id, status='exploring')

__all__ = ['Alchemy', 'Cultivation', 'PvpStatsDao', 'Users', 'Pvp', 'RingInventory', 'Pet', 'Temp', 'Factions', 'Inventory', 'Techniques', 'Quests', 'AllRings', 'AllItems', 'Market', 'GuildOptions', 'Crafted', 'GuildOptionsDict', 'AllBeasts', 'AllPets', 'Character', 'AuctionDao', 'BeastBattleDao', 'ID_UNCREATED', 'RuinsDao']

# Move Character model to top of file
class Character(Model):
    """Database model for player characters"""
    user_id = fields.BigIntField(pk=True)
    name = fields.CharField(max_length=100)
    level = fields.IntField(default=1)
    experience = fields.IntField(default=0)
    stats = fields.JSONField(default={})
    skills = fields.JSONField(default=[])
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "characters"

class AllPets(Model):
    """Database model for all available pets"""
    pet_id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=100)
    description = fields.TextField()
    type = fields.CharField(max_length=50)
    stats = fields.JSONField()
    rarity = fields.CharField(max_length=50)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "all_pets"

class AllBeasts(Model):
    """Database model for all available beasts"""
    beast_id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=100)
    description = fields.TextField()
    type = fields.CharField(max_length=50)
    stats = fields.JSONField()
    rarity = fields.CharField(max_length=50)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "all_beasts"

class GuildOptionsDict(Model):
    """Database model for guild options dictionary"""
    guild_id = fields.BigIntField(pk=True)
    options = fields.JSONField()
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "guild_options_dict"

class Crafted(Model):
    """Database model for crafted items"""
    item_id = fields.UUIDField(pk=True)
    crafter_id = fields.BigIntField()
    recipe_id = fields.IntField()
    quality = fields.IntField()
    stats = fields.JSONField()
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "crafted_items"

class GuildOptions(Model):
    """Database model for guild-specific settings"""
    guild_id = fields.BigIntField(pk=True)
    name = fields.CharField(max_length=100, null=True)  # Added name field
    pvp_enabled = fields.BooleanField(default=True)
    economy_enabled = fields.BooleanField(default=True)
    value = fields.JSONField(default={})  # Added value field for storing additional settings
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "guild_options"

    @classmethod
    async def get_or_create(cls, guild_id: int, name: Optional[str] = None) -> 'GuildOptions':
        """Get or create guild options"""
        options, _ = await cls.get_or_create(guild_id=guild_id, defaults={'name': name})
        return options

    async def update_value(self, key: str, value: Any):
        """Update a specific value in the settings"""
        self.value[key] = value
        await self.save()

    @classmethod
    async def get_by_name(cls, name: str) -> Optional['GuildOptions']:
        """Get guild options by name"""
        return await cls.filter(name=name).first()

class Market(Model):
    """Database model for marketplace listings"""
    listing_id = fields.UUIDField(pk=True)
    seller_id = fields.BigIntField()
    item = fields.JSONField()
    price = fields.IntField()
    quantity = fields.IntField()
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "market"

class AllItems(Model):
    """Database model for all available items"""
    item_id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=100)
    description = fields.TextField()
    type = fields.CharField(max_length=50)
    stats = fields.JSONField()
    rarity = fields.CharField(max_length=50)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "all_items"

class AllRings(Model):
    """Database model for all available rings"""
    ring_id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=100)
    description = fields.TextField()
    stats = fields.JSONField()
    rarity = fields.CharField(max_length=50)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "all_rings"

class Inventory(Model):
    """Database model for player inventory"""
    user_id = fields.BigIntField(pk=True)
    items = fields.JSONField(default={})
    equipment = fields.JSONField(default={})
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "inventory"

class Techniques(Model):
    """Database model for player techniques"""
    user_id = fields.BigIntField(pk=True)
    techniques = fields.JSONField(default=[])
    equipped = fields.JSONField(default=[])
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "techniques"

class Quests(Model):
    """Database model for player quests"""
    user_id = fields.BigIntField(pk=True)
    active_quests = fields.JSONField(default=[])
    completed_quests = fields.JSONField(default=[])
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "quests"

class Factions(Model):
    """Database model for player factions"""
    user_id = fields.BigIntField(pk=True)
    faction = fields.CharField(max_length=50)
    rank = fields.CharField(max_length=50)
    reputation = fields.IntField(default=0)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "factions"

class Temp(Model):
    """Database model for temporary data storage"""
    id = fields.UUIDField(pk=True)
    user_id = fields.BigIntField()
    data = fields.JSONField()
    expires_at = fields.DatetimeField()
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "temp_data"

class Pet(Model):
    """Database model for player pets"""
    pet_id = fields.UUIDField(pk=True)
    user_id = fields.BigIntField()
    name = fields.CharField(max_length=50)
    type = fields.CharField(max_length=50)
    level = fields.IntField(default=1)
    experience = fields.IntField(default=0)
    stats = fields.JSONField(default={})
    skills = fields.JSONField(default=[])
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "pets"

class RingInventory(Model):
    """Database model for ring inventory"""
    user_id = fields.BigIntField(pk=True)
    rings = fields.JSONField(default=[])
    equipped_rings = fields.JSONField(default=[])
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "ring_inventory"

class Pvp(Model):
    """Database model for active PvP matches"""
    match_id = fields.UUIDField(pk=True)
    challenger_id = fields.BigIntField()
    defender_id = fields.BigIntField()
    status = fields.CharField(max_length=20, default='pending')
    turn = fields.IntField(default=0)
    challenger_energy = fields.IntField(default=100)
    challenger_dou_qi = fields.IntField(default=100)
    defender_energy = fields.IntField(default=100)
    defender_dou_qi = fields.IntField(default=100)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "pvp_matches"

class Users(Model):
    """Database model for user accounts"""
    user_id = fields.BigIntField(pk=True)
    energy = fields.IntField(default=100)
    dou_qi = fields.IntField(default=100)
    max_energy = fields.IntField(default=100)
    max_dou_qi = fields.IntField(default=100)
    money = fields.IntField(default=0)
    star = fields.IntField(default=0)
    money_cooldown = fields.IntField(default=0)
    status_effects = fields.JSONField(default={})
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "users"

class Alchemy(Model):
    """Database model for alchemy recipes"""
    id = fields.IntField(pk=True)
    recipe_name = fields.CharField(max_length=100)
    ingredients = fields.JSONField()
    result = fields.JSONField()
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "alchemy_recipes"

class Cultivation(Model):
    """Database model for cultivation progress"""
    user_id = fields.BigIntField(pk=True)
    stage = fields.CharField(max_length=50)
    experience = fields.IntField(default=0)
    max_energy = fields.IntField(default=100)
    max_dou_qi = fields.IntField(default=100)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "cultivation"

class AuctionDao(Model):
    """Database model for auction listings"""
    auction_id = fields.UUIDField(pk=True)
    seller_id = fields.BigIntField()
    item = fields.JSONField()
    starting_price = fields.IntField()
    current_bid = fields.IntField(null=True)
    bidder_id = fields.BigIntField(null=True)
    end_time = fields.DatetimeField()
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "auctions"

    @property
    def is_active(self) -> bool:
        """Check if auction is still active"""
        return datetime.now(timezone.utc) < self.end_time

    @classmethod
    async def get_active_auctions(cls) -> list['AuctionDao']:
        """Get all active auctions"""
        return await cls.filter(end_time__gt=datetime.now(timezone.utc))

class BeastBattleDao(Model):
    """Database model for PvE beast battles"""
    battle_id = fields.UUIDField(pk=True)
    user_id = fields.BigIntField()
    beast_id = fields.UUIDField()
    status = fields.CharField(max_length=20, default='active')
    turn = fields.IntField(default=0)
    player_energy = fields.IntField(default=100)
    player_dou_qi = fields.IntField(default=100)
    beast_energy = fields.IntField(default=100)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "beast_battles"

    @property
    def is_active(self) -> bool:
        """Check if battle is still active"""
        return self.status == 'active'

    @classmethod
    async def get_active_battles(cls, user_id: int) -> list['BeastBattleDao']:
        """Get all active battles for a user"""
        return await cls.filter(user_id=user_id, status='active')

class RuinsDao(Model):
    """Database model for ruins exploration"""
    exploration_id = fields.UUIDField(pk=True)
    user_id = fields.BigIntField()
    ruin_id = fields.UUIDField()
    status = fields.CharField(max_length=20, default='exploring')
    progress = fields.IntField(default=0)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "ruins_explorations"

    @property
    def is_active(self) -> bool:
        """Check if exploration is still active"""
        return self.status == 'exploring'

    @classmethod
    async def get_active_explorations(cls, user_id: int) -> list['RuinsDao']:
        """Get all active explorations for a user"""
        return await cls.filter(user_id=user_id, status='exploring')

class PvpStatsDao(Model):
    """Database model for PvP statistics"""
    user_id = fields.BigIntField(pk=True)
    wins = fields.IntField(default=0)
    losses = fields.IntField(default=0)
    draws = fields.IntField(default=0)
    last_match = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "pvp_stats"

    @property
    def win_rate(self) -> float:
        """Calculate win rate percentage"""
        total = self.wins + self.losses + self.draws
        if total == 0:
            return 0.0
        return (self.wins / total) * 100

    @classmethod
    async def get(cls, user_id: int) -> Optional['PvpStatsDao']:
        """Get or create PvP stats for a user"""
        stats, _ = await cls.get_or_create(user_id=user_id)
        return stats

    async def add_win(self):
        """Increment win count"""
        self.wins += 1
        self.last_match = fields.now()
        await self.save()

    async def add_loss(self):
        """Increment loss count"""
        self.losses += 1
        self.last_match = fields.now()
        await self.save()

    async def add_draw(self):
        """Increment draw count"""
        self.draws += 1
        self.last_match = fields.now()
        await self.save()

async def init_database():
    """Initialize database connection"""
    from tortoise import Tortoise
    await Tortoise.init(
        db_url='sqlite://db.sqlite3',
        modules={'models': ['utils.Database']}
    )
    await Tortoise.generate_schemas()

__all__.append('init_database')

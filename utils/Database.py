from tortoise import Tortoise, fields
from tortoise.models import Model

DB_CONFIG = {
    "connections": {"default": "sqlite://./data.sqlite"},
    "apps": {
        "models": {
            "models": ["utils.Database", "aerich.models"],
            "default_connection": "default",
        },
    },
}

ID_UNCREATED: int = -1


# ==============================
# PLAYER DATA
# ==============================
class Users(Model):
    user_id = fields.BigIntField(pk=True, generated=False)  # Discord user ID

    # Money and energy
    money = fields.BigIntField(default=0)  # Gold
    money_cooldown = fields.BigIntField(default=0)  # Daily stipend cooldown
    star = fields.BigIntField(default=0)
    energy = fields.SmallIntField(default=60)  # Current energy
    HP = fields.SmallIntField(default=0) # Current HP
    Qi = fields.SmallIntField(default=0) # Current Qi
    elements = fields.JSONField(default=[]) # List of elemental affinities
    max_energy = fields.SmallIntField(default=60)
    market_points = fields.BigIntField(default=0)
    patreon_cooldown = fields.BigIntField(default=0)

    # Things on body
    pill_used = fields.JSONField(default=[])  # List of IDs of pills in effect
    equipped = fields.JSONField(default={"techniques": {}, "method": None, "weapons": {}, "ring": None})  # For now, learned techniques and method
    bonuses = fields.JSONField(default={"exp": 0, "cp": 0})  # Permanent bonuses
    battle_boost = fields.JSONField(default=[0, 0], null=True)  # number of battle boost is for

    # Other table references
    cultivation: fields.ReverseRelation["Cultivation"]
    crafting: fields.ReverseRelation["Crafting"]
    pet: fields.ReverseRelation["Pet"]
    alchemy: fields.ReverseRelation["Alchemy"]
    pvp: fields.ReverseRelation["Pvp"]

    faction: fields.ReverseRelation["Factions"]

    inventory: fields.ReverseRelation["Inventory"]
    temp: fields.ReverseRelation["Temp"]

    market_author: fields.ReverseRelation["Market"]
    quests: fields.ReverseRelation["Quests"]

    auction_author: fields.ReverseRelation["AuctionDao"]
    auction_bidder: fields.ReverseRelation["AuctionDao"]

    pvp_challenger: fields.ReverseRelation["PvpMatches"]
    pvp_defender: fields.ReverseRelation["PvpMatches"]

    ruins_discovered: fields.ReverseRelation["RuinsDao"]


class Cultivation(Model):
    user = fields.ForeignKeyField("models.Users", related_name="cultivation", pk=True)

    major = fields.SmallIntField(default=0)
    minor = fields.SmallIntField(default=0)
    current_exp = fields.BigIntField(default=0)
    total_exp = fields.BigIntField(default=0)

    msg_limit = fields.SmallIntField(default=0)
    in_voice = fields.SmallIntField(default=0)

    cooldown = fields.DatetimeField()
    cultivate_cooldown = fields.DatetimeField()  # New


class Crafting(Model):
    user = fields.ForeignKeyField("models.Users", related_name="crafting", pk=True)

    # Crafting status
    c_lvl = fields.SmallIntField(default=0)  # crafting tier
    c_exp = fields.SmallIntField(default=0)  # Total crafting EXP

    crafted = fields.JSONField(default=[])  # History of items crafted
    craft_cooldown = fields.IntField(default=0)  # Cooldown since last crafting attempt


class Pet(Model):
    id = fields.IntField(pk=True, generated=True)
    user = fields.ForeignKeyField("models.Users", related_name="pet")

    beast = fields.ForeignKeyField("models.AllBeasts", related_name="human_pet")

    pet = fields.ForeignKeyField("models.AllPets", related_name="hatched")
    nickname = fields.CharField(max_length=255)
    main = fields.SmallIntField(default=0)

    p_cp = fields.BigIntField()
    p_major = fields.SmallIntField(default=0)
    p_minor = fields.SmallIntField(default=0)
    p_exp = fields.BigIntField(default=1)

    growth_rate = fields.FloatField()
    reroll_count = fields.SmallIntField(default=0)


class Alchemy(Model):
    user = fields.ForeignKeyField("models.Users", related_name="alchemy", pk=True)

    # Alchemy status
    a_lvl = fields.SmallIntField(default=0)  # Alchemy tier
    a_exp = fields.SmallIntField(default=0)  # Total alchemy EXP

    # Cauldron and flame
    cauldron = fields.CharField(max_length=255, null=True)  # Cauldron ID
    flame = fields.CharField(max_length=255, null=True)  # Equipped Flame ID

    # Pill refinement
    pill_refined = fields.JSONField(default={})  # History of # pills refined per tier
    pill_cooldown = fields.IntField(default=0)  # Cooldown since last pill refine attempt
    next_tier_chance = fields.SmallIntField(default=50)  # Refinement rate for next tier pill
    pill_pity = fields.SmallIntField(default=0)  # Pity for alchemy tier breakthrough


class Pvp(Model):
    user = fields.ForeignKeyField("models.Users", related_name="pvp", pk=True)

    pvp_promo = fields.SmallIntField(default=0)  # PVP promos status
    pvp_demote = fields.SmallIntField(default=0)  # Whether about to demote
    rank_points_before_promo = fields.SmallIntField(default=0)  # Rank points before promos
    rank_points = fields.IntField(default=0)  # PVP rank points
    pvp_coins = fields.BigIntField(default=0)  # PVP Arena Coins
    pvp_cooldown = fields.IntField(default=0)  # Amount of PVP matches remaining for the day


class Quests(Model):
    id = fields.IntField(pk=True, generated=True)
    rank = fields.SmallIntField(default=0)
    user = fields.ForeignKeyField("models.Users", related_name="quests", null=True)
    item = fields.ForeignKeyField("models.AllItems", related_name="quest_item")
    max_count = fields.SmallIntField(default=1)
    count = fields.SmallIntField(default=1)
    reward = fields.JSONField(default={})
    contributors = fields.JSONField(default={})
    till = fields.BigIntField()


# ==============================
# CONSTANT DATA
# ==============================


class AllBeasts(Model):
    name = fields.CharField(max_length=255, pk=True)  # Name of beast
    rank = fields.SmallIntField()  # Rank of beast
    health = fields.IntField()  # Total health of beast (hunt)
    affinity = fields.CharField(max_length=255, null=True)  # Elemental affinity of beast
    exp_given = fields.IntField()  # Total EXP given
    drop_rate = fields.IntField()  # Monster core drop rate
    mat_drop_types = fields.JSONField(default=[])  # List of possible material drop IDs

    spawned: fields.ReverseRelation["Beast"]
    human_pet: fields.ReverseRelation["Pet"]


class AllPets(Model):
    name = fields.CharField(max_length=255, pk=True)
    rank = fields.SmallIntField()
    rarity = fields.CharField(max_length=255)
    growth_rate = fields.JSONField(default=[])
    base_cp = fields.BigIntField()
    evolution = fields.JSONField(default={})
    start_stage = fields.JSONField(default={})

    hatched: fields.ReverseRelation["Pet"]


class AllItems(Model):
    id = fields.CharField(max_length=255, pk=True)

    type = fields.CharField(max_length=255)  # Item type
    tier = fields.SmallIntField(default=0)  # Item tier
    weight = fields.SmallIntField(default=1)
    name = fields.CharField(max_length=255)  # Item name
    description = fields.CharField(max_length=999, default="No description")  # Item description
    e_description = fields.CharField(max_length=999, default="No effect")  # Item effect description
    properties = fields.JSONField(default={})  # Item-specific properties dictionary
    max = fields.SmallIntField(default=99)  # Maximum allowed in inventory

    buy_cost_d = fields.JSONField(default={})  # Cost to buy (in gold)
    # buy_ac_cost = fields.JSONField(default=0) # Cost to buy (in Arena Coins)
    sell_cost_d = fields.JSONField(default={})  # Sell price (in gold)

    inventory_item: fields.ReverseRelation["Inventory"]
    crafted_item: fields.ReverseRelation["Crafted"]
    market_item: fields.ReverseRelation["Market"]
    ring_item: fields.ReverseRelation["RingInventory"]
    temp_item: fields.ReverseRelation["Temp"]
    quest_item: fields.ReverseRelation["Quests"]


class Factions(Model):
    user = fields.ForeignKeyField("models.Users", related_name="faction", pk=True)
    name = fields.CharField(max_length=255)
    role_id = fields.BigIntField()
    multiplier = fields.SmallIntField()


# ==============================
# DYNAMIC PLAYER DATA
# ==============================

class Market(Model):
    id = fields.BigIntField(pk=True, generated=True)
    user = fields.ForeignKeyField("models.Users", related_name="market_author")
    item = fields.ForeignKeyField("models.AllItems", related_name="market_item")
    amount = fields.SmallIntField(default=1)
    price = fields.IntField(default=1)
    created = fields.DatetimeField(auto_now_add=True)
    expiry = fields.DatetimeField()
    unique_id = fields.IntField(null=True)


class Beast(Model):
    beast = fields.ForeignKeyField("models.AllBeasts", related_name="spawned")
    beast_type = fields.CharField(max_length=255, null=True)
    msg_id = fields.BigIntField()
    total_health = fields.IntField()
    current_health = fields.IntField()
    attackers = fields.JSONField(default={})
    till = fields.DatetimeField(null=True)
    mcore_drop = fields.BigIntField(null=True)
    bflame_drop = fields.BigIntField(null=True)
    mat_drops = fields.JSONField(default=[])


class BeastBattleDao(Model):
    # Using the database as a NoSQL one for this case to add flexibility to the model without touching the database since this object will always be completely read and written
    # Furthermore, there are no hard relationship with other table beside some player ids and beast name and the latter should not really have been a table to begin with
    # Just keeping the PK and history columns since PK is needed for lookup and history for purges
    # There's obviously a risk doing so in case someone alters the database directly since there are no database integrity constraints
    id = fields.BigIntField(pk=True, generated=True)
    data = fields.JSONField(default={})
    created_at = fields.DatetimeField()
    updated_at = fields.DatetimeField()

    class Meta:
        table = "beast_battle"


class GuildOptions(Model):
    name = fields.CharField(max_length=255)
    value = fields.CharField(max_length=255)


class GuildOptionsDict(Model):
    name = fields.CharField(max_length=255)
    value = fields.JSONField()


class Inventory(Model):
    user = fields.ForeignKeyField("models.Users", related_name="inventory")
    item = fields.ForeignKeyField("models.AllItems", related_name="inventory_item")
    unique_id = fields.IntField(null=True)
    count = fields.SmallIntField(default=1)


class Crafted(Model):
    id = fields.IntField(pk=True, generated=True)
    item = fields.ForeignKeyField("models.AllItems", related_name="crafted_item")
    stats = fields.JSONField(default={})


class AllRings(Model):
    id = fields.IntField(pk=True, generated=True)
    ring = fields.CharField(max_length=255, null=True)
    total_weight = fields.IntField(null=True)

    items: fields.ReverseRelation["RingInventory"]


class RingInventory(Model):
    ring = fields.ForeignKeyField("models.AllRings", related_name="items", null=True)
    item = fields.ForeignKeyField("models.AllItems", related_name="ring_item")
    unique_id = fields.IntField(null=True)
    count = fields.SmallIntField(default=1)


class Temp(Model):
    user = fields.ForeignKeyField("models.Users", related_name="temp", pk=True)
    till = fields.BigIntField()  # Time when breakthrough ends
    role_id = fields.BigIntField(null=True)
    item = fields.ForeignKeyField("models.AllItems", related_name="temp_item", null=True)
    cp = fields.SmallIntField(null=True)
    exp = fields.SmallIntField(null=True)
    event_exp = fields.SmallIntField(null=True)
    event_cp = fields.SmallIntField(null=True)

class PvpMatches(Model):
    id = fields.BigIntField(pk=True, generated=True)
    challenger = fields.ForeignKeyField("models.Users", related_name="pvp_challenger", null=True)
    defender = fields.ForeignKeyField("models.Users", related_name="pvp_defender", null=True)
    status = fields.CharField(max_length=255, default="pending") # Match status
    turn = fields.SmallIntField(default=0) # Turn number
    player_stats = fields.JSONField(default={}) # Dictionary: user ID -> stats dict
    player_action = fields.JSONField(default={}) # Dictionary: user ID -> action dict
    player_status = fields.JSONField(default={}) # Dictionary: user ID -> status dict
    created_at = fields.DatetimeField(null=True)
    updated_at = fields.DatetimeField(null=True)

    class Meta:
        table = "pvp_matches"

class AuctionDao(Model):
    # PK
    id = fields.BigIntField(pk=True, generated=True)

    # The new auctioned item post id on the auction channel
    msg_id = fields.BigIntField(null=True)

    # Source detail
    user = fields.ForeignKeyField("models.Users", related_name="auction_author", null=True)
    system_auction = fields.BooleanField(default=False)

    # Unique id to allow users to select the entry to place their bids
    item = fields.ForeignKeyField("models.AllItems", related_name="auction_item")
    unique_id = fields.IntField(null=True)
    quantity = fields.SmallIntField(default=1)
    minimum_bid = fields.IntField(default=1)
    minimum_increment = fields.IntField(default=1)
    start_time = fields.DatetimeField(null=True)
    duration = fields.IntField(default=6)
    countdown_start_time = fields.DatetimeField(null=True)
    end_time = fields.DatetimeField(null=True)
    item_remaining_lifespan = fields.IntField(null=True)
    item_retrieved = fields.BooleanField(default=False)

    # the user currently winning this auction
    winning_user = fields.ForeignKeyField("models.Users", related_name="auction_bidder", null=True)
    winning_current_amount = fields.BigIntField(null=True)
    winning_maximum_amount = fields.BigIntField(null=True)
    winning_reserved_amount = fields.IntField(null=True)
    winning_tax_rate = fields.IntField(null=True)
    winning_bid_time = fields.DatetimeField(null=True)

    class Meta:
        table = "auction"


class RuinsDao(Model):
    id = fields.BigIntField(pk=True, generated=True)
    msg_id = fields.BigIntField()
    user = fields.ForeignKeyField(model_name="models.Users", related_name="ruins_discovered", null=True, on_delete=fields.SET_NULL)
    ended = fields.BooleanField(default=False)
    data = fields.JSONField(default={})
    created_at = fields.DatetimeField()
    updated_at = fields.DatetimeField()

    class Meta:
        table = "ruins"


class GamingTableDao(Model):
    id = fields.BigIntField(pk=True, generated=True)
    game_id = fields.CharField(max_length=255)
    data = fields.JSONField(default=None)
    ended = fields.BooleanField(default=False)
    expires_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField()
    updated_at = fields.DatetimeField()

    class Meta:
        table = "gaming_table"


# Initialize models and database
async def init_database():
    # Create SQLite DB using models specified above
    await Tortoise.init(
        db_url="sqlite://./data.sqlite",
        modules={"models": ["utils.Database"]}
    )

    # Generate schema
    await Tortoise.generate_schemas(safe=True)

    print("[Database] Initialized")

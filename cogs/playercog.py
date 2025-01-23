import random
from typing import Optional, cast, Union

import disnake
import logging
from disnake.ext import commands
from tortoise.expressions import F

from adventure.chests import ChestLootConfig
from world.compendium import ItemCompendium, ItemDefinition, ChestDefinition, autocomplete_item_id, EggDefinition, FlameDefinition, BeastFlameDefinition, HeavenlyFlameDefinition
from character.player import PlayerRoster, Player, ENERGY_RECOVERY_RATE_MINUTES
from utils.Database import Inventory, Alchemy
from utils.EconomyUtils import shop_view
from utils.Embeds import BasicEmbeds
from utils.InventoryUtils import inventory_view, convert_id, get_user_all_rings_id, give_multiple_ring_inv, check_item_in_inv, remove_from_inventory, get_equipped_ring_id, add_to_inventory, check_inv_weight, ITEM_TYPE_CHEST
from utils.LoggingUtils import log_event
from utils.Styles import PLUS, TICK, ITEM_EMOJIS, EXCLAMATION, RIGHT, LEFT
from utils.base import BaseStarfallCog
from world.cultivation import PlayerCultivationStage
from utils.loot import Loot

_BASE_FLAME_CHANCE: int = 25
_SHORT_NAME = "roster"


class PlayerCog(BaseStarfallCog):
    def __init__(self, bot):
        super().__init__(bot, "Player Roster Cog", _SHORT_NAME)

    @commands.slash_command(name="inventory")
    async def slash_inventory(self, inter: disnake.CommandInteraction):
        """
        Parent Command
        """
        pass

    @slash_inventory.sub_command(name="view", description="View your inventory")
    async def slash_inventory_view(self, inter: disnake.CommandInteraction):
        await inter.response.defer()
        embed, view = await inventory_view(inter.author)
        if view:
            await inter.edit_original_message(embed=embed, view=view)
        else:
            await inter.edit_original_message(embed=embed)

    @slash_inventory.sub_command_group(name="chests")
    async def slash_inventory_chests(self, inter: disnake.CommandInteraction):
        """
        Parent Command
        """
        pass

    @slash_inventory_chests.sub_command(name="open", description="Open your chest(s)")
    async def slash_inventory_chests_open(self,
                                          inter: disnake.CommandInteraction,
                                          item_id: str = commands.Param(name="item_id", description="the chest identifier"),
                                          quantity: int = commands.Param(name="quantity", description="the number of chests to open", default=1, gt=0)):
        await inter.response.defer()

        compendium: ItemCompendium = ItemCompendium()
        item_definition: Optional[ItemDefinition] = compendium.get(item_id)
        if item_definition is None:
            embed = BasicEmbeds.item_not_found()
            await inter.edit_original_message(embed=embed)
            return

        inventory_check: bool = await consume_chests(inter.author, item_id, quantity)
        if not inventory_check:
            await inter.edit_original_message(embed=BasicEmbeds.not_enough_item(item_id, "quest"))
            return

        chest_definition: ChestDefinition = cast(ChestDefinition, item_definition)
        chest_loot: Loot = ChestLootConfig().loot(chest_type=chest_definition.loot_type, rank=chest_definition.loot_rank, tier=chest_definition.loot_tier)

        loot: dict[str, int] = chest_loot.roll(quantity)

        rooster: PlayerRoster = PlayerRoster()
        player: Player = rooster.get(inter.author.id)
        async with player:
            await player.acquire_loot(loot)

        embed = BasicEmbeds.empty_embed()
        embed.description = f"**Successfully Opened {item_definition.name} x{quantity} times. You got:**\n{compendium.describe_dict(loot)}"

        await inter.edit_original_message(embed=embed)

    @slash_inventory_chests.sub_command(name="view", description="View your chests")
    async def slash_inventory_chests_view(self, inter: disnake.CommandInteraction):
        await inter.response.defer()
        embed, view = await chests_view(inter.author)
        if embed:
            if view:
                await inter.edit_original_message(embed=embed, view=view)
            else:
                await inter.edit_original_message(embed=embed)
        else:
            await inter.send("You don't own any chest", ephemeral=True)

    @slash_inventory.sub_command(name="search", description="Search an item in all your inventory")
    async def slash_inventory_search(self,
                                     inter: disnake.CommandInteraction,
                                     full_id: str = commands.Param(name="item_id", autocomplete=autocomplete_item_id),
                                     quantity: int = commands.Param(name="quantity", default=1, gt=0)):
        await inter.response.defer()
        item_id, unique_id = convert_id(full_id)

        compendium: ItemCompendium = ItemCompendium()
        item: ItemDefinition = compendium.get(item_id)
        if item is None:
            embed = BasicEmbeds.item_not_found()
            await inter.edit_original_message(embed=embed)
            return

        embed = BasicEmbeds.empty_embed()
        embed.title = f"Searching all inventories... for {item.name}"
        await inter.edit_original_message(embed=embed)

        all_rings = await get_user_all_rings_id(inter.author.id)

        ring_ids_with_item = await give_multiple_ring_inv(all_rings)

        ring_amount = []
        for ring_id, ring_item_dict in ring_ids_with_item.items():

            if item_id in ring_item_dict.keys():
                if quantity <= ring_item_dict[item_id]:
                    ring_amount.append((ring_id, ring_item_dict[item_id]))

        base_amount = await Inventory.filter(item_id=item_id, unique_id=unique_id, user_id=inter.author.id).values_list("count", flat=True)

        embed = BasicEmbeds.empty_embed()
        embed.title = "Search Complete!"
        embed.description = f"{TICK} Found **{len(ring_amount)}** ring(s)"

        if len(base_amount) >= quantity:
            embed.description += " and base inventory"

        embed.description += f" with at least `{quantity}` amount of {item.name}."

        if len(ring_amount) > 0:
            embed.description += f"\n\n{PLUS} **All Rings-**"
            for r, i in ring_amount:
                embed.description += f"\n- Ring **`{r}`** have `{i}x` {ITEM_EMOJIS.get(item_id, '')}{item.name}"

        if len(base_amount) >= quantity:
            embed.description += f"\n\n{PLUS} **Base Inventory-**"
            embed.description += f"\n- have `{base_amount[0]}x` {ITEM_EMOJIS.get(item_id, '')}{item.name}"

        if len(ring_amount) < 1 and len(base_amount) < 1:
            embed.description = f"{EXCLAMATION} Item not found \nYou dont possess enough of this item in any of your inventories/rings."
        embed.set_footer(text=f"Searched by {inter.author.name}")
        await inter.edit_original_message(embed=embed)

    @commands.slash_command(name="energy", description="Show your energy")
    async def slash_energy(self, inter: disnake.CommandInteraction, member: disnake.Member = None):
        player: Player = PlayerRoster().find_player_for(inter, member)
        if player is None:
            # Requested energy of an unknown member
            await inter.response.send_message("You could nod find any information about this cultivator")
        else:
            energy: int = player.energy
            max_energy: int = player.maximum_energy

            energy_str: str = f"Energy : `{energy:,}`/{max_energy:,}"
            if energy < max_energy:
                missing: int = max_energy - energy
                time_to_full: int = missing * ENERGY_RECOVERY_RATE_MINUTES if missing > 0 else 0
                energy_str += f"\nTime till full: {time_to_full} minute(s)"

            embed = disnake.Embed(description=energy_str, color=disnake.Color(0x2e3135))
            await inter.response.send_message(embed=embed)

    @commands.slash_command(name="shop", description="Open up shop menu")
    async def slash_shop(self, inter: disnake.CommandInteraction):
        embed, view = await shop_view(inter.author)
        await inter.response.send_message(embed=embed, view=view)

    @commands.slash_command(name="swallow", description="Swallow a flame")
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def slash_swallow(self, inter: disnake.CommandInteraction,
                            flame_id: str = commands.Param(name="flame_id", description="Type the flame id to use it")):
        compendium: ItemCompendium = ItemCompendium()
        item: Optional[ItemDefinition] = compendium.get(flame_id)
        if item is None or not isinstance(item, FlameDefinition):
            embed = BasicEmbeds.item_not_found()
            await inter.response.send_message(embed=embed)
            return

        player: Player = PlayerRoster().find_player_for(inter)
        cultivation: PlayerCultivationStage = player.cultivation

        item_check = await check_item_in_inv(inter.author.id, flame_id)
        if not item_check:
            embed = BasicEmbeds.not_enough_item("beast")
            await inter.response.send_message(embed=embed)
            return

        from utils.DatabaseUtils import compute_pill_bonus
        _, swallow_bonus, _, _ = await compute_pill_bonus(user_id=inter.author.id, flame_remove=True)

        if isinstance(item, BeastFlameDefinition):
            flame: BeastFlameDefinition = cast(BeastFlameDefinition, item)
            flame_chance = _BASE_FLAME_CHANCE + (cultivation.major - flame.tier) * 20 + swallow_bonus

            if flame_chance > 100:
                flame_chance = 100
            if flame_chance < 0:
                flame_chance = 0

            if random.randint(1, 100) <= flame_chance:
                content = f"You have successfully swallowed the flame! ({flame_chance}% chance)\nFlame updated to {flame.name}"
                await Alchemy.filter(user_id=inter.author.id).update(flame=flame_id)
                embed = BasicEmbeds.right_tick(content)
                log_event(inter.author.id, "flame", f"Swallowed {flame.name} ({flame_chance}%)")
            else:
                content = f"You were heavily injured after failing to swallow {flame.name} and lost 2 sub-levels of cultivation. ({flame_chance}% chance)"

                async with player:
                    await player.change_realm(2, "demote", inter.guild)
                embed = BasicEmbeds.exclamation(content)
                log_event(inter.author.id, "flame", f"Failed to swallow {flame.name}, Level decreased by 2", "WARN")

            await remove_from_inventory(inter.author.id, flame_id, 1)

            await inter.response.send_message(embed=embed)

        if isinstance(item, HeavenlyFlameDefinition):
            flame: HeavenlyFlameDefinition = cast(HeavenlyFlameDefinition, item)
            if cultivation.major < 11:
                alt_major = cultivation.major
            elif cultivation.major == 11:
                alt_major = 11 if 0 <= cultivation.minor <= 14 else 12
            else:
                alt_major = cultivation.major + 1

            flame_ref_alt_major = flame.absorption_difficulty

            flame_chance = _BASE_FLAME_CHANCE + (alt_major - flame_ref_alt_major) * 15 + swallow_bonus

            if flame_chance > 100:
                flame_chance = 100
            elif flame_chance < 0:
                flame_chance = 0

            if random.randint(1, 100) <= flame_chance:
                content = f"You have successfully swallowed the flame! ({flame_chance}% chance)\nFlame updated to {flame.name}"
                await Alchemy.filter(user_id=inter.author.id).update(flame=flame_id)
                embed = BasicEmbeds.right_tick(content)
                log_event(inter.author.id, "flame", f"Swallowed {flame.name} ({flame_chance}%)")
            else:
                content = f"You were heavily injured after failing to swallow {flame.name} and lost 9 sub-levels of cultivation. ({flame_chance}% chance)"
                async with player:
                    await player.change_realm(9, "demote", inter.guild)

                embed = BasicEmbeds.exclamation(content)
                log_event(inter.author.id, "flame", f"Failed to swallow {flame.name}, Level decreased by 9", "WARN")

            await remove_from_inventory(inter.author.id, flame_id, 1)

            await inter.response.send_message(embed=embed)

    @commands.slash_command(name="exchange", description="Exchange one item for another of equivalent tier (currently only works for eggs)")
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def slash_exchange(self,
                             inter: disnake.CommandInteraction,
                             item_id: str = commands.Param(name="item_id", description="Item ID of egg to exchange for beast drop of equivalent tier"),
                             exchanged_item_id: str = commands.Param(name="exchanged_item_id", description="Item ID of beast drop of equivalent tier"),
                             quantity: int = commands.Param(name="quantity", description="Amount of eggs you want to exchange", default=1, ge=1)):

        await inter.response.defer()
        compendium: ItemCompendium = ItemCompendium()
        egg: Optional[ItemDefinition] = compendium.get(item_id)
        if egg is None:  # Check if item ID is valid
            embed = BasicEmbeds.item_not_found()
            await inter.edit_original_message(embed=embed)
            return

        if not isinstance(egg, EggDefinition):  # Check if item is egg
            embed = BasicEmbeds.exclamation(f"Make sure the item ID is correct. You can only exchange eggs.")
            await inter.edit_original_message(embed=embed)
            return

        target_item: ItemDefinition = compendium.get(exchanged_item_id)
        if target_item is None:  # Check if exchanged item ID is valid
            embed = BasicEmbeds.exclamation(
                f"Make sure the exchanged item ID is correct. It must be a non-egg `/beast hunt` drop of equivalent tier.")
            await inter.edit_original_message(embed=embed)
            return

        item_check = await check_item_in_inv(inter.author.id, item_id, quantity)
        if not item_check:  # Check if item in inventory
            embed = BasicEmbeds.not_enough_item(item_id, "beast")
            await inter.edit_original_message(embed=embed)
            return

        if (target_item.type not in ["monster", "core"]) or target_item.tier != egg.tier:  # Check if exchanged item is equivalent beast drop
            embed = BasicEmbeds.exclamation(
                f"Make sure the exchanged item ID is correct. It must be a non-egg `/beast hunt` drop of equivalent tier.")
            await inter.edit_original_message(embed=embed)
            return

        # Exchange for a beast drop of equivalent tier (not including other eggs

        ring_id: int = await get_equipped_ring_id(inter.author.id)
        if egg.weight < target_item.weight:  # Technically shouldn't happen
            weight_diff = target_item.weight - egg.weight
            continue_check, _, _ = await check_inv_weight(inter.channel, inter.author.id, exchanged_item_id, quantity,
                                                          ring_id=ring_id,
                                                          confirm_text=f"Make sure you have at least {weight_diff}wt worth of free space in your inventory/ring. You may lose some of the items. Continue?")
            if not continue_check:
                embed = BasicEmbeds.cmd_not_continued()
                await inter.edit_original_message(embed=embed)
                return

        log_event(inter.author.id, "exchange", f"Exchanged {quantity}x {item_id} for {exchanged_item_id}")

        await remove_from_inventory(inter.author.id, item_id, quantity, ring_id)
        await add_to_inventory(inter.author.id, exchanged_item_id, quantity, ring_id)  # Potentially sus

        embed = BasicEmbeds.right_tick(
            f"You exchanged {egg.name} (`{item_id}`) for `{quantity}x` {target_item.name} (`{exchanged_item_id}`).")
        await inter.edit_original_message(embed=embed)

    @commands.slash_command(name="combine", description="Combine eggs to get a higher tier egg")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def slash_combine(self,
                            inter: disnake.CommandInteraction,
                            egg_id: str = commands.Param(name="egg_id", description="Item ID of egg to combine"),
                            times: int = commands.Param(name="times", description="How many times you want to combine (1 times cost 10x eggs and 20x eggs to get tier 8)", default=1, ge=1)):
        await inter.response.defer()

        compendium: ItemCompendium = ItemCompendium()
        egg: Optional[ItemDefinition] = compendium.get(egg_id)
        if egg is None:  # Check if item ID is valid
            await inter.edit_original_message(embed=BasicEmbeds.item_not_found())
            return

        if not isinstance(egg, EggDefinition):  # Check if item is egg
            await inter.edit_original_message(embed=BasicEmbeds.exclamation(f"Make sure the item ID is correct. You can only exchange eggs."))
            return

        if egg.tier == 8:
            await inter.edit_original_message(embed=BasicEmbeds.exclamation(f"You cant combine R{egg.tier} eggs"))
            return

        if egg.tier == 7:
            amount = times * 20
        else:
            amount = times * 10

        item_check = await check_item_in_inv(inter.author.id, egg_id, amount)
        if not item_check:  # Check if item in inventory
            await inter.edit_original_message(embed=BasicEmbeds.not_enough_item(egg_id, "beast"))
            return

        await remove_from_inventory(inter.author.id, egg_id, amount)

        combined_eggs = {}
        higher_tier = egg.tier + 1
        higher_tier_eggs: list[ItemDefinition] = compendium.filter(tier=higher_tier, item_type="egg")
        ring_id = await get_equipped_ring_id(inter.author.id)

        for i in range(times):
            high_egg: ItemDefinition = random.choice(higher_tier_eggs)
            e_amount = 1
            if random.randint(1, 100) < 10:
                e_amount = 2

            await add_to_inventory(inter.author.id, high_egg.id, e_amount, ring_id)

            if high_egg.name not in combined_eggs.keys():
                combined_eggs[high_egg.name] = 0

            combined_eggs[high_egg.name] += e_amount

        egg_str = "\n- ".join(f"{PLUS} {i}x {e}" for e, i in combined_eggs.items())
        log_event(inter.author.id, "combine",
                  f"Combined {egg_id} {times} times (total amount of {amount}) and got {combined_eggs}")

        embed = BasicEmbeds.right_tick(
            f"You combined {egg.name} `{times}` times (used {amount}x eggs) and got \n{egg_str}")
        await inter.edit_original_message(embed=embed)


async def consume_chests(author: disnake.User, item_id: str, quantity: int) -> bool:
    consumed_row_count = await Inventory.filter(user_id=author.id, item_id=item_id, count__gte=quantity).update(count=F("count") - quantity)
    return consumed_row_count > 0


async def get_all_chest(author) -> dict[str, int]:
    base_inventory = await Inventory.filter(user_id=author.id, item__type=ITEM_TYPE_CHEST).order_by("item__tier").values_list("count", "item__id")

    full_inv: dict[str, int] = {}
    for count, item_id in base_inventory:
        if item_id not in full_inv.keys():
            full_inv[item_id] = count
        else:
            full_inv[item_id] += count

    return full_inv


async def chests_view(author: disnake.Member):
    chest_counts: dict[str, int] = await get_all_chest(author)
    chest_counts: dict[str, int] = {item_id: quantity for item_id, quantity in chest_counts.items() if quantity > 0}
    item_ids: list[str] = list(chest_counts.keys())
    item_ids.sort()

    embeds = []
    item_per_page = 8
    chest_type_count: int = len(item_ids)
    page_count = chest_type_count // item_per_page + 1 if chest_type_count % item_per_page != 0 else 0

    pages = [item_ids[page_index * item_per_page:page_index * item_per_page + item_per_page] for page_index in range(0, page_count)]

    compendium: ItemCompendium = ItemCompendium()

    for chest_page in pages:
        embed = disnake.Embed()
        embed.title = f"{author.name}'s Chests"
        embed.description = f"Showing {len(chest_page)} items"

        for item_id in chest_page:
            chest_count: int = chest_counts[item_id]
            chest: ItemDefinition = compendium.get(item_id)
            embed.add_field(name=f"{chest.name} T{chest.tier}", value=f"> `{chest_count}` left | `{item_id}`")

        if author.avatar:
            embed.set_thumbnail(url=author.avatar.url)

        embeds.append(embed)

    if len(embeds) > 1:
        view = ChestPaginatorView(embeds, author)
    else:
        view = None

    return embeds[0] if len(embeds) > 0 else None, view


class ChestPaginatorView(disnake.ui.View):
    def __init__(self, embeds, author):
        super().__init__(timeout=None)
        self.author = author
        self.embeds = embeds
        self.embed_count = 0

        self.prev_page.disabled = True
        if len(self.embeds) <= 1:
            self.next_page.disabled = True

        for i, embed in enumerate(self.embeds):
            embed.set_footer(text=f"Page {i + 1} of {len(self.embeds)}")

    async def interaction_check(self, inter):
        return inter.author == self.author

    @disnake.ui.button(emoji=LEFT, style=disnake.ButtonStyle.secondary)
    async def prev_page(self, _: disnake.ui.Button, interaction: disnake.MessageInteraction):
        self.embed_count -= 1

        embed = self.embeds[self.embed_count]

        self.next_page.disabled = False
        if self.embed_count == 0:
            self.prev_page.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

    @disnake.ui.button(emoji=RIGHT, style=disnake.ButtonStyle.secondary)
    async def next_page(self, _: disnake.ui.Button, interaction: disnake.MessageInteraction):
        self.embed_count += 1
        embed = self.embeds[self.embed_count]

        self.prev_page.disabled = False
        if self.embed_count == len(self.embeds) - 1:
            self.next_page.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)


def _log(user_id: Union[int, str], message: str, level: str = "INFO"):
    log_event(user_id, _SHORT_NAME, message, level)


# The bootstrap code
def setup(bot: commands.Bot):
    cog = PlayerCog(bot)
    bot.add_cog(cog)
    _log("system", f"{cog.name} Created")

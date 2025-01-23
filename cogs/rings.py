from typing import cast

import disnake

from disnake.ext import commands

from utils.InventoryUtils import add_to_inventory, get_equipped_ring_id, give_custom_ring_inv, remove_from_inventory, convert_id, give_combined_inv, add_ring_to_inventory, check_item_in_inv, check_inv_weight
from utils.Embeds import BasicEmbeds
from utils.Database import AllRings, Users
from utils.LoggingUtils import log_event
from utils.Styles import EXCLAMATION
from world.compendium import ItemCompendium, GeneralStorageRingDefinition


async def equip_ring(user_id, unique_ring_id):
    equipped = await Users.get_or_none(user_id=user_id).values_list("equipped", flat=True)
    previous_ring = equipped.get("ring", None)
    equipped["ring"] = unique_ring_id

    await Users.filter(user_id=user_id).update(equipped=equipped)
    return previous_ring


class Rings(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(name="ring", description="Parent Command")
    async def slash_ring(self, inter: disnake.CommandInteraction):
        """
        Parent Command
        """
        pass

    @slash_ring.sub_command(name="transfer", description="Transfer an items from one ring to another")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def slash_ring_transfer(self,
                                  inter: disnake.CommandInteraction,
                                  from_ring_full_id: str = commands.Param(name="from_ring_id", description="Ring id of the ring to move item from (with unique id)"),
                                  to_ring_full_id: str = commands.Param(name="to_ring_id", description="Ring id of the ring to move item to (with unique id)"),
                                  item_type: str = commands.Param(name="item_id", description="id of the item transfer (all for all items)"),
                                  quantity: int = commands.Param(0, ge=0, name="quantity", description="the number of the item you want to transfer (0 for all items)")):
        await inter.response.defer()

        compendium: ItemCompendium = ItemCompendium()

        item_id, unique_id = convert_id(item_type)
        transfer_all: bool = item_type == "all"
        if not transfer_all:
            if item_id not in compendium:
                await inter.edit_original_message(embed=BasicEmbeds.item_not_found())
                return

        from_item_id, from_unique_id_str = convert_id(from_ring_full_id)
        if from_unique_id_str is None or not from_unique_id_str.isdigit():
            await inter.edit_original_message(embed=BasicEmbeds.wrong_unique_id())
            return

        to_item_id, to_unique_id_str = convert_id(to_ring_full_id)
        if to_unique_id_str is None or not to_unique_id_str.isdigit():
            await inter.edit_original_message(embed=BasicEmbeds.wrong_unique_id())
            return

        from_unique_id: int = int(from_unique_id_str)
        to_unique_id: int = int(to_unique_id_str)

        all_inv_items: dict[str, int] = await give_combined_inv(inter.author.id)

        ring_id: int = await get_equipped_ring_id(inter.author.id)
        all_inv_items[f"mring/{ring_id}"] = 1
        all_inv_items[f"hring/{ring_id}"] = 1
        all_inv_items[f"lring/{ring_id}"] = 1

        if all_inv_items.get(from_ring_full_id, 0) != 1:
            embed = BasicEmbeds.not_enough_item(from_ring_full_id, "craft")
            await inter.edit_original_message(embed=embed)
            return

        if all_inv_items.get(to_ring_full_id, 0) != 1:
            await inter.edit_original_message(embed=BasicEmbeds.not_enough_item(to_ring_full_id, "craft"))
            return

        from_ring_inv: dict[str, int] = await give_custom_ring_inv(from_unique_id)
        if transfer_all:
            to_ring_inv: dict[str, int] = await give_custom_ring_inv(to_unique_id)
            embed = await _transfer_all_items(inter.author.id, (from_ring_full_id, from_ring_inv), (to_ring_full_id, to_ring_inv), compendium)
        else:
            if quantity == 0:
                if not unique_id:
                    if item_id in from_ring_inv.keys():
                        quantity = from_ring_inv[item_id]
                else:
                    quantity = 1

            item_check = await check_item_in_inv(inter.author.id, item_type, quantity, from_ring_inv)
            if item_check:
                continue_check, _, add_check = await check_inv_weight(inter.channel, inter.author.id, item_type, quantity, to_unique_id, only_ring=True)
                if not continue_check or not add_check:
                    embed = BasicEmbeds.cmd_not_continued()
                    await inter.edit_original_message(embed=embed)
                    return

                await add_to_inventory(inter.author.id, item_type, quantity, to_unique_id, add_check)
                await remove_from_inventory(inter.author.id, item_type, quantity, from_unique_id)
                log_event(inter.author.id, "ring", f"Transferred {quantity}x {item_type} from {from_ring_full_id} to {to_ring_full_id}")
                embed = BasicEmbeds.right_tick(f"Successfully transferred {quantity}x {item_type} from ring `{from_ring_full_id}` to ring `{to_ring_full_id}`")
            else:
                embed = BasicEmbeds.not_enough_item(item_type)

        await inter.edit_original_message(embed=embed)

    @slash_ring.sub_command(name="equip", description="Equip one of your owned ring")
    async def equip(self, inter: disnake.CommandInteraction, ring_full_id: str = commands.Param(name="ring_id", description="Ring id (with unique id) you want to equip")):
        await inter.response.defer()

        ring_id, unique_id = convert_id(ring_full_id)
        if unique_id is None or not unique_id.isdigit():
            embed = BasicEmbeds.wrong_unique_id()
            await inter.edit_original_message(embed=embed)
            return

        ring_details = await AllRings.get_or_none(id=unique_id).values_list("ring", flat=True)
        if ring_details is None or ring_id != ring_details:
            embed = BasicEmbeds.item_not_found()
            await inter.edit_original_message(embed=embed)
            return

        ring_check = await check_item_in_inv(inter.author.id, ring_full_id, 1)
        if ring_check is False:
            equip_ring_id = await get_equipped_ring_id(inter.author.id)
            if unique_id == equip_ring_id:
                embed = BasicEmbeds.exclamation(content="This ring is already equipped")
            else:
                embed = BasicEmbeds.not_enough_item(ring_full_id, "craft")
            await inter.edit_original_message(embed=embed)
            return

        previous_ring = await equip_ring(inter.author.id, unique_id)
        log_event(inter.author.id, "ring", f"Equipped {ring_full_id}")
        await remove_from_inventory(inter.author.id, ring_full_id, 1)

        if previous_ring is not None:
            ring_details = await AllRings.get_or_none(id=previous_ring).values_list("ring", flat=True)
            log_event(inter.author.id, "ring", f"Unequipped {ring_details}/{previous_ring}")
            await add_ring_to_inventory(inter.author.id, ring_details, previous_ring, True)

        embed = BasicEmbeds.right_tick(f"Successfully equipped `{ring_full_id}`")
        await inter.edit_original_message(embed=embed)


async def _transfer_all_items(author_id: int, from_ring: tuple[str, dict[str, int]], to_ring: tuple[str, dict[str, int]], compendium: ItemCompendium) -> disnake.Embed:
    from_ring_full_id, from_ring_inventory = from_ring
    _, from_ring_unique_id_str = convert_id(from_ring_full_id)
    from_ring_unique_id: int = int(from_ring_unique_id_str)

    to_ring_full_id, to_ring_inventory = to_ring
    to_ring_item_id, to_ring_unique_id_str = convert_id(to_ring_full_id)
    to_ring_unique_id: int = int(to_ring_unique_id_str)

    initial_weight: int = compendium.compute_weight(to_ring_inventory)
    weight_capacity: int = cast(GeneralStorageRingDefinition, compendium[to_ring_item_id]).weight_capacity

    extra_weight: int = compendium.compute_weight(from_ring_inventory)
    target_weight: int = initial_weight + extra_weight
    if target_weight > weight_capacity:
        return disnake.Embed(description=f"{EXCLAMATION} Target ring {to_ring_full_id} is missing {target_weight - weight_capacity} weight capacity to contain all the items from {from_ring_full_id}.",
                             color=disnake.Color(0x2e3135))

    for item_id, quantity in from_ring_inventory.items():
        await add_to_inventory(author_id, item_id, quantity, to_ring_unique_id)
        await remove_from_inventory(author_id, item_id, quantity, from_ring_unique_id)
        log_event(author_id, "ring", f"Transferred {quantity}x {item_id} from {from_ring_full_id} to {to_ring_full_id}")

    return BasicEmbeds.right_tick(f"Successfully transferred all items from ring `{from_ring_full_id}` to ring `{to_ring_full_id}`")


def setup(bot):
    bot.add_cog(Rings(bot))
    print("[Rings] Loaded")

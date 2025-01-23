from typing import Optional

import disnake

from collections import defaultdict
from tortoise.expressions import F

from utils.Database import Inventory, AllItems, Market, Users, AllRings, RingInventory
from utils.LoggingUtils import log_event
from utils.Styles import RIGHT, LEFT, ITEM_EMOJIS, EXCLAMATION, CROSS, TICK


BASE_WEIGHT = 80

# Should be moved to items.py once the other classes use the latter instead of this module
ITEM_TYPE_BEAST_FLAME = "b_flame"
ITEM_TYPE_CAULDRON = "cauldron"
ITEM_TYPE_CHEST = "chest"
ITEM_TYPE_EGG = "egg"
ITEM_TYPE_FIGHT_TECHNIQUE_MANUAL = "fight_technique"
ITEM_TYPE_HEAVENLY_FLAME = "h_flame"
ITEM_TYPE_HERB = "alchemy"
ITEM_TYPE_MAP_FRAGMENT = "map_fragment"
ITEM_TYPE_MISCELLANEOUS = "misc"
ITEM_TYPE_MONSTER_CORE = "core"
ITEM_TYPE_MONSTER_PART = "monster"
ITEM_TYPE_ORIGIN_QI = "originqi"
ITEM_TYPE_PILL = "pill"
ITEM_TYPE_QI_FLAME = "qi_flame"
ITEM_TYPE_QI_METHOD_MANUAL = "qi_method"
ITEM_TYPE_RING = "ring"
ITEM_TYPE_VALUABLE = "sellable"
ITEM_TYPE_WEAPON = "weapon"

_RING_ITEM_CODES = {"lring", "mring", "hring", "accept_stone"}


class ConfirmDelete(disnake.ui.View):
    def __init__(self, author_id, erase_after: bool = False):
        super().__init__(timeout=60)
        self.author_id = author_id
        self._erase_after: bool = erase_after
        self.confirm = False

    async def interaction_check(self, inter):
        return inter.author.id == self.author_id

    @disnake.ui.button(emoji=TICK, style=disnake.ButtonStyle.secondary)
    async def confirm_button(self, _: disnake.ui.Button, interaction: disnake.MessageInteraction):
        self.confirm = True
        self.clear_items()

        if self._erase_after:
            await interaction.message.delete()
        else:
            await interaction.response.edit_message(f"Confirmed {TICK}", view=self)

        self.stop()

    @disnake.ui.button(emoji=CROSS, style=disnake.ButtonStyle.secondary)
    async def rejection_button(self, _: disnake.ui.Button, interaction: disnake.MessageInteraction):
        self.confirm = False
        self.clear_items()

        if self._erase_after:
            await interaction.message.delete()
        else:
            await interaction.response.edit_message(f"Rejected {CROSS}", view=self)

        self.stop()

    async def on_timeout(self):
        self.clear_items()
        self.stop()


class InventoryTypeDropdown(disnake.ui.Select):

    def __init__(self, inv_type_list: list):
        self.inv_type_list = inv_type_list
        options = [
            *(disnake.SelectOption(label=f"{name.capitalize()}", value=f"{name}") for name in inv_type_list[:24]),
        ]

        super().__init__(
            # custom_id=f"pill_{round(time(), 3)}",
            placeholder="Choose Inventory Type",
            max_values=1,
            options=options
        )

    async def callback(self, inter):
        embed, view = await inventory_view(inter.author, inv_type=inter.values[0])
        await inter.response.edit_message(embed=embed, view=view)


class InventoryMenu(disnake.ui.View):
    def __init__(self, inv_embeds, ring_embeds, stone_embeds, author, inv_list):
        super().__init__(timeout=None)
        self.inv_embeds = inv_embeds
        self.ring_embeds = ring_embeds
        self.stone_embeds = stone_embeds
        self.author = author

        self.embeds = inv_embeds
        self.embed_count = 0

        self.prev_page.disabled = True
        if len(self.embeds) <= 1:
            self.next_page.disabled = True

        for i, embed in enumerate(self.inv_embeds):
            embed.set_footer(text=f"Page {i + 1} of {len(self.inv_embeds)}")

        for i, embed in enumerate(self.ring_embeds):
            embed.set_footer(text=f"Page {i + 1} of {len(self.ring_embeds)}")

        for i, embed in enumerate(self.stone_embeds):
            embed.set_footer(text=f"Page {i + 1} of {len(self.stone_embeds)}")

        if len(ring_embeds) < 1:
            self.inv_ring_switch.label = "No ring equipped"
            self.inv_ring_switch.disabled = True

        if len(stone_embeds) < 1:
            self.stone_switch.label = "Nothing"
            self.stone_switch.disabled = True

        self.add_item(InventoryTypeDropdown(inv_list))

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

    @disnake.ui.button(label="to Ring", style=disnake.ButtonStyle.blurple)
    async def inv_ring_switch(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        if self.embeds == self.inv_embeds:
            self.embeds = self.ring_embeds
            button.label = "to Base"
            button.style = disnake.ButtonStyle.green
        else:
            self.embeds = self.inv_embeds
            button.label = "to Ring"
            button.style = disnake.ButtonStyle.blurple
            self.stone_switch.style = disnake.ButtonStyle.grey
            self.stone_switch.disabled = False

        self.embed_count = 0

        self.prev_page.disabled = True
        self.next_page.disabled = False
        if len(self.embeds) <= 1:
            self.next_page.disabled = True

        embed = self.embeds[self.embed_count]
        await interaction.response.edit_message(embed=embed, view=self)

    @disnake.ui.button(label="Accept Stone", style=disnake.ButtonStyle.grey)
    async def stone_switch(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        self.embeds = self.stone_embeds
        self.inv_ring_switch.label = "to Base"
        self.inv_ring_switch.style = disnake.ButtonStyle.grey
        button.style = disnake.ButtonStyle.green
        button.disabled = True
        self.embed_count = 0

        self.prev_page.disabled = True
        self.next_page.disabled = False
        if len(self.embeds) <= 1:
            self.next_page.disabled = True

        embed = self.embeds[self.embed_count]
        await interaction.response.edit_message(embed=embed, view=self)


async def get_ring_inv_embeds(author, ringid, item_weight, ring_capacity, inv_type=None):
    if inv_type and inv_type != "clear":
        data = await RingInventory.filter(ring_id=ringid, item__type=inv_type).order_by("item__type", "item__tier").values_list("count", "item__name", "item__id", "item__type", "item__weight", "unique_id", "item__tier")
    else:
        data = await RingInventory.filter(ring_id=ringid).order_by("item__type", "item__tier").values_list("count", "item__name", "item__id", "item__type", "item__weight", "unique_id", "item__tier")

    embeds = []
    max_items = 5
    items_list = [data[i:i + max_items] for i in range(0, len(data), max_items)]

    for items in items_list:
        embed = disnake.Embed(
            title=f"{author.name}'s Ring",
            description=f"ID: **`{ringid}`** \nWeight: **`{item_weight}/{ring_capacity}`**",
            color=disnake.Color(0x5c9af7)
        )
        if author.avatar:
            embed.set_thumbnail(url=author.avatar.url)

        if inv_type and inv_type != "clear":
            embed.description = f"**Sort Type: `{inv_type}`** \nID: **`{ringid}`** \nWeight: **`{item_weight}/{ring_capacity}`**"

        for item in items:
            count, name, _id, _type, weight, unique_id, item_rank = item
            total_weight = abs(int(weight * count))

            emoji = ITEM_EMOJIS.get(_id)
            if not emoji:
                emoji = ""

            full_id = _id
            if unique_id:
                full_id = f"{_id}/{unique_id}"

            embed.add_field(name="\u200b", value=f"**`{count}` x {emoji} {name}** \n> ID: `{full_id}` | Type: `{_type.capitalize()}` \n>  Rank: `{item_rank}` |  Weight: `{total_weight}`", inline=False)
        embed.set_footer(text="Page 1")
        embeds.append(embed)

    if len(embeds) < 1:
        embed = disnake.Embed(
            title=f"{author.name}'s Ring",
            description=f"ID: **`{ringid}`** \nWeight: **`{item_weight}/{ring_capacity}`** \n\n**Empty**",
            color=disnake.Color(0x5c9af7)
        )
        if author.avatar:
            embed.set_thumbnail(url=author.avatar.url)

        if inv_type and inv_type != "clear":
            embed.description = f"Weight: **`{item_weight}/{ring_capacity}`** \n\n**{EXCLAMATION} No item found with type `{inv_type}`**"

        embeds.append(embed)

    return embeds


async def get_base_inv_embeds(author, item_weight, inv_type=None):
    if inv_type and inv_type != "clear":
        data = await Inventory.filter(user_id=author.id, item__type=inv_type).order_by("item__type", "item__tier").values_list("count", "item__name", "item__id", "item__type", "item__weight", "unique_id", "item__tier")
    else:
        data = await Inventory.filter(user_id=author.id, item__type__not="chest").order_by("item__type", "item__tier").values_list("count", "item__name", "item__id", "item__type", "item__weight", "unique_id", "item__tier")
    
    all_ring_ids = [item[5] for item in data if item[3] == "ring"]
    all_rings_item = await AllRings.filter(id__in=all_ring_ids).values_list("id", "items__item_id", "items__count")

    ring_items_dict = defaultdict(list)
    for ring in all_rings_item:
        ring_items_dict[ring[0]].append((ring[2], ring[1]))

    embeds = []
    max_items = 5
    items_list = [data[i:i + max_items] for i in range(0, len(data), max_items)]
    for items in items_list:
        embed = disnake.Embed(
            title=f"{author.name}'s Inventory",
            description=f"Weight: **`{item_weight}/80`**",
            color=disnake.Color(0x2cde70)
        )
        if author.avatar:
            embed.set_thumbnail(url=author.avatar.url)

        if inv_type and inv_type != "clear":
            embed.description = f"**Sort Type: `{inv_type}`** \nWeight: **`{item_weight}/80`**"

        for item in items:
            count, name, _id, _type, weight, unique_id, item_rank = item
            total_weight = abs(int(weight * count))

            ring_items_str = None
            if _type == "ring":
                ring_items = ring_items_dict[unique_id]
                if len(ring_items) > 0:
                    ring_items_str = ", ".join(f"`{c}x {i}`" for c, i in ring_items)
                else:
                    ring_items_str = "No Items"

            emoji = ITEM_EMOJIS.get(_id)
            if not emoji:
                emoji = ""

            full_id = _id
            if unique_id:
                full_id = f"{_id}/{unique_id}"

            if ring_items_str:
                embed.add_field(name="\u200b", value=f"**`{count}` x {emoji} {name}** \n> ID: `{full_id}` | Weight: `{total_weight}` \n**Items**: {ring_items_str[:170]}", inline=False)
            else:
                embed.add_field(name="\u200b", value=f"**`{count}` x {emoji} {name}** \n> ID: `{full_id}` | Type: `{_type.capitalize()}` \n> Rank: `{item_rank}` | Weight: `{total_weight}`", inline=False)
        embed.set_footer(text="Page 1")
        embeds.append(embed)

    return embeds


async def get_equipped_ring_id(user_id) -> Optional[int]:
    equipped: dict = await Users.get_or_none(user_id=user_id).values_list("equipped", flat=True)
    unique_ring_id: Optional[int] = equipped.get("ring")

    return unique_ring_id


async def get_stone_inv_embeds(author, stone_id):
    embed = disnake.Embed(
        title=f"{author.name}'s Acceptance Stone",
        color=disnake.Color(0x2cde70)
    )
    total_weight = 0

    data = await RingInventory.filter(ring_id=stone_id).values_list("item__name", "item__id", "item__weight", "item__tier")

    for item in data:
        name, _id, weight, item_rank = item

        emoji = ITEM_EMOJIS.get(_id)
        if not emoji:
            emoji = ""

        full_id = _id
        total_weight += weight
        embed.add_field(name="\u200b", value=f"**{emoji} {name}** \n> ID: `{full_id}` | Rank: `{item_rank}` \n>  Weight: `{weight}`", inline=False)

    embed.description = f"ID: **`{stone_id}`** \nWeight: **`{total_weight}/50`**"

    if author.avatar:
        embed.set_thumbnail(url=author.avatar.url)

    return [embed]


async def get_user_all_rings_id(user_id):
    base_items = await Inventory.filter(user_id=user_id).values_list("unique_id", "item__type")
    ring_ids = [item[0] for item in base_items if item[1] == "ring"]
    equip_ring_id = await get_equipped_ring_id(user_id)

    ring_ids.append(equip_ring_id)
    return ring_ids


async def get_item_types_list(user_id):
    final_list = []
    
    base_item_types = await Inventory.filter(user_id=user_id, item__type__not="chest").values_list("item__type", flat=True)

    equip_ring_id = await get_equipped_ring_id(user_id)
    ring_item_types = await RingInventory.filter(ring_id=equip_ring_id, item__type__not="chest").values_list("item__type", flat=True)

    final_list.extend(base_item_types)
    final_list.extend(ring_item_types)
    final_list.append("clear")
    final_list = list(set(final_list))

    return final_list[:24]


async def inventory_view(author: disnake.Member, admin: disnake.Member = None, inv_type=None):
    unique_ring_id = await get_equipped_ring_id(author.id)

    inv_weight, ring_weight, ring_total_weight = await give_total_user_weight(author.id, unique_ring_id)

    if unique_ring_id:
        ring_embeds = await get_ring_inv_embeds(author, unique_ring_id, ring_weight, ring_total_weight, inv_type)
    else:
        ring_embeds = []

    base_embeds = await get_base_inv_embeds(author, inv_weight, inv_type)

    equipped = await Users.get_or_none(user_id=author.id).values_list("equipped", flat=True)
    previous_stone = equipped.get("stone", None)
    if previous_stone is None:
        stone_embeds = []
    else:
        stone_embeds = await get_stone_inv_embeds(author, previous_stone)

    inv_list = await get_item_types_list(author.id)

    temp_embed = disnake.Embed(
        title=f"{author.name}'s Inventory",
        description=f"Weight: **`{inv_weight}/80`** \n{EXCLAMATION} Empty",
        color=disnake.Color(0x2e3135)
    )
    if author.avatar:
        temp_embed.set_thumbnail(url=author.avatar.url)

    if inv_type:
        temp_embed.description = f"Weight: **`{inv_weight}/80`** \n\n**{EXCLAMATION} No item found with type `{inv_type}`**"

    if len(base_embeds) < 1:
        base_embeds = [temp_embed]

    if admin:
        view = InventoryMenu(base_embeds, ring_embeds, stone_embeds, admin, inv_list)
    else:
        view = InventoryMenu(base_embeds, ring_embeds, stone_embeds, author, inv_list)

    return base_embeds[0], view


async def give_combined_inv(user_id: int) -> dict[str, int]:
    unique_ring_id = await get_equipped_ring_id(user_id)

    ring_data: Optional[list[tuple[int, str, int]]] = None
    if unique_ring_id:
        ring_data: list[tuple[int, str, int]] = await RingInventory.filter(ring_id=unique_ring_id).order_by("item__type").values_list("count", "item_id", "unique_id")

    base_data: list[tuple[int, str, int]] = await Inventory.filter(user_id=user_id).order_by("item__type").values_list("count", "item_id", "unique_id")

    final_dict: dict[str, int] = {}

    for b_count, b_id, b_unique_id in base_data:
        full_id = combine_id(b_id, b_unique_id)
        if full_id not in final_dict.keys():
            final_dict[full_id] = b_count
        else:
            final_dict[full_id] += b_count

    if ring_data:
        for r_count, r_id, r_unique_id in ring_data:
            full_id = combine_id(r_id, r_unique_id)
            if full_id not in final_dict.keys():
                final_dict[full_id] = r_count
            else:
                final_dict[full_id] += r_count

    return final_dict


async def give_custom_ring_inv(ring_id):
    ring_data = await RingInventory.filter(ring_id=ring_id).order_by("item__type").values_list("count", "item_id", "unique_id")

    final_dict = {}
    if ring_data:
        for r_count, r_id, r_unique_id in ring_data:
            full_id = combine_id(r_id, r_unique_id)

            if full_id not in final_dict.keys():
                final_dict[full_id] = 0

            final_dict[full_id] += r_count

    return final_dict


async def give_multiple_ring_inv(ring_id_list):
    ring_data = await RingInventory.filter(ring_id__in=ring_id_list).order_by("item__type").values_list("count", "item_id", "unique_id", "ring_id", "ring__ring")

    big_dict = {}
    if ring_data:
        for r_count, r_id, r_unique_id, user_ring_id, ring_type in ring_data:
            full_id = combine_id(r_id, r_unique_id)
            full_ring_id = combine_id(ring_type, user_ring_id)

            if full_ring_id not in big_dict.keys():
                big_dict[full_ring_id] = {}

            if full_id not in big_dict[full_ring_id].keys():
                big_dict[full_ring_id][full_id] = 0

            big_dict[full_ring_id][full_id] += r_count

    return big_dict


async def mass_check_items(user_id: int, item_dict: dict[str, int], combined_inv=None) -> tuple[bool, str]:
    if not combined_inv:
        combined_inv = await give_combined_inv(user_id)

    content: str = ""
    mat_check: int = 0

    for item_id, item_count in item_dict.items():
        if combined_inv.get(item_id, 0) >= item_count:
            mat_check += 1
            content += f"{ITEM_EMOJIS.get(item_id, '')} **`{combined_inv.get(item_id, 0)}/{item_count}`** | id:`{item_id}` {TICK}\n"
        else:
            content += f"{ITEM_EMOJIS.get(item_id, '')} **`{combined_inv.get(item_id, 0)}/{item_count}`** | id:`{item_id}` {CROSS}\n"

    check = False
    if mat_check == len(item_dict):
        check = True

    return check, content


async def give_total_user_weight(user_id, unique_ring_id: Optional[int] = None):
    inv_weight = 0
    ring_weight = 0
    ring_total_weight = 0

    inv_items = await Inventory.filter(user_id=user_id).values_list("item_id", "item__weight", "count")

    for _id, weight, count in inv_items:
        inv_weight += abs(int(weight * count))

    if unique_ring_id:
        ring_total_weight = await AllRings.get_or_none(id=unique_ring_id).values_list("total_weight", flat=True)
        ring_items = await RingInventory.filter(ring_id=unique_ring_id).values_list("item_id", "item__weight", "count")

        for _id, weight, count in ring_items:
            ring_weight += abs(int(weight * count))
    else:
        ring_weight = 0

    return inv_weight, ring_weight, ring_total_weight


"""async def check_for_weight(user_id, channel):
    unique_ring_id = await get_equipped_ring_id()
    
    current_inv_weight, current_ring_weight, RING_WEIGHT = await give_total_user_weigth(user_id, unique_ring_id)
    
    base_check = False
    ring_check = False
    weight_threshold = 90

    if unique_ring_id:
        percent_filled = (current_ring_weight / (RING_WEIGHT+1)) * 100
        if percent_filled < weight_threshold:
            ring_check = True
            
    percent_filled = (current_inv_weight / BASE_WEIGHT) * 100
    if percent_filled < weight_threshold:
        base_check = True

    if base_check is False and ring_check is False:
        view = ConfirmDelete(user_id)
        await channel.send("Your inventory is almost full, and you may lose this item. Continue?", view=view)
        
        await view.wait()
        return view.confirm

    return True"""


async def add_ring_to_inventory(user_id: int, ringid: str, unique_ring_id: int = None, ignore_weight: bool = False) -> None:
    ring_details = await AllItems.get_or_none(id=ringid).values_list("properties", "weight")
    properties, weight = ring_details
    total_weight = properties["total_weight"]

    current_inv_weight, _, _ = await give_total_user_weight(user_id, unique_ring_id)
    items = await Inventory.filter(user_id=user_id, item__type="ring").values_list("item_id", flat=True)

    if unique_ring_id is None:
        new_ring = await AllRings.create(ring=ringid, total_weight=total_weight)
        unique_ring_id = new_ring.id

    if len(items) > 5:
        if (current_inv_weight + weight) <= BASE_WEIGHT:
            await Inventory.create(item_id=ringid, user_id=user_id, count=1, unique_id=unique_ring_id)
            log_event(user_id, "inventory", f"Added ring ({ringid}/{unique_ring_id}) to inventory")
        elif ignore_weight is True:
            await Inventory.create(item_id=ringid, user_id=user_id, count=1, unique_id=unique_ring_id)
            log_event(user_id, "inventory", f"Added ring ({ringid}/{unique_ring_id}) to inventory (Ignored Weight)")
        else:
            log_event(user_id, "inventory", f"Lost ring ({ringid}/{unique_ring_id})", "WARN")

    else:
        await Inventory.create(item_id=ringid, user_id=user_id, count=1, unique_id=unique_ring_id)
        log_event(user_id, "inventory", f"Added ring ({ringid}/{unique_ring_id}) to inventory (below 5)")


def convert_id(item_id) -> tuple[str, Optional[str]]:
    if "/" in item_id:
        item_id, unique_id, *_ = item_id.split("/")
        return item_id, unique_id
    else:
        return item_id, None


def combine_id(item_id, unique_id) -> str:
    if unique_id is not None:
        full_id = f"{item_id}/{unique_id}"
    else:
        full_id = item_id
    return full_id


async def check_inv_weight(channel, user_id: int, item_id: str, quantity: int = 1, ring_id: Optional[int] = None, only_ring: bool = False,
                           confirm_prompt: bool = True, confirm_text: Optional[str] = None) -> tuple[bool, Optional[int], bool]:
    itemid, _ = convert_id(item_id)

    item_details = await AllItems.get_or_none(id=itemid).values_list("weight", "type")
    item_weight, item_type = item_details
    total_item_weight = int(quantity * int(item_weight))

    if not ring_id:
        ring_id: Optional[int] = await get_equipped_ring_id(user_id)

    current_inv_weight, current_ring_weight, ring_weight = await give_total_user_weight(user_id, ring_id)

    if ring_id is not None:
        if (ring_weight - current_ring_weight) >= total_item_weight:
            return True, ring_id, True

        log_event(user_id, "ring", f"Ring full for {quantity}x {item_id} ({total_item_weight})", "WARN")

    if not only_ring:
        if (BASE_WEIGHT - current_inv_weight) >= total_item_weight or item_type == ITEM_TYPE_RING:
            return True, None, True

        log_event(user_id, "inventory", f"Inv full for {quantity}x {item_id} ({total_item_weight})", "WARN")

    if confirm_prompt:
        view = ConfirmDelete(user_id)
        if confirm_text:
            await channel.send(confirm_text, view=view)
        else:
            await channel.send(f"Your inventory is full, and you may lose this item ({quantity}x {item_id}). Continue?", view=view)

        await view.wait()
        return view.confirm, None, False

    return False, None, False


async def add_to_inventory(user_id: int, itemid: str, amount: int = 1, ring_id: int = None, add_check: bool = True, ignore_ring_weight: bool = True) -> None:
    if not add_check:
        return

    itemid, unique_item_id = convert_id(itemid)

    item_type = await AllItems.get_or_none(id=itemid).values_list("type", flat=True)
    if item_type == ITEM_TYPE_RING:
        await add_ring_to_inventory(user_id, itemid, unique_item_id, ignore_ring_weight)
        return

    if ring_id and item_type != "chest":
        await add_item(user_id, itemid, amount, ring_id, unique_item_id=unique_item_id)
    else:
        await add_item(user_id, itemid, amount, unique_item_id=unique_item_id)


async def add_item(user_id, itemid, amount, ring_id: Optional[int] = None, unique_item_id: Optional[int] = None) -> None:
    if not ring_id:
        item_check = await Inventory.get_or_none(item_id=itemid, user_id=user_id, unique_id=unique_item_id).values_list("count")

        if item_check and unique_item_id is None:
            await Inventory.filter(item_id=itemid, user_id=user_id).update(count=F("count") + amount)
        else:
            await Inventory.create(item_id=itemid, user_id=user_id, count=amount, unique_id=unique_item_id)

        log_event(user_id, "inventory", f"Added {amount}x {itemid}/{unique_item_id}", "DEBUG")

    else:
        item_check = await RingInventory.get_or_none(item_id=itemid, ring_id=ring_id, unique_id=unique_item_id).values_list("count")
        if item_check and unique_item_id is None:
            await RingInventory.filter(item_id=itemid, ring_id=ring_id).update(count=F("count") + amount)
        else:
            await RingInventory.create(item_id=itemid, ring_id=ring_id, count=amount, unique_id=unique_item_id)
        log_event(user_id, "ring", f"Added {amount}x {itemid}/{unique_item_id}", "DEBUG")


async def check_item_in_inv(user_id: int, item_id: str, quantity: int = 1, full_inventory: Optional[dict[str, int]] = None):
    if not full_inventory:
        full_inventory = await give_combined_inv(user_id)

    if item_id in full_inventory.keys():
        if quantity <= full_inventory[item_id]:
            return True

    return False


async def remove_from_inventory(user_id: int, itemid: str, amount: int = 1, ring_id: Optional[int] = None) -> None:
    itemid, unique_item_id = convert_id(itemid)

    if not ring_id:
        ring_id: int = await get_equipped_ring_id(user_id)

    return await remove_item(user_id, itemid, amount, ring_id, unique_item_id=unique_item_id)


async def remove_item(user_id: int, itemid, quantity: int, ring_id: Optional[int] = None, unique_item_id: Optional[int] = None) -> None:
    total_quantity = quantity

    if ring_id:
        ring_item_count = await RingInventory.get_or_none(ring_id=ring_id, item_id=itemid, unique_id=unique_item_id).values_list("count", flat=True)
        if ring_item_count:
            ring_buffer = ring_item_count - total_quantity
            if ring_buffer > 0:
                await RingInventory.filter(ring_id=ring_id, item_id=itemid, unique_id=unique_item_id).update(count=F("count") - total_quantity)
                log_event(user_id, "ring", f"Removed {quantity}x {itemid}/{unique_item_id}")

            elif ring_buffer <= 0:
                await RingInventory.filter(ring_id=ring_id, item_id=itemid, unique_id=unique_item_id).delete()
                log_event(user_id, "ring", f"Removed {quantity}x {itemid}/{unique_item_id}")

            total_quantity -= ring_item_count

    if total_quantity > 0:
        inv_item_count = await Inventory.get_or_none(item_id=itemid, user_id=user_id, unique_id=unique_item_id).values_list("count", flat=True)
        inv_buffer = inv_item_count - total_quantity
        if inv_buffer > 0:
            await Inventory.filter(item_id=itemid, user_id=user_id, unique_id=unique_item_id).update(count=F("count") - total_quantity)
            log_event(user_id, "inventory", f"Removed {quantity}x {itemid}/{unique_item_id}")

        elif inv_buffer == 0:
            await Inventory.filter(item_id=itemid, user_id=user_id, unique_id=unique_item_id).delete()
            log_event(user_id, "inventory", f"Removed {quantity}x {itemid}/{unique_item_id}")


async def check_item_everywhere(item_id) -> bool:
    itemid, unique_item_id = convert_id(item_id)
    base_check = await Inventory.filter(item_id=itemid, unique_id=unique_item_id).values_list("count", flat=True)

    if len(base_check) == 0:
        ring_check = await RingInventory.filter(item_id=itemid, unique_id=unique_item_id).values_list("count", flat=True)

        if len(ring_check) == 0:
            market_check = await Market.filter(item_id=itemid, unique_id=unique_item_id).values_list("amount", flat=True)

            if len(market_check) == 0:
                return True

    return False


def is_ring(item_id: str) -> bool:
    item_code, _ = convert_id(item_id)
    return item_code in _RING_ITEM_CODES

import disnake
import random
import math

from time import time
from typing import Any, Optional
from disnake.ext import commands

from utils.InventoryUtils import add_ring_to_inventory, add_to_inventory, give_combined_inv, remove_from_inventory, convert_id, combine_id, check_inv_weight, check_item_in_inv, mass_check_items, get_equipped_ring_id, give_custom_ring_inv, \
    ITEM_TYPE_CAULDRON, ITEM_TYPE_RING, ITEM_TYPE_WEAPON, ITEM_TYPE_ORIGIN_QI
from utils.Embeds import BasicEmbeds
from utils.Database import Alchemy, AllItems, AllRings, Crafted, Crafting, Users
from utils.Styles import EXCLAMATION, PLUS
from utils.LoggingUtils import log_event
from utils.loot import WeightedChoice
from world.compendium import ItemCompendium, ItemDefinition, CauldronDefinition

PROP_CRAFT = "craft"
PROP_REQUIREMENTS = "requirements"

PROP_CAULDRON_COOLDOWN_REDUCTION = "alchemy_cdr"
PROP_CAULDRON_REFINE_BONUS = "refine_bonus_per_tier_above"

UNSTACKABLE_ITEM_TYPES = [ITEM_TYPE_CAULDRON, ITEM_TYPE_RING, ITEM_TYPE_WEAPON, ITEM_TYPE_ORIGIN_QI]

MIN_DISMANTLE_RECOVERY_PERCENT: int = 20
MAX_DISMANTLE_RECOVERY_PERCENT: int = 30

"""
{
    craft:{
        requirements: {
            item_id : item_count
        },
        exp_given : number
    }
    
}
"""


async def equip_cauldron(user_id, unique_id):
    prev_cauldron = await Alchemy.get_or_none(user_id=user_id).values_list("cauldron", flat=True)

    await Alchemy.filter(user_id=user_id).update(cauldron=unique_id)
    return prev_cauldron


async def check_for_lvl_up(user_id, exp_to_give, user_tier, user_exp):
    lvl_up = False
    # required_exp = round(500 * (12 ** (user_tier - 1)))
    required_exp = get_required_exp(user_tier)

    updated_user_exp = user_exp + exp_to_give
    log_event(user_id, "craft", f"Added {exp_to_give} EXP, total {updated_user_exp} EXP")
    while updated_user_exp >= required_exp:
        user_tier += 1
        updated_user_exp -= required_exp
        lvl_up = True
        required_exp = get_required_exp(user_tier)
        log_event(user_id, "craft", f"Level reached {user_tier}, {updated_user_exp} EXP left")

    await Crafting.filter(user_id=user_id).update(c_lvl=user_tier, c_exp=updated_user_exp)

    return lvl_up, user_tier


async def calculate_mat_exp(mats):
    mat_items = await AllItems.filter(id__in=mats.keys()).values_list("id", "tier")
    exp = 0
    for _id, tier in mat_items:
        count = mats.get(_id, 0)
        exp += count * (tier ** 3)

    return exp


MAX_EXPERIENCE_PER_CRAFTING_LEVEL: int = 200_000


def get_required_exp(user_tier):
    required_exp = 50 + round(user_tier * (2500 * user_tier - 2000))
    if required_exp > MAX_EXPERIENCE_PER_CRAFTING_LEVEL:
        required_exp = MAX_EXPERIENCE_PER_CRAFTING_LEVEL

    return required_exp


def calculate_exp_bonus(user_tier, item_tier):
    amount = item_tier - user_tier
    if amount > 1:
        amount = 1
    if amount < 1:
        amount = 0

    return amount * 2


def check_double_refine(user_tier, item_tier):
    quantity = 1
    chance = abs(user_tier - item_tier)
    if chance < 1:
        chance = 1

    if random.randint(1, 100) <= chance:
        quantity = 2

    return quantity


def check_tier_limit(user_tier, item_tier):
    return (item_tier - user_tier) <= 1


def craft_embed(item_details):
    _id, name, tier, item_type, properties, e_description, requirements, base_exp = item_details

    # ID, tier
    embed = disnake.Embed(
        title=name,
        description=f"(**`{_id}`**) \n\n**Tier : `{tier}`** \n**BaseExp Given : `{base_exp}`**",
        color=disnake.Color(0xe5fe88)
    )

    # Effect
    embed.add_field(name="Effect", value=e_description if e_description else "None", inline=False)

    # Picture
    try:
        path = f"./media/{item_type}/{_id}.png"
        embed.set_thumbnail(file=disnake.File(path))
    except OSError:
        pass

    # Requirements
    embed.add_field(name="Requirements", value=requirements, inline=False)

    return embed


def is_variable_item_type(item_type: str) -> bool:
    """
    Determine if items with the specified item type vary between each others, i.e., they have properties with variable (often random) values

    Parameters
    ----------
    item_type: The item type to test

    Returns
    ----------
    True is items with the specified item type vary between each others, False otherwise
    """
    return item_type in [ITEM_TYPE_CAULDRON, ITEM_TYPE_WEAPON]


async def _generate_unique_item_internal(item_id: str, properties: dict[str, list[int]]) -> str:
    """
    Generate a new unique item from the specified item_id. If the item with the specified item_id is a fungible then this function won't do anything and simply return the item_id

    Parameters
    ----------
    item_id:    The item id to generate a unique instance from
    properties: The crating parameters to enforce, this parameter will have an effect only if the item_id is for a variable item. The actual properties varies depending on the item type
                For cauldron the keys are "alchemy_cdr" and "refine_bonus_per_tier_above" and values should be a list with 2 items: the min value and the max value, in that order

    Returns
    ----------
    The full id of the newly generated item with the specified item_id. If the specified item_id is in fact for a fungible item then the item_id itself is returned
    """
    stats = dict()
    for key, item in properties.items():
        if key != PROP_CRAFT:
            min_value = item[0]
            max_value = item[1]
            stats[key] = min_value if min_value == max_value else random.randint(item[0], item[1])

    new_crafted_item = await Crafted.create(item_id=item_id, stats=stats)

    full_id = combine_id(item_id, new_crafted_item.id)

    return full_id


async def generate_unique_item(item_id: str, properties: Optional[dict[str, int]]) -> Optional[tuple[str, str, bool]]:
    """
    Generate a new unique item from the specified item_id. If the item with the specified item_id is a fungible then this function won't do anything and simply return the item_id

    Parameters
    ----------
    item_id:
        The item id to generate a unique instance from
    
    properties:
        The crating parameters to enforce, this parameter will have an effect only if the item_id is for a variable item. The actual properties varies depending on the item type.
        
        For cauldron the keys are "alchemy_cdr" and "refine_bonus_per_tier_above" and values should be int for the required value. Going out of normal value range for any property of a given item will prevent its creation

    Returns
    ----------
    A tuple containing 
        - The full id of the newly generated item with the specified item_id. If the specified item_id is in fact for a fungible item of properties are invalid, then the item_id itself is returned and no item is physically created
        
        - The item_type linked to the specified item_id

        - True if the generation can be considered successful, False if the specified properties were out of bound and prevented creation

    Or None if the specified item type does not exist
    """
    details: Optional[tuple[str, dict[str, Any]]] = await AllItems.get_or_none(id=item_id).values_list("type", "properties")
    if details is None:
        return None

    item_type, effective_properties = details
    if not is_variable_item_type(item_type):
        return item_id, item_type, True

    # Remove the craft property, it's worthless to actual generation
    effective_properties.pop(PROP_CRAFT)
    if properties is not None:
        # Override the properties with the specified ones
        for key, overriding_value in properties.items():
            if key != PROP_CRAFT and key in effective_properties:
                normal_bound: list[int] = effective_properties[key]
                if overriding_value < normal_bound[0] or overriding_value > normal_bound[1]:
                    # Invalid override
                    return item_id, item_type, False
                else:
                    effective_properties[key] = [overriding_value, overriding_value]

    unique_id = await _generate_unique_item_internal(item_id, effective_properties)

    return unique_id, item_type, True


class CraftingDropdown(disnake.ui.Select):

    def __init__(self, item_list):
        self.item_list = item_list
        options = [
            *(disnake.SelectOption(label=name, value=str(_id), description=f"{_id} | T{tier} | {item_type}") for _id, name, tier, item_type, _, _, _, _ in item_list[:24]),
        ]

        super().__init__(
            # custom_id=f"craft_menu_{round(time()/99999)}",
            placeholder="Choose an item to craft",
            max_values=1,
            options=options,
        )

    async def callback(self, inter: disnake.MessageInteraction):
        for item in self.item_list:
            if item[0] == inter.values[0]:
                self.view.current_item = item
                await inter.response.edit_message(attachments=[])
                await inter.edit_original_message(embed=craft_embed(item), view=self.view)
                # await inter.message.edit(embed=embed)


class CraftingMenu(disnake.ui.View):
    def __init__(self, item_list, author):
        super().__init__(timeout=None)
        self.item_list = item_list[:24]
        self.item_list_2 = item_list[24:]
        self.current_item = self.item_list[0]
        self.author = author

        self.add_item(CraftingDropdown(self.item_list))
        if len(self.item_list_2) > 0:
            self.add_item(CraftingDropdown(self.item_list_2))

    async def interaction_check(self, inter):
        return inter.author == self.author

    @disnake.ui.button(label="Craft", style=disnake.ButtonStyle.green)
    async def craft_pill(self, _: disnake.ui.Button, inter: disnake.MessageInteraction):
        self.clear_items()
        _id, name, tier, item_type, properties, e_description, requirements, base_exp = self.current_item
        requirements_dict = properties[PROP_CRAFT][PROP_REQUIREMENTS]

        crafting_data = await Crafting.get_or_none(user_id=inter.author.id).values_list("c_lvl", "c_exp", "crafted", "craft_cooldown")
        if crafting_data is None:
            await Crafting.create(user_id=inter.author.id, c_lvl=0, c_exp=0, crafted=[])
            crafting_data = (0, 0, [], 0)
            log_event(inter.author.id, "craft", f"Added user to crafting table")

        user_tier, user_exp, crafted_items, craft_cooldown = crafting_data

        if time() <= craft_cooldown:
            await inter.response.edit_message(embed=BasicEmbeds.exclamation(f"Crafting is on cooldown, try again after <t:{craft_cooldown}:R>"), view=self)
            return

        tier_limit_check = check_tier_limit(user_tier, tier)
        if not tier_limit_check:
            embed = BasicEmbeds.exclamation(f"You dont possess a important thing to craft this item.. knowledge! \nMaybe you will gain it from crafting more items.. who knows")
            await inter.response.edit_message(embed=embed, view=self)
            return

        await inter.response.defer()
        continue_check, ring_id, add_check = await check_inv_weight(inter.channel, inter.author.id, _id, 1)
        if not continue_check:
            await inter.edit_original_message(embed=BasicEmbeds.cmd_not_continued(), view=self)
            return

        mat_check, _ = await mass_check_items(inter.author.id, requirements_dict)
        if mat_check:
            # Removing the mats from inventory
            for item_id, item_count in requirements_dict.items():
                await remove_from_inventory(inter.author.id, item_id, item_count)

            quantity: int = 1

            # Creating the actual item
            if item_type == ITEM_TYPE_RING:
                await add_ring_to_inventory(inter.author.id, _id)
                log_event(inter.author.id, "craft", f"Crafted a Ring ({_id})")

            elif is_variable_item_type(item_type):
                full_id = await _generate_unique_item_internal(_id, properties)
                log_event(inter.author.id, "craft", f"Crafted a Cauldron ({full_id})")

                # adding the item in inventory with unique id
                await add_to_inventory(inter.author.id, full_id, quantity, ring_id, add_check)

            else:
                quantity = check_double_refine(user_tier, tier)
                await add_to_inventory(inter.author.id, _id, quantity, ring_id, add_check)
                log_event(inter.author.id, "craft", f"Crafted an item ({_id})")

            for i in range(quantity):
                crafted_items.append(_id)

            bonus_amount = calculate_exp_bonus(user_tier, tier)
            bonus_exp = (base_exp * bonus_amount) - base_exp
            if bonus_exp < 0:
                bonus_exp = 0

            lvl_up_check, lvl = await check_for_lvl_up(inter.author.id, (base_exp + bonus_exp), user_tier, user_exp)

            content = f"You have crafted a {name}!"
            if quantity == 2:
                content = f"{EXCLAMATION} **Congratulation!!** \nYou have successfully double crafted, getting 2x {name}!"

            content += f"\n\n{PLUS} You got {base_exp:,} exp for crafting a tier {tier} item"
            if bonus_amount > 1:
                content += f"\n\n{PLUS} You have crafted an item above your tier, {bonus_exp:,} exp given!"

            if lvl_up_check is True:
                content += f"\n\n{EXCLAMATION} **Congratulation!!** \nYou have leveled up and reached {lvl} level"

            embed = BasicEmbeds.add_plus(content)

            craft_cooldown = int(time() + 3600)
            await Crafting.filter(user_id=inter.author.id).update(crafted=crafted_items, craft_cooldown=craft_cooldown)
            log_event(inter.author.id, "craft", f"Cooldown added for {round((craft_cooldown - time()) / 60, 1)} minutes")
            await inter.edit_original_message(embed=embed, view=self)

        else:
            content = f"You dont have enough materials to craft {name}"
            embed = BasicEmbeds.exclamation(content)
            log_event(inter.author.id, "craft", f"Failed to craft ({_id})")

            await inter.edit_original_message(embed=embed, view=self)


class CraftingCog(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    # //////////////////////////////////////// #
    @commands.slash_command(name="craft")
    async def slash_craft(self, inter: disnake.CommandInteraction):
        """
        Parent Command
        """
        pass

    @slash_craft.sub_command(name="menu", description="Show you craft menu")
    async def slash_craft_menu(self, inter: disnake.CommandInteraction):
        await inter.response.defer()
        all_items = await AllItems.all().order_by("type", "tier").values_list("id", "name", "tier", "type", "properties", "e_description")

        item_list = []
        combined_inv = await give_combined_inv(inter.author.id)

        for item in all_items:

            _id, name, tier, item_type, properties_dict, e_description = item
            if PROP_CRAFT in properties_dict.keys():
                crafting_mats = properties_dict[PROP_CRAFT][PROP_REQUIREMENTS]
                mass_check, check_content = await mass_check_items(inter.author.id, crafting_mats, combined_inv)
                base_exp = await calculate_mat_exp(crafting_mats)

                item_list.append((_id, name, tier, item_type, properties_dict, e_description, check_content, base_exp))

        view = CraftingMenu(item_list, inter.author)
        await inter.edit_original_message(embed=craft_embed(item_list[0]), view=view)

    @slash_craft.sub_command(name="profile", description="Shows your crafting stats")
    async def slash_craft_profile(self, inter: disnake.CommandInteraction, member: Optional[disnake.Member] = commands.Param(name="member", default=None, description="Mention a member to view their stats")):
        if member is None:
            member = inter.author

        craft_data = await Crafting.get_or_none(user_id=member.id).values_list("c_lvl", "c_exp", "crafted")
        if craft_data is None:
            await inter.response.send_message(embed=BasicEmbeds.exclamation("Please craft something using `/craft menu` to get started"))
            return

        user_level, user_exp, crafted_items = craft_data

        required_exp = get_required_exp(user_level)
        crafted_item_str = "Nothing Yet"
        if crafted_items:
            crafted_items.reverse()
            crafted_item_str = ""
            for i in crafted_items:
                if i not in crafted_item_str:
                    crafted_item_str += f"{crafted_items.count(i)}x {i}, "

            crafted_item_str = crafted_item_str[:-2]

        values = [
            f"**Crafting Tier** : `{user_level}`",
            f"**Current exp/Required exp** : `{user_exp:,}`/`{required_exp:,}`",
            f"**Crafted Items** : \n```{crafted_item_str[:1000]}```"
        ]
        embed = disnake.Embed(
            description="\n".join(value for value in values),
            color=member.color
        )
        if member.avatar is not None:
            embed.set_author(name=member.name, icon_url=member.avatar.url)
        else:
            embed.set_author(name=member.name)
        await inter.response.send_message(embed=embed)

    @commands.slash_command(name="equip", description="Equip Cauldrons")
    async def slash_equip(self, inter: disnake.CommandInteraction, itemid: str = commands.Param(name="item_id", description="Item id (with unique id) you want to equip (eg. cauldron/10)")):
        await inter.response.defer()
        item_id, unique_id = convert_id(itemid)
        if unique_id is None or not unique_id.isdigit():
            embed = BasicEmbeds.exclamation(f"Please pass in the unique ring id as a number separated by '/'! \n\nexample: `cauldron/10`, `cauldron/309` etc")
            await inter.edit_original_message(embed=embed)
            return

        item_details = await AllItems.get_or_none(id=item_id).values_list("properties", "type")
        if item_details is None:
            embed = BasicEmbeds.exclamation(f"Make sure the item id is correct. You can only equip Cauldrons and Weapons")
            await inter.edit_original_message(embed=embed)
            return

        properties_dict, item_type = item_details
        if item_id != "accept_stone":
            if PROP_CRAFT not in properties_dict.keys() or not is_variable_item_type(item_type):
                embed = BasicEmbeds.exclamation(f"Make sure the item id is correct. You can only equip Cauldrons and Weapons")
                await inter.edit_original_message(embed=embed)
                return

        item_check = await check_item_in_inv(inter.author.id, itemid, 1)
        if item_check is False:
            embed = BasicEmbeds.not_enough_item(itemid, "craft")
            await inter.edit_original_message(embed=embed)
            return

        if item_id == "accept_stone":
            equipped = await Users.get_or_none(user_id=inter.author.id).values_list("equipped", flat=True)
            previous_stone = equipped.get("stone", None)
            equipped["stone"] = unique_id

            await Users.filter(user_id=inter.author.id).update(equipped=equipped)
            await remove_from_inventory(inter.author.id, itemid, 1)

            content = f"Successfully equipped the stone ({itemid})"
            log_event(inter.author.id, "craft", f"Equipped a Acceptance Stone ({itemid})")

            if previous_stone:
                stone_details = await AllRings.get_or_none(id=previous_stone).values_list("ring", flat=True)
                log_event(inter.author.id, "ring", f"Unequipped {stone_details}/{previous_stone}")

                await add_ring_to_inventory(inter.author.id, stone_details, previous_stone, True)

                content = f"Successfully swapped the stone ({stone_details}/{previous_stone}) with new stone ({itemid})"

            embed = BasicEmbeds.right_tick(content)
            await inter.edit_original_message(embed=embed)
            return

        if item_type == ITEM_TYPE_CAULDRON:
            ring_id = await get_equipped_ring_id(inter.author.id)

            await remove_from_inventory(inter.author.id, itemid, 1, ring_id)
            previous_cauldron = await equip_cauldron(inter.author.id, unique_id)
            content = f"Successfully equipped the cauldron ({itemid})"

            log_event(inter.author.id, "craft", f"Equipped a cauldron ({itemid})")

            if previous_cauldron is not None:
                cauldron_id = await Crafted.get_or_none(id=previous_cauldron).values_list("item_id", flat=True)
                full_id = combine_id(cauldron_id, previous_cauldron)
                log_event(inter.author.id, "craft", f"Swapped a cauldron with {full_id}")

                content = f"Successfully swapped the cauldron ({full_id}) with new cauldron ({itemid})"
                await add_to_inventory(inter.author.id, full_id, 1, ring_id)

            embed = BasicEmbeds.right_tick(content)
            await inter.edit_original_message(embed=embed)

    @commands.slash_command(name="stone_store", description="Store a flame in an acceptance stone (Gives 50% of the stats)")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def slash_stone_store(self, inter: disnake.CommandInteraction, flame_id: str = commands.Param(name="flame_id", description="Type the flame id to use it")):
        await inter.response.defer()

        flame = await AllItems.get_or_none(id=flame_id).values_list("id", "type", "properties", "name", "tier")

        if flame is None:
            embed = BasicEmbeds.item_not_found()
            await inter.edit_original_message(embed=embed)
            return

        item_id, flame_type, properties, flame_name, flame_ref_rank = flame

        item_check = await check_item_in_inv(inter.author.id, flame_id)
        if item_check is False:
            embed = BasicEmbeds.not_enough_item("beast")
            await inter.edit_original_message(embed=embed)
            return

        if flame_type not in ["h_flame", "b_flame"]:
            await inter.edit_original_message(embed=BasicEmbeds.exclamation("You can only store flames in acceptance stone"))
            return

        equipped = await Users.get_or_none(user_id=inter.author.id).values_list("equipped", flat=True)
        previous_stone = equipped.get("stone", None)
        if previous_stone is None:
            await inter.edit_original_message(embed=BasicEmbeds.exclamation("You dont have a acceptance stone equipped. Equip a stone through `/equip`"))
            return

        stone_inv = await give_custom_ring_inv(previous_stone)
        if len(stone_inv) == 0:
            await add_to_inventory(inter.author.id, flame_id, 1, previous_stone, True)
            await remove_from_inventory(inter.author.id, flame_id, 1)
            content = f"You have successfully stored the flame!"
            log_event(inter.author.id, "flame", f"Stored {flame_name} (Stone: {previous_stone})")
            await inter.edit_original_message(embed=BasicEmbeds.right_tick(content))

        else:
            content = f"Failed to stored the flame. You have already have flame stored in the stone"
            await inter.edit_original_message(embed=BasicEmbeds.exclamation(content))

    @commands.slash_command(name="dismantle", description="Dismantle cauldrons, recovering between 20% and 30% of the material")
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def slash_dismantle(self, inter: disnake.CommandInteraction, itemid: str = commands.Param(name="item_id", description="Item id (with unique id) you want to dismantle (e.g., cauldron/10)")):
        await inter.response.defer()
        item_id, unique_id = convert_id(itemid)
        if unique_id is None or not unique_id.isdigit():
            await inter.edit_original_message(embed=BasicEmbeds.exclamation(f"Please pass in the unique ring id as a number separated by '/'! \n\nexample: `cauldron/10`, `cauldron/309` etc"))
            return

        compendium: ItemCompendium = ItemCompendium()
        item_definition: ItemDefinition = compendium.get(item_id)
        if item_definition is None:
            await inter.edit_original_message(embed=BasicEmbeds.exclamation(f"Make sure the item id is correct. You can only dismantle cauldrons"))
            return

        if not item_definition.craftable or not isinstance(item_definition, CauldronDefinition):
            await inter.edit_original_message(embed=BasicEmbeds.exclamation(f"Make sure the item id is correct. You can only dismantle cauldrons"))
            return

        item_check = await check_item_in_inv(inter.author.id, itemid, 1)
        if not item_check:
            await inter.edit_original_message(embed=BasicEmbeds.not_enough_item(itemid, "craft"))
            return

        crafting_materials: dict[str, int] = item_definition.crafting_materials
        total_quantity: int = sum(crafting_materials.values())

        recovered_percent: int = random.randint(MIN_DISMANTLE_RECOVERY_PERCENT, MAX_DISMANTLE_RECOVERY_PERCENT)
        recovered_quantity: int = math.ceil(total_quantity * recovered_percent / 100)

        ring_id = await get_equipped_ring_id(inter.author.id)
        continue_check, _, _ = await check_inv_weight(inter.channel, inter.author.id, "metal_1", recovered_quantity, ring_id=ring_id,
                                                      confirm_text=f"Make sure you have at least {recovered_quantity:,}wt worth of free space in your inventory/ring. You may lose some of the items, Continue?")
        if not continue_check:
            await inter.edit_original_message(embed=BasicEmbeds.cmd_not_continued())
            return

        # Waited for user interaction, need to perform the inventory check again
        item_check = await check_item_in_inv(inter.author.id, itemid, 1)
        if not item_check:
            await inter.edit_original_message(embed=BasicEmbeds.not_enough_item(itemid, "craft"))
            return

        recovered_material: dict[str, int] = {}
        material_caps: dict[str, int] = crafting_materials.copy()
        for i in range(recovered_quantity):
            if len(crafting_materials) > 0:
                material_id: str = WeightedChoice(material_caps).choose()
                if material_caps[material_id] == 1:
                    material_caps.pop(material_id)
                else:
                    material_caps[material_id] -= 1

                if material_id not in recovered_material:
                    recovered_material[material_id] = 1
                else:
                    recovered_material[material_id] += 1

        # If for some obscure reason the recovery ratio went above 100% which will be taken care of in the above loop, then the recovered quantity may differ from the initially expected recover_quantity, so let recompute the real recovery
        # before notifying the player
        recovered_quantity: int = sum(recovered_material.values())
        recovered_percent: float = recovered_quantity * 100 / total_quantity

        log_event(inter.author.id, "cauldron", f"Dismantled {itemid}, {recovered_percent}% mats recovered")

        await remove_from_inventory(inter.author.id, itemid, 1, ring_id)
        for item_id, quantity in recovered_material.items():
            continue_check, d_ring_id, _ = await check_inv_weight(None, inter.author.id, item_id, quantity, ring_id=ring_id, confirm_prompt=False)
            if continue_check:
                await add_to_inventory(inter.author.id, item_id, quantity, d_ring_id)

        await inter.edit_original_message(embed=BasicEmbeds.right_tick(f"You recovered {recovered_percent:.1f}% of the material used to craft {item_definition.name}:\n{compendium.describe_dict(recovered_material)}"))


def setup(bot):
    bot.add_cog(CraftingCog(bot))
    print("[Crafting] Loaded")

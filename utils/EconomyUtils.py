import math
from datetime import datetime, timedelta

import disnake
from disnake.interactions import MessageInteraction

from utils.Database import AllItems, GuildOptionsDict
from utils.ParamsUtils import TECH_TIER_NAMES, format_num_simple, CURRENCY_NAME_GOLD, CURRENCY_NAME_ARENA_COIN, CURRENCY_NAME_STAR, CURRENCY_NAME_EVENT
from utils.Styles import RIGHT, LEFT, ITEM_EMOJIS

# =====================================
# EconomyUtils specific params
# =====================================


SHOP_CATEGORY_TYPE_DICT = {
    "alchemy": 'Alchemy Shop',
    "pill": 'Pill Tower',
    "fight_technique": 'Fight Technique Shop',
    "qi_method": 'Qi Method Shop',
    "arena_shop": 'Arena Shop',
    "ring": "Ring Shop",
    "monster": "Monster Shop",
    "misc": "Misc Shop"
}

CURRENCY_COLUMN_ARENA_COIN = "pvp_coins"
CURRENCY_COLUMN_GOLD = "money"
CURRENCY_COLUMN_STAR = "star"

DEFAULT_CURRENCY_TYPES = ["Gold Shop", "Pvp Shop (ac)", "FSP Star Echelon", "Clear Filter"]

CURRENCY_TYPE_DICT = {
    "Gold Shop": CURRENCY_NAME_GOLD, 
    "Pvp Shop (ac)": CURRENCY_NAME_ARENA_COIN, 
    "FSP Star Echelon": CURRENCY_NAME_STAR, 
    "Event Shop": CURRENCY_NAME_EVENT,
    "Clear Filter": None
}

# Tacky solution for now
ARENA_SHOP_IIDS = ['goldbar', 'cherb', 'rherb', 'uherb', 'lherb', 'mherb', 'skelking', 'resolveflame', 'shatterclaw', 'skysteps', 'jade']
ARENA_EXCLUSIVE_IIDS = ['skelking', 'resolveflame', 'shatterclaw', 'skysteps']


class CurrencyButton(disnake.ui.Button):
    def __init__(self, currency: str):
        self.currency = currency

        super().__init__(style=disnake.ButtonStyle.secondary, label=currency.capitalize())

    async def callback(self, inter: MessageInteraction):
        self.view.confirm = self.currency
        self.view.clear_items()

        await inter.response.edit_message(f"Selected {self.currency}", view=self.view)
        self.view.stop()


class ConfirmCurrency(disnake.ui.View):
    def __init__(self, author_id, currency_list):
        super().__init__(timeout=None)
        self.author_id = author_id
        self.confirm = None

        for c in currency_list:
            self.add_item(CurrencyButton(c))

    async def interaction_check(self, inter):
        return inter.author.id == self.author_id


async def prepare_embeds(max_items, currency_type: str = None, shop_type: str = None):

    all_items_types = await AllItems.all().order_by("type", "tier").values_list("type", "id", "name", "buy_cost_d", "description", "e_description", "tier")
    if shop_type:
        all_items = await AllItems.filter(type=shop_type).order_by("type", "tier").values_list("type", "id", "name", "buy_cost_d", "description", "e_description", "tier")
    else:
        all_items = all_items_types

    embeds = []
    # menu_item_list = [item[0] for item in all_items_types for key, value in item[3].items() if int(value) > 0 if currency_type is not None]
    menu_item_dict = {}
    for item in all_items_types:
        item_type, item_id, item_name, item_cost_dict, item_desc, item_effect_desc, item_tier = item

        if EVENT_SHOP.is_active and currency_type == 'ec' and item_id not in EVENT_SHOP._items:
            continue
        
        for key, value in item_cost_dict.items():
            if int(value) > 0:
                if currency_type is not None:
                    if key == currency_type:
                        if item_type not in menu_item_dict.keys():
                            menu_item_dict[item_type] = 0

                        menu_item_dict[item_type] += 1
                        # print(item_name, item_type, "ADDED CURRENCY")
                else:
                    if item_type not in menu_item_dict.keys():
                        menu_item_dict[item_type] = 0

                    menu_item_dict[item_type] += 1
                    # print(item_name, item_type, "ADDED ONCE")
                    break
    
    # Split items across multiple pages

    items_list = all_items
    page_item_count = 0
    item_count = 0

    for i in range(math.ceil(len(items_list) / max_items)):
        embed = disnake.Embed(
            color=disnake.Color(0x2e3135)
        )

        if shop_type:
            embed.title = shop_type.capitalize() + " Shop"
        elif currency_type == 'ec':
            embed.title = EVENT_SHOP._name
        else:
            embed.title = "All Items"

        if currency_type is not None:
            embed.description = f"Showing only **{currency_type.capitalize()}** currency items"
        else:
            embed.description = "Showing all currency items"

        for item in items_list[item_count:]:  # Each item on a page
            item_count += 1
            item_type, item_id, item_name, item_cost_dict, item_desc, item_effect_desc, item_tier = item

            if EVENT_SHOP.is_active and currency_type == 'ec' and item_id not in EVENT_SHOP._items:
                continue

            item_cost_str = ""
            for key, value in item_cost_dict.items():
                if int(value) > 0:
                    if currency_type is not None:
                        if key == currency_type:
                            item_cost_str += f"{str(key).capitalize()}: `{format_num_simple(int(value))}` | "
                    else:
                        item_cost_str += f"{str(key).capitalize()}: `{format_num_simple(int(value))}` | "

            if len(item_cost_str) == 0:
                continue

            final_str = f"{ITEM_EMOJIS.get(item_id, ' ')} **{item_name} (`{item_id}`)**\n> **Tier : `{item_tier}`**\n**> Cost :**{item_cost_str[:-2]} \n> **Description :** \n> {item_desc}\n> **Effect :** \n> {item_effect_desc}"
            if item_type in ["fight_technique", "qi_method"]:
                final_str = f"{ITEM_EMOJIS.get(item_id, ' ')} **{item_name} (`{item_id}`)**\n> **Tier : `{TECH_TIER_NAMES[item_tier - 1]}`**\n**Cost :**{item_cost_str[:-2]} \n> **Description :** \n> {item_desc}\n> **Effect :** \n> {item_effect_desc}"

            embed.add_field(name="\u200b", value=final_str)

            page_item_count += 1
            if page_item_count % max_items == 0:
                break
        if embed.fields is not None and len(embed.fields) > 0:
            embeds.append(embed)

    for i, embed in enumerate(embeds):
        embed.set_footer(text=f"Page {i + 1} of {len(embeds)}")

    if len(embeds) < 1:
        embed = disnake.Embed(
            color=disnake.Color(0x2e3135)
        )

        if shop_type:
            embed.title = shop_type.capitalize()

        if currency_type is not None:
            embed.description = f"Showing only **{currency_type.capitalize()}** currency items"
        else:
            embed.description = "Showing all currency items"\

        embed.description += "\n\nNo item of such type available"

        embeds.append(embed)

    return embeds, menu_item_dict


class ShopDropdown(disnake.ui.Select):

    def __init__(self, shop_type_dict):
        options = [
            *(disnake.SelectOption(label=SHOP_CATEGORY_TYPE_DICT.get(str(name), str(name)), description=f"Item Count: {value}", value=str(name)) for name, value in shop_type_dict.items()),
        ]

        super().__init__(
            custom_id="main_shop",
            placeholder="Choose a shop",
            max_values=1,
            options=options,
        )

    async def callback(self, inter):
        self.view.embeds, self.view.shop_type_dict = await prepare_embeds(6, currency_type=self.view.currency_type, shop_type=inter.values[0])
        self.view.embed_count = 0

        self.view.prev_page.disabled = True
        self.view.next_page.disabled = False
        if len(self.view.embeds) <= 1:
            self.view.next_page.disabled = True

        await inter.response.edit_message(embed=self.view.embeds[0], view=ShopMenu(inter.author, self.view.embeds, self.view.shop_type_dict, self.view.currency_type))


class CurrencyDropdown(disnake.ui.Select):

    def __init__(self):
        options = [
            *(disnake.SelectOption(label=str(name), value=str(name)) for name in DEFAULT_CURRENCY_TYPES),
        ]

        # Add event shop option if active
        if EVENT_SHOP.is_active:
            options.append(
                disnake.SelectOption(
                    label=EVENT_SHOP._name,
                    description=f"Limited time special items!",
                    value="Event Shop"
                )
            )
        
        super().__init__(
            custom_id="currency_menu",
            placeholder="Choose a currency",
            max_values=1,
            options=options,
        )

    async def callback(self, inter):
        self.view.currency_type = CURRENCY_TYPE_DICT[inter.values[0]]
        self.view.embeds, self.view.shop_type_dict = await prepare_embeds(6, currency_type=self.view.currency_type)
        self.view.embed_count = 0

        self.view.prev_page.disabled = True
        self.view.next_page.disabled = False
        if len(self.view.embeds) <= 1:
            self.view.next_page.disabled = True

        await inter.response.edit_message(embed=self.view.embeds[0], view=ShopMenu(inter.author, self.view.embeds, self.view.shop_type_dict, self.view.currency_type))


class ShopMenu(disnake.ui.View):
    def __init__(self, author, embeds, shop_menu_dict, currency_type=None):
        super().__init__(timeout=None)

        self.author = author
        self.embeds = embeds
        self.embed_count = 0
        self.shop_type_dict = shop_menu_dict
        self.currency_type = currency_type
        self.add_item(ShopDropdown(self.shop_type_dict))
        self.add_item(CurrencyDropdown())

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


async def shop_view(author):
    embeds, shop_menu_dict = await prepare_embeds(6)
    view = ShopMenu(author, embeds, shop_menu_dict)
    return embeds[0], view


def currency_dict_to_str(currency_dict):
    item_cost_str = ""

    for key, value in currency_dict.items():
        if int(value) > 0:
            item_cost_str += f"- {str(key).capitalize()}: `{format_num_simple(int(value))}`\n"

    return item_cost_str


async def check_for_tax():
    new_tax_details = await GuildOptionsDict.get_or_none(name="new_tax_details").values_list("value", flat=True)
    if new_tax_details is None:
        await GuildOptionsDict.create(name="new_tax_details", value='{}')
        new_tax_details = {}
    else:
        new_tax_details = new_tax_details

    old_tax_details = await GuildOptionsDict.get_or_none(name="old_tax_details").values_list("value", flat=True)
    if old_tax_details is None:
        await GuildOptionsDict.create(name="old_tax_details", value='{}')
        old_tax_details = {}
    else:
        old_tax_details = old_tax_details

    return new_tax_details, old_tax_details


async def add_tax_amount(user_id: int, amount: int):
    new_tax_details, _ = await check_for_tax()
    if str(user_id) not in new_tax_details.keys():
        new_tax_details[str(user_id)] = 0

    new_tax_details[str(user_id)] += amount

    await GuildOptionsDict.filter(name="new_tax_details").update(value=new_tax_details)


async def get_tax_details(user_id: int):
    _, old_tax_details = await check_for_tax()
    total_tax = sum(list(old_tax_details.values()))

    if str(user_id) not in old_tax_details.keys():
        old_tax_details[str(user_id)] = 0

    user_amount = old_tax_details[str(user_id)]

    user_tax_percent = 0
    if total_tax > 0:
        user_tax_percent = round((user_amount / total_tax) * 100, 2)

    return user_tax_percent, user_amount, total_tax


class EventShopConfig:
    def __init__(self):
        self._enabled = False
        self._end_time = None
        self._items = []
        self._name = 'Event Shop'
    
    @property
    def is_active(self) -> bool:
        if not self._enabled:
            return False
        if self._end_time and datetime.now() > self._end_time:
            self._enabled = False
            return False
        return True

    def enable(self, duration_hours: int = 168):  # Default 1 week
        self._enabled = True
        self._end_time = datetime.now() + timedelta(hours=duration_hours)
    
    def disable(self):
        self._enabled = False
        self._end_time = None
    
    def set_name_and_items(self, name: str, items: list):
        self._name = name
        self._items = items

# Current event shop instance
EVENT_SHOP = EventShopConfig()

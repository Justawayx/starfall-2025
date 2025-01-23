from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Union, Optional

import disnake
from disnake.ext import commands, tasks

from adventure.auction import AuctionHouse
from utils.CommandUtils import add_market_points_for_sale
from world.compendium import ItemCompendium, ItemDefinition
from character.player import PlayerRoster, Player
from utils.Database import AllItems, Market, AllRings
from utils.DatabaseUtils import compute_market_userinfo
from utils.EconomyUtils import add_tax_amount, ConfirmCurrency, currency_dict_to_str
from utils.Embeds import BasicEmbeds
from utils.InventoryUtils import ConfirmDelete, convert_id, combine_id, remove_from_inventory, add_to_inventory, check_inv_weight, check_item_in_inv, get_equipped_ring_id, ITEM_TYPE_RING, ITEM_TYPE_CHEST
from utils.LoggingUtils import log_event
from utils.ParamsUtils import format_num_full, CURRENCY_NAME_GOLD
from utils.Styles import RIGHT, LEFT, ITEM_EMOJIS, TICK, CROSS
from utils.base import BaseStarfallCog

ITEM_TYPE_AUTOCOMPLETE: list = []


class Confirmation(disnake.ui.View):
    def __init__(self, author: disnake.Member):
        super().__init__(timeout=None)
        self.author = author
        self.confirm = False

    async def interaction_check(self, inter):
        return inter.author == self.author

    @disnake.ui.button(emoji=TICK, style=disnake.ButtonStyle.secondary)
    async def confirm_button(self, _: disnake.ui.Button, interaction: disnake.MessageInteraction):
        text = f"Confirmed {TICK}"
        self.confirm = True
        self.clear_items()

        await interaction.response.edit_message(text, view=self)
        self.stop()

    @disnake.ui.button(emoji=CROSS, style=disnake.ButtonStyle.secondary)
    async def rejection_button(self, _: disnake.ui.Button, interaction: disnake.MessageInteraction):
        text = f"Rejected {CROSS}"
        self.confirm = False
        self.clear_items()

        await interaction.response.edit_message(text, view=self)
        self.stop()


class MarketPaginatorView(disnake.ui.View):
    def __init__(self, embeds, author, label):
        super().__init__(timeout=None)
        self.add_item(IDButton(label))
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


class SubmitItemId(disnake.ui.Modal):
    def __init__(self, label):
        self.label = label

        components = [
            disnake.ui.TextInput(
                label="Market Item Id",
                placeholder="Type the item id from market (eg. 1, 12, 382)",
                custom_id="market_item_id",
                style=disnake.TextInputStyle.short,
                max_length=5,
            )
        ]
        super().__init__(
            title=f"{self.label} Item",
            custom_id="filling_item_id",
            components=components,
        )

    async def callback(self, inter: disnake.ModalInteraction):
        await inter.response.defer()

        _id = inter.text_values["market_item_id"]
        item_check = await Market.get_or_none(id=_id).values_list("user_id", "item__name", "item__type", "item_id", "amount", "price", "unique_id")
        if item_check:

            user_id, item_name, _, item_id, quantity, price, unique_id = item_check

            continue_check, ring_id, add_check = await check_inv_weight(inter.channel, inter.author.id, item_id, quantity)
            if not continue_check:
                embed = BasicEmbeds.cmd_not_continued()
                await inter.edit_original_message(embed=embed, view=self)
                return

            if self.label == "Buy":

                if user_id == inter.author.id:
                    embed = BasicEmbeds.wrong_cross("You cant buy your own item")
                    await inter.edit_original_message(embed=embed)
                    return

                _, _, buy_tax, _, _, _ = await compute_market_userinfo(inter.author.id)

                b_tax = round((buy_tax / 100) * price)
                total_price = price + b_tax

                roster: PlayerRoster = PlayerRoster()
                buyer: Player = roster.get(inter.author.id)
                async with buyer:
                    money_check: bool = buyer.spend_funds(total_price)

                if money_check:
                    await add_tax_amount(inter.author.id, b_tax)

                    _, sell_tax, _, _, _, _ = await compute_market_userinfo(user_id)
                    await Market.filter(id=_id).delete()

                    s_tax = round((sell_tax / 100) * price)
                    await add_tax_amount(user_id, s_tax)

                    price_after_tax = price - s_tax
                    seller: Player = roster.get(user_id)
                    async with buyer:
                        seller.add_funds(price_after_tax)

                    await add_market_points_for_sale(user_id, price)

                    full_id = combine_id(item_id, unique_id)

                    log_event(inter.author.id, "market", f"Bought {quantity}x {full_id} (M_ID: {_id}) for {total_price:,} gold")
                    await add_to_inventory(inter.author.id, full_id, quantity, ring_id, add_check)

                    try:
                        user_to_dm = await inter.guild.getch_member(int(user_id))
                        await user_to_dm.send(
                            embed=BasicEmbeds.right_tick(f"{quantity}x {item_name} is bought by {inter.author.mention} for {price:,} gold \n\nYou got **`{price_after_tax:,}`** gold after tax", "Market Item Sold!"))
                        log_event(user_id, "market", f"Sold {quantity}x {full_id} (M_ID: {_id}) to {inter.author.id}, got {price_after_tax:,} gold")
                    except disnake.Forbidden:
                        pass

                    embed = BasicEmbeds.add_plus(f"You have successfully bought {quantity}x {item_name} for {format_num_full(total_price)} gold from market!")
                else:
                    embed = BasicEmbeds.wrong_cross("You dont have enough gold to buy the item")
            else:
                full_id = combine_id(item_id, unique_id)

                await Market.filter(id=_id).delete()
                await add_to_inventory(inter.author.id, full_id, quantity, ring_id, add_check)
                embed = BasicEmbeds.right_tick(f"{full_id} successfully removed from the market")

                log_event(inter.author.id, "market", f"Removed {quantity}x {full_id} (M_ID: {_id})")

            await inter.edit_original_message(embed=embed)
        else:
            embed = BasicEmbeds.wrong_cross("Item does not exist now, either bought or removed. \n\n*Do the command again to refresh the market*")
            await inter.edit_original_message(embed=embed)


class IDButton(disnake.ui.Button):

    def __init__(self, label):
        self.label = label
        super().__init__(label=str(label), style=disnake.ButtonStyle.green, custom_id="id_button")

    async def callback(self, inter: disnake.MessageInteraction):
        await inter.response.send_modal(SubmitItemId(self.label))


class MainMarket(BaseStarfallCog):

    def __init__(self, bot):
        super().__init__(bot, "Market", "market")

    async def _do_load(self):
        if not self.expire_item.is_running():
            self.expire_item.start()

    def _do_unload(self):
        self.expire_item.cancel()

    @tasks.loop(minutes=30)
    async def expire_item(self):
        market_items = await Market.all().values_list("id", "user_id", "expiry", "amount", "item_id", "unique_id", "item__type")
        for item in market_items:
            _id, user_id, expiry, quantity, item_id, unique_id, item_type = item

            if datetime.now(timezone.utc) > expiry:
                await Market.filter(id=_id).delete()
                full_id = combine_id(item_id, unique_id)

                log_event(user_id, "market", f"Expired item, {quantity}x {full_id} (M_ID: {_id})")

                ring_id = await get_equipped_ring_id(user_id)
                await add_to_inventory(user_id, full_id, int(quantity), ring_id)

    @expire_item.before_loop
    async def before_number(self):
        await self.bot.wait_until_ready()

    @commands.slash_command(name="market")
    async def slash_market(self, inter: disnake.CommandInteraction):
        """
        Parent Command
        """
        pass

    @slash_market.sub_command(name="add", description="Add your item to market")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def slash_market_add(self, inter: disnake.CommandInteraction, item_id: str, quantity: int = commands.Param(1, gt=0), price: int = commands.Param(1000, gt=0)):
        await inter.response.defer()
        global ITEM_TYPE_AUTOCOMPLETE

        itemid, unique_id = convert_id(item_id)
        if unique_id is not None:
            quantity = 1

        if price < 700:
            await inter.edit_original_message(embed=BasicEmbeds.wrong_cross("Please set a price more than 700"))
            return

        if quantity < 1:
            await inter.edit_original_message(embed=BasicEmbeds.wrong_cross("Please put at least 1 item"))
            return

        compendium: ItemCompendium = ItemCompendium()
        definition: ItemDefinition = compendium.get(itemid)
        if definition is None:
            await inter.edit_original_message(embed=BasicEmbeds.item_not_found())
            return

        if definition.type == ITEM_TYPE_CHEST:
            await inter.edit_original_message(embed=BasicEmbeds.wrong_cross("Chests cannot be added to the market"))
            return

        view = ConfirmDelete(inter.author.id)
        await inter.edit_original_message("You will be paying listing tax based on your tier (max 5%) \n Do you want to continue?", view=view)
        await view.wait()
        if not view.confirm:
            await inter.edit_original_message(embed=BasicEmbeds.exclamation(f"Command stopped by the user"), view=None)
            return

        item_count = await Market.filter(user_id=inter.author.id).count()
        item_count += AuctionHouse().active_auction_count(author_id=inter.author.id)
        listing_tax, _, _, item_limit, _, _ = await compute_market_userinfo(inter.author.id)

        if item_count >= item_limit:
            await inter.edit_original_message(embed=BasicEmbeds.wrong_cross(f"You have maximum number ({item_count}/{item_limit}) of items possible on market and auction"))
            return

        item_check = await check_item_in_inv(inter.author.id, item_id, quantity)
        if item_check:
            total_price = int(price * quantity)
            tax = round((listing_tax / 100) * total_price)

            async with PlayerRoster().get(inter.author.id) as player:
                money_check: bool = player.spend_funds(tax)

            if money_check:
                await add_tax_amount(inter.author.id, tax)
                await remove_from_inventory(inter.author.id, item_id, quantity)
                market_item = await Market.create(user_id=inter.author.id, item_id=itemid, amount=quantity, price=total_price, expiry=datetime.utcnow() + timedelta(days=3), unique_id=unique_id)

                log_event(inter.author.id, "market", f"Added {quantity}x {item_id} (M_ID: {market_item.id}) for {total_price:,} gold, paid {tax:,} tax")

                if unique_id:
                    embed = BasicEmbeds.right_tick(f"Added a Unique Item (||{item_id}||) to market for {total_price:,} gold \n\n*Deducted {tax:,} gold as listing fee {listing_tax}%*")
                else:
                    embed = BasicEmbeds.right_tick(f"Added {quantity}x item (||{item_id}||) to market for {total_price:,} gold \n\n*Deducted {tax:,} gold as listing fee {listing_tax}%*")
                    # await inter.edit_original_message(embed=embed)
            else:
                embed = BasicEmbeds.exclamation("You dont have enough gold to pay the tax")
                # await inter.edit_original_message(embed=embed)

        else:
            embed = BasicEmbeds.not_enough_item(item_id)

        await inter.edit_original_message(embed=embed)

        ITEM_TYPE_AUTOCOMPLETE = []

    @slash_market.sub_command(name="profile", description="Show Market profile")
    async def slash_market_profile(self, inter: disnake.CommandInteraction, member: disnake.Member = None):
        if not member:
            member = inter.author

        listing_tax, sell_tax, buy_tax, item_limit, market_points, user_market_tier = await compute_market_userinfo(member.id)

        values = [
            f"**Username** : {member.name}",
            f"**Total Points** : {market_points}",
            f"**User Tier** : {user_market_tier}",
            f"\n**Sell Tax** : `{sell_tax}` %",
            f"**Listing Fee** : `{listing_tax}` %",
            f"**Buy Tax** : `{buy_tax}` %",
            f"**Item Limit** : `{item_limit}`",
        ]
        embed = disnake.Embed(
            title="Market Profile",
            description="\n".join(value for value in values),
            color=disnake.Color(0x2e3135)
        )
        if member.avatar:
            embed.set_thumbnail(url=member.avatar.url)

        await inter.response.send_message(embed=embed)

    @slash_market.sub_command(name="items", description="Show your items currently on market")
    async def slash_market_items(self, inter: disnake.CommandInteraction):
        await inter.response.defer()

        market_items = await Market.filter(user_id=inter.author.id).values_list("id", "user_id", "item__name", "item__type", "item_id", "amount", "price", "expiry", "unique_id")
        embeds = []
        max_items = 5
        embed = disnake.Embed(
            title=f"{inter.author.name}'s Items",
            color=disnake.Color(0x2e3135)
        )
        items_list = [market_items[i:i + max_items] for i in range(0, len(market_items), max_items)]
        for items in items_list:

            for item in items:
                _id, user_id, item_name, item_type, item_id, quantity, price, expiry, unique_id = item
                emoji = ITEM_EMOJIS.get(item_id, "")
                if unique_id:
                    full_id = f"{item_id}/{unique_id}"
                    embed.add_field(name="\u200b", value=f"ID: `{_id}` \n**{emoji} {item_name}** \n> Unique ID: `{full_id}` | Price: `{price:,}` gold", inline=False)
                else:
                    embed.add_field(name="\u200b", value=f"ID: `{_id}` \n**`{quantity}` x {emoji} {item_name}** \n> Type: `{item_type.capitalize()}` | Price: `{price:,}` gold", inline=False)
            embed.set_footer(text="Page 1")
            embeds.append(embed)

        if len(embeds) > 0:
            view = MarketPaginatorView(embeds, inter.author, "Remove")
            await inter.edit_original_message(embed=embeds[0], view=view)
        else:
            embed.description = f"*No item found*"

            await inter.edit_original_message(embed=embed)

    Sorting = commands.option_enum(
        {
            "Price - High": "-price",
            "Price - Low": "price",
            "Created - Old": "-created",
            "Created - New": "created",
        }
    )

    @slash_market.sub_command(name="search", description="Search for items using \"type\" filter")
    async def slash_market_search(self, inter: disnake.CommandInteraction, type: str, sorting: Sorting = "created"):
        await inter.response.defer()

        if type == "all":
            market_items = await Market.all().order_by(sorting).values_list("id", "user_id", "item__name", "item__type", "item_id", "amount", "price", "unique_id")
        else:
            market_items = await Market.filter(item__type=type).order_by(sorting).values_list("id", "user_id", "item__name", "item__type", "item_id", "amount", "price", "unique_id")

        all_ring_ids = [item[7] for item in market_items if item[3] == "ring"]
        all_rings_item = await AllRings.filter(id__in=all_ring_ids).values_list("id", "items__item_id", "items__count")

        ring_items_dict = defaultdict(list)
        for ring in all_rings_item:
            ring_items_dict[ring[0]].append((ring[2], ring[1]))

        embeds = []
        max_items = 5

        items_list = [market_items[i:i + max_items] for i in range(0, len(market_items), max_items)]
        listing_tax, sell_tax, buy_tax, item_limit, market_points, user_market_tier = await compute_market_userinfo(inter.author.id)

        for items in items_list:
            embed = disnake.Embed(
                title="Market",
                description=f"Type: `{type}` \n*Tax amount is shown as in brackets- (+amount)*",
                color=disnake.Color(0x2e3135)
            )
            for item in items:
                _id, user_id, item_name, item_type, item_id, quantity, price, unique_id = item
                emoji = ITEM_EMOJIS.get(item_id, "")
                tax = round((buy_tax / 100) * price)
                total_price = f"{format_num_full(price)} (+{format_num_full(tax)})"

                if unique_id:
                    if item_type == "ring":
                        ring_items = ring_items_dict[unique_id]
                        if len(ring_items) > 0:
                            ring_items_str = ", ".join(f"`{c}x {i}`" for c, i in ring_items[:20])
                        else:
                            ring_items_str = "No Items"

                        embed.add_field(name="\u200b", value=f"ID: `{_id}` \n**{emoji} {item_name}** \n> Unique ID: `{unique_id}` | Price: `{total_price}` gold \n**Items**: {ring_items_str[:170]}", inline=False)
                    else:
                        embed.add_field(name="\u200b", value=f"ID: `{_id}` \n**{emoji} {item_name}** \n> Unique ID: `{unique_id}` | Price: `{total_price}` gold", inline=False)
                else:
                    embed.add_field(name="\u200b", value=f"ID: `{_id}` \n**`{quantity}` x {emoji} {item_name}** \n> Type: `{item_type.capitalize()}` | Price: `{total_price}` gold", inline=False)
            embed.set_footer(text="Page 1")
            embeds.append(embed)

        if len(embeds) > 0:
            view = MarketPaginatorView(embeds, inter.author, "Buy")
            await inter.edit_original_message(embed=embeds[0], view=view)
        else:
            embed = disnake.Embed(
                title="Market",
                description=f"by type: `{type}` \n\n*No item found*",
                color=disnake.Color(0x2e3135)
            )
            await inter.edit_original_message(embed=embed)

    @slash_market_search.autocomplete("type")
    async def language_autocomplete(self, _: disnake.ApplicationCommandInteraction, string: str):
        string = string.lower()
        global ITEM_TYPE_AUTOCOMPLETE

        if len(ITEM_TYPE_AUTOCOMPLETE) < 1:
            item_types = await Market.all().values_list("item__type", flat=True)
            ITEM_TYPE_AUTOCOMPLETE = item_types
        else:
            item_types = ITEM_TYPE_AUTOCOMPLETE

        item_types.append("all")
        unique_types = set(item_types)

        all_types = [t for t in unique_types]
        return [t for t in all_types if string in t.lower()]

    @commands.slash_command(name="buy", description="Buy an item from shop")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def slash_buy(self,
                        inter: disnake.CommandInteraction,
                        item_id: str = commands.Param(name="item_id", description="Type the item id to buy it"),
                        quantity: int = commands.Param(default=1, gt=0, name="quantity", description="Enter the amount you want to buy (default to 1)")):
        await inter.response.defer()
        compendium: ItemCompendium = ItemCompendium()
        definition: Optional[ItemDefinition] = compendium.get(item_id)
        if definition is None:
            await inter.send(embed=BasicEmbeds.item_not_found())
            return
        elif not definition.buyable():
            await inter.send(embed=BasicEmbeds.wrong_cross("Item can't be bought"))
            return

        if definition.type == ITEM_TYPE_RING:
            quantity = 1

        currency_list: list[str] = [str(key) for key, value in definition.shop_buy_prices.items() if int(value) > 0]
        if len(currency_list) > 1:
            view = ConfirmCurrency(inter.author.id, currency_list)
            currency_str = currency_dict_to_str(definition.shop_buy_prices)
            await inter.channel.send(f"Detected more than 1 currency price for this item. Choose one from below \n{currency_str}", view=view)
            await view.wait()
            if view.confirm is None:
                await inter.edit_original_message(embed=BasicEmbeds.exclamation(f"Command stopped by the user"))
                return

            currency = view.confirm
        else:
            currency: str = currency_list[0]

        continue_check, ring_id, add_check = await check_inv_weight(inter.channel, inter.author.id, item_id, quantity)
        if not continue_check:
            await inter.edit_original_message(embed=BasicEmbeds.cmd_not_continued())
            return

        content, check = await _buy_from_shop(inter.author.id, item_id, quantity, currency)
        if check:
            await add_to_inventory(inter.author.id, item_id, quantity, ring_id, add_check)
            embed = BasicEmbeds.right_tick(content, "Successfully bought!")
        else:
            embed = BasicEmbeds.wrong_cross(content)

        await inter.edit_original_message(embed=embed)

    @commands.slash_command(name="sell", description="Sell an item from inventory (use itemid=beast_drops to mass sell)")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def slash_sell(self,
                         inter: disnake.CommandInteraction,
                         itemid: str = commands.Param(name="item_id", description="Type the item id to sell it"),
                         quantity: int = commands.Param(default=1, gt=0, name="quantity", description="Number of item you want to sell")):
        await inter.response.defer()
        item_id, unique_id = convert_id(itemid)
        if itemid.lower() == "beast_drops":
            # content, check = await mass_sell_to_shop(inter.author.id, "beast_drops")
            embed = BasicEmbeds.exclamation("Under Work")  # if check else BasicEmbeds.wrong_cross(content)
        else:
            compendium: ItemCompendium = ItemCompendium()
            definition: Optional[ItemDefinition] = compendium.get(item_id)
            if definition is None:
                await inter.edit_original_message(embed=BasicEmbeds.item_not_found())
                return

            if definition.type == ITEM_TYPE_RING:
                view = Confirmation(inter.author)
                await inter.edit_original_message("Selling a ring will delete all the items inside it! \n Do you want to continue?", view=view)
                await view.wait()
                if not view.confirm:
                    await inter.edit_original_message(embed=BasicEmbeds.exclamation(f"Command stopped by the user"))
                    return

            item_check = await check_item_in_inv(inter.author.id, itemid, quantity)
            if item_check:
                content, check = await _sell_to_shop(inter.author.id, item_id, quantity)
                if check:
                    await remove_from_inventory(inter.author.id, itemid, quantity)
                    embed = BasicEmbeds.right_tick(content, "Successfully Sold!")
                else:
                    embed = BasicEmbeds.wrong_cross(content)
            else:
                embed = BasicEmbeds.not_enough_item("shop")

        await inter.edit_original_message(embed=embed)


async def _buy_from_shop(user_id: int, itemid: str, amount: int = 1, currency: str = CURRENCY_NAME_GOLD) -> tuple[str, bool]:
    item: Optional[ItemDefinition] = ItemCompendium().get(itemid)
    if item is not None:
        item_cost_dict: dict[str, int] = item.shop_buy_prices
        cost = int(item_cost_dict.get(currency, 0)) * amount
        if cost > 0:  # Can only buy items with positive buy cost
            player: Player = PlayerRoster().get(user_id)
            async with player:
                if player.spend_funds(cost, currency):
                    log_event(user_id, "economy", f"Spent {cost:,} {currency.capitalize()}, Bought {amount}x {itemid}")

                    content = f"You bought `{amount}`x {item.name} for `{cost:,}` **{currency.capitalize()}**"
                    return content, True
                else:
                    content = "You don't have enough money"
                    log_event(user_id, "economy", f"Failed to buy {amount}x {itemid}, cost {cost:,} {currency.capitalize()}")
        else:
            content = "Item can't be bought"
    else:
        content = "Item not found"

    return content, False


async def _sell_to_shop(user_id: int, itemid: str, amount: int = 1) -> tuple[str, bool]:
    item: Optional[ItemDefinition] = ItemCompendium().get(itemid)
    if item is not None:
        item_cost_dict: dict[str, int] = item.shop_sell_prices
        cost = item_cost_dict.get("gold", 0)
        if cost > 0:
            sell_cost = cost * amount

            player: Player = PlayerRoster().get(user_id)
            async with player:
                player.add_funds(sell_cost)

            log_event(user_id, "economy", f"Earned {sell_cost:,} Gold, Sold {amount}x {itemid}")

            content = f"You got `{sell_cost:,}` from selling `{amount}`x {item.name}"

            return content, True
        else:
            content = "Chosen item is not sellable"
    else:
        content = "Item not Found"
    return content, False


def _log(user_id: Union[int, str], message: str, level: str = "INFO"):
    log_event(user_id, "market", message, level)


def setup(bot):
    cog = MainMarket(bot)
    bot.add_cog(MainMarket(bot))
    _log("system", f"{cog.name} Created")

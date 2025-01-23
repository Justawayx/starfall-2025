from datetime import timedelta
from time import time
from typing import Optional, Union, Any, Coroutine, Callable

import disnake
from disnake.ext import commands, tasks

from adventure.auction import EXPECTED_LOOP_DELAY_SECONDS, MINIMUM_BID, MINIMUM_INCREMENT, DEFAULT_DURATION, MINIMUM_DURATION, AuctionHouse, AuctionedItem, MAXIMUM_DURATION
from cogs.crafting import generate_unique_item, PROP_CAULDRON_COOLDOWN_REDUCTION, PROP_CAULDRON_REFINE_BONUS, UNSTACKABLE_ITEM_TYPES
from utils.CommandUtils import unregister_item_expiration, ORIGIN_QI_LIFESPAN
from utils.Database import Market
from utils.DatabaseUtils import compute_market_userinfo
from utils.Embeds import BasicEmbeds
from utils.InventoryUtils import ConfirmDelete, check_item_in_inv, convert_id, remove_from_inventory, ITEM_TYPE_ORIGIN_QI, ITEM_TYPE_CHEST
from utils.LoggingUtils import log_event
from utils.base import BaseStarfallCog, CogNotLoadedError
from world.compendium import ItemCompendium, autocomplete_item_id, ItemDefinition

_SHORT_NAME: str = "auction"
_MAIN_LOOP_DELAY_SECONDS: int = EXPECTED_LOOP_DELAY_SECONDS
_COUNTDOWN_LOOP_DELAY_SECONDS: int = 3
_MINIMUM_OQI_REMAINING_LIFETIME: timedelta = timedelta(hours=1)


class AuctionHouseNotLoadedError(CogNotLoadedError):
    def __init__(self):
        super().__init__()


class AuctionHouseCog(BaseStarfallCog):
    def __init__(self, bot: commands.Bot):
        super().__init__(bot, "Auction House Cog", "auction")

    # ========================================= Disnake lifecycle methods ========================================

    async def _do_load(self):
        if not self.main_auction_loop.is_running():
            self.main_auction_loop.start()

        if not self.countdown_auction_loop.is_running():
            self.countdown_auction_loop.start()

    def _do_unload(self):
        self.main_auction_loop.cancel()
        self.countdown_auction_loop.cancel()
        self._active_auctions: set[AuctionedItem] = set()
        self._countdown_auctions: set[AuctionedItem] = set()
        self._auctions_by_ids: dict[int, AuctionedItem] = dict()
        self._auctions_by_msg_ids: dict[int, AuctionedItem] = dict()

    async def _initialize_views(self) -> list[disnake.ui.View]:
        return AuctionHouse().persistent_views

    # Loop management
    @tasks.loop(seconds=_MAIN_LOOP_DELAY_SECONDS)
    async def main_auction_loop(self):
        house: AuctionHouse = AuctionHouse()
        await house.update_all_auction_states()

    @tasks.loop(seconds=_COUNTDOWN_LOOP_DELAY_SECONDS)
    async def countdown_auction_loop(self):
        house: AuctionHouse = AuctionHouse()
        await house.update_countdown_auction_states()

    @main_auction_loop.before_loop
    async def before_main_auction_loop(self):
        await self._bot.wait_until_ready()

    @countdown_auction_loop.before_loop
    async def before_countdown_auction_loop(self):
        await self._bot.wait_until_ready()

    # ============================================= Discord commands ============================================

    @commands.slash_command(name="auction")
    async def slash_auction(self, _: disnake.CommandInteraction):
        """
        Parent Command
        """
        pass

    @slash_auction.sub_command(name="add", description="Create a new auction for an item in your inventory.")
    async def slash_auction_add(
            self,
            inter: disnake.CommandInteraction,
            item_id: str = commands.Param(description="The item id including the unique id if applicable"),
            quantity: int = commands.Param(default=1, gt=0, description="The item quantity, only valid for fungible items, will be forced to 1 for other cases"),
            minimum_bid: Optional[int] = commands.Param(default=MINIMUM_BID, ge=MINIMUM_BID, description="The first bid will have to be at least this value (for the lot)"),
            minimum_increment: Optional[int] = commands.Param(default=MINIMUM_INCREMENT, ge=MINIMUM_INCREMENT, description="By how much gold a new bid must be above the previous one for it to be accepted"),
            duration_hours: Optional[int] = commands.Param(default=DEFAULT_DURATION, gt=MINIMUM_DURATION, description="How long the auction is expected to last in hours.")
    ):
        await inter.response.defer()

        if await self._validate_add_parameters(inter, item_id, minimum_bid, minimum_increment, duration_hours):
            view = ConfirmDelete(inter.author.id)
            await inter.followup.send(
                f"You're about to start an auction for `{quantity if quantity > 0 else 1} x {item_id}` lasting `{duration_hours} hours`, with a `{minimum_bid:,} gold` minimum bid and a minimum increment of `{minimum_increment:,} gold`."
                f"\n\nYou will be paying commission based on your market tier (listing + selling rates) at time of auction completion (max 15%)."
                f"\n\nIf the auction remains unsold then you'll have to pay the commission based on the minimum bid (`{minimum_bid:,} gold`) to retrieve your item."
                f"\n\nDo you want to continue?", view=view)
            await view.wait()
            if view.confirm:
                house: AuctionHouse = AuctionHouse()
                item_count = await Market.filter(user_id=inter.author.id).count()
                item_count += house.active_auction_count(author_id=inter.author.id)
                _, _, _, item_limit, _, _ = await compute_market_userinfo(inter.author.id)

                if item_count < item_limit:
                    _, unique_id = convert_id(item_id)
                    quantity = quantity if quantity >= 1 and not unique_id else 1
                    item_check = await check_item_in_inv(inter.author.id, item_id, quantity)
                    if item_check:
                        remaining_lifespan_seconds = await self._check_oqi_lifespan(inter, view, item_id)
                        if remaining_lifespan_seconds != -1:
                            effective_remaining = timedelta(seconds=remaining_lifespan_seconds) if remaining_lifespan_seconds is not None else None
                            await remove_from_inventory(inter.author.id, item_id, quantity)
                            await house.create_auction(inter=inter, item_id=item_id, quantity=quantity, minimum_bid=minimum_bid, minimum_increment=minimum_increment, duration_hours=duration_hours, remaining_lifespan=effective_remaining)
                    else:
                        await inter.followup.send(embed=BasicEmbeds.not_enough_item(item_id))
                else:
                    await inter.followup.send(embed=BasicEmbeds.wrong_cross(f"You have maximum number ({item_count}/{item_limit}) of items possible on market and auction"))
            else:
                await inter.followup.send(embed=BasicEmbeds.exclamation(f"Command stopped by the user"))

    @commands.slash_command(name="auction_admin")
    @commands.default_member_permissions(manage_guild=True)
    async def slash_auction_admin(self, _: disnake.CommandInteraction):
        """
        Parent Command
        """
        pass

    @slash_auction_admin.sub_command(name="add", description="Create a new auction as a NPC.")
    async def slash_auction_admin_add(
            self,
            inter: disnake.CommandInteraction,
            item_id: str = commands.Param(autocomplete=autocomplete_item_id, name="item_id", description="The item id without the unique id part"),
            quantity: int = commands.Param(1, gt=0, name="quantity", description="The item quantity, only valid for fungible items, will be forced to 1 for other cases"),
            minimum_bid: int = commands.Param(MINIMUM_BID, ge=MINIMUM_BID, name="minimum_bid", description="The first bid will have to be at least this value (for the lot)"),
            minimum_increment: int = commands.Param(MINIMUM_INCREMENT, ge=MINIMUM_INCREMENT, name="minimum_increment", description="By how much gold a new bid must be above the previous one for it to be accepted"),
            duration_hours: int = commands.Param(DEFAULT_DURATION, gt=MINIMUM_DURATION, name="duration_hours", description="How long the auction is expected to last in hours"),
            refine_bonus: Optional[int] = commands.Param(default=0, ge=0, le=100, name="refine_bonus", description="Refine bonus above tier (cauldron only)"),
            cooldown_reduction: Optional[int] = commands.Param(default=0, ge=0, le=100, name="cooldown_reduction", description="Cooldown reduction (cauldron only)")
    ):
        # A crafted item instance may be generated if the specified item id is a craft-able such as a cauldron or rings. Item creation will be deferred as late as possible but may be to be generated
        # right away whenever the crafting may result in randomization (e.g., cauldrons) so that the rolled staff are displayed in the auction description.
        # 
        # Auction will last about the specified duration, but not exactly as it will allow a countdown period when a new bid occurs to prevent sniping (Dynamic closing auction). The countdown will start
        # after (duration - 1 hour), with the countdown reset every time a new bid is made during the countdown phase.
        # 
        # In system/npc auctions, the winning bid money gets destroyed instead of being given back to players
        # Parameters
        # ----------
        # item_id:            The item id without the unique id part, so only the part before the / for non-fungible items (e.g., cherb for common herb, lring for low-grade storage ring)
        # quantity:           The item quantity, only valid for fungible items, will be forced to 1 for other cases
        # minimum_bid:        The first bid will have to be at least this value, if quantity is more than one then this is the minimum price for the lot, it is NOT a unit price
        # minimum_increment:  By how much gold a new bid must be above the previous one for it to be accepted
        # duration_hours:     How long the auction is expected to last in hours. The exact value can actually be different in very active auction since the final countdown cans be reset on new bid
        # refine_bonus:       The fixed refine bonus rate for the auctioned cauldron (only used if the specified item_id is a cauldron type)
        # cooldown_reduction: The fixed cooldown reduction for the auctioned cauldron (only used if the specified item_id is a cauldron type)

        await inter.response.defer()

        if await self._validate_add_parameters(inter, item_id, minimum_bid, minimum_increment, duration_hours, True):
            item_code, unique_id = convert_id(item_id)
            if unique_id:
                embed = BasicEmbeds.exclamation(f"admin_add generates new item instance when needed so unique ids should not be provided")
                await inter.followup.send(embed=embed)
            else:
                view = ConfirmDelete(inter.author.id)
                await inter.followup.send(
                    f"You're about to start a system auction for `{quantity if quantity > 0 else 1} x {item_id}` "
                    f"lasting `{duration_hours} hours`, with a `{minimum_bid:,} gold` minimum bid and a minimum increment of `{minimum_increment:,} gold`."
                    f"\n\nDo you want to continue?", view=view)
                await view.wait()
                if view.confirm:
                    quantity = quantity if quantity >= 1 else 1
                    props: dict[str, int] = {}
                    if refine_bonus > 0:
                        props[PROP_CAULDRON_REFINE_BONUS] = refine_bonus

                    if cooldown_reduction > 0:
                        props[PROP_CAULDRON_COOLDOWN_REDUCTION] = cooldown_reduction

                    result = await generate_unique_item(item_code, props if len(props) > 0 else None)
                    if result is None:
                        embed = BasicEmbeds.exclamation(f"{item_code} does not exist")
                        await inter.followup.send(embed=embed, view=None)
                    else:
                        full_id, item_type, success = result
                        if not success:
                            embed = BasicEmbeds.exclamation(f"The specified refine_bonus and cooldown_reduction does not respect the {item_id} constraints")
                            await inter.followup.send(embed=embed, view=None)
                        else:
                            if item_type in UNSTACKABLE_ITEM_TYPES:
                                quantity = 1

                            house: AuctionHouse = AuctionHouse()
                            remaining_lifespan = ORIGIN_QI_LIFESPAN if item_code == ITEM_TYPE_ORIGIN_QI else None
                            await house.create_auction(inter=inter, item_id=full_id, quantity=quantity, minimum_bid=minimum_bid, minimum_increment=minimum_increment, duration_hours=duration_hours, remaining_lifespan=remaining_lifespan,
                                                       system_auction=True)
                else:
                    embed = BasicEmbeds.exclamation(f"Command stopped by the user")
                    await inter.followup.send(embed=embed, view=view)

    @slash_auction_admin.sub_command(name="end", description="Forces an auction to end immediately as if its final countdown had ended.")
    async def slash_auction_admin_end(self, inter: disnake.CommandInteraction, auction_id: str = commands.Param(name="auction_id", description="The auction id (can be found in the auction's footer)")) -> None:
        await self._force_auction_update(inter, int(auction_id), f"Auction {auction_id} was forcefully ended", lambda auction: auction.end())

    @slash_auction_admin.sub_command(name="refresh", description="Forces the display (embed) refresh of a given auction.")
    async def slash_auction_admin_refresh(self, inter: disnake.CommandInteraction, auction_id: str = commands.Param(name="auction_id", description="The auction id (can be found in the auction's footer)")):
        await self._force_auction_update(inter, int(auction_id), f"Auction {auction_id} display was refreshed")

    @staticmethod
    async def _force_auction_update(inter: disnake.CommandInteraction, auction_id: int, message: str, action: Optional[Callable[[AuctionedItem], Coroutine[Any, Any, Any]]] = None):
        await inter.response.defer()

        house: AuctionHouse = AuctionHouse()
        auction: AuctionedItem = house.get_auction(auction_id)
        if auction is None:
            # Could force a load from database here to allow admin to handle strange issues where not everything would be in RAM
            await inter.followup.send(embed=BasicEmbeds.exclamation(f"There's no auctioned item with id {auction_id}, or it already ended"))
        else:
            if action is not None:
                await action(auction)

            await house.refresh_message(auction)
            await inter.followup.send(embed=BasicEmbeds.exclamation(message))

    # ============================================== "Real" methods =============================================

    @staticmethod
    async def _check_oqi_lifespan(inter: disnake.CommandInteraction, view: ConfirmDelete, item_id) -> Optional[int]:
        remaining_lifespan = None
        if item_id == ITEM_TYPE_ORIGIN_QI:
            exists_until = await unregister_item_expiration(inter.author.id, item_id)
            remaining_lifespan = exists_until - time()
            if remaining_lifespan < _MINIMUM_OQI_REMAINING_LIFETIME.total_seconds():
                await inter.followup.send(f"Origin Qi needs to have a remaining lifespan of at least {_MINIMUM_OQI_REMAINING_LIFETIME} to be auctioned.", view=view)
                return -1

        return remaining_lifespan

    @staticmethod
    async def _validate_add_parameters(inter: disnake.CommandInteraction, item_id: str, minimum_bid: int, minimum_increment: int, duration_hours: int, allow_chests: bool = False) -> bool:
        valid = True
        if len(item_id) == 0:
            valid = False
            await inter.edit_original_message(embed=BasicEmbeds.wrong_cross(f"Please specify a valid item id"))
        elif minimum_bid < MINIMUM_BID:
            valid = False
            await inter.edit_original_message(embed=BasicEmbeds.wrong_cross(f"Please set the minimum bid of at least {MINIMUM_BID:,} gold"))
        elif minimum_increment < MINIMUM_INCREMENT:
            valid = False
            await inter.edit_original_message(embed=BasicEmbeds.wrong_cross(f"Please set the minimum increment of at least {MINIMUM_INCREMENT:,} gold"))
        elif duration_hours < MINIMUM_DURATION:
            valid = False
            await inter.edit_original_message(embed=BasicEmbeds.wrong_cross(f"Please set the duration of at least {MINIMUM_DURATION:,} hours"))
        elif duration_hours > MAXIMUM_DURATION:
            valid = False
            await inter.edit_original_message(embed=BasicEmbeds.wrong_cross(f"Please set the duration of at most {MAXIMUM_DURATION:,} hours"))
        else:
            item_code, _ = convert_id(item_id)
            definition: Optional[ItemDefinition] = ItemCompendium().get(item_code)
            if definition is None:
                valid = False
                await inter.edit_original_message(embed=BasicEmbeds.item_not_found())
            if definition.type == ITEM_TYPE_CHEST and not allow_chests:
                valid = False
                await inter.edit_original_message(embed=BasicEmbeds.wrong_cross(f"Chests cannot be added to auction"))

        return valid


# =================================== Bootstrap and util class-level functions ==================================


def _log(user_id: Union[int, str], message: str):
    log_event(user_id, _SHORT_NAME, message)


# The bootstrap code, including the singleton instance
def setup(bot):
    cog = AuctionHouseCog(bot)
    bot.add_cog(cog)
    _log("system", f"{cog.name} Created")

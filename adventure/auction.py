from __future__ import annotations

import traceback
from asyncio import Lock
from datetime import datetime, timedelta
from typing import Optional, Union, Any

import disnake

from character.player import PlayerRoster, Player
from utils.CommandUtils import add_temp_item, destroy_crafted_item, add_market_points_for_sale
from utils.Database import AllRings, AuctionDao, Crafted
from utils.DatabaseUtils import compute_market_userinfo
from utils.EconomyUtils import add_tax_amount
from utils.Embeds import BasicEmbeds
from utils.InventoryUtils import add_to_inventory, check_inv_weight, combine_id, convert_id, ITEM_TYPE_CAULDRON, ITEM_TYPE_ORIGIN_QI, ITEM_TYPE_RING
from utils.LoggingUtils import log_event
from utils.Styles import COLOR_LIGHT_GREEN
from utils.base import PrerequisiteNotMetException, PlayerInputException, singleton, BaseStarfallPersistentView
from world.continent import Continent
from world.compendium import ItemCompendium, ItemDefinition

MINIMUM_BID = 100_000_000
MINIMUM_INCREMENT = 10_000_000
MINIMUM_DURATION = 1
MAXIMUM_DURATION = 72
DEFAULT_DURATION = 24

COUNTDOWN_DURATION: timedelta = timedelta(hours=1)  # the auction will terminate once this delay pass without any new bid once the main phase ends
EXPECTED_LOOP_DELAY_SECONDS: int = 50

_CLAIM_BUTTON_LABEL = "Retrieve Item"
_MAXIMUM_RING_CONTENT_ITEM_DISPLAY = 20
_MAXIMUM_TIME_TO_CLAIM = timedelta(days=3)
_SHORT_NAME: str = "auction"


class InvalidBidException(PlayerInputException):
    def __init__(self, system_message: str, player_message: Optional[str] = None, player_embed: Optional[disnake.Embed] = None, ephemeral: bool = False):
        super().__init__(system_message, player_message, player_embed, ephemeral)


class UnknownItemException(PlayerInputException):
    def __init__(self, system_message: str, player_message: Optional[str] = None, player_embed: Optional[disnake.Embed] = None, ephemeral: bool = False):
        super().__init__(system_message, player_message, player_embed, ephemeral)


class InsufficientFundException(PrerequisiteNotMetException):
    def __init__(self, system_message: str, player_message: Optional[str] = None, player_embed: Optional[disnake.Embed] = None, ephemeral: bool = False):
        super().__init__(system_message, player_message, player_embed, ephemeral)


class Bid:
    def __init__(self, auction_id: int, bidder_id: int, current_amount: int, maximum_amount: int, reserved_amount: int, tax_rate: int, bid_time: datetime):
        self.auction_id = auction_id
        self.bidder_id = bidder_id
        self.current_amount = current_amount
        self.maximum_amount = maximum_amount  # Assuming maximum > current check was done by the caller
        self.reserved_amount = reserved_amount
        self.tax_rate = tax_rate
        self.bid_time = bid_time

    def __str__(self):
        return f"{self.current_amount:,} gold bid for auction {self.auction_id} from {self.bidder_id} made on {self.bid_time} with the possibility to go up to {self.maximum_amount:,} gold."

    async def persist(self) -> Bid:
        await AuctionDao.filter(id=self.auction_id).update(winning_user_id=self.bidder_id,
                                                           winning_current_amount=self.current_amount,
                                                           winning_maximum_amount=self.maximum_amount,
                                                           winning_reserved_amount=self.reserved_amount,
                                                           winning_tax_rate=self.tax_rate,
                                                           winning_bid_time=datetime.utcfromtimestamp(self.bid_time.timestamp()))

        return self

    async def update_current_amount(self, new_current_amount) -> Bid:
        if new_current_amount > self.maximum_amount:
            raise InvalidBidException(f"You cannot bid over your maximum bid of {self.maximum_amount:,}")

        elif new_current_amount != self.current_amount:
            self.current_amount = new_current_amount
            self.bid_time = datetime.now()
            await AuctionDao.filter(id=self.auction_id).update(winning_current_amount=new_current_amount, winning_bid_time=datetime.utcfromtimestamp(self.bid_time.timestamp()))

        return self

    async def update_maximum_amount(self, new_maximum_amount) -> Bid:
        if new_maximum_amount < self.current_amount:
            raise InvalidBidException(f"Your updated maximum bid must be be at least your current bid of {self.current_amount:,}")

        elif new_maximum_amount != self.maximum_amount:
            old_maximum_amount = self.maximum_amount
            old_reserved_amount = self.reserved_amount
            old_tax_amount = old_reserved_amount - old_maximum_amount
            new_tax_amount = round(new_maximum_amount * self.tax_rate / 100)
            new_reserved_amount = new_maximum_amount + new_tax_amount

            if new_maximum_amount > old_maximum_amount:
                await _reserve_funds(self.bidder_id, new_maximum_amount - old_maximum_amount, new_tax_amount - old_tax_amount,
                                     f"You don't have enough gold to increase your maximum bid to {new_maximum_amount:,}",
                                     f"You don't have enough gold to increase your maximum bid to {new_maximum_amount:,} because of your buy tax rate."
                                     f"\n\nYou would need at least {new_reserved_amount:,} gold to raise your max bid to {new_maximum_amount:,} gold.")
            else:
                player: Player = PlayerRoster().get(self.bidder_id)
                async with player:
                    player.add_funds(old_reserved_amount - new_reserved_amount)

            self.maximum_amount = new_maximum_amount
            self.reserved_amount = new_reserved_amount
            await AuctionDao.filter(id=self.auction_id).update(winning_maximum_amount=new_maximum_amount, winning_reserved_amount=self.reserved_amount)

        return self


class AuctionedItem:
    def __init__(self, auction_id: Optional[int], msg_id: Optional[int], author_id: int, system_auction: bool, item_id: str, quantity: int, minimum_bid: int, minimum_increment: int,
                 start_time: datetime, duration: int, remaining_lifespan: Optional[timedelta] = None, countdown_start_time: Optional[datetime] = None, end_time: Optional[datetime] = None,
                 item_retrieved: bool = False, winning_bid: Optional[Bid] = None):
        self._id: Optional[int] = auction_id
        self._msg_id: int = msg_id
        self._author_id: int = author_id
        self._item_id: str = item_id  # The item id string, including its unique id if not a fungible item, using "<id>/<unique_id>" format
        self._minimum_bid: int = minimum_bid
        self._minimum_increment: int = minimum_increment
        self._quantity: int = quantity
        self._start_time: datetime = datetime.fromtimestamp(start_time.timestamp()) if start_time is not None else None
        self._duration: int = duration
        self._remaining_lifespan: Optional[timedelta] = remaining_lifespan
        self._system_auction: bool = system_auction
        self._countdown_start_time: Optional[datetime] = datetime.fromtimestamp(countdown_start_time.timestamp()) if countdown_start_time is not None else None
        self._end_time: Optional[datetime] = datetime.fromtimestamp(end_time.timestamp()) if end_time is not None else None
        self._item_retrieved: bool = item_retrieved
        self.winning_bid: Optional[Bid] = winning_bid
        self.lock: Lock = Lock()

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"Auction {self._id} for {self._quantity}x {self._item_id} that started on {self._start_time}"

    def __str__(self):
        return f"Auctioned {self._quantity}x {self._item_id} that started on {self._start_time}"

    # ================================================ Properties ===============================================

    @property
    def msg_id(self) -> Optional[int]:
        return self._msg_id

    @msg_id.setter
    def msg_id(self, value: Optional[int]):
        if value is not None:
            self._msg_id = value

    @property
    def author_id(self) -> Optional[int]:
        return self._author_id

    @property
    def completed(self) -> bool:
        return self.ended and self._item_retrieved

    @property
    def countdown_started(self) -> bool:
        return self._countdown_start_time is not None

    @property
    def countdown_start_time(self) -> Optional[datetime]:
        return self._countdown_start_time

    @property
    def counting_down(self) -> bool:
        return self.countdown_started and not self.ended

    @property
    def duration(self) -> int:
        return self._duration

    @property
    def ended(self) -> bool:
        return self._end_time is not None

    @property
    def end_time(self) -> Optional[datetime]:
        return self._end_time

    @property
    def expected_end_time(self) -> datetime:
        expected_countdown_start_time: float = self.expected_countdown_start_time.timestamp()
        latest_activity_time: float = expected_countdown_start_time if self.winning_bid is None else max(expected_countdown_start_time, self.winning_bid.bid_time.timestamp())
        return datetime.fromtimestamp(latest_activity_time) + COUNTDOWN_DURATION

    @property
    def expected_countdown_start_time(self) -> datetime:
        return self._start_time + timedelta(hours=self._duration) - COUNTDOWN_DURATION

    @property
    def expired(self) -> bool:
        """
        Check if this auction is expired.
        """
        if not self.ended:
            # Active auction
            return False
        elif self.completed:
            # Ended and item retrieved, can be considered expired
            return True
        elif self._remaining_lifespan is not None and datetime.now() > self._end_time + self._remaining_lifespan:
            # The item expired before being claimed
            return True
        else:
            return datetime.now().timestamp() > (self._end_time + _MAXIMUM_TIME_TO_CLAIM).timestamp()

    @property
    def id(self) -> Optional[int]:
        return self._id

    @property
    def item_definition(self) -> ItemDefinition:
        item_id, _ = convert_id(self._item_id)
        return ItemCompendium()[item_id]

    @property
    def item_id(self) -> str:
        return self._item_id

    @property
    def item_retrieved(self) -> bool:
        return self._item_retrieved

    @property
    def minimum_bid(self) -> int:
        return self._minimum_bid

    @property
    def minimum_increment(self) -> int:
        return self._minimum_increment

    @property
    def quantity(self) -> int:
        return self._quantity

    @property
    def remaining_lifespan(self) -> Optional[timedelta]:
        return self._remaining_lifespan

    @property
    def start_time(self) -> datetime:
        return self._start_time

    @property
    def system_auction(self) -> bool:
        return self._system_auction

    @property
    def title(self) -> str:
        item: ItemDefinition = self.item_definition
        return item.name if self.quantity == 1 else f"{self.quantity:,} x {item.name}"

    # ============================================== "Real" methods =============================================

    async def bid(self, bidder_id: int, amount: int, max_amount: int = 0) -> (bool, str):
        # Input validation
        if amount <= 0:
            raise InvalidBidException("You're supposed to bid something")

        # Auto-adjust max bid in case of inconsistent or default valued max bid
        max_amount = max_amount if max_amount >= amount else amount

        # Thread lock to handle concurrent bid issues
        async with self.lock:
            biddable, txt = self.is_biddable_by(bidder_id)
            if not biddable:
                raise InvalidBidException(txt)

            elif not self.winning_bid or not self.winning_bid.bidder_id:
                # First bid, just make sure it's sufficient for the auctioned item parameters
                return True, await self._handle_first_bid(bidder_id, amount, max_amount)

            elif bidder_id == self.winning_bid.bidder_id:
                # Winner is bidding again, allow only max bid update
                return False, await self._handle_max_bid_update(bidder_id, amount, max_amount)

            else:
                # There's an existing winning bid, then the new bid has to be higher the current bid by at least the minimum increment else just reject the bid and do nothing
                minimum_new_bid = self.winning_bid.current_amount + self._minimum_increment
                if amount < minimum_new_bid:
                    # The bid is insufficient, but maybe the max_bid is enough
                    if max_amount >= minimum_new_bid:
                        amount = minimum_new_bid
                    else:
                        # Nope, either the player is dumb, or someone else bid while he was placing his bid
                        raise InvalidBidException(f"Your bid must respect the `{self._minimum_increment:,}` gold minimum increment, so the bid should be at least is `{minimum_new_bid:,}`")

                # Generate a new bid with proper fund reservation, including buy tax
                new_bid: Bid = await self._instantiate_bid(bidder_id, amount, max_amount)

                # If we're here, then the bid is valid, but can still trigger a bidding battle with the currently winning bidder
                winner_id, winning_amount = self._handle_bidding_battle((self.winning_bid.bidder_id, self.winning_bid.maximum_amount), (bidder_id, max_amount), amount)
                if winner_id == bidder_id:
                    # The new bidder won the bidding battle

                    old_winning_bid = self.winning_bid

                    new_bid.current_amount = winning_amount
                    self.winning_bid = await new_bid.persist()

                    # Reimburse the reserved funds to the incumbent
                    player: Player = PlayerRoster().get(old_winning_bid.bidder_id)
                    async with player:
                        player.add_funds(old_winning_bid.reserved_amount)

                    incumbent_notif = BasicEmbeds.wrong_cross(f"You have been outbid on `{self._quantity}x {self._item_id}`. The new winning bid is `{winning_amount:,}` gold."
                                                              f"\n\nYour `{old_winning_bid.reserved_amount:,}` gold were sent back to your account.")
                    await Continent().whisper(old_winning_bid.bidder_id, incumbent_notif)

                    # Notify the bidder that his bid was accepted
                    if winning_amount == amount:
                        return True, self._compose_bid_accepted_msg(self.winning_bid)
                    else:
                        return (True, f"Your bid of `{amount:,}` gold for item {self._item_id} was immediately challenged resulting in an intense bidding war."
                                      f"\n\nYou had to raise your bid to `{winning_amount:,}` to finally get ahead of your adversary."
                                      f"\n\nYour bid may be automatically increased up to `{max_amount:,}` if other players attempt to outbid you."
                                      f"\n\n{self._compose_bid_reserve_msg(self.winning_bid)}")

                else:
                    # The incumbent bidder won the battle:

                    # Reimburse the reserved funds to the bidder
                    player: Player = PlayerRoster().get(bidder_id)
                    async with player:
                        player.add_funds(new_bid.reserved_amount)

                    # Update the current amount
                    await self.winning_bid.update_current_amount(winning_amount)

                    incumbent_notif = BasicEmbeds.exclamation(f"Your bid on `{self._quantity}x {self._item_id}` was automatically increased to `{winning_amount:,}` gold following a bidding contest with another participant.")
                    await Continent().whisper(self.winning_bid.bidder_id, incumbent_notif)

                    # Notify the bidder that his bid is insufficient given there was a new bid at winning_bid and that the new minimum bid is winning_amount + self.minimum_increment
                    return (True, f"Your `{amount:,}` gold bid for item {self.item_id} was immediately challenged resulting in a failed bidding war."
                                  f"\n\nYour adversary bid all the way to `{winning_amount:,}`, forcing you to bow down. All is not lost however, you still have time to place higher bid if you wish.")

    async def check_state(self) -> (bool, bool):
        state_changed = False
        now: float = datetime.now().timestamp()
        if not self.countdown_started:
            # Currently in the main phase, checking for its end with a 1/2 loop time shift to maximize chance to shift phase around the right time
            if now >= (self.expected_countdown_start_time - timedelta(seconds=EXPECTED_LOOP_DELAY_SECONDS / 2)).timestamp():
                # The main phase has ended, entering final phase
                _log("system", f"Starting countdown for auction {self.id}")
                await self._start_countdown()
                state_changed = True

        elif not self.ended:
            # Currently in the final phase, but not finished. assert self.countdown_start_time not None
            if now >= self.expected_end_time.timestamp():
                # The final phase has ended
                _log("system", f"Terminating auction {self._id} after normal countdown")
                await self.end()
                state_changed = True

        elif self.completed:
            _log("system", f"Cleaning auction {self._id} from RAM since item was claimed")
            # Shouldn't happen, but clean up in case it does
            state_changed = True

        elif self.expired:
            _log("system", f"Cleaning auction {self._id} from RAM since item expired")
            # TODO We could relist as a system auction here instead
            state_changed = True

        return state_changed

    async def claim(self, user_id: int) -> Optional[str]:
        if self.expired:
            return "The item expired, you cannot claim it anymore"
        elif self.winning_bid:
            if user_id == self.winning_bid.bidder_id:
                if self._item_retrieved:
                    return "You already retrieved the item"
                else:
                    return await self._handle_sold_retrieval(user_id)
            else:
                return "You didn't win this auction"
        else:
            if self.is_author(user_id):
                if self._item_retrieved:
                    return "You already retrieved the item"
                else:
                    return await self._handle_unsold_retrieval(user_id)
            else:
                return "You're not the one who set up this auction"

    async def end(self) -> AuctionedItem:
        now = datetime.now()
        self._end_time = now

        # Should always be ok, but let not take any chance
        countdown_start_time = self._countdown_start_time if self._countdown_start_time else now
        self._countdown_start_time = countdown_start_time

        if not self.winning_bid and self._system_auction:
            self._item_retrieved = True
            await self._destroy_generated_item()

        async with self.lock:
            await AuctionDao.filter(id=self._id).update(end_time=datetime.utcfromtimestamp(now.timestamp()), countdown_start_time=datetime.utcfromtimestamp(countdown_start_time.timestamp()), item_retrieved=self._item_retrieved)

        if self.winning_bid:
            # There's a winner
            # Send the sale money to the author
            sale_price = self.winning_bid.current_amount

            if not self._system_auction:
                # Pay the seller
                listing_tax_rate, sell_tax_rate, *_ = await compute_market_userinfo(self._author_id)
                seller_tax_rate = listing_tax_rate + sell_tax_rate
                seller_tax_amount = round(sale_price * seller_tax_rate / 100)
                amount_paid_to_seller = sale_price - seller_tax_amount

                player: Player = PlayerRoster().get(self._author_id)
                async with player:
                    player.add_funds(amount_paid_to_seller)

                await add_tax_amount(self._author_id, seller_tax_amount)
                await add_market_points_for_sale(self._author_id, sale_price)
                author_notif = BasicEmbeds.right_tick(f"Auctioned {self._quantity}x {self._item_id} was sold for {sale_price:,} gold."
                                                      f"\n\nYou got **`{amount_paid_to_seller:,}`** gold after {seller_tax_amount:,} gold commission ({seller_tax_rate}%).",
                                                      "Auction Item Sold!")
            else:
                author_notif = ""

            # Adjust the buyer's balance and tax data
            winner_id = self.winning_bid.bidder_id
            buy_tax_rate = self.winning_bid.tax_rate
            buyer_tax_amount = round(sale_price * buy_tax_rate / 100)
            buyer_total_price = sale_price + buyer_tax_amount
            await add_tax_amount(winner_id, buyer_tax_amount)

            # unfreeze the leftover reserved funds of the winning bidder
            leftover_funds = self.winning_bid.reserved_amount - buyer_total_price
            if leftover_funds > 0:
                player: Player = PlayerRoster().get(winner_id)
                async with player:
                    player.add_funds(leftover_funds)

            msg = (f"You won auctioned `{self._quantity}x {self._item_id}` for `{sale_price:,}` and paid a `{buyer_tax_amount:,}` gold commission (`{buy_tax_rate}%`)."
                   f"\n\nYou can claim the item by going to the auction house and click the \"{_CLAIM_BUTTON_LABEL}\" button.")
            if leftover_funds > 0:
                msg = msg + f"\n\nThe leftover `{leftover_funds:,}` gold from your maximum bid reserve was sent back to your account"

            winner_notif = BasicEmbeds.right_tick(msg, "Auction Won!")
            await Continent().whisper(winner_id, winner_notif)
        else:
            # No one bid on the item(s)
            author_notif = BasicEmbeds.wrong_cross(f"Auctioned `{self._quantity}x {self._item_id}` could not be sold."
                                                   f"\n\nYou can retrieve your item by going to the auction house and click the \"{_CLAIM_BUTTON_LABEL}\" button, "
                                                   f"but you will have to pay the commission based on your market tier and the `{self._minimum_bid:,}` gold minimum bid.",
                                                   "Auction Item Unsold!")

        # System auctions don't technically have player authors
        if not self._system_auction:
            await Continent().whisper(self._author_id, author_notif)

        return self

    def has_winning_bid(self) -> bool:
        return self.winning_bid is not None

    async def insert(self) -> AuctionDao:
        item_code, unique_id = convert_id(self._item_id)
        lifespan = None if self._remaining_lifespan is None else self._remaining_lifespan.total_seconds()

        dto = await AuctionDao.create(user_id=self._author_id, msg_id=self._msg_id, system_auction=self._system_auction,
                                      item_id=item_code, unique_id=unique_id, quantity=self._quantity, minimum_bid=self._minimum_bid, minimum_increment=self._minimum_increment,
                                      start_time=datetime.utcfromtimestamp(self._start_time.timestamp()), duration=self._duration, item_remaining_lifespan=lifespan, countdown_start_time=None, end_time=None, item_retrieved=False,
                                      winning_user_id=None, winning_current_amount=None, winning_maximum_amount=None, winning_reserved_amount=None, winning_tax_rate=None, winning_bid_time=None)

        self._id = dto.id

        return dto

    def is_author(self, user_id: int) -> bool:
        return not self._system_auction and user_id == self._author_id

    def is_biddable_by(self, bidder_id: int) -> (bool, str):
        if self.is_author(bidder_id):
            # Cannot bid on your own item
            _log(bidder_id, f"Attempted to bid on their own item (auction {self._id})")
            return False, f"You cannot bid on your own item"

        elif self._end_time:
            # This auction ended
            _log(bidder_id, f"Bid sent while auction {self._id} has already ended")
            return False, f"The auction {self._id} already ended"

        else:
            # Biddable
            return True, ""

    def is_winner(self, user_id: int) -> bool:
        return self.winning_bid is not None and self.winning_bid.bidder_id == user_id

    @staticmethod
    def _combine_retrieve_message(base_msg: str, msg_addendum: Optional[str]) -> str:
        if msg_addendum is None:
            return base_msg

        return f"{base_msg}\n\n{msg_addendum}"

    def _compose_bid_accepted_msg(self, bid: Bid) -> str:
        amount = bid.current_amount
        max_amount = bid.maximum_amount
        msg = (f"Your bid of `{amount:,}` gold was successfully placed for item {self._item_id}."
               f"\n\nYour bid may be automatically increased up to `{max_amount:,}` if other players attempt to outbid you."
               f"\n\n{self._compose_bid_reserve_msg(bid)}")

        return msg

    @staticmethod
    def _compose_bid_reserve_msg(bid: Bid) -> str:
        reserve = bid.reserved_amount
        tax_rate = bid.tax_rate
        return f"The auction house reserved `{reserve:,}` of your gold to cover their `{tax_rate}%` commission and allow you to go up to your maximum bid."

    async def _destroy_generated_item(self) -> bool:
        _, unique_id = convert_id(self._item_id)
        if not unique_id:
            return False

        # The item was crafted by the system for auction purpose
        return await destroy_crafted_item(self._item_id)

    async def _do_retrieve(self, user_id: int, ring_id: Optional[int], add_check: bool) -> Optional[str]:
        self._item_retrieved = True

        item_id = self._item_id

        msg_addendum = None
        await add_to_inventory(user_id, item_id, self._quantity, ring_id, add_check)
        if item_id == ITEM_TYPE_ORIGIN_QI:
            time_since_end = datetime.now() - self._end_time
            time_left = self._remaining_lifespan - time_since_end
            await add_temp_item(user_id, self._item_id, time_left)

            expire_on: datetime = datetime.now() + time_left
            msg_addendum = f"The Origin Qi will disappear <t:{int(expire_on.timestamp())}:F>"

        async with self.lock:
            await AuctionDao.filter(id=self._id).update(item_retrieved=True)

        return msg_addendum

    def _handle_bidding_battle(self, incumbent: tuple[int, int], challenger: tuple[int, int], challenger_starting_bid: int) -> tuple[int, int]:
        # There are two possible strategies in an automated bidding battle:
        # - The minimum_increment keeps being added alternatively between bidder1 and bidder2 until one of the player cannot bid anymore
        #       This option simulates a case where each bidder would bid in turn, but never over bidding more than the minimum increment
        # - Directly compare the maximum bid of each bidder and arbitrate for the highest, ideally with the other bidder's max bid plus the minimum increment
        #       This scenario would not happen in real life since it depends on a form of omniscience to know the maximum bid of each bidder
        #
        # For now we're using the second approach since it seems less contentious considering the bidder with the highest maximum bid can still lose with the 
        # first version in some cases where the maximum bid between the bidders differ by less than minimum_increment

        incumbent_id, incumbent_max = incumbent
        challenger_id, challenger_max = challenger

        # Firstly, an edge case to give a semblance of credibility. If the incumbent's max bid is not enough to outbid the challenger's initial bid by minimum_increment
        # then the challenger wins directly. This is necessary to prevent hacking the minimum_increment by tuning the maximum amount
        if incumbent_max < challenger_starting_bid + self._minimum_increment:
            return challenger_id, challenger_starting_bid

        if incumbent_max >= challenger_max:
            # Incumbent wins at the minimum of the challenger's maximum amount + minimum_increment and the incumbent's maximum bid
            return incumbent_id, min(incumbent_max, challenger_max + self._minimum_increment)
        else:
            # Challenger wins at the minimum of the incumbent's maximum amount + minimum_increment and the challenger's maximum bid
            return challenger_id, min(challenger_max, incumbent_max + self._minimum_increment)

    async def _handle_first_bid(self, bidder_id: int, amount: int, max_amount: int) -> str:
        if amount < self._minimum_bid:
            _log(bidder_id, f"Bid below the {self._minimum_bid:,} gold minimum bid of auction {self._id}")
            raise InvalidBidException(f"The minimum bid for this item is `{self._minimum_bid:,}`")

        # Get the buying tax rate

        # Keep the data in memory
        self.winning_bid = await self._instantiate_bid(bidder_id, amount, max_amount)
        await self.winning_bid.persist()
        _log(bidder_id, f"First bid of {amount:,} gold up to {max_amount:,} on auction {self._id}")

        return self._compose_bid_accepted_msg(self.winning_bid)

    async def _handle_max_bid_update(self, bidder_id: int, amount: int, max_amount: int) -> str:
        # The currently winning player wants to update his maximum bid, we don't allow to update the current bid amount until someone else bids over
        if amount > self.winning_bid.current_amount:
            return f"You cannot outbid yourself."

        old_maximum = self.winning_bid.maximum_amount
        if old_maximum != max_amount:
            await self.winning_bid.update_maximum_amount(max_amount)
            _log(bidder_id, f"Updated maximum bid from `{old_maximum:,}` up to `{max_amount:,}` gold on auction {self._id}")
            return f"Your maximum bid for item {self._item_id} was set to `{max_amount:,}`."
        else:
            return "Action canceled."

    async def _handle_sold_retrieval(self, user_id: int) -> str:
        has_room, ring_id, add_check = await check_inv_weight(channel=None, user_id=user_id, item_id=self._item_id, quantity=self._quantity, confirm_prompt=False)
        if not has_room:
            return "You don't have enough room in your equipped ring" if ring_id else "You don't have enough room in your inventory"

        msg_addendum = await self._do_retrieve(user_id, ring_id, add_check)
        _log(user_id, f"Retrieved their purchased {self._quantity}x {self._item_id} from auction {self._id}")
        return self._combine_retrieve_message(f"You retrieved your `{self._quantity}x {self._item_id}` purchase from the auction house", msg_addendum)

    async def _handle_unsold_retrieval(self, user_id: int) -> str:
        # FIXME: Should probably find a way to ask the player's confirmation before releasing the item since the taxes can be intense
        has_room, ring_id, add_check = await check_inv_weight(channel=None, user_id=user_id, item_id=self._item_id, quantity=self._quantity, confirm_prompt=False)
        if not has_room:
            return "You don't have enough room in your equipped ring" if ring_id else "You don't have enough room in your inventory"

        listing_tax_rate, sell_tax_rate, *_ = await compute_market_userinfo(self._author_id)
        sale_tax_rate = listing_tax_rate + sell_tax_rate
        sale_tax = round(self._minimum_bid * sale_tax_rate / 100)

        player: Player = PlayerRoster().get(user_id)
        async with player:
            money_check = player.spend_funds(sale_tax)

        if money_check:
            await add_tax_amount(user_id, sale_tax)
            await add_market_points_for_sale(user_id, self._minimum_bid)
            msg_addendum = await self._do_retrieve(user_id, ring_id, add_check)

            _log(user_id, f"Retrieved their unsold {self._quantity}x {self._item_id} from auction {self._id} after paying a {sale_tax:,} ({sale_tax_rate}%) commission to the auction house")
            return self._combine_retrieve_message(f"You retrieved `{self._quantity}x {self._item_id}` from the auction house, "
                                                  f"but had to pay `{sale_tax:,}` (`{sale_tax_rate}%`) in gold as a commission to compensate them", msg_addendum)
        else:
            return f"You couldn't retrieve `{self._quantity}x {self._item_id}` from the auction house because you couldn't afford to pay the commission of `{sale_tax:,}` gold to compensate them"

    async def _instantiate_bid(self, bidder_id: int, amount: int, max_amount: int) -> Bid:
        """
        Generate a new bid instance if player with the specified bidder_id can afford to make the bet. The Bid instance won't be persisted
        in the database, but the change to the player's gold balance will

        :param self:       the auction on which a new bid is needed
        :param amount:     the amount of the bid
        :param max_amount: the maximum amount the bidder is willing

        :return: a new Bid instance

        :raise: InsufficientFundException - if the bidder cannot afford the bid (either because of the max_amount itself, or the extra buy tax)
        """
        # Create a new bid object if the bidder can afford it. The bid itself isn't persisted, but the player fund reservation is written to the database
        # if the bidder has enough fund that is
        _, _, buy_tax, _, _, _ = await compute_market_userinfo(bidder_id)
        tax_amount = round(max_amount * buy_tax / 100)
        reserve_amount = max_amount + tax_amount

        # Reserve the funds right away to prevent multithreading command using shop and auction at the same time to fool the system and duplicate money
        await _reserve_funds(bidder_id, max_amount, tax_amount)

        return Bid(auction_id=self._id, bidder_id=bidder_id, current_amount=amount, maximum_amount=max_amount, reserved_amount=reserve_amount, tax_rate=buy_tax, bid_time=datetime.utcfromtimestamp(datetime.now().timestamp()))

    async def _start_countdown(self) -> AuctionedItem:
        now = datetime.now()
        self._countdown_start_time = now
        async with self.lock:
            await AuctionDao.filter(id=self._id).update(countdown_start_time=datetime.utcfromtimestamp(now.timestamp()))

        return self


@singleton
class AuctionHouse:
    def __init__(self):
        super().__init__()
        self._active_auctions: set[AuctionedItem] = set()
        self._countdown_auctions: set[AuctionedItem] = set()
        self._auctions_by_ids: dict[int, AuctionedItem] = dict()
        self._auctions_by_msg_ids: dict[int, AuctionedItem] = dict()
        self._active_auction_view: Optional[ActiveAuctionView] = ActiveAuctionView()
        self._ended_auction_view: Optional[EndedAuctionView] = EndedAuctionView()

    # ================================================ Properties ================================================

    @property
    def persistent_views(self) -> list[disnake.ui.View]:
        return [self._active_auction_view, self._ended_auction_view]

    # ============================================== "Real" methods =============================================

    def active_auctions(self, author_id: Optional[int] = None) -> list[AuctionedItem]:
        return [auction for auction in self._active_auctions if author_id is None or auction.author_id == author_id]

    def active_auction_count(self, author_id: Optional[int] = None) -> int:
        return len(self.active_auctions(author_id))

    def get_escrow(self, player_id: int) -> int:
        escrow: int = 0
        for auction in self._active_auctions:
            if auction.is_winner(player_id):
                escrow += auction.winning_bid.reserved_amount

        return escrow

    async def load(self):
        active_items: list[dict[str, Any]] = await AuctionDao.filter(item_retrieved=False).values()
        for item in active_items:
            auction_id: int = item["id"]
            msg_id: int = item["msg_id"]
            user_id: int = item["user_id"]
            system_auction: bool = item["system_auction"]
            item_id: str = item["item_id"]
            unique_id: Optional[str] = item.get("unique_id")
            quantity: int = item["quantity"]
            minimum_bid: int = item["minimum_bid"]
            minimum_increment: int = item["minimum_increment"]
            start_time: datetime = item["start_time"]
            duration: int = item["duration"]
            item_remaining_lifespan: Optional[int] = item["item_remaining_lifespan"]
            countdown_start_time: Optional[datetime] = item.get("countdown_start_time")
            end_time: Optional[datetime] = item.get("end_time")
            item_retrieved: bool = item["item_retrieved"]
            winning_user_id: Optional[int] = item.get("winning_user_id")
            winning_current_amount: Optional[int] = item.get("winning_current_amount")
            winning_maximum_amount: Optional[int] = item.get("winning_maximum_amount")
            winning_reserved_amount: Optional[int] = item.get("winning_reserved_amount")
            winning_tax_rate: Optional[int] = item.get("winning_tax_rate")
            winning_bid_time: Optional[datetime] = item.get("winning_bid_time")

            combined_item_id = combine_id(item_id, unique_id)
            winning_bid = None
            if winning_user_id:
                winning_bid = Bid(auction_id, winning_user_id, winning_current_amount, winning_maximum_amount, winning_reserved_amount, winning_tax_rate, winning_bid_time)

            lifespan = None if item_remaining_lifespan is None else timedelta(seconds=item_remaining_lifespan)

            auction = AuctionedItem(auction_id=auction_id, msg_id=msg_id, author_id=user_id, system_auction=system_auction,
                                    item_id=combined_item_id, quantity=quantity, minimum_bid=minimum_bid, minimum_increment=minimum_increment,
                                    start_time=start_time, duration=duration, remaining_lifespan=lifespan, countdown_start_time=countdown_start_time, end_time=end_time,
                                    item_retrieved=item_retrieved, winning_bid=winning_bid)

            self._auctions_by_ids[auction_id] = auction
            self._auctions_by_msg_ids[msg_id] = auction
            if not auction.ended:
                self._active_auctions.add(auction)
                if auction.counting_down:
                    self._countdown_auctions.add(auction)

    def unload(self):
        self._active_auctions: set[AuctionedItem] = set()
        self._countdown_auctions: set[AuctionedItem] = set()
        self._auctions_by_ids: dict[int, AuctionedItem] = dict()
        self._auctions_by_msg_ids: dict[int, AuctionedItem] = dict()

    # Loop management
    async def update_all_auction_states(self):
        await self._do_update_auction_states(self._active_auctions)

    async def update_countdown_auction_states(self):
        await self._do_update_auction_states(self._countdown_auctions)

    async def _do_update_auction_states(self, auctions: set[AuctionedItem]):
        for auction in auctions.copy():
            if not auction.ended:
                state_changed = await auction.check_state()
                if state_changed:
                    if auction.counting_down:
                        self._countdown_auctions.add(auction)

                    await self.refresh_message(auction)

            if auction.ended:
                _remove_silently(self._countdown_auctions, auction)
                if auction.completed or auction.expired:
                    # Wait for completed before removal from the active list to make sure to refresh the view after retrieval
                    _remove_silently(self._active_auctions, auction)
                    self._auctions_by_ids.pop(auction.id)
                    self._auctions_by_msg_ids.pop(auction.msg_id)

    # ============================================== "Real" methods =============================================

    async def bid_from_interaction(self, inter: Union[disnake.MessageInteraction | disnake.ModalInteraction], bid_amount: int, max_bid: int) -> AuctionHouse:
        auction = self.get_auction_from_interaction(inter)
        if auction is None:
            await inter.followup.send(f"This auction is no longer active", ephemeral=True)
        else:
            bidder_id = inter.author.id

            try:
                changed, player_message = await auction.bid(bidder_id, bid_amount, max_bid)
                if changed:
                    await self.refresh_message(auction)

                await inter.followup.send(player_message, ephemeral=True)

            except InvalidBidException as err:
                _log(bidder_id, f"Made an invalid bid on {auction.id}: {err.message}")
                await inter.followup.send(err.message, ephemeral=True)

            except InsufficientFundException as err:
                _log(bidder_id, f"Has insufficient fund to bid on {auction.id}: {err.message}")
                await inter.followup.send(err.message, ephemeral=True)

            except UnknownItemException as err:
                _log(bidder_id, f"Auction {auction.id} now has an invalid item_id: {err.message}")
                await inter.followup.send(err.message, ephemeral=True)

            except Exception as err:
                traceback.print_exc()
                _log(bidder_id, f"An unexpected error occurred while {bidder_id} placed a bid on {auction.id}: {err}")
                await inter.followup.send("An unexpected error occurred", ephemeral=True)

        return self

    async def check_claim_from_interaction(self, inter: disnake.MessageInteraction):
        msg_id = inter.message.id
        if msg_id not in self._auctions_by_msg_ids:
            await inter.followup.send("This auction was already fully completed", ephemeral=True)
        else:
            auction = self._auctions_by_msg_ids[msg_id]
            message = await auction.claim(inter.author.id)
            if message:
                await inter.followup.send(message, ephemeral=True)

            if auction.completed:
                await self.refresh_message(auction)

    def get_auction(self, auction_id: int) -> Optional[AuctionedItem]:
        if auction_id not in self._auctions_by_ids:
            if auction_id not in self._auctions_by_msg_ids:
                return None
            else:
                return self._auctions_by_msg_ids[auction_id]
        else:
            return self._auctions_by_ids[auction_id]

    def get_auction_from_interaction(self, inter: Union[disnake.MessageInteraction | disnake.ModalInteraction]) -> Optional[AuctionedItem]:
        msg_id = inter.message.id
        if msg_id not in self._auctions_by_msg_ids:
            return None
        else:
            return self._auctions_by_msg_ids[msg_id]

    async def update_maximum_bid_from_interaction(self, inter: disnake.ModalInteraction, max_bid: int):
        await self.bid_from_interaction(inter, 1, max_bid)

    async def validate_bid_preconditions(self, inter: disnake.MessageInteraction) -> (bool, Optional[AuctionedItem]):
        """
        Validate that the player that activated this interaction can bid on this auction
        """
        auction = self.get_auction_from_interaction(inter)
        if auction is None:
            await inter.response.send_message(f"This auction is no longer active", ephemeral=True)
            return False, None

        bidder_id = inter.author.id
        biddable, txt = auction.is_biddable_by(bidder_id)
        if not biddable:
            await inter.response.send_message(txt, ephemeral=True)
            return False, auction

        return True, auction

    async def create_auction(self, inter: disnake.CommandInteraction, item_id: str, quantity: int, minimum_bid: int, minimum_increment: int, duration_hours: int, remaining_lifespan: Optional[timedelta] = None,
                             system_auction: bool = False) -> AuctionedItem:
        start_time = datetime.now()

        auction = AuctionedItem(auction_id=None, author_id=inter.author.id, msg_id=None, system_auction=system_auction,
                                item_id=item_id, quantity=quantity, minimum_bid=minimum_bid, minimum_increment=minimum_increment,
                                start_time=start_time, duration=duration_hours, remaining_lifespan=remaining_lifespan)

        auction_embed = await AuctionEmbed(auction).initialize()

        continent: Continent = Continent()
        msg = await continent.auction_channel.send(embed=auction_embed, view=self._active_auction_view)
        auction.msg_id = msg.id
        self._auctions_by_ids[auction.id] = auction
        self._auctions_by_msg_ids[auction.msg_id] = auction
        self._active_auctions.add(auction)
        await auction.insert()

        author_description = "administrator" if system_auction else "player"
        _log(inter.author.id,
             f"Auction started by {author_description} for {quantity}x {item_id} for a {minimum_bid:,} gold minimum bid and a {minimum_increment:,} gold minimum increment, lasting {duration_hours} hours (auction_id: {auction.id})")

        if not system_auction:
            embed = BasicEmbeds.right_tick(f"Started an auction for `{quantity}x {item_id}` for a `{minimum_bid:,}` gold minimum bid and a `{minimum_increment:,}` gold minimum increment, lasting `{duration_hours} hours`.",
                                           "Auction Accepted")
            await continent.whisper(inter.author.id, embed=embed)

        return auction

    async def refresh_message(self, auction: AuctionedItem, force_view_refresh: bool = False):
        try:
            msg: disnake.Message = await Continent().auction_channel.fetch_message(auction.msg_id)
            if msg:
                embed = AuctionEmbed(auction)
                await embed.initialize()
                if auction.completed:
                    # Auction completed with the item retrieved, remove the button
                    await msg.edit(embed=embed, view=None)
                elif auction.ended:
                    # Auction has ended, but the item still has to be retrieved so display the claim button
                    await msg.edit(embed=embed, view=self._ended_auction_view)
                else:
                    # Only the auction display data should be updated, don't touch the buttons, unless it was forced
                    if force_view_refresh:
                        await msg.edit(embed=embed, view=self._active_auction_view)
                    else:
                        await msg.edit(embed=embed)
        except disnake.NotFound as e:
            _log("system", f"Could not locate the message for auction {auction.id} with msg_id: {auction.msg_id}: {e}")


class AuctionEmbed(disnake.Embed):
    # main auction embed used in auction channel
    def __init__(self, auction: AuctionedItem):
        super().__init__()
        self._auction: AuctionedItem = auction

    @property
    def auction(self) -> AuctionedItem:
        return self._auction

    async def initialize(self) -> AuctionEmbed:
        auction: AuctionedItem = self._auction
        item_id, unique_id = convert_id(auction.item_id)

        item: ItemDefinition = auction.item_definition
        if not item:
            raise UnknownItemException(f"Cannot identify item {item_id}")

        self.title = auction.title
        self.description = f"**Type : `{item.type}`** | **{item.tier_label} : `{item.tier}`**"
        self.color = COLOR_LIGHT_GREEN

        image = item.image
        if image is not None:
            self.set_thumbnail(file=image)

        self.add_field(name="Minimum Bid", value=f"`{auction.minimum_bid:,} gold`")
        self.add_field(name="Minimum Increment", value=f"`{auction.minimum_increment:,} gold`")

        if auction.ended:
            self.set_footer(text=f"Auction id: {auction.id}")
            if auction.has_winning_bid():
                self.add_field(name="Winning Bid", value=f"`{auction.winning_bid.current_amount:,} gold`", inline=False)
            else:
                self.add_field(name="Winning Bid", value="`Unsold`", inline=False)

            self.add_field(name="Ended On", value=f"<t:{int(auction.end_time.timestamp())}:F>", inline=False)
        else:
            self.set_footer(text=f"Press 'Bid' below to place a bid on this item. Auction id: {auction.id}")

            current_bid_str = f"`{auction.winning_bid.current_amount:,} gold`" if auction.has_winning_bid() else "`No bid yet`"
            self.add_field(name="Current Bid", value=current_bid_str, inline=False)

            if auction.countdown_start_time:
                self.add_field(name="Bid Closing", value=f"<t:{int(auction.expected_end_time.timestamp())}:R>", inline=False)
            else:
                self.add_field(name="Starting Countdown At", value=f"<t:{int(auction.expected_countdown_start_time.timestamp())}:F>", inline=False)

        self.add_field(name="Description", value=item.description, inline=False)
        self.add_field(name="Effect", value=item.effect_description, inline=False)

        if item.type == ITEM_TYPE_CAULDRON:
            characteristics = await self._list_cauldron_characteristics(unique_id)
            self.add_field(name="Cauldron Characteristics", value=characteristics, inline=False)
        elif item.type == ITEM_TYPE_RING:
            if auction.item_retrieved:
                # Don't list the ring contents once the item is retrieved
                self.add_field(name="Ring Contents", value="Unknown", inline=False)
            else:
                contents = await self._list_ring_contents(unique_id)
                self.add_field(name="Ring Contents", value=contents, inline=False)

        if auction.remaining_lifespan is not None:
            if auction.ended:
                expiration = auction.end_time + auction.remaining_lifespan
                self.add_field(name=f"Expiration", value=f"<t:{int(expiration.timestamp())}:F>", inline=False)
            else:
                self.add_field(name=f"Lifespan After Auction End", value=f"`{auction.remaining_lifespan}`", inline=False)

        return self

    @staticmethod
    async def _list_cauldron_characteristics(cauldron_unique_id: Union[int, str]) -> str:
        stats = await Crafted.get_or_none(id=cauldron_unique_id).values_list("stats")
        if not stats:
            # The cauldron was most likely purged from the database (assuming it was claimed)
            _log(0, f"Auctioned cauldron {cauldron_unique_id} could not be located in the crafted table")
            return "Unknown"
        else:
            stats = stats[0]
            cooldown_reduction = stats['alchemy_cdr']
            refine_bonus = stats['refine_bonus_per_tier_above']
            return f"- Alchemy Cooldown Reduction: `{cooldown_reduction}`%\n- Higher Tier Refine Bonus: `{refine_bonus}`%"

    @staticmethod
    async def _list_ring_contents(rung_unique_id: Union[int, str]) -> str:
        ring_contents = await AllRings.filter(id=rung_unique_id).order_by("items__item_id", "items__unique_id").values_list("items__item_id", "items__unique_id", "items__count")
        item_count = len(ring_contents)
        if item_count > 0:
            has_more = False
            if item_count > _MAXIMUM_RING_CONTENT_ITEM_DISPLAY:
                ring_contents = ring_contents[0:_MAXIMUM_RING_CONTENT_ITEM_DISPLAY]
                has_more = True

            ring_items_str = "- " + "\n- ".join(f"`{count}x {combine_id(item_id, unique_id)}`" for item_id, unique_id, count in ring_contents)
            if has_more:
                ring_items_str = ring_items_str + f"\n- Plus {item_count - _MAXIMUM_RING_CONTENT_ITEM_DISPLAY} more items..."
        else:
            ring_items_str = "Empty"

        return ring_items_str


class AuctionBidModal(disnake.ui.Modal):
    def __init__(self, inter: disnake.MessageInteraction, item_desc: str):
        super().__init__(
            title=f"Bidding on {item_desc[0:min(len(item_desc), 34)]}",
            custom_id=f"bidding_modal-{inter.id}",
            components=[
                disnake.ui.TextInput(
                    label="Bid Amount",
                    placeholder="Type the amount you want to bid",
                    custom_id="bid_amount",
                    style=disnake.TextInputStyle.short,
                    min_length=1,
                    max_length=12
                ),
                disnake.ui.TextInput(
                    label="Max Amount (will be reserved w/ tax)",
                    placeholder="Type the maximum amount you can possibly bid",
                    custom_id="max_bid_amount",
                    style=disnake.TextInputStyle.short,
                    max_length=12,
                    required=False
                )
            ],
        )

    async def callback(self, inter: disnake.ModalInteraction):
        await inter.response.defer(ephemeral=True)

        bid_amount_str = inter.text_values["bid_amount"]
        if len(bid_amount_str) > 0:
            try:
                bid_amount = int(bid_amount_str.replace(",", ""))
                try:
                    max_bid_amount_str = inter.text_values["max_bid_amount"]
                    max_bid_amount = int(max_bid_amount_str.replace(",", "")) if len(max_bid_amount_str) > 0 else bid_amount
                    await AuctionHouse().bid_from_interaction(inter, bid_amount, max_bid_amount)
                except ValueError:
                    await inter.followup.send("Please enter a valid maximum bid amount", ephemeral=True)
            except ValueError:
                await inter.followup.send("Please enter a valid bid amount", ephemeral=True)
        else:
            await inter.followup.send("Please enter a valid bid amount", ephemeral=True)


class AuctionMaxBidUpdateModal(disnake.ui.Modal):
    def __init__(self, inter: disnake.MessageInteraction, item_desc: str):
        super().__init__(
            title=f"Set max bid for {item_desc[0:min(len(item_desc), 29)]}",
            custom_id=f"bidding_modal-{inter.id}",
            components=[
                disnake.ui.TextInput(
                    label="Max Amount (will be reserved w/ tax)",
                    placeholder="Type the maximum amount you can possibly bid",
                    custom_id="max_bid_amount",
                    style=disnake.TextInputStyle.short,
                    max_length=12,
                )
            ],
        )

    async def callback(self, inter: disnake.ModalInteraction):
        await inter.response.defer(ephemeral=True)

        max_bid_amount_str = inter.text_values["max_bid_amount"]
        if len(max_bid_amount_str) > 0:
            try:
                max_bid_amount = int(max_bid_amount_str.replace(",", ""))
                await AuctionHouse().update_maximum_bid_from_interaction(inter, max_bid_amount)
            except ValueError:
                await inter.followup.send("Please enter a valid maximum bid amount", ephemeral=True)
        else:
            await inter.followup.send("Please enter a valid maximum bid amount", ephemeral=True)


class ActiveAuctionView(BaseStarfallPersistentView):
    # Active auction view used in auction channel
    def __init__(self):
        super().__init__()

    # Bid button so they can bid
    @disnake.ui.button(label="Bid", style=disnake.ButtonStyle.green, custom_id="starfall:auction:bid")
    async def auction_bid(self, _: disnake.ui.Button, inter: disnake.MessageInteraction):
        biddable, auction = await AuctionHouse().validate_bid_preconditions(inter)
        if biddable:
            # Send the right modal as the response
            if auction.is_winner(inter.author.id):
                await inter.response.send_modal(AuctionMaxBidUpdateModal(inter, auction.title))
            else:
                await inter.response.send_modal(AuctionBidModal(inter, auction.title))


class EndedAuctionView(BaseStarfallPersistentView):
    # Terminated auction view used in auction channel
    def __init__(self):
        super().__init__()

    @disnake.ui.button(label=_CLAIM_BUTTON_LABEL, emoji="🎁", style=disnake.ButtonStyle.blurple, custom_id="starfall:auction:claim")
    async def claim_button(self, _: disnake.ui.Button, inter: disnake.MessageInteraction):
        await inter.response.defer(ephemeral=True)
        await AuctionHouse().check_claim_from_interaction(inter)


# =================================== Bootstrap and util class-level functions ==================================


def _log(user_id: Union[int, str], message: str):
    log_event(user_id, _SHORT_NAME, message)


def _remove_silently(s: set[AuctionedItem], v: AuctionedItem) -> bool:
    try:
        s.remove(v)
        return True
    except KeyError:
        return False


async def _reserve_funds(user_id: int, base_amount: int, tax_amount: int = 0, message: Optional[str] = None, tax_message: Optional[str] = None):
    # FIXME: Ideally there should be a reserved gold entry that is shown on /balance so that player don't feel like their gold simply disappeared
    player: Player = PlayerRoster().get(user_id)
    async with player:
        total_amount = base_amount + tax_amount
        if total_amount > 0:
            if not player.spend_funds(total_amount):
                available_funds = player.current_gold
                if available_funds >= base_amount:
                    # Cannot afford because of the taxes
                    if tax_message:
                        effective_message = tax_message
                    elif message:
                        effective_message = message
                    else:
                        effective_message = f"You don't have enough money to bid up to `{base_amount:,}` gold because of your buying tax rate.\n\nYou would need at least `{total_amount:,}` gold to raise your max bid to `{base_amount:,}` gold."

                    raise InsufficientFundException(effective_message)
                else:
                    raise InsufficientFundException(message if message else f"You don't have enough money to bid up to `{base_amount:,}` gold.")
        elif total_amount < 0:
            player.add_funds(-total_amount)

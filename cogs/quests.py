import asyncio
import math
import random
from datetime import datetime, timedelta
from typing import Optional

import disnake
from disnake.ext import commands, tasks
from tortoise.exceptions import MultipleObjectsReturned

from character.player import PlayerRoster, Player
from utils.Database import GuildOptions, Quests
from utils.Embeds import BasicEmbeds
from utils.InventoryUtils import check_item_in_inv, remove_from_inventory, ConfirmDelete, convert_id
from utils.Styles import PLUS, RIGHT, CROSS
from utils.base import BaseStarfallCog, BaseStarfallEmbed
from utils.loot import RandomLoot, uniform_quantity, FlatEnergyLoot, ChoiceLoot, Loot, uniform_distribution, PSEUDO_ITEM_ID_GOLD
from world.compendium import ItemCompendium, ItemDefinition
from world.continent import Continent

QUEST_RANK_NAMES = {
    0: "Unranked",
    1: "Easy",
    2: "Doable",
    3: "Hard",
    4: "Impossible"
}

PERSISTENT_QUEST_BOARD_PAGE_SIZE: int = 10
EPHEMERAL_QUEST_BOARD_PAGE_SIZE: int = 5


def contributor_dict_to_str(contributors: dict[int, int]) -> str:
    list_prefix = "- "
    desc_list: list[str] = []
    for user_id, quantity in contributors.items():
        if quantity > 0:
            desc_list.append(f"<@{user_id}> {RIGHT} {quantity}")

    return list_prefix + f"\n{list_prefix}".join(desc_list)


def get_user_quest_count(user_id: int) -> int:
    global quest_board
    quest_count = 0
    for quest in quest_board.quests:
        if quest.user_id == int(user_id):
            quest_count += 1

    return quest_count


class Quest:
    def __init__(self, quest_id: int = None, user_id: int = None, rank: int = 0, item_id: str = "", quantity: int = 1, max_quantity: int = 1, rewards: Optional[dict[str, int]] = None, till: int = 0, contributors: Optional[dict[int, int]] = None):
        self._quest_id: int = quest_id
        self._rank: int = rank
        self._user_id: int = user_id
        self._item_id: str = item_id
        self._quantity: int = quantity
        self._max_quantity: int = max_quantity
        self._reward: dict[str, int] = rewards if rewards is not None else {}
        self._till: int = till
        self._contributors: dict[int, int] = {int(contributor_id): qty for contributor_id, qty in contributors.items()} if contributors is not None else {}
        self._rewards_list: list[tuple[int, float]] = []

    # ============================================= Special methods =============================================

    def __repr__(self) -> str:
        return f"Quest {{id: {self._quest_id}, rank: {self._rank}, item_id: {self._item_id}, number: {self._quantity}, rewards: {self._reward}}}"

    def __str__(self) -> str:
        return self.__repr__()

    # ================================================ Properties ===============================================

    @property
    def id(self) -> int:
        return int(self._quest_id)

    @property
    def user_id(self) -> int:
        return self._user_id

    @property
    def item_id(self) -> str:
        return self._item_id

    @property
    def amount(self) -> int:
        return self._quantity

    @property
    def max_amount(self) -> int:
        return self._max_quantity

    @property
    def contributors(self) -> dict[int, int]:
        return self._contributors

    @property
    def rewards(self) -> dict[str, int]:
        return self._reward

    @property
    def till(self) -> int:
        return self._till

    @property
    def rank(self) -> str:
        return QUEST_RANK_NAMES[self._rank]

    @property
    def owner(self) -> str:
        return "System" if self.is_system() else f"<@{int(self._user_id)}>"

    def is_system(self) -> bool:
        return self._user_id is None

    async def persist(self) -> None:
        quest = await Quests.create(user_id=self._user_id, item_id=self._item_id, max_count=self._max_quantity, rank=self._rank, count=self._quantity, reward=self._reward, till=self._till, contributors=self._contributors)
        self._quest_id = quest.id

    async def contribute(self, inter: disnake.CommandInteraction, quantity: int) -> bool:
        if inter.author.id in self._contributors.keys():
            embed = BasicEmbeds.wrong_cross("You've already contributed to the quest once")
            await inter.edit_original_message(embed=embed)
            return False

        if quantity < 1 or self._quantity <= 0:
            quantity = 1
        elif quantity > self._quantity:
            quantity = self._quantity

        item_check = await check_item_in_inv(inter.author.id, self._item_id, quantity)
        if not item_check:
            await inter.edit_original_message(embed=BasicEmbeds.not_enough_item(self._item_id))
            return False

        await remove_from_inventory(inter.author.id, self._item_id, quantity)

        self._contributors[inter.author.id] = quantity
        self._quantity -= quantity

        await Quests.filter(id=self._quest_id).update(contributors=self._contributors, count=self._quantity)
        await inter.edit_original_message(embed=BasicEmbeds.right_tick(f"You have contributed to the quest by {self.owner}\n\n{quantity}x {self._item_id} was removed from your inventory, and rewards will be given after the quests ends"))

        return True

    async def end(self) -> None:
        roster: PlayerRoster = PlayerRoster()

        main_contributor_count: int = 0
        contributed_quantity: int = 0
        full_quantity: int = self._max_quantity
        remaining_quantity: int = full_quantity
        for user_id, item_quantity in self._contributors.items():
            player = roster.get(user_id)
            if remaining_quantity > 0:
                if item_quantity > remaining_quantity:
                    # The player contributed more than what was remaining
                    effective_quantity: int = remaining_quantity
                    item_quantity = item_quantity - effective_quantity
                else:
                    effective_quantity: int = item_quantity
                    item_quantity = 0

                contributed_quantity += effective_quantity
                remaining_quantity -= effective_quantity

                main_contributor_count += 1
                if player is not None:
                    local_reward: dict[str, int] = {item_id: quantity * effective_quantity for item_id, quantity in self._reward.items()}
                    async with player:
                        await player.acquire_loot(local_reward)

            if item_quantity > 0:
                # Over contribution, don't penalise the player who posted for the extra
                reward_multiplier: float = 1 / (len(self._contributors.keys()) - main_contributor_count + 1)
                if player is not None:
                    local_reward: dict[str, int] = {item_id: max(round(quantity * reward_multiplier), 1) for item_id, quantity in self._reward.items()}
                    async with player:
                        await player.acquire_loot(local_reward)

        if not self.is_system():
            owner: Optional[Player] = roster.get(self._user_id)
            if owner is not None:
                unit_gold_reward: int = self._reward.get(PSEUDO_ITEM_ID_GOLD, 0)
                reserved_gold: int = unit_gold_reward * (self._max_quantity + 1)
                spent_gold: int = unit_gold_reward * contributed_quantity
                remaining_funds: int = reserved_gold - spent_gold
                items: dict[str, int] = {self._item_id: contributed_quantity}
                async with owner:
                    await owner.acquire_loot(items)
                    if remaining_funds > 0:
                        owner.add_funds(remaining_funds)

        await Quests.filter(id=self._quest_id).delete()


class QuestTemplate:
    def __init__(self, rank: int, possible_requests: Loot, reward: Loot):
        self._rank: int = rank
        self._possible_requests: Loot = possible_requests
        self._reward: Loot = reward

    # ============================================= Special methods =============================================

    def __repr__(self) -> str:
        return f"QuestModel {{rank: {self._rank}, possible_requests: {self._possible_requests}, reward: {self._reward}}}"

    def __str__(self) -> str:
        return self.__repr__()

    @property
    def rank(self) -> int:
        return self._rank

    @property
    def possible_requests(self) -> Loot:
        return self._possible_requests

    @property
    def reward(self) -> Loot:
        return self._reward

    def new_quest(self) -> Quest:
        requirements: dict[str, int] = self._possible_requests.roll()
        for item_id, quantity in requirements.items():
            till: int = int((datetime.now() + timedelta(minutes=10)).timestamp())
            return Quest(user_id=None, rank=self._rank, item_id=item_id, quantity=quantity, max_quantity=quantity, rewards=self._reward.roll(), till=till)

        raise ValueError(f"Quest requirements were badly configured")


class QuestBoardView(disnake.ui.View):
    def __init__(self, author, embeds):
        super().__init__(timeout=None)

        self.author = author
        self.embeds = embeds
        self.embed_count = 0

        self.prev_page.disabled = True
        if len(self.embeds) <= 1:
            self.next_page.disabled = True

    async def interaction_check(self, inter):
        return inter.author == self.author

    @disnake.ui.button(label="Prev", style=disnake.ButtonStyle.secondary)
    async def prev_page(self, _: disnake.ui.Button, interaction: disnake.MessageInteraction):
        self.embed_count -= 1

        embed = self.embeds[self.embed_count]

        self.next_page.disabled = False
        if self.embed_count == 0:
            self.prev_page.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

    @disnake.ui.button(label="Right", style=disnake.ButtonStyle.secondary)
    async def next_page(self, _: disnake.ui.Button, interaction: disnake.MessageInteraction):
        self.embed_count += 1
        embed = self.embeds[self.embed_count]

        self.prev_page.disabled = False
        if self.embed_count == len(self.embeds) - 1:
            self.next_page.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)


class QuestBoardEmbed(BaseStarfallEmbed):
    def __init__(self, quests: list[Quest], page: int = 0, page_size: int = PERSISTENT_QUEST_BOARD_PAGE_SIZE, description: Optional[str] = None, footer: Optional[str] = None):
        super().__init__()

        self.title = "Quest Board"
        if description is not None and len(description) > 0:
            self.description = description

        if footer is not None and len(footer) > 0:
            self.set_footer(text=footer)

        self._quests: list[Quest] = quests
        self._visible_quests: list[Quest] = []
        if len(quests) < page_size:
            self._visible_quests: list[Quest] = quests
        elif page == 0:
            self._visible_quests: list[Quest] = quests[:page_size]
        else:
            start_index: int = page * page_size
            end_index: int = start_index + page_size
            if end_index > len(quests):
                end_index = len(quests)

            self._visible_quests: list[Quest] = quests[start_index:end_index]

        compendium: ItemCompendium = ItemCompendium()
        for quest in self._visible_quests:
            user_str: str = "System Quest" if quest.user_id is None else f"<@{quest.user_id}> Quest"
            reward_str: str = compendium.describe_dict(quest.rewards, list_prefix=f"{PLUS} ")
            contributor_str: str = contributor_dict_to_str(quest.contributors) if len(quest.contributors) > 0 else "No Contributions"

            amount_buffer: int = quest.max_amount - quest.amount
            if amount_buffer < 0:
                extra_amount: str = f" ({quest.amount - quest.max_amount})"
                contribute_amount = quest.max_amount
            else:
                extra_amount: str = ""
                contribute_amount: int = amount_buffer

            quest_block: str = (f">>> {user_str}"
                                f"\n**Request:**"
                                f"\n`{quest.item_id}`: `{contribute_amount}{extra_amount}/{quest.max_amount}`"
                                f"\n**Reward:**"
                                f"\n{reward_str}"
                                f"\n**Contributors:**"
                                f"\n{contributor_str}"
                                f"\n**Expire:** <t:{int(quest.till + 10)}:R>")

            self.add_field(name=f"Quest {quest.id} | `{quest.rank}`", value=quest_block, inline=True)

    @property
    def quests(self) -> list[Quest]:
        return self._quests.copy()

    @property
    def visible_quests(self) -> list[Quest]:
        return self._visible_quests.copy()


class QuestBoard:
    def __init__(self):
        self._quests_list: list[Quest] = []
        self._system_quests_time: int = 0

    @property
    def quests(self) -> list[Quest]:
        return self._quests_list.copy()

    @property
    def is_quest_time(self) -> bool:
        return int(self._system_quests_time) < int((datetime.now()).timestamp())

    @property
    def embed(self) -> disnake.Embed:
        return QuestBoardEmbed(self._quests_list, footer=f"Showing {min(len(self._quests_list), PERSISTENT_QUEST_BOARD_PAGE_SIZE)} oldest quests")

    @property
    def all_embeds(self) -> list[disnake.Embed]:
        quests: list[Quest] = self._quests_list
        page_count: int = math.ceil(len(quests) / EPHEMERAL_QUEST_BOARD_PAGE_SIZE)
        return [QuestBoardEmbed(quests, page=page_num, page_size=EPHEMERAL_QUEST_BOARD_PAGE_SIZE, footer=f"Page {page_num + 1} of {page_count}") for page_num in range(page_count)]

    def user_embed(self, user_id: int) -> disnake.Embed:
        embed = BasicEmbeds.empty_embed()
        embed.title = "Your items"

        for quest in self._quests_list:
            if quest.user_id == user_id:
                reward_str = ItemCompendium().describe_dict(quest.rewards, list_prefix=f"{PLUS} ")
                contributor_str = contributor_dict_to_str(quest.contributors)

                if len(contributor_str) < 1:
                    contributor_str = "No Contributions"

                amount_buffer = quest.max_amount - quest.amount

                extra_amount = ""
                if amount_buffer < 0:
                    extra_amount = f" ({quest.amount - quest.max_amount})"

                contribute_amount = quest.max_amount if amount_buffer < 0 else amount_buffer

                quest_str = f"> you will receive {contribute_amount}{extra_amount}x {quest.item_id}\n> You'll pay approx {contribute_amount + 1}x {reward_str} gold \n> **Contributors:** {contributor_str} \n> **Expire:** <t:{int(quest.till + 10)}:R>"
                embed.add_field(name=f"Quest ID:{quest.id}", value=quest_str, inline=False)

        return embed

    @staticmethod
    async def board_id() -> int | None:
        try:
            quest_msg_id = await GuildOptions.get_or_none(name="quest_board").values_list("value", flat=True)
        except MultipleObjectsReturned:
            await GuildOptions.filter(name="quest_board").delete()
            quest_msg_id = None

        return quest_msg_id

    async def send_msg(self) -> int:
        await GuildOptions.filter(name="quest_board").delete()
        embed = self.embed
        msg = await Continent().quest_channel.send(embed=embed, view=QuestsView())

        await GuildOptions.create(name="quest_board", value=msg.id)

        return msg.id

    async def update_msg(self) -> None:
        embed = self.embed
        msg_id = await self.board_id()
        if msg_id is None:
            await self.send_msg()
        else:
            try:
                msg = await Continent().quest_channel.fetch_message(int(msg_id))
                await msg.edit(embed=embed, view=QuestsView())
            except disnake.NotFound:
                await self.send_msg()

    async def get_quests(self) -> None:
        all_quests = await Quests.all().order_by("till").values_list("id", "user_id", "item_id", "count", "max_count", "reward", "till", "contributors", "rank")

        for quest in all_quests:
            quest_id, user_id, item_id, amount, max_count, reward, till, contributors, rank = quest

            q = Quest(quest_id=quest_id, user_id=user_id, item_id=item_id, quantity=amount,
                      max_quantity=max_count, rewards=reward, till=till, contributors=contributors, rank=rank)

            self._quests_list.append(q)

    async def get_quest_time(self) -> None:
        quest_create_time = await GuildOptions.get_or_none(name="quest_create_time").values_list("value", flat=True)
        if quest_create_time is None:
            quest_create_time = int((datetime.now() + timedelta(seconds=10)).timestamp())
            await GuildOptions.create(name="quest_create_time", value=quest_create_time)

        self._system_quests_time = int(quest_create_time)

    async def increase_quest_time(self) -> None:
        self._system_quests_time = int((datetime.now() + timedelta(hours=4)).timestamp())
        await GuildOptions.filter(name="quest_create_time").update(value=self._system_quests_time)

    async def create_system_quests(self, num: int = 4) -> None:
        quests: list[Quest] = await QuestBuilder().generate_quest(num)
        for quest in quests:
            await quest.persist()
            self._quests_list.append(quest)

        await self.increase_quest_time()

    async def create_quest(self, user_id: int, item_id: str, quantity: int, rewards: dict[str, int], till: int) -> None:
        quest = Quest(user_id=user_id, item_id=item_id, quantity=quantity, max_quantity=quantity, rewards=rewards, till=till)
        await quest.persist()
        self._quests_list.append(quest)

    async def end_quest(self, quest_id: int) -> None:
        for quest in self._quests_list:
            if quest.id == int(quest_id):
                await quest.end()
                self._quests_list.remove(quest)

    async def contribute_to_quest(self, inter, quest_id: int, quest_amount: int) -> bool:
        for quest in self._quests_list:
            if quest.id == quest_id:
                return await quest.contribute(inter, quest_amount)

        return False


quest_board: Optional[QuestBoard] = None


class QuestBuilder:
    TEMPLATES: list[QuestTemplate] = [
        QuestTemplate(1,
                      RandomLoot(uniform_distribution(["lherb", "uherb", "ssnake_egg", "csnake_egg", "mouse_egg", "phoenix_egg", "rat_egg", "uwolf_egg", "snail_egg", "sabertooth_egg", "bape_egg", "wlion_egg", "boar_egg", "elemheartpill"]),
                                 uniform_quantity(1, 3),
                                 single_item_id=True),
                      ChoiceLoot([
                          RandomLoot({"chest_mixed_1": 1}, uniform_quantity(10, 50)),
                          RandomLoot({"chest_mixed_2": 1}, uniform_quantity(10, 50)),
                          FlatEnergyLoot(min_value=15, max_value=25),
                      ], [40, 40, 20])),

        QuestTemplate(2,
                      RandomLoot(
                          uniform_distribution(["abyss_rune", "oceanic_rune", "glacier_rune", "noxious_rune", "teagle_egg", "leopard_egg", "sserpent_egg", "rhino_egg", "weed_egg", "wood_egg", "sape_egg", "awlion_egg", "golem_egg", "bserpent_egg",
                                                "croc_egg", "sbeast_egg", "sdscorp_egg", "scorpemp_egg", "mherb", "flamedemonpill", "mcore_8", "mcore_3", "horn_1"]),
                          uniform_distribution([1, 2, 3, 5, 7]),
                          single_item_id=True),
                      ChoiceLoot([
                          RandomLoot({"chest_mixed_3": 1}, uniform_quantity(20, 50)),
                          RandomLoot({"chest_mixed_4": 1}, uniform_quantity(20, 50)),
                          RandomLoot({"chest_mixed_5": 1}, uniform_quantity(20, 50)),
                          FlatEnergyLoot(min_value=24, max_value=50)
                      ])),

        QuestTemplate(3,
                      RandomLoot(uniform_distribution(["divine_meat", "jade", "rune_base_3", "mcore_9", "pinnacle_lure", "mythical_rune", "claws_7", "horn_8", "pincers_7", "dragonbone", "purple_lion_crystal", "bserpent_egg"]),
                                 uniform_distribution([6, 7, 8, 9, 10, 12, 15]),
                                 single_item_id=True),
                      ChoiceLoot([
                          RandomLoot({"chest_mixed_6": 1}, uniform_quantity(10, 40)),
                          RandomLoot({"chest_mixed_7": 1}, uniform_quantity(10, 40)),
                          FlatEnergyLoot(min_value=49, max_value=75)
                      ], [40, 40, 20])),

        QuestTemplate(4,
                      RandomLoot(uniform_distribution(["pet_amp_1", "pet_amp_3", "pet_amp_2", "godpill", "bodhipill", "amethystlionflame"]),
                                 uniform_distribution([7, 14, 21]),
                                 single_item_id=True),
                      ChoiceLoot([
                          RandomLoot({"chest_mixed_8": 1}, uniform_quantity(5, 30)),
                          RandomLoot({"chest_mixed_9": 1}, uniform_quantity(5, 30)),
                          FlatEnergyLoot(min_value=74, max_value=100)
                      ], [40, 40, 20]))
    ]

    def __init__(self):
        super().__init__()

    async def generate_quest(self, quest_count: int = 4) -> list[Quest]:
        rank_list: list[int] = self._rank_list(quest_count)
        quests: list[Quest] = []
        for rank in rank_list:
            quest: Quest = self.TEMPLATES[rank - 1].new_quest()
            quests.append(quest)

        return quests

    @staticmethod
    def _rank_list(quest_count: int) -> list[int]:
        ranks = [1, 1, 1, 2]
        if random.randint(1, 100) <= 30:
            ranks.append(4)
            ranks.remove(1)

        if random.randint(1, 100) <= 70:
            ranks.append(3)
            ranks.remove(1)

        if len(ranks) < quest_count:
            for _ in range(len(ranks), quest_count):
                ranks.append(random.randint(1, 3))

        return ranks


class SubmitRequestedItemModal(disnake.ui.Modal):
    def __init__(self):
        components = [
            disnake.ui.TextInput(label="Quest ID", placeholder="Type the quest id from board (eg. 1, 12, 382)", custom_id="quest_id", style=disnake.TextInputStyle.short, max_length=5),
            disnake.ui.TextInput(label="Amount", placeholder="Type the amount you want to contribute", custom_id="quest_amount", style=disnake.TextInputStyle.short, value="1", max_length=2)
        ]
        super().__init__(
            title=f"Submit Quest",
            custom_id="filling_quest_id",
            components=components,
        )

    async def callback(self, inter):
        global quest_board
        await inter.response.defer(ephemeral=True)
        quest_id = int(inter.text_values["quest_id"])
        quest_amount = int(inter.text_values["quest_amount"])

        item_check = await quest_board.contribute_to_quest(inter, quest_id, quest_amount)
        if item_check:
            await quest_board.update_msg()


class QuestsView(disnake.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @disnake.ui.button(label="Contribute", emoji=PLUS, style=disnake.ButtonStyle.green, custom_id="quest_accept_button")
    async def confirm_button(self, _: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.send_modal(SubmitRequestedItemModal())

    @disnake.ui.button(label="View all quests", style=disnake.ButtonStyle.grey, custom_id="all_quest_button")
    async def all_quest_button(self, _: disnake.ui.Button, interaction: disnake.MessageInteraction):
        global quest_board
        embeds = quest_board.all_embeds
        await interaction.response.send_message(embed=embeds[0], view=QuestBoardView(interaction.author, embeds), ephemeral=True)


class QuestsSystem(BaseStarfallCog):

    def __init__(self, bot):
        super().__init__(bot, "Quest System", "quests")

    #     self.accept_view = False
    #     self.loop_count = 0
    #     if not self.end_quest_loop.is_running():
    #         self.end_quest_loop.start()

    def _do_unload(self):
        # self.end_quest_loop.cancel()
        pass

    async def _do_load(self):
        # await self.bot.wait_until_ready()

        # global quest_board
        # if quest_board is None:
        #     quest_board = QuestBoard()
        #     await quest_board.get_quest_time()
        #     await quest_board.get_quests()
        pass

    # @tasks.loop(seconds=5)
    # async def end_quest_loop(self):
    #     global quest_board
    #     for quest in quest_board.quests:
    #         if quest.till < int((datetime.now()).timestamp()):
    #             await quest_board.end_quest(quest.id)
    #             await quest_board.update_msg()
    #
    #     if self.loop_count == 0:
    #         await asyncio.sleep(20)
    #         self.loop_count = 1
    #
    #     if quest_board.is_quest_time:
    #         await quest_board.create_system_quests()
    #         await quest_board.update_msg()
    #
    #     if len(quest_board.quests) < 3:
    #         await quest_board.create_system_quests()
    #         await quest_board.update_msg()

    # @end_quest_loop.before_loop
    # async def before_end_quest_loop(self):
    #     await self.bot.wait_until_ready()
    #
    # async def _initialize_views(self) -> list[disnake.ui.View]:
    #     return [QuestsView()]
    #
    # # @commands.slash_command(name="request")
    # async def slash_request(self, inter: disnake.CommandInteraction):
    #     """
    #     Parent Command
    #     """
    #     pass

    # @slash_request.sub_command(name="add", description="Add a personal item quest")
    # async def slash_request_add(self, inter: disnake.CommandInteraction,
    #                             item_id: str = commands.Param(name="item_id", description="Item id you want to request"),
    #                             quantity: int = commands.Param(1, ge=1, name="quantity", description="Number of the item you want to request"),
    #                             gold: int = commands.Param(10_000, ge=10_000, name="gold", description="Gold given as reward (per amount)"),
    #                             days: int = commands.Param(2, ge=1, le=3, name="days", description="Days before quest ends")):
    #     global quest_board
    #     await inter.response.defer()
    #     itemid, unique_id = convert_id(item_id)
    #     if unique_id is not None:
    #         await inter.edit_original_message(f"Unique items can't be requested")
    #         return
    #
    #     reward_amount: int = gold * (quantity + 1)
    #
    #     view = ConfirmDelete(inter.author.id)
    #     await inter.edit_original_message(f"The bot will take out `{gold:,}` x (`{quantity:,}+1`) = `{reward_amount:,}` gold for distribution, excess gold will be given back. Continue?", view=view)
    #     await view.wait()
    #     if not view.confirm:
    #         await inter.edit_original_message(f"{CROSS} Rejected by user", view=None)
    #         return
    #
    #     item: Optional[ItemDefinition] = ItemCompendium()[itemid]
    #     if item is None:
    #         await inter.edit_original_message(embed=BasicEmbeds.item_not_found())
    #         return
    #
    #     quest_count = get_user_quest_count(inter.author.id)
    #     if quest_count > 5:
    #         await inter.edit_original_message(embed=BasicEmbeds.exclamation("You have reach the limit of quests you can post at a time (5/5)"))
    #         return
    #
    #     player: Player = PlayerRoster().find_player_for(inter)
    #     async with player:
    #         has_gold: bool = player.spend_funds(reward_amount)
    #
    #     if not has_gold:
    #         await inter.edit_original_message(embed=BasicEmbeds.not_enough_money())
    #         return
    #
    #     till = int((datetime.now() + timedelta(days=days)).timestamp())
    #     reward_dict = {PSEUDO_ITEM_ID_GOLD: gold}
    #
    #     await quest_board.create_quest(user_id=inter.author.id, item_id=item.id, quantity=quantity, rewards=reward_dict, till=till)
    #     await quest_board.update_msg()
    #     await inter.edit_original_message(embed=BasicEmbeds.right_tick(f"Successfully posted the request for `{quantity}x {itemid}`"))

    # # @slash_request.sub_command(name="view", description="View all your item requests")
    # async def slash_request_view(self, inter: disnake.CommandInteraction, quest_id: int):
    #     """
    #     View all your item requests
    #     """
    #     pass


def setup(bot):
    bot.add_cog(QuestsSystem(bot))
    print("[Quests] Loaded")

from abc import ABC, abstractmethod

import disnake

from typing import Union, Optional, cast

from disnake.ext import commands, tasks

from character.player import PlayerRoster, Player, PlayerActionButton
from adventure.ruins import RuinsManager, Ruins, ENERGY_TO_START, RuinsLeftEmbed, RuinsWelcomeEmbed, Room, RoomEmbed, BASE_ENERGY_COST_SEARCH, BASE_ENERGY_COST_EXPLORE, BASE_ENERGY_COST_FIGHT, BASE_ENERGY_COST_SNEAK, \
    BASE_ENERGY_COST_PER_ACTION
from utils.Embeds import BasicEmbeds
from utils.InventoryUtils import ConfirmDelete
from utils.LoggingUtils import log_event
from utils.base import BaseStarfallCog, PlayerInputException, PrerequisiteNotMetException, BaseStarfallPersistentView
from world.cultivation import PlayerCultivationStage

_SHORT_NAME: str = "ruins"
MINIMUM_CULTIVATION_MAJOR = 4


class RuinsManagerCog(BaseStarfallCog):
    def __init__(self, bot: commands.Bot):
        super().__init__(bot, "Ruins Manager Cog", _SHORT_NAME)
        self._welcome_view: Optional[disnake.ui.View] = None
        self._exhausted_view: Optional[disnake.ui.View] = None
        self._battle_view: Optional[disnake.ui.View] = None
        self._guarded_final_view: Optional[disnake.ui.View] = None
        self._guarded_view: Optional[disnake.ui.View] = None
        self._unguarded_view: Optional[disnake.ui.View] = None
        self._unguarded_final_view: Optional[disnake.ui.View] = None
        self._searched_view: Optional[disnake.ui.View] = None

    async def _initialize_views(self) -> list[disnake.ui.View]:
        self._welcome_view: disnake.ui.View = RuinsWelcomeView()
        self._exhausted_view: disnake.ui.View = RuinsPlayerExhaustedView()
        self._battle_view: disnake.ui.View = RuinsBattleView()
        self._guarded_view: disnake.ui.View = RuinsGuardedRoomView()
        self._guarded_final_view: disnake.ui.View = RuinsGuardedFinalRoomView()
        self._unguarded_view: disnake.ui.View = RuinsUnguardedRoomView()
        self._unguarded_final_view: disnake.ui.View = RuinsUnguardedFinalRoomView()
        self._searched_view: disnake.ui.View = RuinsSearchedRoomView()
        return [self._welcome_view, self._exhausted_view, self._battle_view, self._guarded_view, self._guarded_final_view, self._unguarded_view, self._unguarded_final_view, self._searched_view]

    # ============================================= Properties ============================================

    @property
    def welcome_view(self) -> disnake.ui.View:
        return self._welcome_view

    @property
    def exhausted_view(self) -> disnake.ui.View:
        return self._exhausted_view

    @property
    def battle_view(self) -> disnake.ui.View:
        return self._battle_view

    @property
    def guarded_view(self) -> disnake.ui.View:
        return self._guarded_view

    @property
    def guarded_final_view(self) -> disnake.ui.View:
        return self._guarded_final_view

    @property
    def unguarded_view(self) -> disnake.ui.View:
        return self._unguarded_view

    @property
    def unguarded_final_view(self) -> disnake.ui.View:
        return self._unguarded_final_view

    @property
    def searched_view(self) -> disnake.ui.View:
        return self._searched_view

    # ============================================= Discord commands ============================================

    @tasks.loop(hours=12)
    async def periodic_purge(self):
        # await RuinsManager().purge_irrelevant_ruins()
        pass

    # ============================================= Discord commands ============================================

    @commands.slash_command(name="ruins")
    async def slash_ruins(self, _: disnake.CommandInteraction):
        """
        Parent Command
        """
        pass

    @slash_ruins.sub_command(name="explore", description="Explore the continent looking for ancient ruins")
    async def slash_ruins_explore(self, inter: disnake.CommandInteraction):
        await inter.response.defer()

        player: Player = PlayerRoster().find_player_for(inter)
        if player.cultivation.major < MINIMUM_CULTIVATION_MAJOR:
            await inter.edit_original_message(embed=BasicEmbeds.exclamation(f"You must be at least {PlayerCultivationStage(MINIMUM_CULTIVATION_MAJOR, 0)} to explore ruins"))
            return

        confirm_view: ConfirmDelete = ConfirmDelete(inter.author.id, True)
        await inter.channel.send(f"Searching for ancient ruins will cost you {ENERGY_TO_START:,} energy, continue?", view=confirm_view)
        await confirm_view.wait()
        if not confirm_view.confirm:
            await inter.edit_original_message(embed=BasicEmbeds.exclamation(f"Exploration stopped by user"))
            return

        async with player:
            enough_energy: bool = player.consume_energy(ENERGY_TO_START)

        if enough_energy:
            await RuinsManager().generate_ruins(inter, player, self._welcome_view)
        else:
            await inter.edit_original_message(embed=BasicEmbeds.exclamation(f"You don't have enough energy to explore any ruins currently"))

    @slash_ruins.sub_command(name="refresh", description="Force ruins button refresh")
    async def slash_ruins_refresh(self, inter: disnake.CommandInteraction, ruins_id: str = commands.Param(name="ruins_id", description="Ruins id or message id")):
        await inter.response.defer(ephemeral=True)

        ruins_manager: RuinsManager = RuinsManager()
        ruins: Optional[Ruins] = ruins_manager.ruins(int(ruins_id))
        if ruins is None:
            await inter.send(f"Could not find ruins {ruins_id}", ephemeral=True)
        elif ruins.user_id != inter.user.id:
            await inter.send(f"You didn't start ruins {ruins_id}", ephemeral=True)
        else:
            if await _refresh_ruins_panel(inter, ruins):
                await inter.send(f"Ruins {ruins_id}'s UI was refreshed", ephemeral=True)
            else:
                await inter.send(f"Could not locate the ruins {ruins_id}'s message, make sure to issue refresh from the same channel as the ruins", ephemeral=True)


class BaseRuinsExplorationButton(PlayerActionButton, ABC):
    def __init__(self, style: disnake.ButtonStyle, label: str, custom_id: str):
        super().__init__(style=style, label=label, custom_id="ruins:" + custom_id)

    @property
    def base_energy_cost(self) -> int:
        return BASE_ENERGY_COST_PER_ACTION

    @abstractmethod
    async def execute(self, inter: disnake.MessageInteraction, ruins: Ruins, manager: RuinsManager) -> None:
        pass

    async def callback(self, inter: disnake.MessageInteraction) -> None:
        manager: RuinsManager = RuinsManager()
        ruins: Optional[Ruins] = manager.ruins(inter.message.id)
        if ruins is None:
            _log(inter.author.id, f"Could not locate ruins associated with message {inter.message.id}", "WARN")
        else:
            success, consumed_energy = await self._consume_energy(inter, ruins)
            if success:
                _log(inter.author.id, f"Clicked {type(self)} and consumed {consumed_energy} energy for ruins {ruins.id} with message {ruins.msg_id}")
                try:
                    await self.execute(inter, ruins, manager)
                except PlayerInputException as e:
                    _log(inter.user.id, e.system_message)
                    await e.send(inter)
                except PrerequisiteNotMetException as e:
                    _log(inter.user.id, e.system_message)
                    await e.send(inter)
                except Exception as e:
                    print("Error in ruins button callback", e)

                await _refresh_ruins_panel(inter, ruins)

    async def _consume_energy(self, inter: disnake.MessageInteraction, ruins: Ruins) -> tuple[bool, int]:
        if not await _check_interaction(inter, ruins):
            return False, 0

        base_cost: int = self.base_energy_cost
        if base_cost <= 0:
            return True, 0

        consumption_rate: int = ruins.type.energy_consumption_rate
        if consumption_rate <= 0:
            # Hopefully no type offer that would give infinite exp, let prevent it anyway
            return True, 0

        effective_cost = base_cost * consumption_rate // 100

        async with self.player(inter) as player:
            if player.consume_energy(effective_cost):
                ruins.register_energy_consumption(effective_cost)
                return True, effective_cost

        await inter.response.send_message(f"You need {effective_cost} energy to perform that action, you only have {player.energy}", ephemeral=True)
        return False, effective_cost


class BeginExplorationButton(BaseRuinsExplorationButton):
    def __init__(self):
        super().__init__(disnake.ButtonStyle.primary, "Begin", "begin")

    async def execute(self, inter: disnake.MessageInteraction, ruins: Ruins, manager: RuinsManager) -> None:
        await ruins.start()


class LeaveRuinsButton(BaseRuinsExplorationButton):
    def __init__(self):
        super().__init__(disnake.ButtonStyle.danger, "Leave", "leave")

    @property
    def base_energy_cost(self) -> int:
        return 0

    async def execute(self, inter: disnake.MessageInteraction, ruins: Ruins, manager: RuinsManager) -> None:
        await ruins.end()
        manager.unregister(ruins)


class ExploreDeeperButton(BaseRuinsExplorationButton):
    def __init__(self):
        super().__init__(disnake.ButtonStyle.primary, "Explore", "explore")

    @property
    def base_energy_cost(self) -> int:
        return BASE_ENERGY_COST_EXPLORE

    async def execute(self, inter: disnake.MessageInteraction, ruins: Ruins, manager: RuinsManager) -> None:
        await ruins.explore()


class FightGuardianButton(BaseRuinsExplorationButton):
    def __init__(self):
        super().__init__(disnake.ButtonStyle.success, "Fight", "fight")

    @property
    def base_energy_cost(self) -> int:
        return BASE_ENERGY_COST_FIGHT

    async def execute(self, inter: disnake.MessageInteraction, ruins: Ruins, manager: RuinsManager) -> None:
        await ruins.fight(self.player(inter))


class SearchRoomButton(BaseRuinsExplorationButton):
    def __init__(self):
        super().__init__(disnake.ButtonStyle.success, "Search Room", "search")

    @property
    def base_energy_cost(self) -> int:
        return BASE_ENERGY_COST_SEARCH

    async def execute(self, inter: disnake.MessageInteraction, ruins: Ruins, manager: RuinsManager) -> None:
        await ruins.search(self.player(inter))


class SneakPastGuardianButton(BaseRuinsExplorationButton):
    def __init__(self):
        super().__init__(disnake.ButtonStyle.secondary, "Sneak", "sneak")

    @property
    def base_energy_cost(self) -> int:
        return BASE_ENERGY_COST_SNEAK

    async def execute(self, inter: disnake.MessageInteraction, ruins: Ruins, manager: RuinsManager) -> None:
        await ruins.sneak(self.player(inter))


class BaseRuinsExplorationView(BaseStarfallPersistentView):
    def __init__(self):
        super().__init__()
        self._leave_button: LeaveRuinsButton = LeaveRuinsButton()

    @property
    def leave_button(self) -> LeaveRuinsButton:
        return self._leave_button

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:
        return await _check_interaction(inter, RuinsManager().ruins(inter.message.id))


class RuinsWelcomeView(BaseRuinsExplorationView):
    def __init__(self):
        super().__init__()
        self.add_item(BeginExplorationButton())
        self.add_item(self.leave_button)


class RuinsPlayerExhaustedView(BaseRuinsExplorationView):
    def __init__(self):
        super().__init__()
        self.add_item(self.leave_button)


class RuinsBattleView(BaseRuinsExplorationView):
    def __init__(self):
        super().__init__()
        self.add_item(FightGuardianButton())
        self.add_item(self.leave_button)


class RuinsGuardedRoomView(BaseRuinsExplorationView):
    def __init__(self):
        super().__init__()
        self.add_item(FightGuardianButton())
        self.add_item(SneakPastGuardianButton())
        self.add_item(self.leave_button)


class RuinsGuardedFinalRoomView(BaseRuinsExplorationView):
    def __init__(self):
        super().__init__()
        self.add_item(FightGuardianButton())
        self.add_item(self.leave_button)


class RuinsUnguardedRoomView(BaseRuinsExplorationView):
    def __init__(self):
        super().__init__()
        self.add_item(ExploreDeeperButton())
        self.add_item(SearchRoomButton())
        self.add_item(self.leave_button)


class RuinsUnguardedFinalRoomView(BaseRuinsExplorationView):
    def __init__(self):
        super().__init__()
        self.add_item(SearchRoomButton())
        self.add_item(self.leave_button)


class RuinsSearchedRoomView(BaseRuinsExplorationView):
    def __init__(self):
        super().__init__()
        self.add_item(ExploreDeeperButton())
        self.add_item(self.leave_button)


async def _check_interaction(inter: disnake.MessageInteraction, ruins: Optional[Ruins]) -> bool:
    if ruins is None:
        return False

    if inter.user.id == ruins.user_id:
        return True

    await inter.response.send_message("You can only explore ruins that you discovered yourself", ephemeral=True)
    return False


async def _refresh_ui_from_interaction(inter: disnake.MessageInteraction, embed: disnake.Embed, view: Optional[disnake.ui.View], file: Optional[disnake.File]) -> None:
    if file is None:
        await inter.response.edit_message(embed=embed, view=view, attachments=[])
    else:
        await inter.response.edit_message(embed=embed, view=view, file=file)


async def _refresh_ui_from_message(message: disnake.Message, embed: disnake.Embed, view: Optional[disnake.ui.View], file: Optional[disnake.File]) -> None:
    if file is None:
        await message.edit(embed=embed, view=view, attachments=[])
    else:
        await message.edit(embed=embed, view=view, file=file)


async def _refresh_ruins_panel(inter: Union[disnake.MessageInteraction, disnake.CommandInteraction], ruins: Ruins) -> bool:
    cog: RuinsManagerCog = cast(RuinsManagerCog, inter.bot.get_cog("RuinsManagerCog"))
    if ruins.ended:
        embed: RuinsLeftEmbed = RuinsLeftEmbed(inter.user, ruins)
        view: Optional[disnake.ui.View] = None
        file: Optional[disnake.File] = None
    elif not ruins.started:
        embed: RuinsWelcomeEmbed = RuinsWelcomeEmbed(inter.user, ruins)
        view: Optional[disnake.ui.View] = cog.welcome_view
        file: Optional[disnake.File] = None
    else:
        room: Room = ruins.current_room
        embed: RoomEmbed = RoomEmbed(inter.user, ruins)
        if room.searched:
            view: Optional[disnake.ui.View] = cog.exhausted_view if room.final_room else cog.searched_view
        elif room.guarded:
            if room.guardian_battle_finished:
                view: Optional[disnake.ui.View] = cog.exhausted_view
            elif room.sneak_failed or room.guardian_battle_started:
                view: Optional[disnake.ui.View] = cog.battle_view
            else:
                view: Optional[disnake.ui.View] = cog.guarded_final_view if room.final_room else cog.guarded_view
        else:
            view: Optional[disnake.ui.View] = cog.unguarded_final_view if room.final_room else cog.unguarded_view

        file: Optional[disnake.File] = embed.clear_current_file()

    if isinstance(inter, disnake.MessageInteraction):
        await _refresh_ui_from_interaction(inter, embed, view, file)
    else:
        try:
            _log(inter.author.id, f"Attempting to refresh buttons using view {type(view)} for ruins {ruins.id} with message {ruins.msg_id}")
            msg: disnake.Message = await inter.channel.fetch_message(ruins.msg_id)
            await _refresh_ui_from_message(msg, embed, view, file)
        except disnake.NotFound:
            return False

    return True


def _log(user_id: Union[int, str], message: str, level: str = "INFO"):
    log_event(user_id, _SHORT_NAME, message, level)


# The bootstrap code
def setup(bot: commands.Bot):
    cog = RuinsManagerCog(bot)
    bot.add_cog(cog)
    _log("system", f"{cog.name} Created")

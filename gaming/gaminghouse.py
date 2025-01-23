import json
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, TypeVar, Any, Union, Callable

import disnake
from disnake import Interaction, Thread, NotFound, Forbidden, HTTPException
from disnake.abc import GuildChannel, PrivateChannel, Messageable
from disnake.ui import Components, ModalUIComponent

from character.player import Player, PlayerRoster, PlayerActionButton
from gaming.catalog import GameCatalog
from gaming.game import Game, GameState, GameConfig, PROP_MAX_PLAYERS, PROP_ACTION_COUNT, PROP_ACTION_COUNT_EXTRA, GameAction, ActionMode, InvalidActionException
from utils.Database import ID_UNCREATED, GamingTableDao
from utils.LoggingUtils import log_event
from utils.ParamsUtils import ranking_str, mention, parse_int
from utils.base import singleton, BaseStarfallEmbed, FunctionalValidationException, BaseStarfallPersistentView, UnsupportedOperationError, PlayerInputException, BaseStarfallUserSelect, BaseStarfallTransientView, BaseStarfallChannelSelect, \
    PrerequisiteNotMetException
from utils.loot import Loot, is_pseudo_item_id, create_fixed_loot, loot_values
from world.continent import Continent
from world.compendium import ItemCompendium

T = TypeVar("T", bound="GamingTable")

_MODULE_ID: str = "gaming"


# =============================================================================================================================================================================================================================================
# =============================================================================================================== GamingTable =================================================================================================================
# =============================================================================================================================================================================================================================================
class GamingTable:
    def __init__(self, table_id: int, game: Game, config: GameConfig, sponsor: Optional[Player] = None, authorized_players: Optional[set[int]] = None, published: bool = False, ended: bool = False, state: Optional[GameState] = None,
                 setup_channel_id: Optional[int] = None, setup_msg_id: Optional[int] = None, publish_channel_id: Optional[int] = None, round_msg_ids: Optional[list[int]] = None, prizes: Optional[list[Loot]] = None,
                 expires_at: Optional[datetime] = None, created_at: datetime = datetime.now(), updated_at: datetime = datetime.now()):
        super().__init__()
        self._id: int = table_id
        self._game: Game = game
        self._config: GameConfig = config
        self._sponsor: Optional[Player] = sponsor
        self._authorized_players: Optional[set[int]] = authorized_players
        self._published: bool = published
        self._ended: bool = ended
        self._state: Optional[GameState] = state
        self._setup_channel_id: Optional[int] = setup_channel_id
        self._setup_msg_id: Optional[int] = setup_msg_id
        self._publish_channel_id: Optional[int] = publish_channel_id
        self._round_msg_ids: Optional[list[int]] = round_msg_ids.copy() if round_msg_ids is not None else []
        self._prizes: Optional[list[Loot]] = prizes.copy() if prizes is not None else []

        self._expires_at: Optional[datetime] = expires_at
        self._created_at: datetime = created_at
        self._updated_at: datetime = updated_at
        self._message: Optional[disnake.Message] = None

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"GamingTable {self}, game: {self._game}, config: {self._config}"

    def __str__(self) -> str:
        return f"{self._game.name} {self._game.instance_label}" if self._published else f"{self._game.name} setup"

    # ================================================ Properties ===============================================

    @property
    def authorized_players(self) -> Optional[set[int]]:
        if self._published:
            return self._game.authorized_players(self._state)
        else:
            return self._authorized_players.copy() if self._authorized_players is not None else None

    @authorized_players.setter
    def authorized_players(self, authorized_players: Optional[set[int]]) -> None:
        if self._published:
            raise ValueError("Cannot explicitly set authorized players once the game is started")

        self._authorized_players = authorized_players.copy() if authorized_players is not None else None

    @property
    def config(self) -> GameConfig:
        return self._config.copy()

    @config.setter
    def config(self, config: GameConfig) -> None:
        self._config = config.copy()

    @property
    def ended(self) -> bool:
        return self._ended

    @property
    def filled(self) -> bool:
        if not self._published:
            return False
        elif self._ended:
            return True

        if self._game.maximum_players is None:
            if self._config.maximum_players is None:
                return False

            max_players: int = self._config.maximum_players
        else:
            max_players: int = self._game.maximum_players if self._config.maximum_players is None else min(self._game.maximum_players, self._config.maximum_players)

        return self.authorized_players is not None and len(self.authorized_players) >= max_players

    @property
    def game(self) -> Game:
        return self._game

    @property
    def id(self) -> int:
        return self._id

    @property
    def current_round_completed(self) -> bool:
        return self._game.current_round_completed(self._state)

    @property
    def latest_msg_id(self) -> Optional[int]:
        if self.published:
            if self._round_msg_ids is None or len(self._round_msg_ids) == 0:
                return None
            else:
                return self._round_msg_ids[len(self._round_msg_ids) - 1]
        else:
            return None if self._setup_msg_id is None else self._setup_msg_id

    @property
    def maximum_players(self) -> Optional[int]:
        if self._config.maximum_players is None:
            return None if self._game.maximum_players is None else self._game.maximum_players
        else:
            return self._config.maximum_players if self._game.maximum_players is None else min(self._game.maximum_players, self._config.maximum_players)

    @property
    def prizes(self) -> Optional[list[Loot]]:
        return self._prizes.copy() if self._prizes is not None and len(self._prizes) > 0 else None

    @prizes.setter
    def prizes(self, prizes: Optional[list[Loot]]) -> None:
        if prizes is None or len(prizes) == 0 or self._game.produces_winning_odds:
            self._prizes = None
            return

        # Rankings support any number of prizes (equals to the max player to be precise), anything else that isn't winning odds supports only up to 2 (winner and consolation)
        if len(prizes) > 2 and not self._game.produces_ranking:
            raise PlayerInputException(f"Attempting to set more prizes than {self._game.name} allows", f"Games such as {self._game.name} only allow 2 prizes, one for the winner, and a consolation prize")

        self._prizes = prizes.copy()

    @property
    def publish_channel_id(self) -> Optional[int]:
        # That 'if' shouldn't be needed but since Python is awesome at protecting data then let add the check just in case
        if not self._published:
            return None

        return self._publish_channel_id

    @property
    def published(self) -> bool:
        return self._published

    @property
    def registering_moves(self) -> bool:
        return not self.ended and self.published and self.filled and not self.current_round_completed

    @property
    def registering_players(self) -> bool:
        return self._state is not None and self._state.action_state == GameState.STATE_REGISTRATION

    @property
    def requires_new_round(self) -> bool:
        return self._game.requires_new_round(self._state)

    @property
    def round_msg_ids(self) -> list[int]:
        return self._round_msg_ids.copy()

    @property
    def setup_channel_id(self) -> Optional[int]:
        return self._setup_channel_id

    @property
    def setup_msg_id(self) -> int:
        return self._setup_msg_id

    @property
    def sponsor(self) -> Optional[Player]:
        return self._sponsor

    @property
    def state(self) -> Optional[GameState]:
        return self._state

    # ============================================= "Real" methods ==============================================

    async def authorizes(self, inter: disnake.MessageInteraction) -> bool:
        player_id: int = inter.author.id
        if self._ended:
            # Game finished, no more action possible
            await inter.response.send_message(f"That {self.game.instance_label} had ended", ephemeral=True)
            return False
        elif self._published:
            # Only authorized players or potential registrations can go through
            if self.filled and player_id not in self.authorized_players:
                await inter.response.send_message(f"You're not allowed to take part of this {self.game.instance_label}", ephemeral=True)
                return False
        else:
            # Setup phase, only the sponsor can configure
            if self._sponsor is None or player_id != self._sponsor.id:
                await inter.response.send_message(f"That {self.game.instance_label} is not published yet", ephemeral=True)
                return False

        return True

    def add_authorized_player(self, player_id: int) -> bool:
        if self._published:
            raise ValueError("Cannot add authorized players once the game is launched, must use registration instead")

        if self._authorized_players is None:
            self._authorized_players: set[int] = {player_id}
            return True

        if player_id not in self._authorized_players:
            self._authorized_players.add(player_id)
            return True

        return False

    def is_sponsor(self, player_id: int) -> bool:
        return self._sponsor is not None and self._sponsor.id == player_id

    def linked_to_message(self, msg_id: int) -> bool:
        return msg_id == self._setup_msg_id or (self._round_msg_ids is not None and msg_id in self._round_msg_ids)

    async def message(self) -> disnake.Message:
        if self._message is None:
            if self._published:
                if self._publish_channel_id is None or len(self._round_msg_ids) == 0:
                    _log("system", f"Gaming Table {self.id} is published but doesn't have a publish channel id ({self._publish_channel_id}) or round message ids ({self._round_msg_ids})", "ERROR")
                    raise UnsupportedOperationError(f"Gaming Table {self.id} is published but doesn't have a publish channel id ({self._publish_channel_id}) or round message ids ({self._round_msg_ids})")

                channel_id: int = self._publish_channel_id
                message_id: int = self._round_msg_ids[len(self._round_msg_ids) - 1]
            else:
                if self._setup_channel_id is None or self._setup_msg_id is None:
                    _log("system", f"Gaming Table {self.id} is in setup mode but doesn't have either a setup channel id ({self._setup_channel_id}) or a setup message id ({self._setup_msg_id})", "ERROR")
                    raise UnsupportedOperationError(f"Gaming Table {self.id} is in setup mode but doesn't have either a setup channel id ({self._setup_channel_id}) or a setup message id ({self._setup_msg_id})")

                channel_id: int = self._setup_channel_id
                message_id: int = self._setup_msg_id

            self._message = await Continent().message(channel_id, message_id)

        return self._message

    async def next_round(self) -> bool:
        if self._published:
            return False

        # Initialize the game with the config
        new_state: GameState = self._game.next_round(self._state)
        if not new_state:
            return False

        action_view: disnake.ui.View = GamingHouse().get_view(new_state.key)
        channel: Optional[Union[Thread, GuildChannel]] = Continent().channel(self._publish_channel_id)

        self._state = new_state
        self._ended = new_state.finished
        new_message: disnake.Message = await channel.send(embed=GamingTableMainEmbed(self), view=action_view)
        self._round_msg_ids.append(new_message.id)
        await self.persist()

        return True

    async def perform_action(self, player: Player, action: GameAction, action_value: Optional[Union[str, int]] = None) -> None:
        if not self.published:
            raise PrerequisiteNotMetException(f"This game has not started yet")

        new_state: Optional[GameState] = self.game.register_action(self._state, player, action.id, action_value)
        if new_state is None:
            raise InvalidActionException("Could not register your action")

        self._state = new_state
        self._ended = new_state.finished
        await self.persist()

    async def persist(self, message: Optional[disnake.Message] = None) -> None:
        if message is not None:
            if not self._published:
                self._setup_channel_id = message.channel.id
                self._setup_msg_id = message.id
            else:
                self._publish_channel_id = message.channel.id

        if self._id == ID_UNCREATED:
            self._created_at = datetime.now()
            self._updated_at = self._created_at
            dto: GamingTableDao = await GamingTableDao.create(game_id=self._game.id, data=self._serialize_data(), ended=self._ended, expires_at=self._expires_at, updated_at=self._updated_at, created_at=self._created_at)
            self._id = dto.id
        else:
            self._updated_at = datetime.now()
            await GamingTableDao.filter(id=self._id).update(game_id=self._game.id, data=self._serialize_data(), ended=self._ended, expires_at=self._expires_at, updated_at=self._updated_at)

    async def publish(self, channel: Optional[Union[GuildChannel, Thread, PrivateChannel]] = None) -> bool:
        if self._published:
            return False

        setup_channel: Union[GuildChannel, Thread] = Continent().channel(self._setup_channel_id)
        if channel is None:
            if self._setup_channel_id is None:
                return False

            channel = setup_channel

        # Initialize the game with the config
        self._state = self.game.start(self.config, self.authorized_players)
        self._ended = self._state.finished
        state_key: tuple[str, str] = self._state.key
        action_view: disnake.ui.View = GamingHouse().get_view(state_key)

        self._publish_channel_id = channel.id
        self._published = True
        main_message: disnake.Message = await channel.send(embed=GamingTableMainEmbed(self), view=action_view)
        self._round_msg_ids.append(main_message.id)

        await self.persist()

        try:
            setup_message: disnake.Message = await setup_channel.fetch_message(self._setup_msg_id)
            await setup_message.delete()
        except (NotFound, Forbidden, HTTPException) as e:
            _log("system", f"Could not delete the setup message: {e}")

        return True

    def remove_authorized_player(self, player_id: int) -> bool:
        if self._published:
            raise ValueError("Cannot remove an authorized player once the game is started")

        if self._authorized_players is None:
            return False

        if player_id not in self._authorized_players:
            return False

        self._authorized_players.remove(player_id)
        return True

    @staticmethod
    def deserialize(row_data: dict[str, Any]) -> T:
        table_id: int = row_data["id"]
        game_id: str = row_data["game_id"]
        ended: bool = row_data["ended"]
        expires_at: Optional[datetime] = row_data["expires_at"]
        created_at: datetime = row_data["created_at"]
        updated_at: datetime = row_data["updated_at"]
        data: dict[str, Any] = row_data["data"]

        game: Game = GameCatalog()[game_id]

        sponsor_id: Optional[int] = data["sponsor"]
        sponsor: Player = PlayerRoster()[sponsor_id] if sponsor_id is not None else None

        published: bool = data["published"]
        if published and "state" in data:
            state: Optional[GameState] = GameState.deserialize(data["state"])
            config: GameConfig = game.config(state)
            authorized_players: set[int] = game.authorized_players(state)
        else:
            state: Optional[GameState] = None
            config: GameConfig = GameConfig.deserialize(data["config"])
            authorized_players_data: Optional[list[int]] = data["authorized_players"]
            authorized_players: Optional[set[int]] = set(authorized_players_data) if authorized_players_data is not None else None

        setup_channel_id: Optional[int] = data.get("setup_channel_id")
        setup_msg_id: Optional[int] = data.get("setup_msg_id")
        publish_channel_id: Optional[int] = data.get("publish_channel_id")
        round_msg_ids: Optional[list[int]] = data.get("round_msg_ids")

        prizes_data: Optional[list[str]] = data["prizes"]
        prizes: Optional[Loot] = None if prizes_data is None else [Loot.deserialize(prize_data) for prize_data in prizes_data]

        return GamingTable(table_id, game, config, sponsor, authorized_players, published, ended, state, setup_channel_id, setup_msg_id, publish_channel_id, round_msg_ids, prizes, expires_at, created_at, updated_at)

    def _serialize_data(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "sponsor": self._sponsor.id,
            "published": self._published,
            "prizes": None if self._prizes is None else [prize.serialize() for prize in self._prizes],
            "setup_channel_id": self._setup_channel_id,
            "setup_msg_id": self._setup_msg_id,
            "publish_channel_id": self._publish_channel_id,
            "round_msg_ids": self._round_msg_ids
        }

        if self._published and self._state is not None:
            # Save the GameState and not the config since the state holds the config, unless we're in a strange mode where there's no state, but shouldn't happen, still let protect against it
            data["state"] = self._state.serialize()
        else:
            # Save the config when in setup mode
            data["config"] = self._config.serialize()
            data["authorized_players"] = [int(player_id) for player_id in self._authorized_players] if self._authorized_players is not None else None

        return data


# =============================================================================================================================================================================================================================================
# ============================================================================================================== GamblingHouse ================================================================================================================
# =============================================================================================================================================================================================================================================
@singleton
class GamingHouse:
    def __init__(self):
        self._active_tables: dict[int, GamingTable] = {}
        self._setup_view: disnake.ui.View = GameSetupView()

        catalog: GameCatalog = GameCatalog()
        persistent_views: list[disnake.ui.View] = [self._setup_view]
        view_by_state_key: dict[tuple[str, str], disnake.ui.View] = {}
        action_views: dict[tuple, disnake.ui.View] = {}
        for game in catalog.games:
            for state_key, actions in game.action_states().items():
                actions_key: tuple = tuple(actions)
                if actions_key in action_views:
                    view: disnake.ui.View = action_views[actions_key]
                else:
                    view: disnake.ui.View = GameActionView(game, actions)
                    action_views[actions_key] = view
                    persistent_views.append(view)

                view_by_state_key[state_key] = view

        self._persistent_views: list[disnake.ui.View] = persistent_views
        self._view_by_state_key: dict[tuple[str, str], disnake.ui.View] = view_by_state_key

    # ============================================= Special methods =============================================

    def __repr__(self):
        return "GamingHouse"

    def __str__(self) -> str:
        return "Gaming House"

    def __getitem__(self, table_id: int) -> GamingTable:
        return self._active_tables[table_id]

    # ================================================ Properties ===============================================

    @property
    def persistent_views(self) -> list[disnake.ui.View]:
        return self._persistent_views.copy()

    # ============================================== "Real" methods =============================================

    def get(self, table_id: int) -> Optional[GamingTable]:
        return self._active_tables.get(table_id)

    def get_by_interaction(self, inter: Union[disnake.MessageInteraction | disnake.ModalInteraction]) -> Optional[GamingTable]:
        return self.get_by_msg_id(inter.message.id)

    def get_by_msg_id(self, msg_id: int) -> Optional[GamingTable]:
        for table in self._active_tables.values():
            if table.linked_to_message(msg_id):
                return table

        return None

    def get_view(self, state_key: tuple[str, str]) -> disnake.ui.View:
        return self._view_by_state_key[state_key]

    async def interaction_check(self, inter: Union[disnake.MessageInteraction, disnake.ModalInteraction]) -> bool:
        table: Optional[GamingTable] = self.get_by_interaction(inter)
        if table is None:
            await inter.response.send_message(f"Could not find the gaming table associated with the message {inter.message.id}", ephemeral=True)
            return False

        return await table.authorizes(inter)

    async def load(self):
        active_tables: dict[int, GamingTable] = {}

        table_data: list[dict[str, Any]] = await GamingTableDao.filter(ended=False).values()
        for row_data in table_data:
            table: GamingTable = GamingTable.deserialize(row_data)
            active_tables[table.id] = table

        self._active_tables: dict[int, GamingTable] = active_tables

    async def publish_prepared_table(self, table_id: int, channel_id: Optional[int] = None) -> Optional[GamingTable]:
        table: Optional[GamingTable] = self.get(table_id)
        if table is None:
            return None

        channel: Optional[Union[GuildChannel, Thread, PrivateChannel]] = None
        if channel_id is not None:
            channel = Continent().channel(channel_id)

        await table.publish(channel)

        return table

    async def prepare_new_table(self, game: Game, sponsor: Player, inter_or_channel: Union[Interaction, Messageable]) -> GamingTable:
        if game is None:
            raise ValueError(f"Game was not specified")
        elif sponsor is None:
            raise ValueError(f"Sponsor was not specified")

        table: GamingTable = GamingTable(ID_UNCREATED, game, game.default_config, sponsor)
        if isinstance(inter_or_channel, Interaction):
            message: disnake.Message = await inter_or_channel.channel.send(embed=GamingTableSetupEmbed(table), view=self._setup_view)
        else:
            message: disnake.Message = await inter_or_channel.send(embed=GamingTableSetupEmbed(table), view=self._setup_view)

        await table.persist(message)
        self._active_tables[table.id] = table

        return table

    async def refresh_interaction(self, inter: disnake.Interaction, table: GamingTable) -> None:
        if table.ended:
            await inter.response.edit_message(embed=GamingTableMainEmbed(table))
        elif table.published:
            await inter.response.edit_message(embed=GamingTableMainEmbed(table), view=self.get_view(table.state.key))
        else:
            await inter.response.edit_message(embed=GamingTableSetupEmbed(table), view=self._setup_view)

    async def refresh_message(self, table: GamingTable) -> None:
        message: disnake.Message = await table.message()
        if table.ended:
            await message.edit(embed=GamingTableMainEmbed(table))
        elif table.published:
            await message.edit(embed=GamingTableMainEmbed(table), view=self.get_view(table.state.key))
        else:
            await message.edit(embed=GamingTableSetupEmbed(table), view=self._setup_view)


# =============================================================================================================================================================================================================================================
# ================================================================================================================= Embeds ====================================================================================================================
# =============================================================================================================================================================================================================================================
class BaseGamingTableEmbed(BaseStarfallEmbed):
    def __init__(self, table: GamingTable):
        super().__init__()
        self._table: GamingTable = table
        image: Optional[disnake.File] = table.game.image
        if image is not None:
            self.set_image(file=image)

        sponsor_str: str = f"Sponsored by {table.sponsor.as_member().name}" if table.sponsor is not None and not table.published else ""
        id_str: str = f"{table.game.instance_label.capitalize()} id: {table.id}" if table.id != ID_UNCREATED else ""
        if len(id_str) > 0:
            self.set_footer(text=f"{id_str}. {sponsor_str}" if len(sponsor_str) > 0 else id_str)
        elif len(sponsor_str) > 0:
            self.set_footer(text=sponsor_str)

    @property
    def config(self) -> GameConfig:
        return self._table.config

    @property
    def table(self) -> GamingTable:
        return self._table

    def _add_action_count_field(self, force: bool = False) -> bool:
        return self._add_conditional_field("Actions", PROP_ACTION_COUNT, lambda config: config.action_count, force)

    def _add_extra_action_count_field(self, force: bool = False) -> bool:
        return self._add_conditional_field("Extra Actions", PROP_ACTION_COUNT_EXTRA, lambda config: config.extra_action_count, force)

    def _add_min_player_field(self) -> bool:
        self.add_field(name="Min Players", value=self._table.game.minimum_players)
        return True

    def _add_max_player_field(self, force: bool = False) -> bool:
        return self._add_conditional_field("Max Players", PROP_MAX_PLAYERS, lambda config: config.maximum_players, force)

    def _add_authorized_players_field(self, force: bool = False) -> bool:
        game: Game = self._table.game
        config: GameConfig = self.config
        if self._table.authorized_players is None:
            if game.maximum_players is None and config.maximum_players is None:
                # No limitation, usually a betting game, there's no need to display the authorized players unless forced to
                if not force:
                    return False

                self.add_field("Players", "Self-registration")
            else:
                self.add_field("Players", "First come, first served")
        else:
            mentions: list[str] = [f"- {mention(player_id)}" for player_id in self._table.authorized_players]
            self.add_field("Players", "\n".join(mentions))

        return True

    def _add_prizes_field(self) -> bool:
        # Gambling games handle prizes differently (winning odds x bet)
        if self._table.game.produces_winning_odds:
            return False

        prizes: Optional[list[Loot]] = self._table.prizes
        if prizes is None or len(prizes) == 0:
            self.add_field("Prize", "Honor & Glory")
        else:
            prize_count = len(prizes)
            if prize_count == 1:
                prizes_desc: str = f"Winner: `{prizes[0]}`"
            else:
                # Multiple prizes
                prizes_entries: list[str] = []
                if self._table.game.produces_ranking:
                    for rank in range(0, prize_count):
                        prizes_entries.append(f"- {ranking_str(rank + 1)}: {prizes[rank]}")
                else:
                    if prize_count > 2:
                        raise ValueError("For games with simply winners and losers, only 2 prizes are permitted: Winner and Consolation")

                    prizes_entries.append(f"- Winner: `{prizes[0]}`")
                    prizes_entries.append(f"- Consolation: `{prizes[1]}`")

                prizes_desc: str = "\n".join(prizes_entries)

            self.add_field("Prizes", prizes_desc)

        return True

    def _add_conditional_field(self, label: str, prop: str, getter: Callable[[GameConfig], Any], force: bool = False, inline: bool = True) -> bool:
        game: Game = self._table.game
        config: GameConfig = self.config
        if force or prop in game.supported_properties or prop in game.required_properties:
            self.add_field(name=label, value=getter(config), inline=inline)
            return True

        return False


class GamingTableMainEmbed(BaseGamingTableEmbed):
    def __init__(self, table: GamingTable):
        super().__init__(table)
        if not table.published:
            raise ValueError(f"GamingTableSetupEmbed should be used for published tables only, found: {table}")

        self.title = f"{table.game}"
        self._add_authorized_players_field(True)
        self._add_min_player_field()
        self._add_max_player_field()
        self._add_prizes_field()
        self._add_action_count_field()
        self._add_extra_action_count_field()

        if table.ended:
            # Completed
            # TODO
            pass
        elif table.registering_players:
            # Registration mode
            # TODO
            self.description = "Waiting for more players to register"
        elif table.registering_moves:
            # Waiting for more player actions
            self._add_register_move_fields(table)
        elif table.current_round_completed:
            # Display round results. Theoretically this could be an else, but let not take chance
            # TODO
            pass

    def _add_register_move_fields(self, table: GamingTable):
        authorized_player_ids: Optional[set[int]] = table.authorized_players
        if authorized_player_ids is not None:
            roster: PlayerRoster = PlayerRoster()
            infinite_action_mode: bool = table.game.allows_unlimited_actions
            required_action_count: int = table.game.required_action_count(table.state)
            for player_id in authorized_player_ids:
                player: Optional[Player] = roster.get(player_id)
                if player is not None:
                    missing_action_count: int = table.game.missing_action_count(table.state, player)
                    # self.add_field(name=f"{player.as_member().name}", value=f"`{}/{required_action_count}`", inline=True)
                    pass

        # TODO
        # self.add_field(name=label, value=getter(config), inline=inline)


class GamingTableSetupEmbed(BaseGamingTableEmbed):
    def __init__(self, table: GamingTable):
        super().__init__(table)
        if table.published:
            raise ValueError(f"GamingTableSetupEmbed should be used for unpublished tables only, found: {table}")

        self.title = f"Setup for {table.game}"
        self._add_authorized_players_field(True)
        self._add_min_player_field()
        self._add_max_player_field(True)
        self._add_prizes_field()
        self._add_action_count_field(True)
        self._add_extra_action_count_field(True)


# =============================================================================================================================================================================================================================================
# ============================================================================================================= Base Classes ==================================================================================================================
# =============================================================================================================================================================================================================================================


class BaseGameView(BaseStarfallPersistentView):
    def __init__(self):
        super().__init__()

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:
        return await GamingHouse().interaction_check(inter)


class BaseGamingTableButton(PlayerActionButton, ABC):
    def __init__(self, label: str, custom_id: str, style: disnake.ButtonStyle.primary, row: Optional[int] = None):
        super().__init__(label=label, custom_id=f"{_MODULE_ID}:{custom_id}", style=style, row=row)

    async def callback(self, inter: disnake.MessageInteraction) -> None:
        house: GamingHouse = GamingHouse()
        table: Optional[GamingTable] = house.get_by_interaction(inter)
        if table is None:
            await inter.response.send_message(f"Could not find the gaming table associated with the message {inter.message.id}", ephemeral=True)
        elif await self.validate_interaction(inter, table):
            try:
                if await self.execute(inter, table):
                    await house.refresh_interaction(inter, table)
                    if table.requires_new_round:
                        await table.next_round()
            except (InvalidActionException, PlayerInputException, FunctionalValidationException, PrerequisiteNotMetException) as e:
                _log(inter.user.id, e.system_message)
                await e.send(inter)

    @abstractmethod
    async def execute(self, inter: disnake.MessageInteraction, table: GamingTable) -> bool:
        pass

    async def validate_interaction(self, inter: disnake.MessageInteraction, table: GamingTable) -> bool:
        return await table.authorizes(inter.author.id)


# =============================================================================================================================================================================================================================================
# ========================================================================================================= ACTIVE Game UI Elements ===========================================================================================================
# =============================================================================================================================================================================================================================================


class GameActionView(BaseGameView):
    def __init__(self, game: Game, actions: list[GameAction]):
        super().__init__()
        for action in actions:
            self.add_item(GameActionButton(game, action))


class GameActionButton(BaseGamingTableButton):
    def __init__(self, game: Game, action: GameAction, stype: disnake.ButtonStyle = disnake.ButtonStyle.primary, row: Optional[int] = None):
        super().__init__(action.label, f"action:{game.id}:{action.id}", stype, row)
        self._game: Game = game
        self._action: GameAction = action

    @property
    def action(self) -> GameAction:
        return self._action

    @property
    def game(self) -> Game:
        return self._game

    async def execute(self, inter: disnake.MessageInteraction, table: GamingTable) -> bool:
        print(f"Executing action {self._action} for game {self._game} on table {table}")
        if self._action.mode == ActionMode.BUTTON:
            await table.perform_action(PlayerRoster().get(inter.author.id), self._action)
            return True
        else:
            await inter.response.send_modal(ActionValueInputModal(inter, table, self._action))
            return False

    async def validate_interaction(self, inter: disnake.MessageInteraction, table: GamingTable) -> bool:
        if not table.published:
            await inter.response.send_message(f"That {self.game.instance_label} is not yet published", ephemeral=True)
            return False

        return await table.authorizes(inter)


class ActionValueInputModal(disnake.ui.Modal, ABC):
    FIELD_ID: str = "action_value"

    def __init__(self, inter: disnake.Interaction, table: GamingTable, action: GameAction):
        self._table: GamingTable = table
        self._action: GameAction = action

        super().__init__(title=f"{action.label}",
                         custom_id=f"{ActionValueInputModal.FIELD_ID}_modal-{inter.id}",
                         components=[disnake.ui.TextInput(label=action.input_label, placeholder=action.input_placeholder, custom_id=ActionValueInputModal.FIELD_ID, style=disnake.TextInputStyle.short, min_length=1, max_length=25)])

    async def callback(self, inter: disnake.ModalInteraction):
        try:
            input_str: str = inter.text_values[ActionValueInputModal.FIELD_ID]
            if self._action.mode == ActionMode.INPUT_STR:
                input_value: Union[str, int] = input_str
            else:
                input_value: Union[str, int] = parse_int(input_str)

            house: GamingHouse = GamingHouse()
            if await house.interaction_check(inter):
                await self._table.perform_action(PlayerRoster().get(inter.author.id), self._action, input_value)
                await house.refresh_interaction(inter, self._table)
        except (InvalidActionException, PlayerInputException, FunctionalValidationException, PrerequisiteNotMetException) as e:
            await e.send(inter)
        except ValueError:
            await inter.send(f"Please enter a valid {self._action.input_label}", ephemeral=True)


# =============================================================================================================================================================================================================================================
# ============================================================================================================== SETUP Mode ===================================================================================================================
# =============================================================================================================================================================================================================================================


class GameSetupView(BaseGameView):
    def __init__(self):
        super().__init__()
        # Action setup
        self.add_item(SetupActionCountButton())
        self.add_item(SetupExtraActionCountButton())

        # Player setup
        self.add_item(SetupAuthorizedPlayerButton())
        self.add_item(ResetAuthorizedPlayerButton())

        # Prizes setup
        self.add_item(SetupSimplePrizesButton())
        self.add_item(SetupAdvancedPrizesButton())
        self.add_item(ResetPrizesButton())

        # Publish
        self.add_item(PublishHereButton())
        self.add_item(PublishOnChannelButton())


class BaseGameSetupModal(disnake.ui.Modal, ABC):
    def __init__(self, inter: disnake.Interaction, table: GamingTable, custom_id: str, components: Components[ModalUIComponent]):
        super().__init__(title=f"{table.game.name} Setup", custom_id=f"{custom_id}-{inter.id}", components=components)

    async def callback(self, inter: disnake.ModalInteraction):
        house: GamingHouse = GamingHouse()
        if await house.interaction_check(inter):
            try:
                table: GamingTable = house.get_by_interaction(inter)
                if await self.execute(inter, house, table):
                    await table.persist()
                    await house.refresh_interaction(inter, table)
                else:
                    await inter.send("Couldn't modify the settings")
            except (PlayerInputException, FunctionalValidationException) as e:
                await e.send(inter)
            except ValueError:
                await inter.send(f"Please enter a valid value", ephemeral=True)

    @abstractmethod
    async def execute(self, inter: disnake.ModalInteraction, house: GamingHouse, table: GamingTable) -> bool:
        pass


class SetConfigFieldModal(BaseGameSetupModal, ABC):
    def __init__(self, inter: disnake.MessageInteraction, table: GamingTable, modal_custom_id: str, field_id: str, label: str, placeholder: str, style: disnake.TextInputStyle = disnake.TextInputStyle.short, min_length: int = 1, max_length: int = 25):
        self._field_id: str = field_id
        super().__init__(inter=inter, table=table, custom_id=modal_custom_id, components=[disnake.ui.TextInput(label=label, placeholder=placeholder, custom_id=field_id, style=style, min_length=min_length, max_length=max_length)])

    async def execute(self, inter: disnake.ModalInteraction, house: GamingHouse, table: GamingTable) -> bool:
        value: str = inter.text_values[self._field_id]
        config: GameConfig = table.config
        if self._update_config(config, value):
            table.config = config
            return True

        return False

    @abstractmethod
    def _update_config(self, config: GameConfig, value: Optional[str]) -> bool:
        pass


class BaseGameSetupButton(BaseGamingTableButton, ABC):
    def __init__(self, label: str, custom_id: str, style: disnake.ButtonStyle = disnake.ButtonStyle.primary, row: Optional[int] = None):
        super().__init__(label=label, custom_id="setup:" + custom_id, style=style, row=row)

    async def validate_interaction(self, inter: disnake.MessageInteraction, table: GamingTable) -> bool:
        if table.published:
            await inter.response.send_message(f"Gaming table {table.id} was already published to players and therefore can no longer be configured", ephemeral=True)
            return False
        elif not table.is_sponsor(inter.author.id):
            await inter.response.send_message(f"Only the table sponsor can configure a gaming table", ephemeral=True)
            return False

        return True


class BaseModalGameSetupButton(BaseGameSetupButton):
    def __init__(self, label: str, custom_id: str, modal_constructor: Callable[[disnake.MessageInteraction, GamingTable], BaseGameSetupModal], style: disnake.ButtonStyle = disnake.ButtonStyle.primary, row: Optional[int] = None):
        super().__init__(label=label, custom_id=custom_id, style=style, row=row)
        self._modal_constructor = modal_constructor

    async def execute(self, inter: disnake.MessageInteraction, table: GamingTable) -> bool:
        await inter.response.send_modal(self._modal_constructor(inter, table))
        return False


class BaseClearSetupFieldButton(BaseGameSetupButton, ABC):
    def __init__(self, custom_id: str, label: str, style: disnake.ButtonStyle = disnake.ButtonStyle.danger, row: Optional[int] = None):
        super().__init__(label=label, custom_id=custom_id, style=style, row=row)

    async def execute(self, inter: disnake.MessageInteraction, table: GamingTable) -> bool:
        return self._clear_field(table)

    @abstractmethod
    def _clear_field(self, table: GamingTable) -> bool:
        pass


# =============================================================================================================================================================================================================================================
# =========================================================================================================== SETUP: Action Count =============================================================================================================
# =============================================================================================================================================================================================================================================


class SetupActionCountButton(BaseModalGameSetupButton):
    def __init__(self):
        super().__init__(label="Action Count", custom_id="action_count", modal_constructor=SetupActionCountModal)


class SetupActionCountModal(SetConfigFieldModal):
    def __init__(self, inter: disnake.MessageInteraction, table: GamingTable):
        super().__init__(inter=inter, table=table, modal_custom_id="action_count_modal", field_id="action_count", label="Action Count", placeholder="Type the number of actions per round", max_length=2)

    def _update_config(self, config: GameConfig, value: Optional[str]) -> bool:
        new_count: int = parse_int(value)
        if new_count == config.action_count:
            return False

        config.action_count = new_count
        return True


# =============================================================================================================================================================================================================================================
# ======================================================================================================== SETUP: Extra Action Count ==========================================================================================================
# =============================================================================================================================================================================================================================================


class SetupExtraActionCountButton(BaseModalGameSetupButton):
    def __init__(self):
        super().__init__(label="Extra Action Count", custom_id="extra_action_count", modal_constructor=SetupExtraActionCountModal)


class SetupExtraActionCountModal(SetConfigFieldModal):
    def __init__(self, inter: disnake.MessageInteraction, table: GamingTable):
        super().__init__(inter=inter, table=table, modal_custom_id="extra_action_count_modal", field_id="extra_action_count", label="Extra Action Count", placeholder="Type the number of extra break-tie actions", max_length=2)

    def _update_config(self, config: GameConfig, value: Optional[str]) -> bool:
        new_count: int = parse_int(value)
        if new_count == config.extra_action_count:
            return False

        config.extra_action_count = new_count
        return True


# =============================================================================================================================================================================================================================================
# ======================================================================================================== SETUP: Authorized Players ==========================================================================================================
# =============================================================================================================================================================================================================================================


class ResetAuthorizedPlayerButton(BaseClearSetupFieldButton):

    def __init__(self):
        super().__init__("reset_authorized_users", "Reset Authorized Players", row=2)

    def _clear_field(self, table: GamingTable) -> bool:
        if table.authorized_players is None:
            return False

        table.authorized_players = None
        return True


class SetupAuthorizedPlayerButton(BaseGameSetupButton):
    def __init__(self):
        super().__init__(label="Authorized Players", custom_id="authorized_users", row=2)

    async def execute(self, inter: disnake.MessageInteraction, table: GamingTable) -> bool:
        await inter.send("Select the authorized players", view=SetupAuthorizedPlayerSetupView(table))
        return False


class SetupAuthorizedPlayerSetupView(BaseStarfallTransientView):
    def __init__(self, table: GamingTable):
        super().__init__()
        self.add_item(SetupAuthorizedPlayerField(table))


class SetupAuthorizedPlayerField(BaseStarfallUserSelect):
    def __init__(self, table: GamingTable):
        maximum: Optional[int] = table.maximum_players
        super().__init__(custom_id=f"{_MODULE_ID}:setup:authorized_users:field", placeholder="Authorized Players", min_values=1, max_values=maximum if maximum is not None else 25)

        self._table: GamingTable = table

    async def callback(self, inter: disnake.MessageInteraction) -> None:
        try:
            self._table.authorized_players = set(inter.values)
            await self._table.persist()
            await GamingHouse().refresh_message(self._table)
            await inter.message.delete()
        except (PlayerInputException, FunctionalValidationException) as e:
            await e.send(inter)


# =============================================================================================================================================================================================================================================
# ============================================================================================================== SETUP: Prizes ================================================================================================================
# =============================================================================================================================================================================================================================================


class ResetPrizesButton(BaseClearSetupFieldButton):

    def __init__(self):
        super().__init__("reset_prizes", "Reset Prizes", row=3)

    def _clear_field(self, table: GamingTable) -> bool:
        if table.prizes is None:
            return False

        table.prizes = None
        return True


class SetupSimplePrizesButton(BaseModalGameSetupButton):
    def __init__(self):
        super().__init__(label="Add Prize", custom_id="prizes_simple", modal_constructor=SetupSimplePrizesModal, row=3)


class SetupSimplePrizesModal(BaseGameSetupModal):
    ITEM_ID_FIELD: str = "prize_item_id"
    QUANTITY_FIELD: str = "prize_quantity"

    def __init__(self, inter: disnake.MessageInteraction, table: GamingTable):
        super().__init__(inter=inter, table=table, custom_id="prizes_modal_simple",
                         components=[
                             disnake.ui.TextInput(label="Item Id", placeholder="Specify the prize's item id or pseudo item id", custom_id=SetupSimplePrizesModal.ITEM_ID_FIELD, style=disnake.TextInputStyle.single_line, required=True),
                             disnake.ui.TextInput(label="Quantity", placeholder="Specify the quantity", custom_id=SetupSimplePrizesModal.QUANTITY_FIELD, style=disnake.TextInputStyle.single_line, max_length=20),
                         ])

    async def execute(self, inter: disnake.ModalInteraction, _: GamingHouse, table: GamingTable) -> bool:
        item_id: str = inter.text_values[SetupSimplePrizesModal.ITEM_ID_FIELD]
        quantity_str: str = inter.text_values[SetupSimplePrizesModal.QUANTITY_FIELD]
        # Validate the item id
        if not is_pseudo_item_id(item_id) and item_id not in ItemCompendium():
            raise PlayerInputException(f"{item_id} is not a valid item id or pseudo-id")

        try:
            quantity: Optional[int] = parse_int(quantity_str)
        except ValueError:
            raise PlayerInputException(f"{quantity_str} is not a valid quantity")

        if quantity is None:
            raise PlayerInputException(f"{quantity_str} is not a valid quantity")
        elif quantity <= 0:
            raise PlayerInputException(f"{quantity_str} is not a strictly positive quantity")

        prize: Loot = create_fixed_loot(item_id, quantity)
        prizes: Optional[list[Loot]] = table.prizes
        if prizes is None:
            prizes: list[Loot] = [prize]
        else:
            prizes.append(prize)

        table.prizes = prizes
        return True


class SetupAdvancedPrizesButton(BaseModalGameSetupButton):
    def __init__(self):
        super().__init__(label="Prizes (Advanced)", custom_id="prizes_advanced", modal_constructor=SetupAdvancedPrizesModal, row=3)


class SetupAdvancedPrizesModal(BaseGameSetupModal):
    DATA_FIELD: str = "prizes_json_data"

    def __init__(self, inter: disnake.MessageInteraction, table: GamingTable):
        super().__init__(inter=inter, table=table, custom_id="prizes_modal_advanced",
                         components=[
                             disnake.ui.TextInput(label="Prizes", placeholder="Specify a valid JSON-serialized list[Loot] prize configuration", custom_id=SetupAdvancedPrizesModal.DATA_FIELD, style=disnake.TextInputStyle.multi_line, required=True)
                         ])

    async def execute(self, inter: disnake.ModalInteraction, _: GamingHouse, table: GamingTable) -> bool:
        table.prizes = loot_values(inter, SetupAdvancedPrizesModal.DATA_FIELD)
        return True


# =============================================================================================================================================================================================================================================
# ========================================================================================================== SETUP: Publish Table =============================================================================================================
# =============================================================================================================================================================================================================================================

async def _do_publish(table: GamingTable, inter: disnake.MessageInteraction, channel: Optional[Union[GuildChannel, Thread, PrivateChannel]] = None) -> None:
    try:
        await table.publish(channel)
        await inter.send("Table published!", ephemeral=True)
    except (PlayerInputException, FunctionalValidationException) as e:
        await e.send(inter)


class PublishOnChannelButton(BaseGameSetupButton):
    def __init__(self):
        super().__init__(label="Publish (Choose Channel)", custom_id="publish_channel", style=disnake.ButtonStyle.success, row=4)

    async def execute(self, inter: disnake.MessageInteraction, table: GamingTable) -> bool:
        await inter.send("Select target channel", view=PublishOnChannelView(table))
        return False


class PublishHereButton(BaseGameSetupButton):
    def __init__(self):
        super().__init__(label="Publish (Here)", custom_id="publish_here", style=disnake.ButtonStyle.success, row=4)

    async def execute(self, inter: disnake.MessageInteraction, table: GamingTable) -> bool:
        await _do_publish(table, inter)
        return False


class PublishOnChannelView(BaseStarfallTransientView):
    def __init__(self, table: GamingTable):
        super().__init__()
        self.add_item(PublishChannelField(table))


class PublishChannelField(BaseStarfallChannelSelect):
    def __init__(self, table: GamingTable):
        super().__init__(custom_id=f"{_MODULE_ID}:publish_channel:field", placeholder="Target Channel", min_values=1, max_values=1)
        self._table: GamingTable = table

    async def callback(self, inter: disnake.MessageInteraction) -> None:
        if len(inter.values) != 1:
            await inter.message.delete()
            await inter.send("You must choose exactly one channel", ephemeral=True)

        channel: Optional[Union[GuildChannel, Thread, PrivateChannel]] = Continent().channel(int(inter.values[0]))
        await inter.message.delete()
        await _do_publish(self._table, inter, channel)


def _log(user_id: Union[int, str], message: str, level: str = "INFO"):
    log_event(user_id, _MODULE_ID, message, level)

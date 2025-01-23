from abc import ABC, abstractmethod, ABCMeta
from datetime import timedelta
from enum import Enum
from typing import Optional, Any, Union, cast, TypeVar, Type

import disnake

from character.player import Player
from utils.ParamsUtils import INVALID_FILE_CHARACTERS
from utils.base import PlayerInputException, PrerequisiteNotMetException, UnsupportedOperationError

# =======================================================================================================================
# ==================================================== Constants ========================================================
# =======================================================================================================================

G = TypeVar("G", bound="Game")
F = TypeVar("F", bound="GameConfig")
C = TypeVar("C", bound="GameScore")
S = TypeVar("S", bound="GameState")

PROP_ACTION_COUNT: str = "action_count"
PROP_ACTION_COUNT_EXTRA: str = "extra_action_count"
PROP_MAX_PLAYERS: str = "max_players"


# =======================================================================================================================
# ================================================ Public functions =====================================================
# =======================================================================================================================


def compute_game_file_path(game_id: str) -> str:
    if game_id is None or len(game_id) == 0:
        raise ValueError(f"game_id must be specified, found: {game_id}")

    file_name = INVALID_FILE_CHARACTERS.sub("_", game_id)
    file_path = f"./media/game/{file_name}.png"

    return file_path


# =======================================================================================================================
# ============================================== Exceptions and Errors ==================================================
# =======================================================================================================================
class InvalidGameStateError(ValueError):
    def __init__(self, system_message: str):
        super().__init__(system_message)


class IllegalGameSettingsException(PlayerInputException):
    def __init__(self, system_message: str, player_message: Optional[str] = None, player_embed: Optional[disnake.Embed] = None, ephemeral: bool = True):
        super().__init__(system_message, player_message, player_embed, ephemeral)


class InvalidActionException(PlayerInputException):
    def __init__(self, system_message: str, player_message: Optional[str] = None, player_embed: Optional[disnake.Embed] = None, ephemeral: bool = True):
        super().__init__(system_message, player_message, player_embed, ephemeral)


class UnauthorizedPlayerException(PrerequisiteNotMetException):
    def __init__(self, system_message: str, player_message: Optional[str] = None, player_embed: Optional[disnake.Embed] = None, ephemeral: bool = True):
        super().__init__(system_message, player_message, player_embed, ephemeral)


class PlayerAlreadyActedException(PrerequisiteNotMetException):
    def __init__(self, system_message: str, player_message: Optional[str] = None, player_embed: Optional[disnake.Embed] = None, ephemeral: bool = True):
        super().__init__(system_message, player_message, player_embed, ephemeral)


# =======================================================================================================================
# =================================================== ActionMode ========================================================
# =======================================================================================================================
class ActionMode(Enum):
    BUTTON: int = 0
    INPUT_INT: int = 1
    INPUT_STR: int = 2


DEFAULT_ACTION_MODE: ActionMode = ActionMode.BUTTON


# =======================================================================================================================
# =================================================== GameAction ========================================================
# =======================================================================================================================
class GameAction:
    def __init__(self, action_id: str, label: str, mode: ActionMode = DEFAULT_ACTION_MODE, input_label: Optional[str] = None, input_placeholder: Optional[str] = None):
        super().__init__()
        self._id: str = action_id
        self._label: str = label
        self._mode: ActionMode = mode
        self._input_label: Optional[str] = input_label
        self._input_placeholder: Optional[str] = input_placeholder

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"GameAction id: {self._id}, label: {self._label}, mode: {self._mode}"

    def __str__(self) -> str:
        return self._label

    def __hash__(self) -> int:
        return hash(self._id) * 3 + hash(self._mode)

    def __eq__(self, other) -> bool:
        return other is not None and isinstance(other, GameAction) and self._id == other._id and self._mode == other._mode

    def __ne__(self, other) -> bool:
        return not self.__eq__(other)

    # ================================================ Properties ===============================================

    @property
    def id(self) -> str:
        return self._id

    @property
    def input_label(self) -> str:
        return self._input_label if self._input_label is not None else ""

    @property
    def input_placeholder(self) -> str:
        return self._input_placeholder if self._input_placeholder is not None else ""

    @property
    def label(self) -> str:
        return self._label

    @property
    def mode(self) -> ActionMode:
        return self._mode


# =======================================================================================================================
# =================================================== GameConfig ========================================================
# =======================================================================================================================
class GameConfig:
    PREDEFINED_KEYS: set[str] = {PROP_ACTION_COUNT, PROP_ACTION_COUNT_EXTRA, PROP_MAX_PLAYERS}

    def __init__(self):
        super().__init__()
        self._max_players: Optional[int] = None
        self._action_count: Optional[int] = None
        self._extra_action_count: Optional[int] = None
        self._extra_properties: dict[str, Any] = {}

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"GameConfig max_contestants: {self._max_players}, action_count: {self._action_count}, extra_action_count: {self._extra_action_count}, extra_properties: {self._extra_properties}"

    def __str__(self) -> str:
        return self.__repr__()

    def __eq__(self, other) -> bool:
        return (other is not None
                and isinstance(other, GameConfig)
                and self._max_players == other._max_players
                and self._action_count == other._action_count
                and self._extra_action_count == other._extra_action_count
                and self._extra_properties == other._extra_properties)

    def __ne__(self, other) -> bool:
        return not self.__eq__(other)

    def __contains__(self, name: str) -> bool:
        return name in GameConfig.PREDEFINED_KEYS or name in self._extra_properties

    def __getitem__(self, name: str) -> Optional[Any]:
        if name in GameConfig.PREDEFINED_KEYS:
            if name == PROP_MAX_PLAYERS:
                return self.maximum_players
            elif name == PROP_ACTION_COUNT:
                return self.action_count
            elif name == PROP_ACTION_COUNT_EXTRA:
                return self.extra_action_count
            else:
                raise ValueError(f"Property {name} is undefined for {self}")
        else:
            return self._extra_properties[name]

    def __setitem__(self, name: str, value: Optional[Any]) -> None:
        if name in GameConfig.PREDEFINED_KEYS:
            if name == PROP_MAX_PLAYERS:
                self.maximum_players = value
            elif name == PROP_ACTION_COUNT:
                self.action_count = value
            elif name == PROP_ACTION_COUNT_EXTRA:
                self.extra_action_count = value
            else:
                raise ValueError(f"Property {name} is undefined for {self}")
        else:
            self._extra_properties[name] = value

    # ================================================ Properties ===============================================

    @property
    def extra_properties(self) -> dict[str, Any]:
        return self._extra_properties.copy()

    @property
    def maximum_players(self) -> Optional[int]:
        return self._max_players

    @maximum_players.setter
    def maximum_players(self, value: Optional[int]) -> None:
        self._max_players = self._reset_if_lt(value, 1)

    @property
    def action_count(self) -> Optional[int]:
        return self._action_count

    @action_count.setter
    def action_count(self, value: Optional[int]) -> None:
        self._action_count = self._reset_if_lt(value, 1)

    @property
    def extra_action_count(self) -> Optional[int]:
        return self._extra_action_count

    @extra_action_count.setter
    def extra_action_count(self, value: Optional[int]) -> None:
        self._extra_action_count = self._reset_if_lt(value, 0)

    @property
    def required_action_count(self) -> Optional[int]:
        action_count: Optional[int] = self.action_count
        extra_action_count: Optional[int] = self.extra_action_count
        if action_count is None:
            return extra_action_count
        elif extra_action_count is None:
            return action_count
        else:
            return action_count + extra_action_count

    @staticmethod
    def _reset_if_lt(value: Optional[int], threshold: int) -> Optional[int]:
        return None if value is None or value < threshold else value

    # ================================================ "Real" methods ===============================================

    def copy(self) -> F:
        """
        Creates a copy of this configuration.

        Returns
        -------
        F
            A copy of this configuration
        """
        config: GameConfig = GameConfig()
        config._max_players = self._max_players
        config._action_count = self._action_count
        config._extra_action_count = self._extra_action_count
        config._extra_properties = self._extra_properties.copy()
        return config

    def serialize(self) -> dict[str, Any]:
        """
        Serialize this configuration for future deserialization

        Returns
        -------
        Any
            A JSON-serializable representation of this configuration
        """
        serialized: dict[str, Any] = {
            PROP_MAX_PLAYERS: self._max_players,
            PROP_ACTION_COUNT: self._action_count,
            PROP_ACTION_COUNT_EXTRA: self._extra_action_count,
            "extra_properties": self._extra_properties.copy()
        }

        return serialized

    @staticmethod
    def deserialize(data: dict[str, Any]) -> F:
        """
        Deserialize the specified JSON-compliant data into a game configuration instances.

        Parameters
        ----------
        data: dict[str, Any]
              The JSON-compliant data to deserialize into a GameConfig instance

        Returns
        -------
        The deserialized instance
        """
        config: GameConfig = GameConfig()
        config.maximum_players = data[PROP_MAX_PLAYERS]
        config.action_count = data[PROP_ACTION_COUNT]
        config.extra_action_count = data[PROP_ACTION_COUNT_EXTRA]

        extra_properties: Optional[dict[str, Any]] = data["extra_properties"]
        if extra_properties is not None:
            for key, value in extra_properties.items():
                config[key] = value

        return config


# =======================================================================================================================
# ==================================================== GameScore ========================================================
# =======================================================================================================================
class GameScore:
    """
    The score a player reached during a game
    """

    def __init__(self, player_id: int, score: float, gambling_odds: bool = False):
        super().__init__()
        self._player_id: int = player_id
        self._score: float = score
        self._gambling_odds: bool = gambling_odds

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"GameScore player_id: {self._player_id}, score: {self._score}, gaming odds: {self._gambling_odds}"

    def __str__(self) -> str:
        return f"{self._score}"

    def __hash__(self) -> int:
        return hash(self._player_id) * 3 + hash(self._score)

    def __eq__(self, other) -> bool:
        return other is not None and isinstance(other, GameScore) and self._player_id == other._player_id and self._score == other._score

    def __ne__(self, other) -> bool:
        return not self.__eq__(other)

    def __ge__(self, other) -> bool:
        return self._score >= self._ensure_score_instance(other)._score

    def __gt__(self, other) -> bool:
        return self._score > self._ensure_score_instance(other)._score

    def __le__(self, other) -> bool:
        return self._score <= self._ensure_score_instance(other)._score

    def __lt__(self, other) -> bool:
        return self._score < self._ensure_score_instance(other)._score

    @staticmethod
    def _ensure_score_instance(other: Any) -> C:
        if isinstance(other, GameScore):
            return other

        raise ValueError(f"{other} is not a GameScore instance")

    # ================================================ Properties ===============================================

    @property
    def gambling_odds(self) -> float:
        """
        Determines if this score represents a gaming odds (winning factor) rather than an absolute score. If this property is True and a bet exists, then this score's value should be interpreted as a multiplier for the bet to the actual winnings

        Returns
        -------
        bool
            True if this score represents a gaming odd / winning factor to apply to the bet, False if this score can be considered as an absolute value giving the player's score
        """
        return self._gambling_odds

    @property
    def player_id(self) -> int:
        return self._player_id

    @property
    def score(self) -> float:
        return self._score


# =======================================================================================================================
# ==================================================== GameState ========================================================
# =======================================================================================================================
class GameState(ABC):
    """
    A mostly opaque, immutable representation of the state of a game. While instances of this class do expose some very basic information, most game-specific information should be accessed through the proper Game instance methods
    """

    STATE_REGISTRATION: str = "registration"

    def __init__(self, game_id: str):
        super().__init__()
        self._game_id: str = game_id

    # ============================================= Special methods =============================================

    def __repr__(self):
        action_state: str = self.action_state
        action_state_str: str = action_state if len(action_state) > 0 else "<empty>"
        return f"GameState game_id: {self._game_id}, state_id: {action_state_str}"

    def __str__(self) -> str:
        return f"{self._game_id}:{self.action_state}"

    def __hash__(self) -> int:
        return hash(self._game_id) * 3 + hash(self.action_state)

    def __eq__(self, other) -> bool:
        return other is not None and isinstance(other, GameState) and self._game_id == other._game_id and self.action_state == other.action_state

    def __ne__(self, other) -> bool:
        return not self.__eq__(other)

    # ================================================ Properties ===============================================

    @property
    @abstractmethod
    def action_state(self) -> str:
        """
        Provides a unique str representation of this game state in terms of possible actions.

        Returns
        -------
        str
            A unique str representation of this game state in terms of possible actions
        """
        pass

    @property
    @abstractmethod
    def canceled(self) -> bool:
        """
        Determines if this state represents a canceled state of the game. A finished game doesn't allow more actions to be registered

        Returns
        -------
        bool
            True if this state represent a canceled gate state, False otherwise
        """
        pass

    @property
    @abstractmethod
    def completed(self) -> bool:
        """
        Determines if this state represents a game that was completed normally.

        Returns
        -------
        bool
            True if this state represent a completed gate state, False otherwise
        """
        pass

    @property
    def finished(self) -> bool:
        """
        Determines if this state represents a finished state of the game. A finished game doesn't allow more actions to be registered. Therefore, a game that is finished, but not canceled can be considered to have terminated normally, while a
        canceled one means that the game was stopped forcefully

        Returns
        -------
        bool
            True if this state represent a finished gate state, False otherwise
        """
        return self.canceled or self.completed

    @property
    def game_id(self) -> str:
        """
        This identifier of the game this state is linked to.

        Returns
        -------
        str
            The identifier of the game this state is linked to
        """
        return self._game_id

    @property
    def key(self) -> tuple[str, str]:
        """
        A unique key for this state. The key should be unique across all games so that it's possible to create a dict[tuple[str, str], list[GameAction]] where tuple[str, str] is this game state key and list[GameAction] the list of possible actions
        for the state with the given key. See GameState.to_key

        Returns
        -------
        tuple[str, str]
            A unique key for this state
        """
        return self.to_key(self._game_id, self.action_state)

    # ================================================ "Real" methods ===============================================

    def serialize(self) -> Any:
        """
        Serialize this state

        Returns
        -------
        Any
            A JSON-serializable representation of this state
        """
        serialized: dict[str, Any] = {
            "type": type(self).__name__,
            "data": self._serialize_data()
        }

        return serialized

    @staticmethod
    def deserialize(data: dict[str, Any]) -> Optional[S]:
        """
        Deserialize the specified JSON-compliant data into a game state instances. Subclasses should include a protected static method named _deserialize_data receiving a GameConfig and an Any parameter to deserialize their class-specific attributes
        as well as instantiate the proper state class

        Parameters
        ----------
        data: dict[str, Any]
              The JSON-compliant data to deserialize into a GameState instance

        Returns
        -------
        The None if row_data is None, the deserialized state

        Raises
        -------
        UnsupportedOperationError
            If the data doesn't represent a GameState of if the concrete GameState class doesn't override _deserialize_data
        """
        if data is None:
            return None

        type_name: str = data["type"]
        inner_data: Any = data["data"]

        clazz: Type[S] = globals()[type_name]
        if hasattr(clazz, "_deserialize_data") and issubclass(clazz, GameState):
            return clazz._deserialize_data(inner_data)

        raise UnsupportedOperationError(f"Trying to deserialize an abstract loot type {clazz}")

    @staticmethod
    def to_key(game_id: str, action_state: str) -> tuple[str, str]:
        return game_id, action_state

    @abstractmethod
    def _serialize_data(self) -> Any:
        """
        Serialize the internal data of this state. The returned value should be a valid input value for the _deserialize_data method receiving

        Returns
        -------
        Any
            A JSON-serializable representation of the internal data of this state
        """
        pass

    @staticmethod
    def _deserialize_data(data: Any) -> S:
        """

        Parameters
        ----------
        data: Any
              The JSON-compliant serialized form of the GameState as previously generated by the _serialize_data method

        Returns
        -------
        GameState
            The deserialized concrete GameState instance
        """
        raise UnsupportedOperationError("Trying to deserialize an abstract loot type")


# =======================================================================================================================
# ======================================================= Game ==========================================================
# =======================================================================================================================
class Game(ABC):
    ACTION_REGISTER: GameAction = GameAction("register", "Register")

    def __init__(self, game_id: str, game_name: str):
        super().__init__()
        self._id: str = game_id
        self._name: str = game_name

    # ============================================= Special methods =============================================

    def __repr__(self):
        return f"Game id: {self._id}, name: {self._name}"

    def __str__(self) -> str:
        return self.name

    def __hash__(self) -> int:
        return hash(self._id) * 3

    def __eq__(self, other) -> bool:
        return other is not None and isinstance(other, Game) and self._id == other._id

    def __ne__(self, other) -> bool:
        return not self.__eq__(other)

    def __ge__(self, other) -> bool:
        return self._name >= self._ensure_game_instance(other).name

    def __gt__(self, other) -> bool:
        return self._name > self._ensure_game_instance(other).name

    def __le__(self, other) -> bool:
        return self._name <= self._ensure_game_instance(other).name

    def __lt__(self, other) -> bool:
        return self._name < self._ensure_game_instance(other).name

    @staticmethod
    def _ensure_game_instance(other: Any) -> G:
        if isinstance(other, Game):
            return other

        raise ValueError(f"{other} is not a Game instance")

    # ================================================ Properties ===============================================

    @property
    def allows_multiple_winners(self) -> bool:
        """
        Determines if this game can produce more than one winner, either because it supports ties as a final state, because it produces ranking, or both. Un-ranked multiple winners are considered a tie at the first position for the purpose
        of the get_winners method

        Returns
        -------
        bool
            True if this game allows more than one winner, False otherwise
        """
        return self.allows_ties or self.produces_ranking

    @property
    def allows_ties(self) -> bool:
        """
        Determines if this game can produce ties as a final result. By default, this method returns False (no ties)

        Returns
        -------
        bool
            True if this game can complete normally while producing ties, False otherwise (will continue until a clear winner emerges)
        """
        return False

    @property
    def allows_unlimited_actions(self) -> bool:
        """
        Determines if this game allows players to register as many actions as they want each round. By default, this property is False, but betting game may instead return True to allow player to place multiple bets

        Returns
        -------
        bool
            True if this game allows players to register as many actions as they want each round
        """
        return False

    @property
    def default_config(self) -> GameConfig:
        """
        The basic configuration for this game.

        Returns
        -------
        GameConfig
            The basic configuration for this game
        """
        return GameConfig()

    @property
    def has_multiple_rounds(self) -> bool:
        """
        Determines if this game can have more than one round, either because it always has more than one rounds, or because previous rounds ended up in a draw and this game doesn't allow ties. By default, this method returns False (single round)

        Returns
        -------
        bool
            True if this game can have more than one round, False otherwise
        """
        return False

    @property
    def hides_action_details(self) -> bool:
        """
        Determines if this game requires that the participants' actions remain hidden while a round or the whole game is running. A game that hides the action during a round may still reveal them once the round or game ends. By default, this method
        return True (the game hides the actions until resolution)

        Returns
        -------
        bool
            True if this game requires that actions remain hidden until resolution, False otherwise
        """
        return True

    @property
    def id(self) -> str:
        """
        This game's identifier.

        Returns
        -------
        str
            The identifier of this game, it should be unique within the game catalog
        """
        return self._id

    @property
    def image(self) -> Optional[disnake.File]:
        """
        This game's image, used on the UI to add ambiance.

        Returns
        -------
        Optional[disnake.File]
            The game's image if any, None otherwise
        """
        file_path = compute_game_file_path(self._id)
        try:
            return disnake.File(file_path)
        except OSError:
            return None

    @property
    def instance_label(self) -> str:
        """
        The label to use for instance of this game, typically placed after the game's name. A player invitation message could therefore look like: "You've been invited to participate in a <game.name> <game.instance_label>".

        Returns
        -------
        str
            The label to use to represent an instance of this game, by default "game"
        """
        return "game"

    @property
    def maximum_duration(self) -> Optional[timedelta]:
        """
        Determines if this game has a maximum duration and, if so, how long it is. A game with a maximum duration should be ended when that duration expires. By default, this method returns None (no maximum duration)

        Returns
        -------
        Optional[timedelta]
            The maximum duration of this game if any, None otherwise
        """
        return None

    @property
    def maximum_players(self) -> Optional[int]:
        """
        Determines if this game has a maximum number of participants and, if so how many. A game with a maximum number of participants may automatically end when the move of the last player is chosen, unless the game also allow multiple moves from
        the same user, or this game consists of multiple rounds. By default, this method returns None (no maximum participants)

        Returns
        -------
        Optional[int]
            The maximum number of players if any, None otherwise
        """
        return None

    @property
    def minimum_players(self) -> int:
        """
        Determines the minimum number of participants for this game to conclude normally (without canceling). A game that cannot conclude usually reimburse the participants. By default, this method returns 1

        Returns
        -------
        int
            The minimum number of players
        """
        return 1

    @property
    def name(self) -> str:
        """
        This game's name.

        Returns
        -------
        str
            The name of this game as understandable by a human
        """
        return self._name

    @property
    def produces_ranking(self) -> bool:
        """
        Determines if this game can rank its winners. False by default

        Returns
        -------
        Optional[int]
            The maximum number of participants if any, None otherwise
        """
        return False

    @property
    def produces_winning_odds(self) -> bool:
        """
        Determines if this game produces scores that should be interpreted as winning odds for gambling purposes. False by default

        Returns
        -------
        bool
            True if this game produces scores that should be interpreted as winning odds for gambling purposes, False otherwise
        """
        return False

    @property
    def required_properties(self) -> set[str]:
        """
        Determines the names of the properties that should be specified when starting a match of this game. By default, this method return an empty set (no required properties)

        Returns
        -------
        set[str]
            The set containing the property name of all the properties that must be defined when starting this game
        """
        return set()

    @property
    def supported_properties(self) -> set[str]:
        """
        Determines the names of the properties that can be specified when starting a match of this game. By default, this method return an empty set (no supported properties)

        Returns
        -------
        set[str]
            The set containing the property name of all the properties that can optionally be defined when starting this game
        """
        return set()

    # ================================================ "Real" methods ===============================================

    @abstractmethod
    def action(self, action_id: str) -> GameAction:
        """
        Gets the action associated with the specified action id for this game.

        Parameters
        ----------
        action_id: str
                   The action identifier

        Returns
        -------
        GameAction
            The action associated with the specified action id for this game

        Raises
        -------
        ValueError
            If the specified action id is not part of this game
        """
        pass

    @abstractmethod
    def actions(self) -> set[GameAction]:
        """
        Gets all the actions that this game may require.

        Returns
        -------
        set[GameAction]
            All the actions that this game may require
        """
        pass

    @abstractmethod
    def action_states(self) -> dict[tuple[str, str], list[GameAction]]:
        """
        Gets all the actions states that this game may end up in. An action is a set of possible action at a given time.

        Returns
        -------
        dict[tuple[str, str], list[GameAction]]
            All the actions states that this game may end up in as a dictionary using the state id (as per GameState.to_key) as a key and the valid actions when in that state as a value
        """
        pass

    def authorized(self, state: GameState, player: Player) -> bool:
        """
        Determines if the specified player can participate in this game in the specified state.

        Parameters
        ----------
        state: GameState
               The current game state, before canceling the game

        player: Player
                The player

        Returns
        -------
        bool
            True if the specified player can participate in this game in the specified state, False otherwise

        Raises
        -------
        InvalidGameStateError
            If the specified current state is not a state from this game
        """
        authorized_ids: Optional[set[int]] = cast(Optional[set[int]], self.authorized_players(state))
        if authorized_ids is None:
            return True

        return player.id in authorized_ids

    @abstractmethod
    def authorized_players(self, state: GameState) -> set[int]:
        """
        Gets the identifiers of the players authorized to submit a move for this game in the specified state.

        Parameters
        ----------
        state: GameState
               The current game state, before canceling the game

        Returns
        -------
        set[int]
            The set of player identifiers authorized to place a move/action on this game in the specified state, or None if any player is authorized

        Raises
        -------
        InvalidGameStateError
            If the specified current state is not a state from this game
        """
        pass

    def can_register_action(self, state: GameState, player: Player) -> bool:
        """
        Determines if the specified player can still register a move for this game in the specified state.

        Parameters
        ----------
        state: GameState
               The current game state, before canceling the game

        player: Player
                The player

        Returns
        -------
        bool
            True if the specified player can still register a move for this game in the specified state, False otherwise

        Raises
        -------
        InvalidGameStateError
            If the specified current state is not a state from this game
        """
        return self.missing_action_count(state, player) > 0

    @abstractmethod
    def cancel(self, state: GameState) -> GameState:
        """
        Cancels a game

        Parameters
        ----------
        state: GameState
               The current game state, before canceling the game

        Returns
        -------
        GameState
            The canceled game state

        Raises
        -------
        InvalidGameStateError
            If the specified current state is not a state from this game
        """
        pass

    @abstractmethod
    def config(self, state: GameState) -> GameConfig:
        """
        Obtain the configuration of this game in the specified state

        Parameters
        ----------
        state: GameState
               The game state

        Returns
        -------
        GameConfig
            The configuration of the game in the given state

        Raises
        -------
        InvalidGameStateError
            If the specified current state is not a state from this game
        """
        pass

    @abstractmethod
    def current_round_completed(self, state: GameState) -> bool:
        """
        Determines if this game in the specified state has completed its current round

        Parameters
        ----------
        state: GameState
               The game state

        Returns
        -------
        bool
            True if the current round is completed, False otherwise. If the game itself is completed then this method should also return True

        Raises
        -------
        InvalidGameStateError
            If the specified current state is not a state from this game
        """
        pass

    def missing_action_count(self, state: GameState, player: Player) -> int:
        """
        Determines how many more action the specified player should take during the current round of this game in the specified state.

        Parameters
        ----------
        state: GameState
               The current game state, before canceling the game

        player: Player
                The player

        Returns
        -------
        int
            The number of action the specified player still need to perform during the round

        Raises
        -------
        InvalidGameStateError
            If the specified current state is not a state from this game
        """
        if state.canceled or state.finished or not self.authorized(state, player):
            return 0

        if self.allows_unlimited_actions:
            return 0

        moves: dict[int, list[tuple[GameAction, Optional[Union[str, int]]]]] = self.round_actions(state)
        player_moves: list[tuple[GameAction, Optional[Union[str, int]]]] = moves[player.id] if player.id in moves else []
        return max(self.required_action_count(state) - len(player_moves), 0)

    @abstractmethod
    def next_round(self, state: GameState) -> GameState:
        """
        Move this game to the next round

        Parameters
        ----------
        state: GameState
               The game state

        Returns
        -------
        GameState
            The new game state after moving to the next round

        Raises
        -------
        InvalidGameStateError
            If the specified current state is not a state from this game or if trying to move to next round while the game is already completed or the current round is not completed
        """
        pass

    def possible_actions(self, state: GameState) -> list[GameAction]:
        """
        Provides the list of actions that players can perform given a specific gate state. The actual state implementation varies per game and can be considered opaque to callers of this method. The current state can be obtained from the
        GamblingTable hosting the game. It's important that implementations of this method are 100% idempotent, i.e., that they always return the same possible actions for a given state "key" (the tuple from its game id and state id)

        Parameters
        ----------
        state: GameState
               The state of the game for which the possible actions must be computed

        Returns
        -------
        list[GameAction]
            The list of possible actions for the players given the specific state

        Raises
        -------
        InvalidGameStateError
            If the specified current state is not a state from this game
        """
        key: tuple[str, str] = state.key
        actions: dict[tuple[str, str], list[GameAction]] = self.action_states()
        if key not in actions:
            raise InvalidGameStateError(f"Couldn't find the possible actions for state key {key} within available actions states {actions}")

        return actions[key].copy()

    def register_action(self, state: GameState, player: Player, action_id: str, action_value: Optional[Union[str, int]] = None) -> GameState:
        """
        Registers the move of a player into this game's state and return the new game state

        Parameters
        ----------
        state: GameState
               The current game state, before registering the player's move

        player: Player
                The player performing the action

        action_id: str
                   The player's action, must be a value within the possible action ids as defined by the possible_actions method for the current state

        action_value: Optional[Union[str, int]], optional
                      The player's action value, applicable only if the action from possible_actions with the specified action's name was requiring an input

        Returns
        -------
        GameState
            The new game state after registering the move

        Raises
        -------
        InvalidGameStateError
            If the specified current state is not a state from this game

        UnauthorizedPlayerException
            If the specified player is not authorized to participate in this game when it's in the specified state

        InvalidActionException
            If the specified action or its value/parameter are not expected/valid for this game in the specified state

        PlayerAlreadyActedException
            If the specified player already filled all their required move(s) for this game in its current state
        """
        if state.canceled:
            raise InvalidActionException(f"This game of {self.name} was canceled")
        elif state.finished:
            raise InvalidActionException(f"This game of {self.name} is finished")

        if action_id == Game.ACTION_REGISTER.id:
            return self.register_player(state, player)

        if not self.authorized(state, player):
            raise UnauthorizedPlayerException("You're not authorized to participate to this game")

        if not self.allows_unlimited_actions:
            moves: dict[int, list[tuple[GameAction, Optional[Union[str, int]]]]] = self.round_actions(state)
            player_moves: list[tuple[GameAction, Optional[Union[str, int]]]] = moves[player.id] if player.id in moves else []
            if len(player_moves) >= self.required_action_count(state):
                raise PlayerAlreadyActedException("You already performed all your actions for the round")

        possible_actions: list[GameAction] = self.possible_actions(state)
        if action_id not in {action.id for action in possible_actions}:
            raise InvalidActionException(f"You cannot perform {action_id} at this time")

        return self._do_register_action(state, player, action_id, action_value)

    def register_player(self, state: GameState, player: Player) -> GameState:
        """
        Registers the player into this game's state and return the new game state. Implementations of this method should make sure that registration is still possible before performing the actual registration. If the player cannot be registered
        because he's already registered or the seat are full, then an InvalidActionException should be raised

        Parameters
        ----------
        state: GameState
               The current game state, before registering the player

        player: Player
                The player to register

        Returns
        -------
        GameState
            The new game state after registering the player

        Raises
        -------
        InvalidGameStateError
            If the specified current state is not a state from this game

        InvalidActionException
            If the specified player cannot be registered into the game, either because he's already registered, because the seat are full, or because this game in the specified state no longer accept registration for some other reason
        """
        if state.canceled:
            raise InvalidActionException(f"This game of {self.name} was canceled")
        elif state.finished:
            raise InvalidActionException(f"This game of {self.name} is finished")

        actual_state: IntransitiveGameState = self._ensure_state_type(state, IntransitiveGameState)
        if actual_state.action_state != GameState.STATE_REGISTRATION:
            raise InvalidActionException(f"Registration for this game of {self.name} is finished")

        authorized_players: set[int] = self.authorized_players(state)
        if player.id in authorized_players:
            raise InvalidActionException("You already registered to participate to this game")

        max_players: Optional[int] = self.maximum_players
        if max_players is not None and len(authorized_players) >= max_players:
            raise InvalidActionException("All places are already taken")

        config: GameConfig = self.config(state)
        if config.maximum_players is not None and len(authorized_players) >= config.maximum_players:
            raise InvalidActionException("All places are already taken")

        return self._do_register_player(state, player)

    def required_action_count(self, state: GameState) -> int:
        """
        Computes the required number of action a player should take in the round of the game represented by the specified state.

        Parameters
        ----------
        state: GameState
               The state of the game

        Returns
        -------
        int
            The required number of actions each participant must register before the round can proceed

        Raises
        -------
        InvalidGameStateError
            If the specified current state is not a state from this game
        """
        return self.config(state).required_action_count

    def requires_new_round(self, state: GameState) -> bool:
        """
        Determines if this game should move to a new round.

        Parameters
        ----------
        state: GameState
               The state of the game

        Returns
        -------
        bool
            True if the current round is completed and a new round is needed to complete the game, False otherwise

        Raises
        -------
        InvalidGameStateError
            If the specified current state is not a state from this game
        """
        if state.completed:
            return False

        if not self.current_round_completed(state):
            return False

        return self._do_requires_new_round(state)

    @abstractmethod
    def round_actions(self, state: GameState) -> dict[int, list[tuple[GameAction, Optional[Union[str, int]]]]]:
        """
        Gets the actions that are performed on the current round represented by the specified game state

        Parameters
        ----------
        state: GameState
               The game state

        Returns
        -------
        dict[int, tuple[int, list[Union[str, int]]]]
            A dictionary containing the list of actions by player id for the round of the game represented by the specified state. Each action entry contains the action and its selected value/parameter

        Raises
        -------
        InvalidGameStateError
            If the specified current state is not a state from this game
        """
        pass

    @abstractmethod
    def round_number(self, state: GameState) -> int:
        """
        Gets the round number for this game when in the specified state

        Parameters
        ----------
        state: GameState
               The game state

        Returns
        -------
        int
            The round number of this game when in the specified state. If the game is finished this method will return the round number of the last round of the game. If this game does not support round, this method returns -1. If the game is still
            in registration state, then this method should return 0

        Raises
        -------
        InvalidGameStateError
            If the specified current state is not a state from this game
        """
        pass

    def score(self, state: GameState, player: Player) -> Optional[float]:
        """
        Get the score of the specified player for this game in the specified state.
        - If this game in the specified state is not completed, this method may or not return a value, depending on this game supports for progressive score accumulation or simply winner determination
        - Else, return the score of the specified player for this game in the specified state, or None if the specified player didn't participate in the game

        Parameters
        ----------
        state: GameState
               A state of this game

        player: Player
                The player whose score must be computed

        Returns
        -------
        Optional[float]
            The score of the specified player of this game in the specified state if this game can compute one, Non otherwise
        """
        scores: Optional[dict[int, float]] = self.scores(state)
        return None if scores is None else scores.get(player.id)

    @abstractmethod
    def scores(self, state: GameState) -> Optional[dict[int, float]]:
        """
        Get the final scores for this game in the specified state, per player id.
        - If this game in the specified state is not completed, this method may or not return a value, depending on this game supports for progressive score accumulation or simply winner determination
        - Else, return the score of all players for this game in the specified state

        Parameters
        ----------
        state: GameState
               A state of this game

        Returns
        -------
        Optional[dict[int, float]]
            The score of all players of this game in the specified state if this game can compute one, Non otherwise
        """
        pass

    @abstractmethod
    def start(self, config: Optional[GameConfig] = None, authorized_players: Optional[set[int]] = None) -> GameState:
        """
        Starts a new game with the specified properties. The expected and supported property keys can be found from the supported_properties and required_properties property.

        Parameters
        ----------
        config: GameConfig, optional
                The game settings for the new game to start, keys should come from supported_properties and required_properties. The meaning of each of those keys can be found in their documentation

        authorized_players: set[int], optional
                            The identifiers of the players authorized to participate in the game. If none are specified and this game has a minimum or maximum number of players then it will be processed as first come, first served for a seat

        Returns
        -------
        GameState
            A fresh/clean state for this game

        Raises
        -------
        IllegalGameSettingsException
            If this game does not support the specified settings (player limitation, multiple rounds, or the specified properties) or, requires settings that were left unspecified
        """
        pass

    def winner(self, state: GameState) -> Optional[list[GameScore]]:
        """
        Identify the winner of the game in the specified state.

        Parameters
        ----------
        state: GameState
               A state of this game

        Returns
        -------
        Optional[list[GameScore]]
            None if this game in the specified state is not completed, the score of the sole winner contained within a list otherwise (or multiple scores in case of ties and this game supports ties)

        Raises
        -------
        InvalidGameStateError
            If the specified state is not a state from this game, or this game produces a ranking rather than a single winner
        """
        if self.produces_ranking:
            raise InvalidGameStateError(f"{self.name} produces a ranking, not a single winner")

        winners: Optional[list[list[GameScore]]] = cast(Optional[list[list[GameScore]]], self.winners(state))
        if winners is None:
            return None

        return winners[0]

    @abstractmethod
    def winners(self, state: GameState) -> Optional[list[list[GameScore]]]:
        """
        Identify the winners of this game given the specified state.

        - If this game in the specified state is not completed, this method returns None
        - Else, if this game supports rankings, then each index within the returned list represent a position in the ranking with each potentially containing more than one score, but only if this game supports ties
        - Else, if this game doesn't support ranking, but supports ties, then only the first index of the returned list will be populated, with the inner list at that index containing the scores of all the winners
        - Else, the returned list will contain a single inner list that itself will contain a single score

        Parameters
        ----------
        state: GameState
               A state of this game

        Returns
        -------
        Optional[list[list[GameScore]]]
            None if this state is not completed, the list of winner scores otherwise, either with a single id if the game this state is linked to doesn't support ranking, or the ranked winner scores if it does. In case of ties at a given ranking,
            more than one score will be present in the list

        Raises
        -------
        InvalidGameStateError
            If the specified state is not a state from this game
        """
        pass

    def _to_non_valued_round_actions(self, current_round_action_ids: dict[int, list[str]], previous_round_action_ids: list[dict[int, list[str]]], round_number: Optional[int] = None) -> dict[int, list[tuple[GameAction, None]]]:
        """
        Locate and transform the specified round action ids into the actual player actions for the specified round number (or latest round if round_number is left unspecified)

        Parameters
        ----------
        current_round_action_ids: dict[int, list[str]]
                                  The player action ids for the current round, which should be round number len(previous_round_action_ids) + 1. When a game is completed, the current_round_action_ids should be the action for the round that
                                  determined the winner

        previous_round_action_ids: list[dict[int, list[str]]]
                                   The player action ids, per round, but only for previously completed rounds when more rounds were necessary (completed round 1 at index 0, completed round 2 at index 1, etc.)

        round_number: int, optional
                      The round number for which the actions should be computed

        Returns
        -------
        dict[int, list[tuple[GameAction, None]]]
            The non-value round actions for the current round if no round number was specified, the non-valued round actions for the specified round otherwise

        Raises
        -------
        ValueError
            If the specified round number is not valid for the specified all_round_action_ids
        """
        max_round_number: int = len(previous_round_action_ids) + 1
        if round_number is not None and round_number > max_round_number:
            raise ValueError(f"Cannot compute the round actions of round {round_number} from the specified round actions since the latter provides only {max_round_number} round of data")

        if max_round_number == 0:
            return {}

        if round_number is None or round_number == max_round_number:
            round_action_ids: dict[int, list[str]] = current_round_action_ids
        else:
            round_action_ids: dict[int, list[str]] = previous_round_action_ids[round_number - 1]

        if len(round_action_ids) == 0:
            return {}

        round_actions: dict[int, list[tuple[GameAction, None]]] = {}
        for player_id, action_ids in round_action_ids.items():
            round_actions[player_id] = [(self.action(action_id), None) for action_id in action_ids]

        return round_actions

    @abstractmethod
    def _do_register_action(self, state: GameState, player: Player, action_id: str, action_value: Optional[Union[str, int]] = None) -> GameState:
        """
        Registers the move of a player into this game's state and return the new game state. This method is called internally from register_action when it was validated that the action is within expected actions in the current state,
        and that the player is authorized to register an action as per can_register_action result. Therefore, subclasses implementing this method can focus on the actual action registration rather than boilerplate validations

        Parameters
        ----------
        state: GameState
               The current game state, before registering the player's move

        player: Player
                The player performing the action

        action_id: str
                   The player's action, must be a value within the possible action ids as defined by the possible_actions method for the current state

        action_value: Optional[Union[str, int]], optional
                      The player's action value, applicable only if the action from possible_actions with the specified action's name was requiring an input

        Returns
        -------
        GameState
            The new game state after registering the move

        Raises
        -------
        InvalidActionException
            If the specified player action cannot be registered for any reason
        """
        pass

    @abstractmethod
    def _do_register_player(self, state: GameState, player: Player) -> GameState:
        """
        Registers the player into this game's state and return the new game state. Implementations of this method don't have to make boilerplate validation such as registration phase, maximum player count or if the specified player is already
        participating or not.

        Parameters
        ----------
        state: GameState
               The current game state, before registering the player

        player: Player
                The player to register

        Returns
        -------
        GameState
            The new game state after registering the player

        Raises
        -------
        InvalidActionException
            If the specified player cannot be registered into the game, or because this game in the specified state no longer accept registration for some other reason
        """
        pass

    @abstractmethod
    def _do_requires_new_round(self, state: GameState) -> bool:
        """
        Determines if this game should move to a new round. Overridden implementations can assume that the game itself is not completed and the current round is completed when this method gets called. The default implementation always return True

        Parameters
        ----------
        state: GameState
               The state of the game

        Returns
        -------
        bool
            True if the current round is completed and a new round is needed to complete the game, False otherwise

        Raises
        -------
        InvalidGameStateError
            If the specified current state is not a state from this game
        """
        return True

    def _ensure_state_type(self, state: GameState, state_class: Type[S]) -> S:
        if isinstance(state, state_class):
            return state

        raise InvalidGameStateError(f"Unexpected game state found for {self.name}. Expected {state_class}, found {type(state)}")


class IntransitiveGameState(GameState):
    STATE_ACTIVE: str = "active"
    STATE_FINISHED: str = "finished"

    def __init__(self, game_id: str, config: GameConfig,
                 authorized_players: set[int],
                 current_round_actions: Optional[dict[int, list[str]]] = None,
                 previous_round_actions: Optional[list[dict[int, list[str]]]] = None,
                 round_scores: Optional[list[dict[int, float]]] = None,
                 completed: bool = False,
                 canceled: bool = False):
        super().__init__(game_id)
        self._authorized_players: set[int] = authorized_players.copy() if authorized_players is not None else set()
        self._config: GameConfig = config
        self._current_round_actions: dict[int, list[str]] = current_round_actions.copy() if current_round_actions is not None else {}
        self._previous_round_actions: list[dict[int, list[str]]] = previous_round_actions.copy() if previous_round_actions is not None else []
        self._round_scores: Optional[list[dict[int, float]]] = round_scores
        self._completed: bool = completed
        self._canceled: bool = canceled

    @property
    def action_state(self) -> str:
        if self.finished:
            return IntransitiveGameState.STATE_FINISHED
        elif len(self._authorized_players) < 2:
            return GameState.STATE_REGISTRATION
        else:
            return IntransitiveGameState.STATE_ACTIVE

    @property
    def authorized_players(self) -> set[int]:
        return self._authorized_players.copy()

    @property
    def canceled(self) -> bool:
        return self._canceled

    @property
    def completed(self) -> bool:
        return self._completed

    @property
    def config(self) -> GameConfig:
        return self._config.copy()

    @property
    def action_count(self) -> int:
        return self._config.action_count

    @property
    def extra_action_count(self) -> int:
        return self._config.extra_action_count

    @property
    def current_round_actions(self) -> dict[int, list[str]]:
        return {player_id: actions.copy() for player_id, actions in self._current_round_actions.items()}

    @property
    def previous_round_actions(self) -> list[dict[int, list[str]]]:
        return [actions.copy() for actions in self._previous_round_actions]

    @property
    def round_scores(self) -> Optional[list[dict[int, float]]]:
        return self._round_scores.copy() if self._round_scores is not None else None

    def _serialize_data(self) -> Any:
        """
        Serialize the internal data of this state. The returned value should be a valid input value for the _deserialize_data method receiving

        Returns
        -------
        Any
            A JSON-serializable representation of the internal data of this state
        """
        data: dict[str, Any] = {
            "game_id": self._game_id,
            "config": self._config.serialize(),
            "authorized_players": [int(player_id) for player_id in self._authorized_players] if self._authorized_players is not None else None,
            "current_round_actions": self._current_round_actions,
            "previous_round_actions": self._previous_round_actions,
            "round_scores": self._round_scores,
            "completed": self._completed,
            "canceled": self._canceled
        }

        return data

    @staticmethod
    def _deserialize_data(data: Any) -> GameState:
        """

        Parameters
        ----------
        data: Any
              The JSON-compliant serialized form of the GameState as previously generated by the _serialize_data method

        Returns
        -------
        GameState
            The deserialized concrete GameState instance
        """
        game_id: str = data["game_id"]
        config: GameConfig = GameConfig.deserialize(data["config"])
        authorized_players_data: Optional[list[int]] = data.get("authorized_players")
        current_round_actions: dict[int, list[str]] = data["current_round_actions"]
        previous_round_actions: list[dict[int, list[str]]] = data["previous_round_actions"]
        round_scores: Optional[list[dict[int, float]]] = data.get("round_scores")
        completed: bool = data["completed"]
        canceled: bool = data["canceled"]

        authorized_players: set[int] = set()
        if authorized_players_data is not None:
            for player_id in authorized_players_data:
                authorized_players.add(int(player_id))

        return IntransitiveGameState(game_id, config, authorized_players, current_round_actions, previous_round_actions, round_scores, completed, canceled)


class IntransitiveGame(Game, metaclass=ABCMeta):

    def __init__(self, game_id: str, name: str, actions: list[GameAction], ascendancy_rules: Optional[dict[str, list[str]]] = None):
        super().__init__(game_id, name)
        self._validate_actions(actions)

        self._actions: list[GameAction] = actions
        self._actions_by_id: dict[str, GameAction] = {action.id: action for action in actions}
        self._actions_by_id[Game.ACTION_REGISTER.id] = Game.ACTION_REGISTER
        self._action_states: dict[tuple[str, str], list[GameAction]] = {
            GameState.to_key(game_id, IntransitiveGameState.STATE_REGISTRATION): [Game.ACTION_REGISTER],
            GameState.to_key(game_id, IntransitiveGameState.STATE_ACTIVE): self._actions.copy(),
            GameState.to_key(game_id, IntransitiveGameState.STATE_FINISHED): []
        }

        self._ascendancy_rules: dict[str, list[str]] = self._compute_ascendancy_relationships(actions, ascendancy_rules)

    # ================================================ Properties ===============================================

    @property
    def default_config(self) -> GameConfig:
        config: GameConfig = super().default_config
        config.maximum_players = 2
        config.action_count = 1
        config.extra_action_count = 0
        return config

    @property
    def minimum_players(self) -> int:
        return 2

    @property
    def maximum_players(self) -> Optional[int]:
        return 2

    @property
    def required_properties(self) -> set[str]:
        return set()

    @property
    def supported_properties(self) -> set[str]:
        return {PROP_ACTION_COUNT, PROP_ACTION_COUNT_EXTRA}

    # ============================================== "Real" methods =============================================

    def authorized_players(self, state: GameState) -> set[int]:
        return self._ensure_state_type(state, IntransitiveGameState).authorized_players

    def action(self, action_id: str) -> GameAction:
        return self._actions_by_id[action_id]

    def actions(self) -> set[GameAction]:
        all_actions: set[GameAction] = {action for action in self._actions}
        all_actions.add(Game.ACTION_REGISTER)
        return all_actions

    def action_states(self) -> dict[tuple[str, str], list[GameAction]]:
        return self._action_states.copy()

    def cancel(self, state: GameState) -> GameState:
        actual_state: IntransitiveGameState = self._ensure_state_type(state, IntransitiveGameState)
        if actual_state.completed:
            raise InvalidGameStateError("Cannot cancel a game that was already completed")

        return IntransitiveGameState(actual_state.game_id, actual_state.config, actual_state.authorized_players, actual_state.current_round_actions, actual_state.previous_round_actions, actual_state.round_scores, False, True)

    def compute_result(self, action_left: str, action_right: str) -> int:
        """
        Determines the result of the ascendancy battle between action_left and action_right

        Parameters
        ----------
        action_left: str
                     The identifier of the action from the first participant

        action_right: str
                      The identifier of the action from the second participant

        Returns
        -------
        int
            -1 if action_left has ascendancy over action_right (left wins, right loses), 0 if action_left and action_right are considered equivalent (draw), 1 if action_right has ascendancy over action_left (left loses, right wins)

        Raises
        -------
        ValueError
            If the specified actions are not valid for this game
        """
        self._validate_action_id(action_left)
        self._validate_action_id(action_right)

        if action_right in self._ascendancy_rules[action_left]:
            return -1
        elif action_left in self._ascendancy_rules[action_right]:
            return 1
        else:
            return 0

    def config(self, state: GameState) -> GameConfig:
        return self._ensure_state_type(state, IntransitiveGameState).config

    def current_round_completed(self, state: GameState) -> bool:
        if state.completed:
            return True

        actual_state: IntransitiveGameState = self._ensure_state_type(state, IntransitiveGameState)
        round_scores: Optional[list[dict[int, float]]] = actual_state.round_scores
        if round_scores is None:
            return False

        # len(round_scores) should actually be equal to len(actual_state.previous_round_actions) + 1 when the current round is completed
        return len(round_scores) > len(actual_state.previous_round_actions)

    def next_round(self, state: GameState) -> GameState:
        if state.completed:
            raise InvalidGameStateError(f"This {self.name} {self.instance_label} was already completed")
        elif state.canceled:
            raise InvalidGameStateError(f"This {self.name} {self.instance_label} was canceled")

        if not self.current_round_completed(state):
            raise InvalidGameStateError(f"Cannot move to next round when another round is in progress")

        actual_state: IntransitiveGameState = self._ensure_state_type(state, IntransitiveGameState)
        current_round_actions: dict[int, list[str]] = actual_state.current_round_actions
        previous_round_actions: list[dict[int, list[str]]] = actual_state.previous_round_actions
        previous_round_actions.append(current_round_actions)
        current_round_actions: dict[int, list[str]] = {player_id: [] for player_id in actual_state.authorized_players}

        return IntransitiveGameState(game_id=self.id, config=actual_state.config, authorized_players=actual_state.authorized_players,
                                     current_round_actions=current_round_actions, previous_round_actions=previous_round_actions, round_scores=actual_state.round_scores)

    def round_actions(self, state: GameState) -> dict[int, list[tuple[GameAction, Optional[Union[str, int]]]]]:
        actual_state: IntransitiveGameState = self._ensure_state_type(state, IntransitiveGameState)
        return self._to_non_valued_round_actions(actual_state.current_round_actions, actual_state.previous_round_actions)

    def round_number(self, state: GameState) -> int:
        actual_state: IntransitiveGameState = self._ensure_state_type(state, IntransitiveGameState)
        if actual_state.action_state == GameState.STATE_REGISTRATION:
            return 0

        return len(actual_state.previous_round_actions) + 1

    def scores(self, state: GameState) -> Optional[dict[int, float]]:
        # TODO
        pass

    def start(self, config: Optional[GameConfig] = None, authorized_players: Optional[set[int]] = None) -> GameState:
        if config is None:
            config = self.default_config

        state: IntransitiveGameState = IntransitiveGameState(game_id=self.id, config=config, authorized_players=authorized_players)

        return state

    def winners(self, state: GameState) -> Optional[list[list[int]]]:
        # TODO
        pass

    @staticmethod
    def _build_ascendancy_relationships(actions: list[GameAction]) -> dict[str, list[str]]:
        ascendancy: dict[str, list[str]] = {}
        for i in range(0, len(actions) - 1):
            ascendancy[actions[i].id] = [actions[i + 1].id]

        ascendancy[actions[len(actions) - 1].id] = [actions[0].id]

        return ascendancy

    @staticmethod
    def _compute_ascendancy_relationships(actions: list[GameAction], ascendancy_rules: Optional[dict[str, list[str]]] = None) -> dict[str, list[str]]:
        if ascendancy_rules is None:
            return IntransitiveGame._build_ascendancy_relationships(actions)
        else:
            IntransitiveGame._validate_ascendancy_relationships(actions, ascendancy_rules)
            return ascendancy_rules

    def _do_register_action(self, state: GameState, player: Player, action_id: str, action_value: Optional[Union[str, int]] = None) -> GameState:
        actual_state: IntransitiveGameState = self._ensure_state_type(state, IntransitiveGameState)
        actions: dict[int, list[str]] = actual_state.current_round_actions
        if player.id in actions:
            actions[player.id].append(action_id)
        else:
            # Shouldn't happen
            actions[player.id] = [action_id]

        round_scores: Optional[list[dict[int, float]]] = actual_state.round_scores
        required_action_count: int = actual_state.config.required_action_count
        if sum(len(player_actions) == required_action_count for player_actions in actions.values()) == len(actions):
            # All actions for the round were registered, resolve the result
            player_1: int = player.id
            player_2: int = next(iter([player_id for player_id in actions.keys() if player_id != player_1]))
            player_1_actions: list[str] = actions[player_1]
            player_2_actions: list[str] = actions[player_2]
            player_1_score: int = 0
            player_2_score: int = 0

            base_action_count: int = actual_state.action_count
            for action_number in range(0, base_action_count):
                result: int = self.compute_result(player_1_actions[action_number], player_2_actions[action_number])
                if result < 0:
                    player_1_score += 1
                elif result > 0:
                    player_2_score += 1

            if player_1_score == player_2_score:
                # Check extra actions which are in sudden death
                extra_action_count: int = actual_state.extra_action_count
                for action_number in range(base_action_count, base_action_count + extra_action_count):
                    result: int = self.compute_result(player_1_actions[action_number], player_2_actions[action_number])
                    if result < 0:
                        player_1_score += 1
                        break
                    elif result > 0:
                        player_2_score += 1
                        break

            completed: bool = player_1_score != player_2_score or self.allows_ties
            round_score: dict[int, float] = {
                player_1: player_1_score,
                player_2: player_2_score
            }
            if round_scores is None:
                round_scores: list[dict[int, float]] = [round_score]
            else:
                round_scores.append(round_score)
        else:
            completed: bool = False

        return IntransitiveGameState(game_id=self.id, config=actual_state.config, authorized_players=actual_state.authorized_players,
                                     current_round_actions=actions, previous_round_actions=actual_state.previous_round_actions, round_scores=round_scores,
                                     completed=completed)

    def _do_register_player(self, state: GameState, player: Player) -> GameState:
        actual_state: IntransitiveGameState = self._ensure_state_type(state, IntransitiveGameState)
        authorized_players: set[int] = actual_state.authorized_players
        authorized_players.add(player.id)
        if len(authorized_players) >= 2:
            # Seat filled, initialize the actions
            current_round_actions: dict[int, list[str]] = {player_id: [] for player_id in authorized_players}
        else:
            current_round_actions: Optional[dict[int, list[str]]] = None

        return IntransitiveGameState(self.id, actual_state.config, authorized_players, current_round_actions)

    def _do_requires_new_round(self, state: GameState) -> bool:
        return True

    def _validate_action_id(self, action_id: str) -> bool:
        if action_id not in self._actions_by_id:
            raise ValueError(f"{action_id} is not known to {self.name}")

        return True

    @staticmethod
    def _validate_actions(actions: list[GameAction]):
        if len(actions) < 3:
            raise ValueError(f"Intransitive games require at least three possible actions")

        action_ids: set[str] = {action.id for action in actions}
        if len(action_ids) < len(actions):
            raise ValueError(f"All actions in an intransitive game should have unique ids, found: {actions}")

    @staticmethod
    def _validate_ascendancy_relationships(actions: list[GameAction], ascendancy_rules: dict[str, list[str]]):
        action_ids: set[str] = {action.id for action in actions}

        missing_winning_over: list[str] = [action_id for action_id in action_ids if action_id not in ascendancy_rules or len(ascendancy_rules[action_id]) == 0]
        if len(missing_winning_over) > 0:
            raise ValueError(f"All actions should be able to win over at least one value, but {missing_winning_over} have advantage over nothing")

        with_ascendancy: set[str] = set([action_id for descendants in ascendancy_rules.values() for action_id in descendants])
        missing_won_over_by: set[str] = action_ids - with_ascendancy
        if len(missing_won_over_by) > 0:
            raise ValueError(f"All actions should be have to lose against at least one value, but nothing can beat {missing_winning_over}")

        winning_over_themselves: set[str] = set([ascendant_id for ascendant_id, descendant_ids in ascendancy_rules.items() if ascendant_id in descendant_ids])
        if len(winning_over_themselves) > 0:
            raise ValueError(f"Action should never win over themselves, but {winning_over_themselves} can each beat themselves")

        return ascendancy_rules

    def _validate_state(self, state: GameState) -> IntransitiveGameState:
        if isinstance(state, IntransitiveGameState):
            return state

        raise InvalidGameStateError(f"{self.name} expects IntransitiveGameState state instances, found {type(state)}")

from typing import Optional, Callable, TypeVar

import disnake

from gaming.game import Game
from gaming.shoushiling import Shoushiling
from gaming.strongranking import StrongRankingGrandCompetition
from utils.CommandUtils import MAX_CHOICE_ITEMS
from utils.base import singleton

C = TypeVar("C", bound="GameCatalog")


async def autocomplete_game_id(_: disnake.ApplicationCommandInteraction, user_input: str) -> list[str]:
    return _autocomplete_game(user_input, lambda game: game.id)


async def autocomplete_game_name(_: disnake.ApplicationCommandInteraction, user_input: str) -> list[str]:
    return _autocomplete_game(user_input, lambda game: game.name)


def _autocomplete_game(user_input: str, supplier: Callable[[Game], str]) -> list[str]:
    games = GameCatalog().games
    if user_input is not None and len(user_input) > 0:
        lookup = user_input.lower()
        candidates = [supplier(item) for item in games if lookup in item.name.lower() or lookup in item.id]
    else:
        candidates = [supplier(item) for item in games]

    if len(candidates) > MAX_CHOICE_ITEMS:
        candidates = candidates[:MAX_CHOICE_ITEMS]

    return candidates


# =======================================================================================================================
# ==================================================== GameCatalog ======================================================
# =======================================================================================================================
@singleton
class GameCatalog:
    def __init__(self):
        self._games: list[Game] = [Shoushiling(), StrongRankingGrandCompetition()]
        self._game_by_id: dict[str, Game] = {game.id: game for game in self._games}
        self._game_by_name: dict[str, Game] = {game.name: game for game in self._games}

    # ============================================= Special methods =============================================

    def __repr__(self) -> str:
        return f"GameCatalog containing the following games: {self._games}"

    def __str__(self) -> str:
        return "GameCatalog"

    def __contains__(self, key: str) -> bool:
        return key in self._game_by_id

    def __getitem__(self, game_id: str) -> Game:
        if game_id not in self._game_by_id:
            raise ValueError(f"Cannot find game {game_id} within the catalog {self}")

        return self._game_by_id[game_id]

    # ================================================ Properties ===============================================

    @property
    def games(self) -> list[Game]:
        """
        Gets all the games within this catalog

        Returns
        -------
        list[Game]
            All the game in this catalog, sorted in ascending order
        """
        return self._games.copy()

    @property
    def game_ids(self) -> list[str]:
        """
        The identifier of all the games within this catalog.

        Returns
        -------
        list[str]
            The identifier of all the games within this catalog, sorted alphabetically
        """
        return [game.id for game in self._games]

    @property
    def game_names(self) -> list[str]:
        """
        The name of all the games within this catalog, sorted alphabetically

        Returns
        -------
        list[str]
            The name of all the games within this catalog, sorted alphabetically
        """
        return [game.name for game in self._games]

    # ================================================ "Real" methods ===============================================

    def get(self, game_id: str) -> Optional[Game]:
        """
        Find a game in this catalog by its identifier.

        Parameters
        ----------
        game_id: str
                 The game's identifier

        Returns
        -------
        Optional[Game]
            The game with the specified identifier in this catalog if found, None otherwise
        """
        return self.get_by_id(game_id)

    def get_by_id(self, game_id: str) -> Optional[Game]:
        return self._game_by_id.get(game_id)

    def get_by_name(self, game_name: str) -> Optional[Game]:
        return self._game_by_name.get(game_name)

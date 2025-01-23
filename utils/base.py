from datetime import timedelta
from typing import Type, TypeVar, Union, Optional

import disnake
from disnake import ChannelType
from disnake.ext import commands

from utils.LoggingUtils import log_event

T = TypeVar("T")

_WAIT_FOR_SLEEP_TIME: float = 0.1
_LAYERED_WAIT_FACTOR: float = 2.0
_WAIT_FOR_MAX_WAIT = timedelta(seconds=20)


def singleton(cls: Type[T]):
    instances: dict[Type[T], T] = {}

    def get_instance(*args, **kwargs) -> T:
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)

        instance: T = instances[cls]

        return instance

    return get_instance


class SingletonMeta(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance

        return cls._instances[cls]

    def get_instances(cls):
        return cls._instances

    def clear_instances(cls):
        cls._instances = {}


class CogNotLoadedError(Exception):
    def __init__(self):
        super().__init__()


class UnsupportedOperationError(Exception):
    def __init__(self, *args):
        super().__init__(*args)


class FunctionalValidationException(ValueError):
    def __init__(self, system_message: str, player_message: Optional[str] = None, player_embed: Optional[disnake.Embed] = None, ephemeral: bool = True):
        super().__init__(system_message)
        self._system_message: str = system_message
        self._player_message: Optional[str] = player_message
        self._player_embed: Optional[disnake.Embed] = player_embed
        self._ephemeral: bool = ephemeral

    @property
    def ephemeral(self) -> bool:
        return self._ephemeral

    @property
    def message(self) -> str:
        return self.system_message if self._player_message is None else self._player_message

    @property
    def player_embed(self) -> Optional[disnake.Embed]:
        return self._player_embed

    @property
    def player_message(self) -> Optional[str]:
        return self._player_message

    @property
    def system_message(self) -> str:
        return self._system_message

    async def send(self, inter: Union[disnake.CommandInteraction | disnake.MessageInteraction | disnake.ModalInteraction]) -> None:
        try:
            if self._player_embed is None:
                await inter.send(content=self.message, ephemeral=self._ephemeral)
            else:
                await inter.send(embed=self._player_embed, ephemeral=self._ephemeral)
        except disnake.errors.InteractionResponded as e:
            log_event(inter.author.id, "base", f"Could not send the error message to the player: {e}")


class PlayerInputException(FunctionalValidationException):
    def __init__(self, system_message: str, player_message: Optional[str] = None, player_embed: Optional[disnake.Embed] = None, ephemeral: bool = True):
        super().__init__(system_message, player_message, player_embed, ephemeral)


class PrerequisiteNotMetException(FunctionalValidationException):
    def __init__(self, system_message: str, player_message: Optional[str] = None, player_embed: Optional[disnake.Embed] = None, ephemeral: bool = True):
        super().__init__(system_message, player_message, player_embed, ephemeral)


class BaseStarfallCog(commands.Cog):

    def __init__(self, bot: commands.Bot, name: str, short_name: str):
        super().__init__()
        self._bot: commands.Bot = bot
        self._name: str = name
        self._short_name: str = short_name
        self._loaded: bool = False
        self._loading: bool = False
        self._waiting: bool = False
        self._views_initialized: bool = False
        self._persistent_views: list[disnake.ui.View] = []

    # ============================================= Special methods =============================================

    def __repr__(self):
        return self._name

    def __str__(self) -> str:
        return self.__repr__()

    # ================================================ Properties ===============================================

    @property
    def bot(self) -> commands.Bot:
        return self._bot

    @property
    def loaded(self) -> bool:
        return self._loaded

    @property
    def loading(self) -> bool:
        return self._loading

    @property
    def name(self) -> str:
        return self._name

    @property
    def persistent_views(self) -> list[disnake.ui.View]:
        return self._persistent_views.copy()

    @property
    def short_name(self) -> str:
        return self._short_name

    @property
    def views_initialized(self) -> bool:
        return self._views_initialized

    # ========================================= Protected loading methods ========================================

    async def _do_load(self):
        pass

    def _do_unload(self):
        pass

    async def _initialize_views(self) -> list[disnake.ui.View]:
        if not self._views_initialized:
            self._log("system", "Attempting to initialize views outside normal lifecycle")

        return []

    # ========================================= Disnake lifecycle methods ========================================

    async def cog_load(self):
        if not self._loaded:
            self._loading = True
            await self._do_load()
            self._loading = False
            self._loaded: bool = True
            self._log("system", f"Loaded {self}")

    def cog_unload(self):
        if self._loaded:
            self._loaded: bool = False
            self._log("system", f"Unloading {self}")
            self._do_unload()

    @commands.Cog.listener()
    async def on_ready(self):
        if not self._views_initialized:
            # Set the flag at the beginning to prevent double init for nothing
            self._views_initialized = True
            self._persistent_views: list[disnake.ui.View] = await self._initialize_views()

        if self._persistent_views is not None:
            # Should always be the case
            for view in self._persistent_views:
                self._add_view(view)

    def _validate_persistent(self, view: disnake.ui.View) -> bool:
        if view.is_persistent():
            return True

        # Provide some extra information about why a view is not persistent since Disnake is not super nice on this matter. This method imply a small performance overhead at on_ready time but allows easier debugging
        non_persistent_items: list[disnake.ui.Item] = [item for item in view.children if not item.is_persistent()]
        if len(non_persistent_items) == 0:
            self._log("system", f"View {view} has a timeout")
            return False

        persistent_error_desc: str = "View has a timeout, " if view.timeout is not None else ""
        self._log("system", persistent_error_desc + " doesn't have a custom_id,".join(str(non_persistent_items)) + " doesn't have a custom_id")
        return False

    # ============================================== "Real" methods =============================================
    def _add_view(self, view: disnake.ui.View) -> bool:
        if view is not None:
            # Add to the bot even if validation failed so that the bot crashes
            self._validate_persistent(view)
            self.bot.add_view(view)
            return True

        return False

    def _log(self, user_id: Union[int, str], message: str, level: str = "INFO"):
        log_event(user_id, self._short_name, message, level)


class BaseStarfallButton(disnake.ui.Button):
    def __init__(self, label: str, custom_id: str, style: disnake.ButtonStyle = disnake.ButtonStyle.primary, row: Optional[int] = None):
        super().__init__(label=label, custom_id="starfall:" + custom_id, style=style, row=row)


class BaseStarfallEmbed(disnake.Embed):
    def __init__(self):
        super().__init__()
        self._uploaded_files: dict[str, str] = {}
        self._current_file: Optional[disnake.File] = None

    @property
    def current_file(self) -> Optional[disnake.File]:
        return self._current_file

    def clear_current_file(self) -> Optional[disnake.File]:
        old_file: Optional[disnake.File] = self._current_file
        self._current_file = None
        return old_file

    def image_url(self, image_file: disnake.File) -> str:
        if image_file.filename in self._uploaded_files:
            url: str = self._uploaded_files[image_file.filename]
        else:
            url: str = f"attachment://{image_file.filename}"
            self._current_file = image_file
            self._uploaded_files[image_file.filename] = url

        return url


class BaseStarfallTransientView(disnake.ui.View):
    def __init__(self):
        super().__init__()


class BaseStarfallPersistentView(disnake.ui.View):
    def __init__(self):
        super().__init__(timeout=None)


class BaseStarfallChannelSelect(disnake.ui.ChannelSelect):
    def __init__(self, custom_id: str, placeholder: Optional[str] = None, min_values: int = 1, max_values: int = 1, disabled: bool = False, row: Optional[int] = None, channel_types: Optional[list[ChannelType]] = None):
        super().__init__(custom_id="starfall:" + custom_id, placeholder=placeholder, min_values=min_values, max_values=max_values, disabled=disabled, row=row, channel_types=channel_types)


class BaseStarfallUserSelect(disnake.ui.UserSelect):
    def __init__(self, custom_id: str, placeholder: Optional[str] = None, min_values: int = 1, max_values: int = 1, disabled: bool = False, row: Optional[int] = None):
        super().__init__(custom_id="starfall:" + custom_id, placeholder=placeholder, min_values=min_values, max_values=max_values, disabled=disabled, row=row)

from typing import Optional, Union

import disnake
from disnake import Embed, Guild, Member, Message, Thread, Role
from disnake.abc import GuildChannel, PrivateChannel
from disnake.errors import Forbidden
from disnake.ext import commands

from utils.Database import GuildOptions
from utils.LoggingUtils import log_event
from utils.base import singleton
from world.config import ServerConfig

_SHORT_NAME: str = "continent"


class ContinentNotLoadedException(Exception):
    def __init__(self):
        super().__init__()


@singleton
class Continent:
    def __init__(self):
        self._bot: Optional[commands.Bot] = None
        self._config: Optional[ServerConfig] = None
        self._origin_qi_counter: int = 0

    async def load(self, bot: commands.Bot):
        self._bot: commands.Bot = bot
        # TODO its not working as intended so commented it out for main bot
        config: ServerConfig = ServerConfig.beta() # Use production or beta
        self._config = config
        # gld = self._bot.get_guild(config.guild_id)
        # if gld and gld.get_channel(config.general_channel_id) is not None:
        #    self._config = config
        # else:
        #    self._config = ServerConfig.beta()

        qi_counter = await GuildOptions.get_or_none(name="qi_counter").values_list("value", flat=True)
        if qi_counter is None:
            await GuildOptions.create(name="qi_counter", value=1)
            qi_counter = 1

        self._origin_qi_counter: int = int(qi_counter)

    # ================================================ Properties ===============================================

    @property
    def approved_suggestion_channel(self) -> Optional[Union[GuildChannel, Thread, PrivateChannel]]:
        self._ensure_loaded()
        return self.channel(self._config.approved_suggestion_channel_id)

    @property
    def auction_channel(self) -> Optional[Union[GuildChannel, Thread, PrivateChannel]]:
        self._ensure_loaded()
        return self.channel(self._config.auction_channel_id)

    @property
    def beast_raid_channel(self) -> Optional[Union[GuildChannel, Thread, PrivateChannel]]:
        self._ensure_loaded()
        return self.channel(self._config.beast_raid_channel_id)

    @property
    def beast_raid_channel_id(self) -> int:
        self._ensure_loaded()
        return self._config.beast_raid_channel_id

    @property
    def bot(self) -> commands.Bot:
        self._ensure_loaded()
        return self._bot

    @property
    def breakthrough_role(self) -> Optional[Role]:
        self._ensure_loaded()
        return self.guild.get_role(self.breakthrough_role_id)

    @property
    def breakthrough_role_id(self) -> int:
        self._ensure_loaded()
        return self._config.breakthrough_role_id

    @property
    def config(self) -> ServerConfig:
        self._ensure_loaded()
        return self._config

    @property
    def error_channel(self) -> Optional[Union[GuildChannel, Thread, PrivateChannel]]:
        self._ensure_loaded()
        return self.channel(self._config.error_channel_id)

    @property
    def event_channel(self) -> Optional[Union[GuildChannel, Thread, PrivateChannel]]:
        self._ensure_loaded()
        return self.channel(self._config.event_channel_id)

    @property
    def event_channel_id(self) -> int:
        self._ensure_loaded()
        return self._config.event_channel_id

    @property
    def general_channel(self) -> Optional[Union[GuildChannel, Thread, PrivateChannel]]:
        self._ensure_loaded()
        return self.channel(self._config.general_channel_id)

    @property
    def general_channel_id(self) -> int:
        self._ensure_loaded()
        return self._config.general_channel_id

    @property
    def guild(self) -> Optional[Guild]:
        self._ensure_loaded()
        return self._bot.get_guild(self._config.guild_id)

    @property
    def origin_qi_counter(self) -> int:
        self._ensure_loaded()
        return self._origin_qi_counter

    @property
    def quest_channel(self) -> Optional[Union[GuildChannel, Thread, PrivateChannel]]:
        self._ensure_loaded()
        return self.channel(self._config.quest_channel_id)

    @property
    def quest_channel_id(self) -> int:
        self._ensure_loaded()
        return self._config.quest_channel_id

    @property
    def suggestion_channel(self) -> Optional[Union[GuildChannel, Thread, PrivateChannel]]:
        self._ensure_loaded()
        return self.channel(self._config.suggestion_channel_id)

    # ============================================== "Real" methods =============================================

    def channel(self, channel_id: int) -> Optional[Union[Thread, GuildChannel]]:
        self._ensure_loaded()
        gld: Guild = self.guild
        if gld:
            return gld.get_channel_or_thread(channel_id)
        else:
            return None

    async def increase_origin_qi_counter(self, increment: int = 1) -> None:
        await self.set_origin_qi_counter(self._origin_qi_counter + increment)

    async def member(self, user_id: int) -> Optional[Member]:
        self._ensure_loaded()
        return await self.guild.getch_member(user_id)

    async def message(self, channel_id: int, message_id: int) -> Optional[Message]:
        self._ensure_loaded()
        channel: Optional[Union[Thread, GuildChannel]] = self.channel(channel_id)
        if channel is None:
            return None

        try:
            return await channel.fetch_message(message_id)
        except disnake.NotFound as e:
            _log("system", f"Could not locate the message {message_id} on channel {channel_id}: {e}", "WARN")

    async def set_origin_qi_counter(self, new_counter: int) -> None:
        if self._origin_qi_counter != new_counter:
            self._origin_qi_counter = new_counter
            await GuildOptions.filter(name="qi_counter").update(value=self._origin_qi_counter)

    async def whisper(self, user_id: int, embed: Embed) -> Optional[Message]:
        self._ensure_loaded()

        user = await self.member(user_id)
        if user:
            try:
                return await user.send(embed=embed)
            except Forbidden as err:
                _log("system", f"Could send the message to member {user_id} because of {err.text}")
        else:
            _log("system", f"Could not find member {user_id}")

        return None

    def _ensure_loaded(self):
        if self._bot is None:
            raise ContinentNotLoadedException()


# =================================== Bootstrap and util class-level functions ==================================
def _log(user_id: Union[int, str], message: str, level: str = "INFO"):
    log_event(user_id, _SHORT_NAME, message, level)

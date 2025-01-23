from typing import TypeVar

C = TypeVar("C", bound="ServerConfig")


class ServerConfig:
    def __init__(self, guild_id: int,
                 general_channel_id: int, event_channel_id: int, beast_raid_channel_id: int, auction_channel_id: int, quest_channel_id: int,
                 suggestion_channel_id: int, approved_suggestion_channel_id: int, error_channel_id: int, breakthrough_role_id: int):
        self._guild_id: int = guild_id
        self._general_channel_id: int = general_channel_id
        self._event_channel_id: int = event_channel_id
        self._beast_raid_channel_id: int = beast_raid_channel_id
        self._auction_channel_id: int = auction_channel_id
        self._quest_channel_id: int = quest_channel_id
        self._suggestion_channel_id: int = suggestion_channel_id
        self._approved_suggestion_channel_id: int = approved_suggestion_channel_id
        self._error_channel_id: int = error_channel_id
        self._breakthrough_role_id: int = breakthrough_role_id

    # ============================================= Special methods =============================================

    def __repr__(self):
        return (f"ServerConfig {{"
                f"guild_id: {self._guild_id}, "
                f"general_channel_id: {self._general_channel_id}, "
                f"event_channel_id: {self._event_channel_id}, "
                f"beast_raid_channel_id: {self._beast_raid_channel_id}, "
                f"auction_channel_id: {self._auction_channel_id}, "
                f"quest_channel_id: {self._quest_channel_id}, "
                f"suggestion_channel_id: {self._suggestion_channel_id}, "
                f"approved_suggestion_channel_id: {self._approved_suggestion_channel_id}, "
                f"error_channel_id: {self._error_channel_id}, "
                f"breakthrough_role_id: {self._breakthrough_role_id}"
                f"}}")

    def __str__(self):
        return self.__repr__()

    def __hash__(self) -> int:
        return (hash(self._guild_id) * 31 + hash(self._general_channel_id) * 29 + hash(self._event_channel_id) * 23 + hash(self._beast_raid_channel_id) * 19 + hash(self._auction_channel_id) * 17 + hash(self._quest_channel_id) * 13 +
                hash(self._suggestion_channel_id) * 11 + hash(self._approved_suggestion_channel_id) * 7 + hash(self._error_channel_id) * 5 + hash(self._breakthrough_role_id) * 3)

    def __eq__(self, other):
        return (other is not None
                and isinstance(other, ServerConfig)
                and self._guild_id == other._guild_id
                and self._general_channel_id == other._general_channel_id
                and self._event_channel_id == other._event_channel_id
                and self._beast_raid_channel_id == other._beast_raid_channel_id
                and self._auction_channel_id == other._auction_channel_id
                and self._quest_channel_id == other._quest_channel_id
                and self._suggestion_channel_id == other._suggestion_channel_id
                and self._approved_suggestion_channel_id == other._approved_suggestion_channel_id
                and self._error_channel_id == other._error_channel_id
                and self._breakthrough_role_id == other._breakthrough_role_id)

    def __ne__(self, other):
        return not self.__eq__(other)

    # ================================================ Properties ===============================================

    @property
    def approved_suggestion_channel_id(self) -> int:
        return self._approved_suggestion_channel_id

    @property
    def auction_channel_id(self) -> int:
        return self._auction_channel_id

    @property
    def beast_raid_channel_id(self) -> int:
        return self._beast_raid_channel_id

    @property
    def breakthrough_role_id(self) -> int:
        return self._breakthrough_role_id

    @property
    def error_channel_id(self) -> int:
        return self._error_channel_id

    @property
    def event_channel_id(self) -> int:
        return self._event_channel_id

    @property
    def guild_id(self) -> int:
        return self._guild_id

    @property
    def general_channel_id(self) -> int:
        return self._general_channel_id

    @property
    def quest_channel_id(self) -> int:
        return self._quest_channel_id

    @property
    def suggestion_channel_id(self) -> int:
        return self._suggestion_channel_id

    # ================================================ Factory methods ===============================================

    @staticmethod
    def beta() -> C:
        return ServerConfig(guild_id=779435063678861383,
                            general_channel_id=941630078452899881,
                            event_channel_id=997897663133519923,
                            beast_raid_channel_id=997897663133519923,
                            auction_channel_id=1178234657511321651,
                            quest_channel_id=1178235107270725702,
                            suggestion_channel_id=0,
                            approved_suggestion_channel_id=0,
                            error_channel_id=998876223256154112,
                            breakthrough_role_id=1150410599008845824)
#        return ServerConfig(guild_id=779435063678861383,
#                            general_channel_id=941630078452899881,
#                            event_channel_id=997897663133519923,
#                            beast_raid_channel_id=941630078452899881,
#                            auction_channel_id=941630078452899881,
#                            quest_channel_id=1161185587219402784,
#                            suggestion_channel_id=0,
#                            approved_suggestion_channel_id=0,
#                            error_channel_id=998876223256154112,
#                            breakthrough_role_id=1150410599008845824)

    @staticmethod
    def production() -> C:
        return ServerConfig(guild_id=352517656814813185,
                            general_channel_id=1010458217362509894,
                            event_channel_id=1049935168716148817,
                            beast_raid_channel_id=1013308720639385620,
                            auction_channel_id=1135294666762354769,
                            quest_channel_id=0,  # FIXME: Add the real channel id
                            suggestion_channel_id=1010481085546778653,
                            approved_suggestion_channel_id=941564693779206164,
                            error_channel_id=1010451695274315836,
                            breakthrough_role_id=1010445866483601458)

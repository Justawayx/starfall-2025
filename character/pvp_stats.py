from typing import Optional
from datetime import datetime
from enum import Enum
from utils.Database import PvpStatsDao

class Element(Enum):
    """Elemental types for PvP combat"""
    FIRE = "Fire"
    WATER = "Water"
    EARTH = "Earth"
    WIND = "Wind"
    LIGHTNING = "Lightning"
    ICE = "Ice"
    LIGHT = "Light"
    DARK = "Dark"

    @classmethod
    def get_weakness(cls, element: 'Element') -> Optional['Element']:
        """Get the element that is weak against this one"""
        weaknesses = {
            cls.FIRE: cls.WATER,
            cls.WATER: cls.EARTH,
            cls.EARTH: cls.WIND,
            cls.WIND: cls.LIGHTNING,
            cls.LIGHTNING: cls.ICE,
            cls.ICE: cls.FIRE,
            cls.LIGHT: cls.DARK,
            cls.DARK: cls.LIGHT
        }
        return weaknesses.get(element)

class PvPStats:
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.wins = 0
        self.losses = 0
        self.draws = 0
        self.last_match: Optional[datetime] = None

    @classmethod
    async def get(cls, user_id: int) -> 'PvPStats':
        """Get PvP stats from database"""
        stats_dao = await PvpStatsDao.get(user_id)
        return cls.from_dao(stats_dao)

    @classmethod
    def from_dao(cls, dao: PvpStatsDao) -> 'PvPStats':
        """Create PvPStats from DAO"""
        stats = cls(dao.user_id)
        stats.wins = dao.wins
        stats.losses = dao.losses
        stats.draws = dao.draws
        stats.last_match = dao.last_match
        return stats

    @property
    def win_rate(self) -> float:
        """Calculate win rate percentage"""
        total = self.wins + self.losses + self.draws
        if total == 0:
            return 0.0
        return (self.wins / total) * 100

    async def add_win(self):
        """Record a win"""
        dao = await PvpStatsDao.get(self.user_id)
        await dao.add_win()

    async def add_loss(self):
        """Record a loss"""
        dao = await PvpStatsDao.get(self.user_id)
        await dao.add_loss()

    async def add_draw(self):
        """Record a draw"""
        dao = await PvpStatsDao.get(self.user_id)
        await dao.add_draw()

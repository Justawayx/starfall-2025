from typing import Optional

from gaming.game import GameAction, IntransitiveGame, GameConfig


class Shoushiling(IntransitiveGame):

    FROG: GameAction = GameAction("frog", "Frog")
    CENTIPEDE: GameAction = GameAction("centipede", "Centipede")
    SNAKE: GameAction = GameAction("snake", "Snake")
    ID: str = "shoushiling"

    def __init__(self):
        super().__init__(Shoushiling.ID, "Shoushiling", [Shoushiling.FROG, Shoushiling.CENTIPEDE, Shoushiling.SNAKE])
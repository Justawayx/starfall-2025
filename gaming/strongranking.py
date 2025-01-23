from gaming.game import GameAction, IntransitiveGame, GameConfig


class StrongRankingGrandCompetition(IntransitiveGame):
    ATTACK: GameAction = GameAction("attack", "Attack")
    DEFEND: GameAction = GameAction("defend", "Defend")
    COUNTER: GameAction = GameAction("counter", "Counterattack")
    FEINT: GameAction = GameAction("feint", "Feint")
    DODGE: GameAction = GameAction("dodge", "Dodge")
    ID: str = "strong_ranking"

    def __init__(self):
        actions: list[GameAction] = [StrongRankingGrandCompetition.ATTACK, StrongRankingGrandCompetition.DEFEND, StrongRankingGrandCompetition.COUNTER, StrongRankingGrandCompetition.FEINT, StrongRankingGrandCompetition.DODGE]
        ascendancy: dict[str, list[str]] = {
            StrongRankingGrandCompetition.ATTACK.id: [StrongRankingGrandCompetition.FEINT.id, StrongRankingGrandCompetition.DODGE.id],
            StrongRankingGrandCompetition.DEFEND.id: [StrongRankingGrandCompetition.DODGE.id, StrongRankingGrandCompetition.ATTACK.id],
            StrongRankingGrandCompetition.COUNTER.id: [StrongRankingGrandCompetition.ATTACK.id, StrongRankingGrandCompetition.DEFEND.id],
            StrongRankingGrandCompetition.FEINT.id: [StrongRankingGrandCompetition.DEFEND.id, StrongRankingGrandCompetition.COUNTER.id],
            StrongRankingGrandCompetition.DODGE.id: [StrongRankingGrandCompetition.COUNTER.id, StrongRankingGrandCompetition.FEINT.id]
        }

        super().__init__(StrongRankingGrandCompetition.ID, "Strong Ranking Grand Competition", actions, ascendancy)

    @property
    def default_config(self) -> GameConfig:
        config: GameConfig = super().default_config
        config.action_count = 7
        config.extra_action_count = 3
        return config

    @property
    def instance_label(self) -> str:
        return "match"

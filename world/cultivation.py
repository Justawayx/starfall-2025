from __future__ import annotations

import math
from typing import Optional, TypeVar

MAJOR_CULTIVATION_REALMS: list[str] = ["Fight Disciple", "Fight Practitioner", "Fight Master", "Fight Grandmaster", "Fight Spirit", "Fight King", "Fight Emperor", "Fight Ancestor", "Fight Venerate", "Peak Fight Venerate", "Half Saint",
                                       "Fight Saint", "Fight God"]

BEAST_EXPERIENCE_RARITY_INCREASE: dict[str, float] = {
    "abundant": 1,
    "scarce": 1.40,
    "exotic": 2.10
}

BASE_BEAST_CULTIVATION_TABLE: list[list[tuple[str, int, int, float]]] = [
    [  # "???" (major = 0)
        ("???", 10_000_000)
    ],
    [  # Rank 1 (major = 1)
        ("1-Star Rank 1", 100, 0, 0.0),
        ("2-Star Rank 1", 136, 0, 0.0),
        ("3-Star Rank 1", 178, 0, 0.0),
        ("4-Star Rank 1", 226, 0, 0.0),
        ("5-Star Rank 1", 280, 0, 0.0),
        ("6-Star Rank 1", 340, 0, 0.0),
        ("7-Star Rank 1", 406, 0, 0.0),
        ("8-Star Rank 1", 478, 0, 0.0),
        ("9-Star Rank 1", 556, 0, 0.0)
    ],
    [  # Rank 2 (major = 2)
        ("1-Star Rank 2", 1_000, 0, 0.0),
        ("2-Star Rank 2", 1_450, 0, 0.0),
        ("3-Star Rank 2", 1_975, 0, 0.0),
        ("4-Star Rank 2", 2_575, 0, 0.0),
        ("5-Star Rank 2", 3_250, 0, 0.0),
        ("6-Star Rank 2", 4_000, 0, 0.0),
        ("7-Star Rank 2", 4_825, 0, 0.0),
        ("8-Star Rank 2", 5_725, 0, 0.0),
        ("9-Star Rank 2", 6_700, 0, 0.0)
    ],
    [  # Rank 3 (major = 3)
        ("1-Star Rank 3", 13_000, 0, 0.0),
        ("2-Star Rank 3", 17_500, 0, 0.0),
        ("3-Star Rank 3", 22_750, 0, 0.0),
        ("4-Star Rank 3", 28_750, 0, 0.0),
        ("5-Star Rank 3", 35_500, 0, 0.0),
        ("6-Star Rank 3", 43_000, 0, 0.0),
        ("7-Star Rank 3", 51_250, 0, 0.0),
        ("8-Star Rank 3", 60_250, 0, 0.0),
        ("9-Star Rank 3", 70_000, 0, 0.0)
    ],
    [  # Rank 4 (major = 4)
        ("1-Star Rank 4", 150_000, 0, 0.0),
        ("2-Star Rank 4", 240_000, 0, 0.0),
        ("3-Star Rank 4", 345_000, 0, 0.0),
        ("4-Star Rank 4", 465_000, 0, 0.0),
        ("5-Star Rank 4", 600_000, 0, 0.0),
        ("6-Star Rank 4", 750_000, 0, 0.0),
        ("7-Star Rank 4", 915_000, 0, 0.0),
        ("8-Star Rank 4", 1_095_000, 0, 0.0),
        ("9-Star Rank 4", 1_290_000, 0, 0.0)
    ],
    [  # Rank 5 (major = 5)
        ("1-Star Rank 5", 2_000_000, 0, 0.0),
        ("2-Star Rank 5", 2_990_000, 0, 0.0),
        ("3-Star Rank 5", 4_145_000, 0, 0.0),
        ("4-Star Rank 5", 5_465_000, 0, 0.0),
        ("5-Star Rank 5", 6_950_000, 0, 0.0),
        ("6-Star Rank 5", 8_600_000, 0, 0.0),
        ("7-Star Rank 5", 10_415_000, 0, 0.0),
        ("8-Star Rank 5", 12_395_000, 0, 0.0),
        ("9-Star Rank 5", 14_540_000, 0, 0.0)
    ],
    [  # Rank 6 (major = 6)
        ("1-Star Rank 6", 23_000_000, 0, 0.0),
        ("2-Star Rank 6", 35_600_000, 0, 0.0),
        ("3-Star Rank 6", 50_300_000, 0, 0.0),
        ("4-Star Rank 6", 67_100_000, 0, 0.0),
        ("5-Star Rank 6", 86_000_000, 0, 0.0),
        ("6-Star Rank 6", 107_000_000, 0, 0.0),
        ("7-Star Rank 6", 130_100_000, 0, 0.0),
        ("8-Star Rank 6", 155_300_000, 0, 0.0),
        ("9-Star Rank 6", 182_600_000, 0, 0.0)
    ],
    [  # Rank 7 (major = 7)
        ("1-Star Rank 7", 290_000_000, 0, 0.0),
        ("2-Star Rank 7", 434_000_000, 0, 0.0),
        ("3-Star Rank 7", 602_000_000, 0, 0.0),
        ("4-Star Rank 7", 794_000_000, 0, 0.0),
        ("5-Star Rank 7", 1_010_000_000, 0, 0.0),
        ("6-Star Rank 7", 1_250_000_000, 0, 0.0),
        ("7-Star Rank 7", 1_514_000_000, 0, 0.0),
        ("8-Star Rank 7", 1_802_000_000, 0, 0.0),
        ("9-Star Rank 7", 2_114_000_000, 0, 0.0)
    ],
    [  # Rank 8 (major = 8)
        ("1-Star Rank 8", 3_500_000_000, 0, 0.0),
        ("2-Star Rank 8", 5_390_000_000, 0, 0.0),
        ("3-Star Rank 8", 7_595_000_000, 0, 0.0),
        ("4-Star Rank 8", 10_115_000_000, 0, 0.0),
        ("5-Star Rank 8", 12_950_000_000, 0, 0.0),
        ("6-Star Rank 8", 16_100_000_000, 0, 0.0),
        ("7-Star Rank 8", 19_565_000_000, 0, 0.0),
        ("8-Star Rank 8", 23_345_000_000, 0, 0.0),
        ("9-Star Rank 8", 27_440_000_000, 0, 0.0)
    ],
    [  # Rank 9 part 1 (major = 9)
        ("1-Star Rank 9", 45_000_000_000, 0, 0.0),
        ("2-Star Rank 9", 72_450_000_000, 0, 0.0),
        ("3-Star Rank 9", 104_475_000_000, 0, 0.0)
    ],
    [  # Rank 9 part 2 (major = 10)
        ("4-Star Rank 9", 140_000_000_000, 0, 0.0),
        ("5-Star Rank 9", 167_450_000_000, 0, 0.0),
        ("6-Star Rank 9", 199_475_000_000, 0, 0.0)
    ],
    [  # Rank 9 part 3 (major = 11)
        ("7-Star Rank 9", 280_000_000_000, 0, 0.0),
        ("8-Star Rank 9", 307_450_000_000, 0, 0.0),
        ("9-Star Rank 9", 339_475_000_000, 0, 0.0)
    ],
    [  # Spirit Class Heavenly Sovereign (major = 12)
        ("Spirit Class Heavenly Sovereign Initial Phase", 520_000_000_000, 0, 0.0),
        ("Spirit Class Heavenly Sovereign Middle Phase", 745_000_000_000, 0, 0.0),
        ("Spirit Class Heavenly Sovereign Late Phase", 1_007_500_000_000, 0, 0.0)
    ],
    [  # Immortal Class Heavenly Sovereign (major = 13)
        ("Immortal Class Heavenly Sovereign Initial Phase", 1_600_000_000_000, 0, 0.0),
        ("Immortal Class Heavenly Sovereign Middle Phase", 1_960_000_000_000, 0, 0.0),
        ("Immortal Class Heavenly Sovereign Late Phase", 2_380_000_000_000, 0, 0.0)
    ],
    [  # Saint Class Heavenly Sovereign (major = 14)
        ("Saint Class Heavenly Sovereign Initial Phase", 3_710_000_000_000, 0, 0.0),
        ("Saint Class Heavenly Sovereign Middle Phase", 4_160_000_000_000, 0, 0.0),
        ("Saint Class Heavenly Sovereign Late Phase", 4_685_000_000_000, 0, 0.0)
    ]
]

BEAST_BASE_CP: dict[str, dict[int, int]] = {
    "abundant": {
        1: 24,
        2: 15,
        3: 70,
        4: 300,
        5: 3_500,
        6: 20_000,
        7: 500_000,
        8: 40_500_000,
        9: 2_800_000_000,
        10: 70_000_000_000,
        11: 1_000_000_000_000,
        12: 40_000_000_000_000,
        13: 150_000_000_000_000,
        14: 300_000_000_000_000
    },
    "scarce": {
        1: 24,
        2: 30,
        3: 100,
        4: 500,
        5: 5_500,
        6: 30_000,
        7: 500_000,
        8: 51_500_000,
        9: 3_100_000_000,
        10: 80_000_000_000,
        11: 1_250_000_000_000,
        12: 50_000_000_000_000,
        13: 200_000_000_000_000,
        14: 500_000_000_000_000
    },
    "exotic": {
        1: 40,
        2: 360,
        3: 2800,
        4: 20_500,
        5: 138_000,
        6: 1_700_000,
        7: 20_100_000,
        8: 421_500_000,
        9: 20_100_000_000,
        10: 100_000_000_000,
        11: 15_250_000_000_000,
        12: 110_000_000_000_000,
        13: 305_000_000_000_000,
        14: 610_000_000_000_000,
    }
}

PLAYER_CULTIVATION_TABLE: list[list[tuple[str, int, int, float]]] = [
    [  # Fight Disciple (major = 0)
        ("???", 50, 60, 0.0),
        ("1st Stage Fight Disciple", 60, 60, 1000.0),
        ("2nd Stage Fight Disciple", 74, 60, 1265.2841317462864),
        ("3rd Stage Fight Disciple", 92, 60, 1602.388423824404),
        ("4th Stage Fight Disciple", 114, 60, 2130.243188301956),
        ("5th Stage Fight Disciple", 140, 60, 2921.19070986021),
        ("6th Stage Fight Disciple", 170, 60, 4065.8838754441636),
        ("7th Stage Fight Disciple", 204, 60, 5678.087823682211),
        ("8th Stage Fight Disciple", 242, 60, 7899.628172056633),
        ("9th Stage Fight Disciple", 270, 60, 10906.064848790229)
    ],
    [  # Fight Practitioner (major = 1)
        ("1-Star Fight Practitioner", 250, 75, 30826.5700956676),
        ("2-Star Fight Practitioner", 262, 75, 39812.89579854543),
        ("3-Star Fight Practitioner", 278, 75, 52044.731764659766),
        ("4-Star Fight Practitioner", 300, 75, 71848.5952021047),
        ("5-Star Fight Practitioner", 326, 75, 102339.90590058449),
        ("6-Star Fight Practitioner", 358, 75, 147517.80155470694),
        ("7-Star Fight Practitioner", 394, 75, 212499.2367618409),
        ("8-Star Fight Practitioner", 434, 75, 303776.4890682699),
        ("9-Star Fight Practitioner", 450, 75, 429519.22466628114)
    ],
    [  # Fight Master (major = 2)
        ("1-Star Fight Master", 420, 90, 1283251.5692266421),
        ("2-Star Fight Master", 435, 90, 1694320.2884150895),
        ("3-Star Fight Master", 456, 90, 2292505.113503531),
        ("4-Star Fight Master", 483, 90, 3293842.3469256605),
        ("5-Star Fight Master", 516, 90, 4877970.904064558),
        ("6-Star Fight Master", 555, 90, 7280915.6374655375),
        ("7-Star Fight Master", 600, 90, 10810603.404887443),
        ("8-Star Fight Master", 631, 90, 15864732.860841189),
        ("9-Star Fight Master", 700, 90, 22952143.0396055)
    ],
    [  # Fight Grandmaster (major = 3)
        ("1-Star Fight Grandmaster", 675, 105, 72633387.00119354),
        ("2-Star Fight Grandmaster", 700, 105, 98200671.18245292),
        ("3-Star Fight Grandmaster", 735, 105, 137905956.08433664),
        ("4-Star Fight Grandmaster", 780, 105, 206622086.0828121),
        ("5-Star Fight Grandmaster", 835, 105, 318319626.41661394),
        ("6-Star Fight Grandmaster", 900, 105, 491778054.5732492),
        ("7-Star Fight Grandmaster", 975, 105, 751982027.1338586),
        ("8-Star Fight Grandmaster", 1060, 105, 1131785201.260449),
        ("9-Star Fight Grandmaster", 1160, 105, 1673934659.0763078)
    ],
    [  # Fight Spirit (major = 4)
        ("1-Star Fight Spirit", 1140, 120, 5623193702.454171),
        ("2-Star Fight Spirit", 1185, 120, 7798282655.0987015),
        ("3-Star Fight Spirit", 1248, 120, 11397281523.406641),
        ("4-Star Fight Spirit", 1329, 120, 17836546711.698418),
        ("5-Star Fight Spirit", 1428, 120, 28590969136.42065),
        ("6-Star Fight Spirit", 1545, 120, 45688457700.98672),
        ("7-Star Fight Spirit", 1680, 120, 71880758860.57852),
        ("8-Star Fight Spirit", 1833, 120, 110852580359.32855),
        ("9-Star Fight Spirit", 1740, 120, 167480257607.44543)
    ],
    [  # Fight King (major = 5)
        ("1-Star Fight King", 1920, 135, 598600153353.4364),
        ("2-Star Fight King", 1980, 135, 878190488888.469),
        ("3-Star Fight King", 2064, 135, 1401107518059.0688),
        ("4-Star Fight King", 2172, 135, 2400906755508.178),
        ("5-Star Fight King", 2304, 135, 4163566371074.7095),
        ("6-Star Fight King", 2460, 135, 7100442284138.948),
        ("7-Star Fight King", 2640, 135, 11792496496967.93),
        ("8-Star Fight King", 2844, 135, 19046841562686.285),
        ("9-Star Fight King", 3000, 135, 29968952829628.387)
    ],
    [  # Fight Emperor (major = 6)
        ("1-Star Fight Emperor", 2950, 150, 116033737513003.11),
        ("2-Star Fight Emperor", 3035, 150, 187946610924410.2),
        ("3-Star Fight Emperor", 3154, 150, 348101212539009.3),
        ("4-Star Fight Emperor", 3307, 150, 686245414813964.6),
        ("5-Star Fight Emperor", 3494, 150, 1332715322543420.8),
        ("6-Star Fight Emperor", 3715, 150, 2488258448259124.0),
        ("7-Star Fight Emperor", 3970, 150, 4454305777243826.0),
        ("8-Star Fight Emperor", 4259, 150, 7673890587689437.0),
        ("9-Star Fight Emperor", 4400, 150, 1.2786488556795852e+16)
    ],
    [  # Fight Ancestor (major = 7)
        ("1-Star Fight Ancestor", 4320, 165, 5.9360808458235336e+16),
        ("2-Star Fight Ancestor", 4420, 165, 1.18306294090342e+17),
        ("3-Star Fight Ancestor", 4560, 165, 2.905989431354979e+17),
        ("4-Star Fight Ancestor", 4740, 165, 7.193724446111958e+17),
        ("5-Star Fight Ancestor", 4960, 165, 1.6572594403925466e+18),
        ("6-Star Fight Ancestor", 5220, 165, 3.541594640631324e+18),
        ("7-Star Fight Ancestor", 5520, 165, 7.10162607042231e+18),
        ("8-Star Fight Ancestor", 5860, 165, 1.351717640322651e+19),
        ("9-Star Fight Ancestor", 6000, 165, 2.4649842704119554e+19)
    ],
    [  # Fight Venerate (major = 8)
        ("1-Star Fight Venerate", 5900, 180, 1.4472289655167468e+20),
        ("2-Star Fight Venerate", 6050, 180, 3.749817676811376e+20),
        ("3-Star Fight Venerate", 6260, 180, 1.2427841090989602e+21),
        ("4-Star Fight Venerate", 6530, 180, 3.7854572427207115e+21),
        ("5-Star Fight Venerate", 6860, 180, 1.014572291649894e+22),
        ("6-Star Fight Venerate", 7250, 180, 2.450498456348844e+22),
        ("7-Star Fight Venerate", 7700, 180, 5.462381867362621e+22),
        ("8-Star Fight Venerate", 8210, 180, 1.1434637783871894e+23),
        ("9-Star Fight Venerate", 8780, 180, 2.2758312096410873e+23)
    ],
    [  # Peak Fight Venerate (major = 9)
        ("1st Change Peak Fight Venerate", 5900, 195, 4.3452538718265765e+23),
        ("2nd Change Peak Fight Venerate", 6050, 195, 1.1258695180268504e+24),
        ("3rd Change Peak Fight Venerate", 6260, 195, 3.7314154087419076e+24),
        ("4th Change Peak Fight Venerate", 6530, 195, 1.1365701718589455e+25),
        ("5th Change Peak Fight Venerate", 6860, 195, 3.04621748429803e+25),
        ("6th Change Peak Fight Venerate", 7250, 195, 7.35753509573579e+25),
        ("7th Change Peak Fight Venerate", 7700, 195, 1.6400608697102572e+26),
        ("8th Change Peak Fight Venerate", 8210, 195, 3.433209622470679e+26),
        ("9th Change Peak Fight Venerate", 8780, 195, 6.833102854451032e+26),
        ("10th Change Peak Fight Venerate", 9500, 195, 1.3046471332808168e+27)
    ],
    [  # Half Saint (major = 10)
        ("Initial Half Saint", 12000, 210, 9.623397340822127e+27),
        ("Intermediate Half Saint", 13500, 210, 1.6825215166094178e+28),
        ("Advanced Half Saint", 15000, 210, 3.4752112022849074e+28)
    ],
    [  # Fight Saint (major = 11)
        # 1-Star (minor = 0 to 2)
        ("1-Star Initial Fight Saint", 20_000, 225, 1.599845409885244e+29),
        ("1-Star Intermediate Fight Saint", 22_000, 225, 3.0455617382377746e+29),
        ("1-Star Advanced Fight Saint", 24_800, 225, 7.054053948794564e+29),
        # 2-Star (minor = 3 to 5)
        ("2-Star Initial Fight Saint", 38_400, 235, 3.5015733594395144e+30),
        ("2-Star Intermediate Fight Saint", 42_800, 235, 6.665805196707496e+30),
        ("2-Star Advanced Fight Saint", 48_000, 235, 1.5439171329009777e+31),
        # 3-Star (minor = 6 to 8)
        ("3-Star Initial Fight Saint", 69_000, 245, 7.663875469328004e+31),
        ("3-Star Intermediate Fight Saint", 75_800, 245, 1.4589413296925147e+32),
        ("3-Star Advanced Fight Saint", 83_400, 245, 3.379163429381642e+32),
        # 4-Star (minor = 9 to 11)
        ("4-Star Initial Fight Saint", 106_800, 255, 1.677388453137222e+33),
        ("4-Star Intermediate Fight Saint", 116_000, 255, 3.1931773291789527e+33),
        ("4-Star Advanced Fight Saint", 126_000, 255, 7.39595748964505e+33),
        # 5-Star (minor = 12 to 14)
        ("5-Star Initial Fight Saint", 161_800, 265, 3.671291416436327e+34),
        ("5-Star Intermediate Fight Saint", 173_400, 265, 6.9888906757692675e+34),
        ("5-Star Advanced Fight Saint", 185_800, 265, 1.6187493837386369e+35),
        # 6-Star (minor = 15 to 17)
        ("6-Star Initial Fight Saint", 224_000, 275, 8.035336501327654e+35),
        ("6-Star Intermediate Fight Saint", 238_000, 275, 1.5296548810965593e+36),
        ("6-Star Advanced Fight Saint", 252_800, 275, 3.54294838906649e+36),
        # 7-Star (minor = 18 to 20)
        ("7-Star Initial Fight Saint", 293_400, 285, 1.7586899367482658e+37),
        ("7-Star Intermediate Fight Saint", 309_800, 285, 3.3479477127534013e+37),
        ("7-Star Advanced Fight Saint", 327_000, 285, 7.75443278229878e+37),
        # 8-Star (minor = 21 to 23)
        ("8-Star Initial Fight Saint", 370_000, 295, 3.8492355523736604e+38),
        ("8-Star Intermediate Fight Saint", 388_800, 295, 7.32763581239681e+38),
        ("8-Star Advanced Fight Saint", 408_400, 295, 1.6972086853072568e+39),
        # 9-Star (minor = 24 to 26)
        ("9-Star Initial Fight Saint", 448_800, 305, 8.424801909683166e+39),
        ("9-Star Intermediate Fight Saint", 470_000, 305, 1.6037958536383864e+40),
        ("9-Star Advanced Fight Saint", 500_000, 305, 3.714671855893585e+40)
    ],
    [  # Fight God (major = 12)
        ("Fight God", 1_000_000, 330, 9.55665222080645E+41)
    ],
    [  # Heavenly Sovereign (major = 13)
        # Spirit Class (minor = 0 to 2)
        ("Spirit Class Heavenly Sovereign Initial Phase", 1_000_000, 330, 9.55665222080645E+41),
        ("Spirit Class Heavenly Sovereign Middle Phase", 1_130_000, 330, 2.21486185564223E+42),
        ("Spirit Class Heavenly Sovereign Late Phase", 1_312_000, 330, 6.50937556061819E+42),
        # Immortal Class (minor = 3 to 5)
        ("Immortal Class Heavenly Sovereign Initial Phase", 1_746_000, 330, 3.75524620426741E+43),
        ("Immortal Class Heavenly Sovereign Middle Phase", 2_032_000, 330, 1.09697903251437E+44),
        ("Immortal Class Heavenly Sovereign Late Phase", 2_370_000, 330, 4.09549586269138E+44),
        # Saint Class (minor = 3 to 5)
        ("Saint Class Heavenly Sovereign Initial Phase", 3_060_000, 330, 2.73180599113202E+45),
        ("Saint Class Heavenly Sovereign Middle Phase", 3_502_000, 330, 1.03843006779426E+46),
        ("Saint Class Heavenly Sovereign Late Phase", 5_000_000, 330, 4.88608807255933E+46)
    ],
    [  # Ruler (major = 14)
        ("Ruler", 5_000_000, 350, 1.88262272605058E+48)
    ]
]

C = TypeVar("C", bound="CultivationStage")
B = TypeVar("B", bound="BeastCultivationStage")


def _find_next_stage(entries: list[list[tuple[str, int, int, float]]], major: int, minor: int) -> Optional[tuple[int, int]]:
    minor_entries: list[tuple[str, int, int, float]] = entries[major]
    if minor == len(minor_entries) - 1:
        # Last entry of a major
        if major == len(entries) - 1:
            # Last major too, so maxed out
            return None
        else:
            return major + 1, 0
    else:
        return major, minor + 1


def _find_previous_stage(entries: list[list[tuple[str, int, int, float]]], major: int, minor: int) -> Optional[tuple[int, int]]:
    if minor == 0:
        # First entry of a major
        if major == 0:
            # First major too, so already at lowest stage
            return None
        else:
            minor_entries: list[tuple[str, int, int, float]] = entries[major - 1]
            return major - 1, len(minor_entries) - 1
    else:
        return major, minor - 1


def _get_cultivation_entry(entries: list[list[tuple[str, int, int, float]]], major: int, minor: int) -> tuple[str, int, int, float]:
    if major < 0:
        raise ValueError(f"Major must be positive, found {major}")

    if minor < 0:
        raise ValueError(f"Minor must be positive, found {minor}")

    if major >= len(entries):
        raise ValueError(f"Major can be at most {len(entries) - 1}, found {major}")

    minor_entries: list[tuple[str, int, int, float]] = entries[major]
    if minor >= len(minor_entries):
        raise ValueError(f"Minor can be at most {len(minor_entries) - 1} for major {major}, found {minor}")

    return minor_entries[minor]


def _get_beast_cultivation_entry(major: int, minor: int) -> tuple[str, int, int, float]:
    return _get_cultivation_entry(BASE_BEAST_CULTIVATION_TABLE, major, minor)


def _get_player_cultivation_entry(major: int, minor: int) -> tuple[str, int, int, float]:
    return _get_cultivation_entry(PLAYER_CULTIVATION_TABLE, major, minor)


def get_beast_breakthrough_experience(major, minor, rarity) -> int:
    base_value: int = _get_beast_cultivation_entry(major, minor)[1]
    return int(base_value * BEAST_EXPERIENCE_RARITY_INCREASE[rarity]) if rarity in BEAST_EXPERIENCE_RARITY_INCREASE else base_value


def get_beast_cultivation_title(major: int, minor: int) -> str:
    return _get_beast_cultivation_entry(major, minor)[0]


def get_player_breakthrough_experience(major: int, minor: int) -> int:
    return _get_player_cultivation_entry(major, minor)[1]


def get_player_combat_power(major: int, minor: int) -> float:
    return _get_player_cultivation_entry(major, minor)[3]


def get_player_cultivation_title(major: int, minor: int) -> str:
    return _get_player_cultivation_entry(major, minor)[0]


def get_player_max_energy(major: int, minor: int) -> int:
    return _get_player_cultivation_entry(major, minor)[2]


# =======================================================================================================================
# =============================================== CultivationStage ======================================================
# =======================================================================================================================
class CultivationStage:
    def __init__(self, major: int, minor: int, entry: Optional[tuple[str, int, int, float]] = None, exp_factor: Optional[float] = None):
        super().__init__()
        self._major: int = major
        self._minor: int = minor

        if entry is None:
            self._name: str = get_beast_cultivation_title(major, minor)
            self._breakthrough_experience: int = get_player_breakthrough_experience(major, minor)
        else:
            self._name: str = entry[0]
            self._breakthrough_experience: int = entry[1]
            if exp_factor is not None:
                self._breakthrough_experience: int = int(self._breakthrough_experience * exp_factor)

    # ============================================= Special methods =============================================

    def __repr__(self) -> str:
        return f"CultivationStage {self._major}, {self._minor}"

    def __str__(self) -> str:
        return self.name

    def __hash__(self) -> int:
        return hash(self._major) * 7 + hash(self._minor) * 3

    def __eq__(self, other) -> bool:
        return other is not None and isinstance(other, CultivationStage) and self._major == other._major and self._minor == other._minor

    def __ne__(self, other) -> bool:
        return not self.__eq__(other)

    def __ge__(self, other) -> bool:
        return self.__gt__(other) or self.__eq__(other)

    def __gt__(self, other) -> bool:
        if other is None or not isinstance(other, CultivationStage):
            return False

        if self._major > other._major:
            return True
        elif self._major < other._major:
            return False
        else:
            return self._minor > other._minor

    def __le__(self, other) -> bool:
        return self.__lt__(other) or self.__eq__(other)

    def __lt__(self, other) -> bool:
        return not self.__ge__(other)

    # ================================================ Properties ===============================================

    @property
    def breakthrough_experience(self) -> int:
        return self._breakthrough_experience

    @property
    def major(self) -> int:
        return self._major

    @property
    def minor(self) -> int:
        return self._minor

    @property
    def name(self) -> str:
        # Fallback on simpler cultivation name of stars and rank which is the BEAST dict
        return self._name

    @property
    def next_stage(self) -> Optional[CultivationStage]:
        return None

    @property
    def previous_stage(self) -> Optional[CultivationStage]:
        return None

    # ================================================ "Real" methods ===============================================

    def advance_by(self, count: int, maintain_major: bool = False) -> CultivationStage:
        if count == 0:
            return self
        elif count > 0:
            next_stage: Optional[CultivationStage] = self.next_stage
            if next_stage is None or maintain_major and next_stage.major != self.major:
                return self

            return next_stage.advance_by(count - 1)
        else:
            # count < 0
            previous_stage: Optional[CultivationStage] = self.previous_stage
            if previous_stage is None or maintain_major and previous_stage.major != self.major:
                return self

            return previous_stage.advance_by(count + 1)

    def required_exp_to_reach(self, stage: C, exp_in_stage: int = 0) -> int:
        """
        Calculate how much experience is needed to reach the specified stage from this stage given the specified experience already accumulated in the current stage.

        Parameters
        ----------
        stage: CultivationStage
               The stage to reach

        exp_in_stage: int
                      The experience already accumulated in this state

        Returns
        -------
        int
            The missing experience before reaching the target stage

        Raises
        ------
        ValueError
            If the specified target stage is unreachable from this stage. The result can be negative if this stage is more advanced than the specified one
        """

        current_stage: CultivationStage = self
        if type(self) is not type(stage):
            raise ValueError(f"{self} is not the same cultivation system as {stage}")

        if current_stage == stage:
            return current_stage.breakthrough_experience - exp_in_stage - 1

        # Normal mode
        if current_stage < stage:
            total_exp: int = self.breakthrough_experience - exp_in_stage
            next_stage: Optional[CultivationStage] = self.next_stage
            while next_stage is not None and next_stage != stage:
                total_exp += next_stage.breakthrough_experience
                current_stage = next_stage
                next_stage = current_stage.next_stage

            if next_stage is None:
                # Shouldn't really happen
                raise ValueError(f"Cannot reach {stage} from {self}")

            total_exp += next_stage.breakthrough_experience - 1
        else:
            # Reverse mode
            total_exp: int = -exp_in_stage - 1
            previous_stage: Optional[CultivationStage] = self.previous_stage
            while previous_stage is not None and previous_stage != stage:
                total_exp -= previous_stage.breakthrough_experience
                current_stage = previous_stage
                previous_stage = current_stage.previous_stage

            if previous_stage is None:
                # Shouldn't really happen
                raise ValueError(f"Cannot reach {stage} from {self}")

        return total_exp


# =======================================================================================================================
# =============================================== PlayerCultivationStage ================================================
# =======================================================================================================================
class PlayerCultivationStage(CultivationStage):
    def __init__(self, major: int, minor: int):
        entry: tuple[str, int, int, float] = _get_player_cultivation_entry(major, minor)
        super().__init__(major, minor, entry)
        self._previous_stage: Optional[PlayerCultivationStage] = None
        self._next_stage: Optional[PlayerCultivationStage] = None
        self._required_total_experience: Optional[int] = None
        self._max_energy: int = entry[2]
        self._combat_power: float = entry[3]

    def __repr__(self) -> str:
        return f"PlayerCultivationStage {self._major}, {self._minor}"

    @property
    def combat_power(self) -> float:
        return self._combat_power

    @property
    def displayed_combat_power(self) -> int:
        return round(self._combat_power ** (1 / 3))

    @property
    def experience_cap(self) -> int:
        return int(self.breakthrough_experience * 150 // 100) if self.has_experience_cap else -1

    @property
    def has_experience_cap(self) -> bool:
        # Special exception for Ruler rank that has no exp cap
        return not self.is_ruler

    @property
    def is_ruler(self) -> bool:
        return self._major == len(PLAYER_CULTIVATION_TABLE) - 1

    @property
    def maximum_energy(self) -> int:
        return self._max_energy

    @property
    def next_stage(self) -> Optional[PlayerCultivationStage]:
        if self._next_stage is None:
            next_stage: Optional[tuple[int, int]] = _find_next_stage(PLAYER_CULTIVATION_TABLE, self._major, self._minor)
            if next_stage is not None:
                self._next_stage = PlayerCultivationStage(next_stage[0], next_stage[1])
                self._next_stage._previous_stage = self

        return self._next_stage

    @property
    def previous_stage(self) -> Optional[PlayerCultivationStage]:
        if self._previous_stage is None:
            prev_stage: Optional[tuple[int, int]] = _find_previous_stage(PLAYER_CULTIVATION_TABLE, self._major, self._minor)
            if prev_stage is not None:
                self._previous_stage = PlayerCultivationStage(prev_stage[0], prev_stage[1])
                self._previous_stage._next_stage = self

        return self._previous_stage

    @property
    def required_total_experience(self) -> int:
        if self._required_total_experience is None:
            previous_stage: Optional[PlayerCultivationStage] = self.previous_stage
            if previous_stage is None:
                self._required_total_experience: int = 0
            else:
                self._required_total_experience: int = previous_stage.required_total_experience + previous_stage.breakthrough_experience

        return self._required_total_experience


# =======================================================================================================================
# =============================================== BeastCultivationStage =================================================
# =======================================================================================================================
class BeastCultivationStage(CultivationStage):
    def __init__(self, major: int, minor: int, rarity: str = "abundant"):
        super().__init__(major, minor, _get_beast_cultivation_entry(major, minor), BEAST_EXPERIENCE_RARITY_INCREASE[rarity] if rarity in BEAST_EXPERIENCE_RARITY_INCREASE else None)
        self._rarity: str = rarity

    def __repr__(self) -> str:
        return f"BeastCultivationStage {self._rarity}, {self._major}, {self._minor}"

    @property
    def next_stage(self) -> Optional[BeastCultivationStage]:
        next_stage: Optional[tuple[int, int]] = _find_next_stage(BASE_BEAST_CULTIVATION_TABLE, self._major, self._minor)
        return BeastCultivationStage(next_stage[0], next_stage[1], self._rarity) if next_stage is not None else None

    @property
    def previous_stage(self) -> Optional[BeastCultivationStage]:
        prev_stage: Optional[tuple[int, int]] = _find_previous_stage(BASE_BEAST_CULTIVATION_TABLE, self._major, self._minor)
        return BeastCultivationStage(prev_stage[0], prev_stage[1], self._rarity) if prev_stage is not None else None

    @property
    def rarity(self) -> str:
        return self._rarity

    # ================================================ Properties ===============================================

    def combat_power(self, from_stage: B, growth_rate: float, inherited_power: int = 0):
        current_cp: int = 0 if inherited_power <= 0 else inherited_power
        current_major: int = from_stage.major
        current_minor: int = from_stage.minor

        for major in range(current_major, self.major + 1):
            current_cp += BEAST_BASE_CP[self.rarity][major]
            max_minor: int = len(BASE_BEAST_CULTIVATION_TABLE[major]) if major < self.major else self.minor + 1
            for minor in range(current_minor, max_minor):
                current_cp = math.floor(current_cp * growth_rate)

            current_minor: int = 0

        return current_cp

    @staticmethod
    def max(rarity: str) -> B:
        max_major: int = len(BASE_BEAST_CULTIVATION_TABLE) - 1
        max_minor: int = len(BASE_BEAST_CULTIVATION_TABLE[max_major]) - 1
        return BeastCultivationStage(max_major, max_minor, rarity)


def generate_player_cultivation_stage_matrix() -> list[list[PlayerCultivationStage]]:
    start: PlayerCultivationStage = PlayerCultivationStage(0, 0)

    current_major: int = -1
    major_list: list[list[PlayerCultivationStage]] = []

    # Create, chain and structure everything
    current_stage: PlayerCultivationStage = start
    while current_stage is not None:
        if current_stage.major > current_major:
            current_major: int = current_stage.major
            minor_list: list[PlayerCultivationStage] = []
            major_list.append(minor_list)
        else:
            minor_list: list[PlayerCultivationStage] = major_list[current_major]

        minor_list.append(current_stage)
        current_stage: Optional[PlayerCultivationStage] = current_stage.next_stage

    return major_list

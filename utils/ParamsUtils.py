# =====================================
# ParamsUtils.py
# =====================================
# Contains parameters (data not stored in database) and related utility functions

import csv
import random
import re
import string
from math import floor
from typing import Optional, Iterable

from world.cultivation import MAJOR_CULTIVATION_REALMS, PlayerCultivationStage

DATA_DIR = './data'
INVALID_FILE_CHARACTERS = re.compile("[^\\w-]")


# =====================================
# Miscellaneous functions
# =====================================
def parse_int(value: Optional[str]) -> Optional[int]:
    if value is None or len(value) == 0:
        return None

    trimmed: str = value.replace(",", "")
    if len(trimmed) == 0:
        return None

    return int(trimmed)


def mention(user_id: int) -> str:
    return f"<@{user_id}>"


def ranking_str(position: int) -> str:
    last_digit: int = position % 10
    if last_digit == 1:
        suffix: str = "st"
    elif last_digit == 1:
        suffix: str = "nd"
    elif last_digit == 1:
        suffix: str = "rd"
    else:
        suffix: str = "th"

    return f"{position}{suffix}"


def list_to_dict(the_list, keys):
    return {key: item for item, key in zip(the_list, keys)}


# Returns True if text contains Chinese characters
def detect_chinese(text):
    if re.search("[\u4e00-\u9FFF]", text):
        return True
    else:
        return False


# =====================================
# Discord roles
# =====================================

PATREON_ROLES = {
    1133259681880621086: {"exp": 0, "cp": 0, "gold": 0, "energy": 0, "cooldown": 30},
    1133259918707802122: {"exp": 0, "cp": 0, "gold": 0, "energy": 0, "cooldown": 30},
    1133259927880749097: {"exp": 0, "cp": 0, "gold": 0, "energy": 0, "cooldown": 30},
    1133259935694729216: {"exp": 0, "cp": 0, "gold": 0, "energy": 0, "cooldown": 30}
}

ROLE_NAMES = ['Fight Disciple - 斗之气', 'Fight Practitioner - 斗者', 'Fight Master - 斗师',
              'Fight Grandmaster - 大斗师', 'Fight Spirit - 斗灵', 'Fight King - 斗王', 'Fight Emperor - 斗皇',
              'Fight Ancestor - 斗宗', 'Fight Venerate - 斗尊', 'Peak Fight Venerate - 斗尊巅峰', 'Half-Saint - 半圣',
              'Fight Saint - 斗圣', 'Fight God - 斗帝', 'Heavenly Sovereign', 'The Ruler']
ROLE_IDS = [825908038103597066, 825908022933061664, 825907997075046400, 825907957207531540, 825907919378972682,
            825907806699126784, 825907772938911755, 825907743411273768, 825907727929835551, 1008912115224035369, 825907648057966643,
            825907213029343322, 825906816416088064, 1132304521842937936, 1132304782028181594]

CURRENCY_NAME_ARENA_COIN = "ac"
CURRENCY_NAME_GOLD = "gold"
CURRENCY_NAME_STAR = "stars"
CURRENCY_NAME_EVENT = "ec"


# Return role ID given class major ID
def get_major_rank_role_id(major):
    return ROLE_IDS[major]


# =====================================
# Number display formatting
# =====================================

# Assumes number is positive
# Note that only after number is MORE than one order of magnitude higher,
# e.g. 10,000 then advance to next unit (-> 10 K)

# Example: 4320K
def format_num_abbr0(num):
    if num > 1e16:
        return '%iQ' % floor(num / 1e15)
    elif num > 1e13:
        return '%iT' % floor(num / 1e12)
    elif num > 1e10:
        return '%iB' % floor(num / 1e9)
    elif num > 1e7:
        return '%iM' % floor(num / 1e6)
    elif num > 1e4:
        return '%iK' % floor(num / 1e3)
    else:
        return "{:,}".format(floor(num))


# Example: 4320.2K
def format_num_abbr1(num):
    if num > 1e16:
        return '%.01fQ' % (num / float(1e15))
    elif num > 1e13:
        return '%.01fT' % (num / float(1e12))
    elif num > 1e10:
        return '%.01fB' % (num / float(1e9))
    elif num > 1e7:
        return '%.01fM' % (num / float(1e6))
    elif num > 1e4:
        return '%.01fK' % (num / float(1e3))
    else:
        return "{:,}".format(num)


# Example: 4320.2K [4,320,281]
def format_num_full(num):
    abbreviated_num_str = format_num_abbr1(num)
    if num > 999999:
        return '%s [%s]' % (abbreviated_num_str, "{:,}".format(num))
    else:
        return "{:,}".format(round(num))


# Example: 4,320,281
def format_num_simple(num):
    return "{:,}".format(num)


def as_discord_list(values: Iterable[str]) -> str:
    return "- " + "\n- ".join(values)


# =====================================
# Technique/Method tiers
# =====================================

# Note that technique tier ID = 1 for Low Huang and so on
TECH_TIER_NAMES = ["Low Huang", "Middle Huang", "High Huang", "Low Xuan", "Middle Xuan", "High Xuan", "Low Di", "Middle Di", "High Di", "Low Tian", "Middle Tian", "High Tian"]


# Returns tier name corresponding to tier ID
def tier_id_to_name(tier_id):
    return TECH_TIER_NAMES[tier_id - 1]


# Returns name of equivalent major class corresponding to tier ID
def tier_id_to_realm_name(tier_id):
    return MAJOR_CULTIVATION_REALMS[tier_id - 1]


# Returns (True, min_realm_ID_major) if player is able to learn a technique of certain tier
# otherwise (False, min_realm_ID_major)
def is_technique_learnable(technique_tier_id, realm_id_major):
    if technique_tier_id in [1, 2, 3]:  # Huang
        return realm_id_major >= 0, 0
    elif technique_tier_id in [4, 5, 6]:  # Xuan
        return realm_id_major >= 1, 1
    elif technique_tier_id == 7:  # Low Di
        return realm_id_major >= 2, 2
    elif technique_tier_id == 8:  # Middle Di
        return realm_id_major >= 3, 3
    elif technique_tier_id == 9:  # High Di
        return realm_id_major >= 5, 5
    elif technique_tier_id in [10, 11, 12]:  # Tian
        return realm_id_major >= 7, 7
    else:
        return True, 0  # TODO: account for other tier IDs


# =====================================
# Technique effects
# =====================================

REF_MULT_BELOW = [0.000002, 0.000005, 0.000017, 0.000053, 0.000169, 0.000535, 0.001694, 0.005358, 0.016884, 0.052652, 0.159049, 0.439469, 1][::-1]
REF_MULT_ABOVE = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096]


# REF_MULT_ABOVE = [1, 1.643032, 2.073321, 2.260232, 2.326458, 2.348184, 2.355129, 2.357331, 2.358027, 2.358246, 2.358316, 2.358338, 2.358345]

# Returns actual display CP bonus granted by a technique with
# given reference CP bonus value and technique tier
def compute_technique_cp_bonus(ref_cp, tech_tier_id, realm_id_major):
    ref_realm_id_major = tech_tier_id - 1
    if realm_id_major < ref_realm_id_major:
        return ref_cp * REF_MULT_BELOW[ref_realm_id_major - realm_id_major]
    else:
        return ref_cp * REF_MULT_ABOVE[realm_id_major - ref_realm_id_major]


# =====================================
# Combat stat conversions
# =====================================

def internal_to_display_cp(internal_cp: float) -> float:
    return internal_cp ** (1 / 3)


def display_to_internal_cp(display_cp: int) -> int:
    return display_cp ** 3


def internal_cp_to_attack(internal_cp: float) -> int:
    attack = (internal_cp ** (1 / 6)) * 10
    attack = round(random.uniform(attack * 0.85, attack))
    return attack


# =====================================
# Base CP values
# =====================================

# Returns base display CP achieved after breaking through to specified sublevel
def compute_breakthrough_cp(major: int, minor: int) -> int:
    return round(internal_to_display_cp(PlayerCultivationStage(major, minor).combat_power))


# =====================================
# PVP elo system
# =====================================

ELO_RANKS = ["Huang", "Xuan", "Di", "Tian"]
ELO_SUB_RANKS = ["Low", "Middle", "High"]
SUB_RANK_POINTS = 100
MAX_EXCESS_POINTS = SUB_RANK_POINTS - 1
MAX_POINTS = (len(ELO_RANKS) * len(ELO_SUB_RANKS) * SUB_RANK_POINTS) - 1

WIN_POINTS = 18  # Number of points gained upon win
WIN_POINTS_DICT = {"Unranked": 18, "Huang": 18, "Xuan": 16, "Di": 14, "Tian": 12}
LOSS_POINTS = 12  # Number of points lost upon loss (POSITIVE NUMBER!!)
LOSS_POINTS_DICT = {"Unranked": 12, "Huang": 12, "Xuan": 14, "Di": 16, "Tian": 18}
PROMOTION_FAIL_PENALTY = 25
DEMOTION_PENALTY = 25


# Promo matches are best of 3 right now. This affects how users.pvp_promo is interpreted.
# TODO: Point system resets x sub-ranks down every cycle/season, daily and seasonal rewards

# Returns (elo_rank, elo_sub_rank, excess_points) given total points
# Note that 1-100 is Low Huang, 101-200 is Middle Huang and so on
def elo_from_rank_points(points):
    total_num_sub_ranks = (points - 1) // SUB_RANK_POINTS
    excess_points = (points - 1) % SUB_RANK_POINTS

    if total_num_sub_ranks == -1:  # 0 ranked points
        return "Unranked", '', -1

    num_ranks = total_num_sub_ranks // len(ELO_SUB_RANKS)
    num_sub_ranks = total_num_sub_ranks % len(ELO_SUB_RANKS)

    elo_rank = ELO_RANKS[num_ranks]
    elo_sub_rank = ELO_SUB_RANKS[num_sub_ranks]

    return elo_rank, elo_sub_rank, excess_points


# =====================================
# Question generation
# =====================================

# Load some data first
f = open('%s/wiktionary_mandarin_1000.tsv' % DATA_DIR, 'r', encoding='utf8')
chinese_pinyin_dict = {}
for line in f:
    simp, pinyin = line.strip().split('\t')
    chinese_pinyin_dict[simp] = pinyin

csv_f = csv.reader(open('%s/country_capitals.csv' % DATA_DIR, 'r', encoding='utf8'))
next(csv_f)  # Skip header
country_capital_dict = {row[0]: row[1] for row in csv_f}


def random_question_from_dict(question_answer_dict, question_format, num_choices=3):
    chosen_question = random.choice(list(question_answer_dict.keys()))
    answer = question_answer_dict[chosen_question]
    question_str = question_format % chosen_question

    other_answers = list(question_answer_dict.values())
    other_answers.remove(answer)
    answer_choices = random.sample(other_answers, num_choices - 1) + [answer]
    return question_str, answer_choices, answer


# Returns random string of specified length
def random_string(length):
    characters = string.ascii_uppercase + string.ascii_lowercase + string.digits
    return ''.join(random.choice(characters) for _ in range(length))


# Returns (question_str, answer_choices, answer)
def generate_macro_question(num_choices=3):
    question_type = random.randint(0, 5)
    if question_type == 0:  # Addition
        num1 = random.randint(0, 50)
        num2 = random.randint(0, 50)
        question_str = "What is %i + %i?" % (num1, num2)
        answer = num1 + num2
        other_answers = list(range(100 + 1))
        other_answers.remove(answer)
        answer_choices = random.sample(other_answers, num_choices - 1) + [answer]
        answer_timeout = 30
    elif question_type == 1:  # Subtraction
        num1 = random.randint(10, 20)
        num2 = random.randint(0, 10)
        question_str = "What is %i - %i?" % (num1, num2)
        answer = num1 - num2
        other_answers = list(range(20 + 1))
        other_answers.remove(answer)
        answer_choices = random.sample(other_answers, num_choices - 1) + [answer]
        answer_timeout = 30
    elif question_type == 2:  # Multiplication
        num1 = random.randint(0, 12)
        num2 = random.randint(0, 12)
        question_str = "What is %i * %i?" % (num1, num2)
        answer = num1 * num2
        other_answers = list(range(144 + 1))
        other_answers.remove(answer)
        answer_choices = random.sample(other_answers, num_choices - 1) + [answer]
        answer_timeout = 30
    elif question_type == 3:  # String character
        str_len = random.randint(5, 10)
        rand_str = random_string(str_len)
        index = random.randint(0, str_len - 1)
        question_str = "What is the character in position %i of string '%s'?" % (index + 1, rand_str)
        answer = rand_str[index]
        other_chars = set(rand_str)
        other_chars.remove(answer)
        num_other_choices = min([len(other_chars), num_choices - 1])
        answer_choices = random.sample(other_chars, num_other_choices) + [answer]
        answer_timeout = 30
    elif question_type == 4:  # Chinese
        question_format = "What is the pinyin for %s? (Hint: use Google Translate.)"
        question_str, answer_choices, answer = random_question_from_dict(chinese_pinyin_dict, question_format)
        answer_timeout = 60
    else:  # Country capitals
        question_format = "What is the capital of %s?"
        question_str, answer_choices, answer = random_question_from_dict(country_capital_dict, question_format)
        answer_timeout = 60

    return question_str, answer_choices, answer, answer_timeout


# =====================================
# Miscellaneous data
# =====================================
MONEY_CARD_LINES = {
    10000: "zero",
    50000: "one",
    100000: "two",
    500000: "three",
    1000000: "four",
    5000000: "five",
    10000000: "six",
    50000000: "seven",
    100000000: "eight",
    500000000: "nine"
}

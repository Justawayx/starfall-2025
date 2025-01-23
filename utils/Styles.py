import disnake

# =====================================
# Styles.py
# =====================================
# Contains colors, emojis and other style-related parameters

# =====================================
# Colors
# =====================================

C_Help = 0xfb3e8f
C_CommandHelp = 0xd70055
C_Nothing = 0xf05454
C_Error = 0xcc0b0b

COLOR_LIGHT_GREEN = disnake.Color(0xdcfe7c)


# =====================================
# Emojis
# =====================================

def get_beast_image(beast_name: str):
    try:
        beast_name = beast_name.replace(" ", "_")
        path = f"./media/beast/{beast_name}.png"
        file = disnake.File(path)

        return file
    except OSError:
        return None


data = {"basicemoji": {
    "arrow_right": "<:arrow_Right:997399523666169926>",
    "arrow_left": "<:arrow_Left:997399526602186762>",
    "plus": "<:plus:987586656934690856>",
    "minus": "<:minus:987586651171725402>",
    "cross": "<:cross_e:987586646797070336>",
    "tick": "<:Check:987586641805848626>",
    "exclamation": "<:exclamation_e:987587626418712587>",
    "vs": "<:vs_e:987586638177771600>",
    "heart": "<:Beast_Hp:987586629399109742>",
    "heart_half": "<:Beast_lose_hp:987587608471298068>",
    "heart_empty": "<:Beast_Hp:987586629399109742>"
},
    "itememoji": {
        "cherb": "",
        "rherb": "",
        "uherb": "",
        "lherb": "",
        "mherb": "",
        "strpill": "<:AmassingStrengthPill:993392786978132068>",
        "healpill": "<:WoundHealingPills:993392826903711814>",
        "conpill": "<:CongealFlamePill:993392794288791584>",
        "recpill": "<:EnergyRecovery:993392799309377597>",
        "bonepill": "<:BoneGrowing:993392791168233492>",
        "refpill": "<:Refreshing:993392820608049263>",
        "windpill": "<:WindWalking:993392825133707314>",
        "bloodpill": "<:BurningBlood:993392792401362994>",
        "heartpill": "<:PurpleHeartBarrierBreaking:993392817856585778>",
        "pathpill": "<:PathProtecting:993392814522110012>",
        "icypill": "<:IcyHeartPill:993392803193299024>",
        "onelinegreen": "<:OnelineGreenSpirit:993392813075079248>",
        "twolinegreen": "<:TwolineGreenSpirit:993392823011381278>",
        "threelinegreen": "<:ThreelineGreenSpirit:993392822067658853>",
    }}

BASIC_EMOJIS = data["basicemoji"]

RIGHT = data["basicemoji"]["arrow_right"]
LEFT = data["basicemoji"]["arrow_left"]
PLUS = data["basicemoji"]["plus"]
MINUS = data["basicemoji"]["minus"]
CROSS = data["basicemoji"]["cross"]
TICK = data["basicemoji"]["tick"]
EXCLAMATION = data["basicemoji"]["exclamation"]
VS = data["basicemoji"]["vs"]
HEART = data["basicemoji"]["heart"]
HEART_HALF = data["basicemoji"]["heart_half"]
HEART_EMPTY = data["basicemoji"]["heart_empty"]

ITEM_EMOJIS = data["itememoji"]  # Dictionary (item ID) -> emoji asset

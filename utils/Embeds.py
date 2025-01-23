import disnake

from utils.Styles import TICK, CROSS, EXCLAMATION, PLUS, MINUS


class BasicEmbeds:

    def __init__(self):
        pass

    @staticmethod
    def empty_embed():
        embed = disnake.Embed(
            color=disnake.Color(0x2e3135)
        )
        return embed

    @staticmethod
    def right_tick(content, title="Done!"):
        embed = disnake.Embed(
            title=title,
            description=TICK + content,
            color=disnake.Color(0x2e3135)
        )
        return embed

    @staticmethod
    def wrong_cross(content, title="Uh oh.. :("):
        embed = disnake.Embed(
            title=title,
            description=CROSS + content,
            color=disnake.Color(0x2e3135)
        )
        return embed

    @staticmethod
    def exclamation(content):
        embed = disnake.Embed(
            description=EXCLAMATION + content,
            color=disnake.Color(0x2e3135)
        )
        return embed

    @staticmethod
    def add_plus(content, title="Added~ :)"):
        embed = disnake.Embed(
            title=title,
            description=PLUS + content,
            color=disnake.Color(0x2e3135)
        )
        return embed

    @staticmethod
    def remove_minus(content, title="Removed~"):
        embed = disnake.Embed(
            title=title,
            description=MINUS + content,
            color=disnake.Color(0x2e3135)
        )
        return embed

    @staticmethod
    def item_not_found():
        embed = disnake.Embed(
            description=EXCLAMATION + "The item id is invalid, please check the id and try again!",
            color=disnake.Color(0x2e3135)
        )
        return embed

    @staticmethod
    def cmd_not_continued():
        embed = disnake.Embed(
            description=EXCLAMATION + "The command was stopped due to full inventory",
            color=disnake.Color(0x2e3135)
        )
        return embed

    @staticmethod
    def no_main_pet():
        embed = disnake.Embed(
            description=EXCLAMATION + "You don't have a main pet. Please use `/pet manage` to choose a main pet!",
            color=disnake.Color(0x2e3135)
        )
        return embed

    @staticmethod
    def hatch_a_pet():
        embed = disnake.Embed(
            description=EXCLAMATION + "You dont have any pet owned. Please use `/hatch` to get a pet!",
            color=disnake.Color(0x2e3135)
        )
        return embed

    @staticmethod
    def not_enough_item(item, area="shop"):
        area_str = "You have get more from Shop using `/buy` command!"

        if area == "beast":
            area_str = "Hunt more beast to get the item using `/beast hunt` "

        elif area == "search":
            area_str = "You can get this from doing `/search`"

        elif area == "craft":
            area_str = "you can craft this item using `/craft` command "

        elif area == "alchemy":
            area_str = "you can refine more of this item using `/pills` command "
            
        elif area == "quest":
            area_str = "You can get more of this by completing quests"

        embed = disnake.Embed(
            description=EXCLAMATION + f"You do not have sufficient {item} in your inventory or ring!" + "\n\n" + area_str,
            color=disnake.Color(0x2e3135)
        )
        return embed

    @staticmethod
    def wrong_unique_id():
        embed = disnake.Embed(
            description=EXCLAMATION + "Please pass in the unique ring id as a number separated by '/'! \nexample: `lring/10`, `cauldron/309` etc",
            color=disnake.Color(0x2e3135)
        )
        return embed

    @staticmethod
    def not_enough_money():
        embed = disnake.Embed(
            description=EXCLAMATION + "You dont have enough money to proceed",
            color=disnake.Color(0x2e3135)
        )
        return embed

    @staticmethod
    def not_enough_energy():
        embed = disnake.Embed(
            description=EXCLAMATION + "You dont have enough energy to execute this command, please wait for a while as energy regen over time \nYou can get more info by doing `/energy`",
            color=disnake.Color(0x2e3135)
        )
        return embed

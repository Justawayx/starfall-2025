import math
import random
from io import BytesIO
from typing import Optional

import disnake
from PIL import Image, ImageFont, ImageDraw

from adventure.auction import AuctionHouse
from character.player import PlayerRoster, Player, compute_pet_cp, compute_user_exp_bonus

from utils.Database import Alchemy, AllItems, Cultivation, GuildOptionsDict, Pvp, Factions, Crafting, Pet
from utils.DatabaseUtils import add_permanent_boost, check_for_great_ruler, compute_pill_bonus
from disnake.ext import commands
from datetime import timedelta, datetime

from utils.CommandUtils import add_temp_role, VoteLinkButton, PatreonLinkButton

from utils.Embeds import BasicEmbeds
from utils.ExpSystem import BREAKTHROUGH_ROLE
from utils.InventoryUtils import add_to_inventory, ConfirmDelete
from utils.LoggingUtils import log_event
from utils.ParamsUtils import format_num_abbr1, format_num_full, format_num_abbr0, detect_chinese, format_num_simple, generate_macro_question, elo_from_rank_points, compute_technique_cp_bonus
from utils.Styles import BASIC_EMOJIS, CROSS, EXCLAMATION, PLUS, RIGHT, LEFT
from utils.base import BaseStarfallCog
from world.cultivation import PlayerCultivationStage, BeastCultivationStage
from cogs.eventshop import EVENT_SHOP, EVENT_CONFIG

BOARD_COLOR_DICT = {
    "Red": (255, 0, 60),
    "Yellow": (255, 255, 0),
    "Blue": (0, 0, 255),
    "Black": (0, 0, 0),
    "Green": (30, 255, 0)
}


class AnswerButton(disnake.ui.Button):
    def __init__(self, label):
        super().__init__(label=str(label), style=disnake.ButtonStyle.grey)
        self.label = label

    async def callback(self, inter):
        self.view.answer = self.label
        self.view.clear_items()
        await inter.response.edit_message(view=self.view)
        self.view.stop()


class AnswerView(disnake.ui.View):
    def __init__(self, answers, author, answer_timeout):
        super().__init__(timeout=answer_timeout)
        for label in answers:
            self.add_item(AnswerButton(label))
        self.answer = None
        self.author = author

    async def interaction_check(self, inter):
        return inter.author == self.author

    async def on_timeout(self):
        self.clear_items()
        self.stop()


class Exp(BaseStarfallCog):

    def __init__(self, bot):
        super().__init__(bot, "Experience", "exp")

    async def _do_load(self):
        pass

    def _do_unload(self):
        pass

    @commands.slash_command(name="rank", description="Shows the level of a member")
    async def slash_rank(self,
                         inter: disnake.CommandInteraction,
                         member: Optional[disnake.Member] = commands.Param(default=None, description="Choose a member to see their rank")):
        await inter.response.defer()
        if member is None:
            member = inter.author

        player: Player = PlayerRoster().find_player_for(inter, member)

        all_users = await Cultivation.all().order_by("-major", "-minor", "-current_exp").values_list("user_id")
        all_users = [user[0] for user in all_users]
        rank = str(all_users.index(member.id) + 1)
        file = await self.make_rank_card(player, member, rank)

        view = disnake.ui.View()
        view.add_item(VoteLinkButton())
        view.add_item(PatreonLinkButton())

        await inter.edit_original_message(file=file, view=view)

    @staticmethod
    async def make_rank_card(player: Player, member: disnake.Member, rank):
        title_name_list = [
            "Fight_Disciple",
            "Fight_Practitioner",
            "Fight_Master",
            "Fight_Grandmaster",
            "Fight_Spirit",
            "Fight_King",
            "Fight_Emperor",
            "Fight_Ancestor",
            "Fight_Venerate",
            "Peak_Fight_Venerate",
            "Half_Saint",
            "Fight_Saint",
            "Fight_God",
            "Fight_God",
            "Fight_God",
            "Fight_God"
        ]

        exp: int = player.current_experience
        stage: PlayerCultivationStage = player.cultivation
        realm: str = stage.name
        if stage.is_ruler:
            tgr_check: str = await check_for_great_ruler(member.id)
            if tgr_check:
                realm = tgr_check

        p_exp: int = min(player.current_experience * 100 // stage.breakthrough_experience, 100)
        percent_floor: int = max(math.floor(p_exp / 10) * 10, 10)
        title_name: str = "Mortal" if stage.major == 0 and stage.minor == 0 else title_name_list[stage.major]

        font = ImageFont.truetype("./media/Rank/edosz.ttf", 74)
        small_font = ImageFont.truetype("./media/Rank/edosz.ttf", 58)
        very_small_rank_font = ImageFont.truetype("./media/Rank/edosz.ttf", 42)
        chinese_font = ImageFont.truetype("./media/Rank/SentyZHAO-20180827.ttf", 64)

        if member.avatar is None:
            member_pic = member.guild.me.avatar.with_size(256)
        else:
            member_pic = member.avatar.with_size(256)

        data1 = BytesIO(await member_pic.read())

        user_pic = Image.open(data1)
        user_pic = user_pic.resize((350, 350))

        big_size = (user_pic.size[0] * 3, user_pic.size[1] * 3)
        mask = Image.new('L', big_size, 0)

        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0) + big_size, fill=255)

        mask = mask.resize(user_pic.size, Image.LANCZOS)
        while len(rank) < 5:
            rank = "0" + rank
        rank_num_list = [(Image.open(f'./media/Rank/Number_Rank/{digit}.png')).resize((35, 57)) for digit in rank]

        user_title = Image.open(f"./media/Rank/Titles/{title_name}.png")
        user_title = user_title.resize((525, 130))

        exp_bar = Image.open(f"./media/Rank/ExpBar/{title_name}{percent_floor}.png")
        exp_bar = exp_bar.resize((2050, 140))

        base = Image.open("./media/Rank/base.png")
        base = base.resize((2160, 722))

        member_name = str(member)
        member_name_font = chinese_font if detect_chinese(member_name) else font

        if stage.has_experience_cap:
            exp_text: str = f"{exp:,} / {stage.breakthrough_experience:,}"
        else:
            exp_text: str = f"{exp:,}"

        card_text = ImageDraw.Draw(base)
        card_text.text((585, 260), member_name, (0, 0, 0), anchor="lm", font=member_name_font)

        if exp >= stage.breakthrough_experience and not stage.is_ruler:
            card_text.text((1545, 458), exp_text, (255, 77, 77), anchor="lm", font=small_font)
        else:
            card_text.text((1545, 458), exp_text, (0, 0, 0), anchor="lm", font=small_font)

        if stage.major == 13:
            card_text.text((595, 458), realm, (0, 0, 0), anchor="lm", font=very_small_rank_font)
        else:
            card_text.text((595, 458), realm, (0, 0, 0), anchor="lm", font=small_font)

        x_cords, y_cords = 130, 105
        base.paste(user_pic, (x_cords, y_cords, x_cords + user_pic.size[0], y_cords + user_pic.size[1]), mask)

        bar_x_cords, bar_y_cords = 70, 495
        base.paste(exp_bar, (bar_x_cords, bar_y_cords, bar_x_cords + exp_bar.size[0], bar_y_cords + exp_bar.size[1]), exp_bar)

        card_text.text((123, 563), "RANK :", (255, 255, 255), anchor="lm", font=small_font)

        rank_x_cords, rank_y_cords = 298, 533
        for image in rank_num_list:
            base.paste(image, (rank_x_cords, rank_y_cords, image.size[0] + rank_x_cords, image.size[1] + rank_y_cords), image)
            rank_x_cords += (3 + image.size[0])

        title_x_cords, title_y_cords = 47, 355
        base.paste(user_title, (title_x_cords, title_y_cords, title_x_cords + user_title.size[0], title_y_cords + user_title.size[1]), user_title)

        buffer = BytesIO()
        base.save(buffer, "png")
        buffer.seek(0)

        file = disnake.File(fp=buffer, filename="base.png")
        return file

    @commands.slash_command(name="cultivate")
    async def slash_cultivate(self, inter: disnake.CommandInteraction):
        pass

    @slash_cultivate.sub_command(name="exp", description="Cultivate to gain Exp")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def slash_cultivate_exp(self, inter: disnake.CommandInteraction):
        await inter.response.defer()

        player: Player = PlayerRoster().find_player_for(inter)
        possible, msg = await player.start_cultivating_exp()
        if not possible:
            await inter.edit_original_message(msg)
            return

        embed = disnake.Embed(
            title="Question time!",
            description=f"To {inter.author.mention} \n",
            color=disnake.Color(0x2e3135)
        )

        question, answers, correct_answer, answer_timeout = generate_macro_question()
        embed.set_footer(text="You have %i seconds to answer." % answer_timeout)

        random.shuffle(answers)
        embed.description += question

        view = AnswerView(answers, inter.author, answer_timeout)
        await inter.edit_original_message(embed=embed, view=view)
        base_exp_reward = random.randint(10, 15)
        await view.wait()
        if view.answer is None:
            exp_penalty = int(0.7 * base_exp_reward)
            log_event(inter.author.id, "exp", f"Wrong cultivation -{exp_penalty}")
            async with player:
                player.remove_experience(exp_penalty)

            embed.title = "Uh oh"
            embed.description = "Question expired"
            embed.set_footer(text=f"Lost {exp_penalty}")

        elif str(view.answer) == str(correct_answer):
            major: int = player.cultivation.major
            if major > 10:
                multiplier: int = 100  # max 1500
            elif major > 6:
                multiplier: int = 60  # max 900
            elif major > 1:
                multiplier: int = 20  # max 300
            else:
                multiplier: int = 6  # max 90 without boost

            message_cooldown_minutes: int = multiplier // 2
            extra_energy_cost: int = (multiplier // 2) - 1

            view = ConfirmDelete(inter.author.id)
            await inter.channel.send(f"You will gain {base_exp_reward:,} base exp, do you want to get {multiplier:,}x the exp?\n\n- The cooldown will increase to {multiplier} minutes "
                                     f"\n- You wont be able to gain message exp for {message_cooldown_minutes} minutes \n- It will cost you {extra_energy_cost:,} more energy", view=view)

            await view.wait()
            if not view.confirm:
                log_event(inter.author.id, "exp", f"Right cultivation +{base_exp_reward}")
                async with player:
                    player.cultivation_cooldown = datetime.now() + timedelta(minutes=1)
                    total_awarded, _ = await player.add_experience(base_exp_reward)

                embed.title = "Nice"
                embed.description = "Thank you for answering the question correctly~"
                embed.set_footer(text=f"{total_awarded:,} exp given")
            else:
                async with player:
                    if player.consume_energy(extra_energy_cost):
                        base_exp_reward = multiplier * base_exp_reward
                        log_event(inter.author.id, "exp", f"Right cultivation +{base_exp_reward} ({multiplier}x)")

                        player.cultivation_cooldown = datetime.now() + timedelta(minutes=multiplier)
                        player.daily_message_cooldown = datetime.now() + timedelta(minutes=message_cooldown_minutes)
                        total_awarded, _ = await player.add_experience(base_exp_reward)

                        embed.title = "Big Nice"
                        embed.description = f"Thank you for answering the question correctly~ \n\n{PLUS}You got {multiplier}x exp!"
                        embed.set_footer(text=f"{total_awarded:,} exp given")
                    else:
                        embed.title = "Sad"
                        embed.description = "You don't have enough energy to cultivate"
                        embed.set_footer(text=f"0 exp given")
        else:
            exp_penalty = base_exp_reward // 2
            log_event(inter.author.id, "exp", f"Wrong cultivation -{exp_penalty}")
            async with player:
                player.remove_experience(exp_penalty)
                player.cultivation_cooldown = datetime.now() + timedelta(minutes=1)

            embed.title = "Wrong Answer"
            embed.description = "Question answered incorrectly"
            embed.set_footer(text=f"Lost {exp_penalty:,}")

        await inter.edit_original_message(embed=embed, view=view)

    @slash_cultivate.sub_command(name="cp", description="Spend Exp to gain Cp")
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def slash_cultivate_cp(self, inter: disnake.CommandInteraction):
        exp_cost = 50000
        cp_boost = 1

        await inter.response.defer()

        view = ConfirmDelete(inter.author.id)
        await inter.channel.send(f"You will be spending {exp_cost:,} EXP for {cp_boost}% permanent CP boost", view=view)

        await view.wait()
        if view.confirm is False:
            embed = BasicEmbeds.exclamation(f"Command stopped by the user")
            await inter.edit_original_message(embed=embed)
            return

        player: Player = PlayerRoster().find_player_for(inter)
        async with player:
            if player.current_experience < exp_cost:
                embed = BasicEmbeds.exclamation(f"You dont have enough exp to proceed")
            else:
                player.remove_experience(exp_cost)
                await add_permanent_boost(inter.author.id, cp=cp_boost)
                embed = BasicEmbeds.exclamation(f"You have gained {cp_boost}% CP boost for {exp_cost:,} EXP")

        await inter.edit_original_message(embed=embed)

    @commands.slash_command(name="breakthrough", description="Breakthrough a class")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def slash_breakthrough(self, inter: disnake.CommandInteraction):
        await inter.response.defer()

        player: Player = PlayerRoster().find_player_for(inter)
        cultivation: PlayerCultivationStage = player.cultivation
        next_stage: Optional[PlayerCultivationStage] = cultivation.next_stage
        if next_stage is None:
            await inter.edit_original_message(embed=BasicEmbeds.exclamation("You have reached the peak of cultivation!"))
            return

        if cultivation.major == 12:  # Fight God
            content = f"{CROSS} Failed to Breakthrough"
            embed_content = f"You've reached the peak of the Dou Qi Continent. To continue your cultivation, proceed to the Great Thousand World using `/transcend`"
            await inter.edit_original_message(content=content, embed=BasicEmbeds.exclamation(embed_content))
            return

        if player.current_experience < cultivation.breakthrough_experience:  # Not enough EXP to breakthrough
            embed = BasicEmbeds.wrong_cross(f"You need `{cultivation.breakthrough_experience - player.current_experience:,}` more exp to breakthrough")
            await inter.edit_original_message(embed=embed)
            return

        timeout_minutes = (cultivation.major * 2) + cultivation.minor
        leftover_experience: int = player.current_experience - cultivation.breakthrough_experience

        # FROM THIS POINT: BREAKTHROUGH
        log_event(inter.author.id, "breakthrough", f"Started to increase realm by 1")
        async with player:
            content, embed_content = await player.change_realm(1, "promote", inter.guild)
            if "Failed" not in content:
                if timeout_minutes >= 1:
                    breakthrough_role = inter.guild.get_role(BREAKTHROUGH_ROLE)
                    if breakthrough_role:
                        await inter.author.add_roles(breakthrough_role, reason="Breaking through a class")
                        await add_temp_role(inter.author.id, breakthrough_role.id, timeout_minutes)

                    embed_content += f"\n\n{EXCLAMATION}You can not gain exp or use commands for {timeout_minutes} minutes! \n*Hint: Choose breakthrough times carefully*"

                # Update current EXP and cooldown
                player.set_current_experience(leftover_experience)
                player.cultivation_cooldown = datetime.now() + timedelta(minutes=timeout_minutes)

                # Add event token drops
                token_text = ""
                if EVENT_SHOP.is_active and hasattr(self.bot.get_cog("EventManager"), "current_event"):
                    event_manager = self.bot.get_cog("EventManager")
                    current_event = event_manager.current_event
                    if current_event and EVENT_CONFIG[current_event]["sources"]["breakthrough"]:
                        drop_config = EVENT_CONFIG[current_event]["drop_rates"]["breakthrough"]
                        if random.randint(1, 100) <= drop_config["chance"]:
                            token_amount = random.randint(drop_config["min"], drop_config["max"])
                            token_id = EVENT_CONFIG[current_event]["token_id"]
                            await add_to_inventory(inter.author.id, token_id, token_amount)
                            token_text = f"\n\nReceived {token_amount}x {token_id} from the event!"
                            log_event(inter.author.id, "event", f"Gained {token_amount}x {token_id} from breakthrough")
                            embed_content += token_text

        await inter.edit_original_message(content=content, embed=disnake.Embed(description=embed_content, color=disnake.Color(0x2e3135)))

    @commands.slash_command(name="transcend", description="Transcend through a class")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def slash_transcend(self, inter: disnake.CommandInteraction):
        await inter.response.defer()

        player: Player = PlayerRoster().find_player_for(inter)
        cultivation: PlayerCultivationStage = player.cultivation

        if cultivation.major < 12:
            embed = BasicEmbeds.wrong_cross(f"You need to reach Fight God to transcend!")
            await inter.edit_original_message(embed=embed)
            return

        elif cultivation.major > 12:
            embed = BasicEmbeds.wrong_cross(f"You have already transcended, please continue your journey using `/breakthrough`")
            await inter.edit_original_message(embed=embed)
            return

        alchemy_level = await Alchemy.get_or_none(user_id=inter.author.id).values_list("a_lvl", flat=True)
        if alchemy_level < 10:
            embed = BasicEmbeds.exclamation(f"You need to be tier 10 alchemist in order to transcend")
            await inter.edit_original_message(embed=embed)
            return

        # Should never be None since major == 12 if we're here
        next_stage: PlayerCultivationStage = cultivation.next_stage

        content = f"{BASIC_EMOJIS['tick']} **Congratulations {inter.author.mention}!**"
        embed_content = f"{BASIC_EMOJIS['exclamation']} You have transcend through from **{cultivation}** to **{next_stage}**"
        log_event(inter.author.id, "transcend", f"Users transcended")

        async with player:
            player.cultivation = next_stage

        embed = disnake.Embed(
            description=embed_content,
            color=disnake.Color(0x2e3135)
        )
        view = disnake.ui.View()
        view.add_item(VoteLinkButton())
        view.add_item(PatreonLinkButton())

        await inter.edit_original_message(content=content, embed=embed, view=view)

    @commands.slash_command(name="exp", description="Parent Command")
    @commands.default_member_permissions(manage_messages=True)
    async def slash_exp(self, ctx):
        pass

    @slash_exp.sub_command(name="add", description="Give some amount of exp to cultivators")
    async def slash_exp_add(self,
                            inter: disnake.CommandInteraction,
                            amount: int = commands.Param(gt=0, description="Select the amount of exp to give"),
                            member: disnake.Member = commands.Param(description="Choose a member to give them exp")):
        async with PlayerRoster().find_player_for(inter, member) as player:
            await player.add_experience(amount, False)

        embed = disnake.Embed(
            description=f"{BASIC_EMOJIS['plus']} Gave {amount:,} exp to {member.mention}.",
            color=disnake.Color(0x2e3135)
        )
        await inter.response.send_message(embed=embed)

    @slash_exp.sub_command(name="remove", description="Take some amount of exp from cultivators")
    async def slash_exp_remove(self,
                               inter: disnake.CommandInteraction,
                               amount: int = commands.Param(gt=0, description="Select the amount of exp to take"),
                               member: disnake.Member = commands.Param(description="Choose a member to take exp from")):
        async with PlayerRoster().find_player_for(inter, member) as player:
            player.remove_experience(amount)

        embed = disnake.Embed(
            description=f"{BASIC_EMOJIS['minus']} Took {amount:,} exp from {member.mention}",
            color=disnake.Color(0x2e3135)
        )
        await inter.response.send_message(embed=embed)

    @commands.slash_command(name="board")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def board(self, ctx):
        """
        Parent Command
        """
        pass

    FONT_STYLE = commands.option_enum(
        {
            "edosz": "edosz.ttf"
        }
    )
    COLOR_OPTION = commands.option_enum(
        [
            "Red",
            "Yellow",
            "Blue",
            "Black",
            "Green"
        ]
    )

    @board.sub_command(name="carve", description="Carve your name on Firmament Board")
    async def carve(self, inter: disnake.CommandInteraction, name: str, font_style: FONT_STYLE, red: int = commands.Param(0, ge=0, le=255), blue: int = commands.Param(0, ge=0, le=255), green: int = commands.Param(0, le=255)):
        """
        Carve your name on Firmament Board

        Parameters
        ----------
        font_style: Select the amount of exp to give
        red: Choose the RED value of custom color
        blue: Choose the BLUE value of custom color
        green: Choose the GREEN value of custom color
        """
        await inter.response.defer()

        cultivation: PlayerCultivationStage = PlayerRoster().find_player_for(inter).cultivation
        if cultivation.major != 14:
            await inter.edit_original_message(embed=BasicEmbeds.exclamation(f"You need to reach the `{PlayerCultivationStage(14, 0)}` realm to continue"))
            return

        board = await GuildOptionsDict.get_or_none(name="firmament_board").values_list("value", flat=True)
        if board is None:
            await GuildOptionsDict.create(name="firmament_board", value=[])
            board = []

        for user in board:
            if int(user["user_id"]) == inter.author.id:
                # await inter.edit_original_message(embed=BasicEmbeds.exclamation(f"You can only carve your name once"))
                # return
                board.remove(user)

        user_dict = {
            "user_id": inter.author.id,
            "name": name,
            "font": font_style,
            "color": (red, blue, green)
        }

        board.append(user_dict)

        await GuildOptionsDict.filter(name="firmament_board").update(value=board)
        log_event(inter.author.id, "board", f"Carved {user_dict}")

        embed = BasicEmbeds.right_tick("Carved your name to firmament board. You can check it with `/board view` command.")
        await inter.edit_original_message(embed=embed)

    @board.sub_command(name="view", description="View the firmament board")
    async def view(self, inter: disnake.CommandInteraction):
        await inter.response.defer()

        board = await GuildOptionsDict.get_or_none(name="firmament_board").values_list("value", flat=True)
        if board is None:
            await GuildOptionsDict.create(name="firmament_board", value=[])
            board = []

        if len(board) < 1:
            await inter.edit_original_message("Nothing to see here")
            return

        file = self.make_firmament_board(board[:10])
        await inter.edit_original_message(file=file)

    @staticmethod
    def make_firmament_board(data_list):
        base = Image.new(mode="RGB", size=(720, 1080), color=(174, 181, 191))

        large_font = ImageFont.truetype("./media/Rank/edosz.ttf", 74)

        padding = 10

        total_rows = 11

        row_len = (base.size[1] - (padding * 2)) / total_rows

        im_draw = ImageDraw.Draw(base)

        row = 0
        title_cords = ((base.size[0] - (padding * 2)) / 2, padding + (row_len / 2) + row_len * row)

        im_draw.text(title_cords, "firmament BOARD", (0, 0, 0), anchor="mm", font=large_font)

        row = 1
        for n, user in enumerate(data_list):
            user_name, user_font, user_color = user["name"], user["font"], user["color"]
            name_cords = (padding, round(padding + (row_len / 2) + row_len * row))
            name_str = f"#{n + 1}  {user_name}"
            try:
                name_font = ImageFont.truetype(f"./media/Fonts/{user_font}", 54)
            except OSError:
                name_font = ImageFont.truetype("./media/Rank/edosz.ttf", 54)

            im_draw.text(name_cords, name_str, (user_color[0], user_color[1], user_color[2]), anchor="lm", font=name_font)
            row += 1

        buffer = BytesIO()
        base.save(buffer, "png")
        buffer.seek(0)

        file = disnake.File(fp=buffer, filename="board.png")
        return file

    @commands.slash_command(name="profile", description="See Profile of the cultivator")
    async def slash_profile(self, inter: disnake.CommandInteraction, member: disnake.Member = None):
        await inter.response.defer()
        if not member:
            member = inter.author

        player: Player = PlayerRoster().find_player_for(inter, member)

        cp = await player.compute_total_cp()
        _, _, battle_boost, _ = await compute_pill_bonus(member.id)
        battle_cp = cp * (1 + battle_boost / 100)

        main_pet_data = await Pet.get_or_none(user_id=member.id, main=1).values_list("nickname", "pet__rarity", "p_major", "p_minor", "pet__name")
        has_pet = main_pet_data is not None
        if has_pet:
            pet_nickname, pet_rarity, pet_major, pet_minor, pet_name = main_pet_data
            pet_cultivation: BeastCultivationStage = BeastCultivationStage(int(pet_major), int(pet_minor), pet_rarity)
            pet_realm: str = pet_cultivation.name
            pet_major_rank_str = "Rank %s" % pet_realm.split("Rank ")[1] if 'Rank' in pet_realm else "Heavenly Sovereign"
            pet_nickname_str = "" if pet_nickname == pet_name else f'"{pet_nickname}" '
        else:
            pet_name = None
            pet_rarity = None
            pet_major_rank_str = None
            pet_nickname_str = None

        major, minor, msg_limit, equipped = await Cultivation.get_or_none(user_id=member.id).values_list("major", "minor", "msg_limit", "user__equipped")
        equipped_techs = equipped["techniques"]
        equipped_method = equipped["method"]

        alchemy_lvl = await Alchemy.get_or_none(user_id=member.id).values_list("a_lvl", flat=True)
        rank_points = await Pvp.get_or_none(user_id=member.id).values_list("rank_points", flat=True)

        techniques_data = await AllItems.filter(type="fight_technique").values_list("id", "tier")

        # Tacky solution TODO make better in the future kek
        tech_id_tier_dict = {}
        for technique_datum in techniques_data:
            technique_id, tier = technique_datum
            tech_id_tier_dict[technique_id] = tier

        faction_data = await Factions.get_or_none(user_id=member.id).values_list("role_id", flat=True)

        if len(equipped_techs) == 0:
            tech_bonus_str = "> *No Fight Techniques learned*"
        else:
            tech_bonus_items = []
            for tech_id, tech_info in sorted(equipped_techs.items(), key=lambda x: x[1][0]):
                ref_cp_bonus, tech_tier, tech_name = tech_info
                actual_cp_bonus = compute_technique_cp_bonus(ref_cp_bonus, tech_tier, major)
                tech_bonus_items.append('> %s (`%s`): +%s CP' % (tech_name, tech_id, format_num_abbr0(actual_cp_bonus)))
            tech_bonus_str = '\n'.join(tech_bonus_items)

        if equipped_method is None:
            method_bonus_str = "> *No Qi Method learned*"
        else:
            method_id, cp_boost, method_tier, method_name = equipped_method
            method_bonus_str = "> %s (`%s`): +%i%% CP" % (method_name, method_id, cp_boost)

        player_cultivation: PlayerCultivationStage = player.cultivation
        realm: str = player_cultivation.name
        if player_cultivation.major == 14:
            tgr_check = await check_for_great_ruler(member.id)
            if tgr_check:
                realm = tgr_check

        if faction_data:
            faction = f"<@&{faction_data}>"
        else:
            faction = "None"

        exp_boost = await compute_user_exp_bonus(member.id)
        elo_rank, elo_sub_rank, excess_points = elo_from_rank_points(rank_points)

        values = [
            f"**Username** : {member.name}",
            f"**Class** : {realm}",
            f"**CP** : {format_num_full(cp)}",
            f"**Battle CP** : {format_num_full(battle_cp)}",
            f"**Pet**: %s" % (f"{pet_nickname_str}{pet_major_rank_str} {pet_rarity.capitalize()} {pet_name}" if has_pet else "*None*"),
            f"**Message Limit** : {msg_limit} / 100",
            f"**Alchemy Tier** : {alchemy_lvl}",
            f"**Exp Boost** : {exp_boost}%",
            f"**Faction** : {faction}",
            f"**Qi Method** : \n{method_bonus_str}",
            f"**Fight Techniques** : \n{tech_bonus_str}",
            f"**PVP Rank** : {elo_sub_rank} {elo_rank}",
            f"**Total Ranked Points** : {rank_points}"
        ]
        embed = disnake.Embed(
            title="Profile",
            description="\n".join(value for value in values),
            color=disnake.Color(0x2e3135)
        )
        if member.avatar:
            embed.set_thumbnail(url=member.avatar.url)

        view = disnake.ui.View()
        view.add_item(VoteLinkButton())
        view.add_item(PatreonLinkButton())

        await inter.edit_original_message(embed=embed, view=view)

    TYPE = commands.option_enum(
        ["Exp", "Balance", "Alchemy", "Craft", "Pet"]
    )

    @commands.slash_command(name="leaderboard", description="Show you a leaderboard of specific type")
    async def slash_leaderboard(self, inter, board_type: TYPE):
        await inter.response.defer()
        leaderboard_embeds = []

        n = 10  # Number of entries per page

        if board_type == "Exp":
            users_data: list[tuple[int, int, int]] = await Cultivation.filter(major__gte=1).order_by("-major", "-minor", "-current_exp").values_list("user_id", "major", "minor")
            # users_data = await Cultivation.all().order_by("-major", "-minor", "-current_exp").limit(n*max_pages).values_list("user_id", "major", "minor")
            num_entries = len(users_data)
            num_pages = math.ceil(num_entries / n)

            for page_idx in range(num_pages):
                embed = disnake.Embed(title="Level Ranking", color=disnake.Color(0x2e3135), timestamp=datetime.now())
                embed.set_thumbnail(url=inter.guild.icon.url)
                embed.description = f"Top **10**" if page_idx == 0 else f"Rank #{page_idx * n + 1}-{min(num_entries, (page_idx + 1) * n)}"
                entries = []
                for i in range(page_idx * n, ((page_idx + 1) * n)):
                    if i >= num_entries:
                        break
                    data = users_data[i]
                    realm = PlayerCultivationStage(data[1], data[2]).name
                    if data[1] == 14:
                        tgr_check = await check_for_great_ruler(int(data[0]), users_data)
                        if tgr_check:
                            realm = tgr_check

                    entries.append(f"**#{i + 1}** <@{data[0]}> | `{realm}`")
                embed.add_field(name="Exp - ", value='\n'.join(entries), inline=False)
                leaderboard_embeds.append(embed)

        elif board_type == "Balance":
            ah: AuctionHouse = AuctionHouse()
            roster: PlayerRoster = PlayerRoster()
            players: list[Player] = roster.list()
            balances: list[tuple[int, int]] = [_compute_gold_balance_entry(player, ah) for player in players]
            balances.sort(key=lambda e: e[1], reverse=True)
            num_entries = len(balances)
            num_pages = math.ceil(num_entries / n)

            for page_idx in range(num_pages):
                embed = disnake.Embed(title="Balance Ranking", color=disnake.Color(0x2e3135), timestamp=datetime.now())
                embed.set_thumbnail(url=inter.guild.icon.url)
                embed.description = f"Top **10**" if page_idx == 0 else f"Rank #{page_idx * n + 1}-{min(num_entries, (page_idx + 1) * n)}"
                entries = []
                for i in range(page_idx * n, ((page_idx + 1) * n)):
                    if i >= num_entries:
                        break
                    data = balances[i]
                    entries.append(f"**#{i + 1}** <@{data[0]}> | `{format_num_simple(data[1])}` **Gold**")
                embed.add_field(name="Balance - ", value='\n'.join(entries), inline=False)
                leaderboard_embeds.append(embed)

        elif board_type == "Alchemy":
            users_data = await Alchemy.filter(a_lvl__gt=0).order_by("-a_lvl", "-a_exp").values_list("user_id", "a_lvl", "a_exp")
            num_entries = len(users_data)
            num_pages = math.ceil(num_entries / n)

            for page_idx in range(num_pages):
                embed = disnake.Embed(title="Alchemy Ranking", color=disnake.Color(0x2e3135), timestamp=datetime.now())
                embed.set_thumbnail(url=inter.guild.icon.url)
                embed.description = f"Top **10**" if page_idx == 0 else f"Rank #{page_idx * n + 1}-{min(num_entries, (page_idx + 1) * n)}"
                entries = []
                for i in range(page_idx * n, ((page_idx + 1) * n)):
                    if i >= num_entries:
                        break
                    data = users_data[i]
                    entries.append(f"**#{i + 1}** <@{data[0]}> | **Tier** `{data[1]}` | {format_num_abbr1(data[2])} **Exp**")
                embed.add_field(name="Alchemy - ", value='\n'.join(entries), inline=False)
                leaderboard_embeds.append(embed)

        elif board_type == "Craft":
            users_data = await Crafting.all().order_by("-c_lvl", "-c_exp").values_list("user_id", "c_lvl", "c_exp")
            num_entries = len(users_data)
            num_pages = math.ceil(num_entries / n)

            for page_idx in range(num_pages):
                embed = disnake.Embed(title="Craft Ranking", color=disnake.Color(0x2e3135), timestamp=datetime.now())
                embed.set_thumbnail(url=inter.guild.icon.url)
                embed.description = f"Top **10**" if page_idx == 0 else f"Rank #{page_idx * n + 1}-{min(num_entries, (page_idx + 1) * n)}"
                entries = []
                for i in range(page_idx * n, ((page_idx + 1) * n)):
                    if i >= num_entries:
                        break
                    data = users_data[i]
                    entries.append(f"**#{i + 1}** <@{data[0]}> | **Level** `{data[1]}` | {format_num_abbr1(data[2])} **Exp**")
                embed.add_field(name="Crafting - ", value='\n'.join(entries), inline=False)
                leaderboard_embeds.append(embed)

        elif board_type == 'Pet':
            pet_per_page: int = 5

            # Name "nickname", user, pet CP, rarity, rank
            init_users_data: list[tuple[str, str, int, int, str, int, int]] = await Pet.filter(main=1).values_list("pet__name", "nickname", "user__user_id", "p_cp", "pet__rarity", "p_major", "p_minor")

            users_data: list[tuple[int, str, str, int, int, str, int, int]] = []
            for user_data in init_users_data:
                user_id: int = user_data[2]
                true_pet_cp = await compute_pet_cp(user_id)
                users_data.append((true_pet_cp, user_data[0], user_data[1], user_data[2], user_data[3], user_data[4], user_data[5], user_data[6]))

            users_data.sort(key=lambda tup: tup[0], reverse=True)

            num_entries = len(users_data)
            num_pages = math.ceil(num_entries / pet_per_page)

            for page_idx in range(num_pages):
                embed = disnake.Embed(title="Pet Ranking", color=disnake.Color(0x2e3135), timestamp=datetime.now())
                embed.set_thumbnail(url=inter.guild.icon.url)
                embed.description = f"Top **5**" if page_idx == 0 else f"Rank #{page_idx * pet_per_page + 1}-{min(num_entries, (page_idx + 1) * n)}"
                entries = []
                for i in range(page_idx * pet_per_page, ((page_idx + 1) * pet_per_page)):
                    if i >= num_entries:
                        break
                    cp, pname, nickname, owner, _, rarity, major, minor = users_data[i]
                    nickname_str = "" if nickname == pname else f' **"{nickname}"**'
                    rank_str = BeastCultivationStage(int(major), int(minor), rarity).name
                    entry_str = f'**#{i + 1}**{nickname_str} {pname} <@{owner}>\n{rarity.capitalize()} {rank_str} | `{format_num_abbr1(cp)}` **CP**'
                    entries.append(entry_str)
                embed.add_field(name="Pet - ", value='\n'.join(entries), inline=False)
                leaderboard_embeds.append(embed)

        await inter.edit_original_message(embed=leaderboard_embeds[0], view=LeaderboardView(leaderboard_embeds, inter.author))


class LeaderboardView(disnake.ui.View):
    def __init__(self, leaderboard_embeds, author):
        super().__init__(timeout=None)
        self.leaderboard_embeds = leaderboard_embeds
        self.embeds = leaderboard_embeds
        self.embed_count = 0  # Page index
        self.author = author

        self.prev_page.disabled = True
        if len(self.embeds) <= 1:
            self.next_page.disabled = True

        for i, embed in enumerate(self.leaderboard_embeds):
            embed.set_footer(text=f"Page {i + 1} of {len(self.leaderboard_embeds)}")

    async def interaction_check(self, inter):
        return inter.author == self.author

    @disnake.ui.button(emoji=LEFT, style=disnake.ButtonStyle.secondary)
    async def prev_page(self, _: disnake.ui.Button, interaction: disnake.MessageInteraction):
        self.embed_count -= 1

        embed = self.embeds[self.embed_count]

        self.next_page.disabled = False
        if self.embed_count == 0:
            self.prev_page.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

    @disnake.ui.button(emoji=RIGHT, style=disnake.ButtonStyle.secondary)
    async def next_page(self, _: disnake.ui.Button, interaction: disnake.MessageInteraction):
        self.embed_count += 1
        embed = self.embeds[self.embed_count]

        self.prev_page.disabled = False
        if self.embed_count == len(self.embeds) - 1:
            self.next_page.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)


def _compute_gold_balance_entry(player: Player, ah: AuctionHouse) -> tuple[int, int]:
    gold: int = player.current_gold
    escrow: int = ah.get_escrow(player.id)
    return player.id, gold + escrow


def setup(bot):
    bot.add_cog(Exp(bot))
    print("[Exp] Loaded")

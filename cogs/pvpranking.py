import asyncio
import math
import random
from datetime import datetime

import disnake
from disnake.ext import commands

from character.player import PlayerRoster, Player
from utils import DatabaseUtils
from utils import ParamsUtils
from utils.Database import Users, Pvp
from utils.Embeds import BasicEmbeds
from utils.ParamsUtils import ELO_RANKS, ELO_SUB_RANKS, SUB_RANK_POINTS, MAX_EXCESS_POINTS, MAX_POINTS
from utils.ParamsUtils import elo_from_rank_points
from utils.Styles import BASIC_EMOJIS, LEFT, RIGHT

WIN_POINTS = 18  # Number of points gained upon win
WIN_POINTS_DICT = {"Unranked": 18, "Huang": 18, "Xuan": 16, "Di": 14, "Tian": 12}
LOSS_POINTS = 12  # Number of points lost upon loss (POSITIVE NUMBER!!)
LOSS_POINTS_DICT = {"Unranked": 12, "Huang": 12, "Xuan": 14, "Di": 16, "Tian": 18}
PROMOTION_FAIL_PENALTY = 25
DEMOTION_PENALTY = 25


# Returns whether the opponent is valid given rank points
def is_potential_opponent(rank_points, opponent_rank_points):
    # Special case: unranked can match with unranked or the lowest sub-rank
    if opponent_rank_points is None:
        return False

    if rank_points == 0:
        return opponent_rank_points <= (1 * SUB_RANK_POINTS)

    sub_rank = (rank_points - 1) // SUB_RANK_POINTS
    opponent_sub_rank = (opponent_rank_points - 1) // SUB_RANK_POINTS
    opponent_excess_points = (opponent_rank_points - 1) % SUB_RANK_POINTS

    opponent_is_unranked = False  # TODO (opponent_rank_points == 0)
    within_one_sub_rank = (sub_rank - 1) <= opponent_sub_rank <= (sub_rank + 1)
    opponent_frozen = (opponent_excess_points == MAX_EXCESS_POINTS) and (opponent_sub_rank == ELO_SUB_RANKS[-1])

    return within_one_sub_rank and not opponent_frozen and not opponent_is_unranked


# Returns True if highest rank
def is_highest_rank(elo_rank, elo_sub_rank):
    return elo_rank == ELO_RANKS[-1] and elo_sub_rank == ELO_SUB_RANKS[-1]


# Returns True if total rank points indicate that player is in promos
# which should be the case when they are at highest sub-rank with MAX_EXCESS_POINTS
# but are not at the highest rank
def in_promos(elo_rank, elo_sub_rank, excess_points):
    return excess_points == MAX_EXCESS_POINTS and elo_sub_rank == ELO_SUB_RANKS[-1] and elo_rank != ELO_RANKS[-1]


# Returns formatted string representing promo status
# where win_status is True if player just won the match
def get_promo_emoji_string(promo_num, win_status):
    edict = {1: BASIC_EMOJIS['tick'], -1: BASIC_EMOJIS['cross'], 0: BASIC_EMOJIS['minus']}

    if promo_num == 2:
        e1, e2, e3 = [-1, 1, 0] if win_status else [1, -1, 0]
    else:
        num_promos_dict = {0: [0, 0, 0], 3: [1, 0, 0], -1: [-1, 0, 0], 6: [1, 1, 0], -2: [-1, -1, 0], 5: [1, -1, 1], 1: [1, -1, -1]}
        e1, e2, e3 = num_promos_dict[promo_num]

    if promo_num in [5, 1]:
        return f"({edict[e1]} / {edict[e2]}) | {edict[e3]}"
    else:
        return f"{edict[e1]} | {edict[e2]} | {edict[e3]}"


# Win probability of player1 against player2
def calculate_chance(cp1, cp2):
    cp1 = ParamsUtils.display_to_internal_cp(cp1)
    cp2 = ParamsUtils.display_to_internal_cp(cp2)

    return cp1 / (cp1 + cp2)


class PvpRanking(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    # @commands.default_member_permissions(manage_messages=True)
    @commands.slash_command()
    async def ranked(self, ctx):
        """
        Parent Command
        """
        pass

    @ranked.sub_command(name="match", description="Play Ranked matches against other players")
    async def match(self, ctx: disnake.CommandInteraction):
        outcome = 'random'
        all_users = await Users.all().prefetch_related("cultivation", "alchemy").values("pill_used", "cultivation__user_id", "cultivation__major", "cultivation__minor",
                                                                                        "pvp__rank_points", "pvp__pvp_promo", "pvp__pvp_demote", "pvp__rank_points_before_promo", "pvp__pvp_cooldown")

        # Represents potential opponents
        allowed_users = [user for user in all_users if user["cultivation__major"] >= 1]

        outcome_str = ""
        host = None
        for user in all_users:
            if user["cultivation__user_id"] == ctx.author.id:  # You are allowed to play
                host = user
                allowed_users.remove(user)  # Can't play against yourself

        if host is not None:
            await ctx.response.defer()

            pvp_cooldown = host["pvp__pvp_cooldown"]
            if pvp_cooldown < 5:
                pvp_cooldown += 1
            elif pvp_cooldown < 10:
                pvp_cooldown += 1
                async with PlayerRoster().get(ctx.author.id) as player:
                    energy_check = player.consume_energy(36)

                if energy_check is False:
                    await ctx.edit_original_message("You don't have enough energy to participate")
                    return
            else:
                await ctx.edit_original_message("You have run out of PVP chances, come back tomorrow for more!")
                return

            await Pvp.filter(user_id=ctx.author.id).update(pvp_cooldown=pvp_cooldown)

            # Promo match number
            # How this works: 0 means not in promos
            # +3 for each win, -1 for each loss
            # Illustrating cases:
            # WW-: 3,6 points    | promote after second match
            # WLW: 3,2,5 points  | promote after third match
            # WLL: 3,2,1 point   | fail third match
            # LWW: -1,2,5 points | promote after third match
            # LWL: -1,2,1 point  | fail third match
            # LL-: -1,-2 points  | fail second match
            # Basically, as soon as you reach >= 5 points, promote
            # and as soon as you reach 1 or -2 points, fail
            # After promoting or failing, promo match number resets to 0
            # Promos begin when you rank points are max within your elo sub-rank
            promo_num = host["pvp__pvp_promo"]

            # Get your own elo information
            elo_rank, elo_sub_rank, excess_points = elo_from_rank_points(host["pvp__rank_points"])

            # Pick an opponent (+/-1 sub-rank)
            # Also, opponent excess points cannot be at MAX_EXCESS_POINTS
            # (Otherwise they would be passively entering promos)
            # good_users = [user for user in allowed_users if ((user[3] % SUB_RANK_POINTS) < MAX_EXCESS_POINTS)]
            good_users = [user for user in allowed_users if is_potential_opponent(host["pvp__rank_points"], user["pvp__rank_points"])]

            if len(good_users) == 0:  # No potential opponents

                await ctx.edit_original_message(content=f'''No potential opponents found!''')

            else:  # Play a ranked match
                opponent = random.choice(good_users)

                # Get opponent elo information
                opponent_elo_rank, opponent_elo_sub_rank, opponent_excess_points = elo_from_rank_points(opponent["pvp__rank_points"])

                # Get CP information
                roster: PlayerRoster = PlayerRoster()
                opponent_player: Player = roster[opponent["cultivation__user_id"]]
                host_player: Player = roster[host["cultivation__user_id"]]

                opponent_cp = await opponent_player.compute_total_cp()
                host_cp = await host_player.compute_total_cp()

                _, _, battle_boost, _ = await DatabaseUtils.compute_pill_bonus(ctx.author.id, battle=1)
                host_cp = host_cp * (1 + battle_boost / 100)
                # Determine winner
                win_chance = round(calculate_chance(host_cp, opponent_cp) * 100)

                # Temporary for testing purposes TODO
                if outcome == 'win':
                    winner = host
                    loser = opponent
                elif outcome == 'lose':
                    winner = opponent
                    loser = host
                else:
                    if random.randint(1, 100) <= win_chance:
                        winner = host
                        loser = opponent
                    else:
                        winner = opponent
                        loser = host

                # No promo emoji string by default
                promo_emoji_string = ''

                # Update rank points and promo info FOR YOURSELF
                if host == winner:  # You won

                    if not in_promos(elo_rank, elo_sub_rank, excess_points):  # Not a promo match

                        if excess_points + WIN_POINTS_DICT[elo_rank] >= MAX_EXCESS_POINTS and in_promos(elo_rank, elo_sub_rank, MAX_EXCESS_POINTS):  # Ready to promote

                            winner_rank_points = winner["pvp__rank_points"] + (MAX_EXCESS_POINTS - excess_points)
                            await Pvp.filter(user_id=winner["cultivation__user_id"]).update(rank_points=winner_rank_points, rank_points_before_promo=winner["pvp__rank_points"])
                            outcome_str = f"You have reached max points within your sub-rank and will begin promos."

                        else:  # Not promoting

                            winner_rank_points = MAX_POINTS if (winner["pvp__rank_points"] + WIN_POINTS_DICT[elo_rank]) > MAX_POINTS else (winner["pvp__rank_points"] + WIN_POINTS_DICT[elo_rank])
                            await Pvp.filter(user_id=winner["cultivation__user_id"]).update(rank_points=winner_rank_points, pvp_demote=0)  # If you won, no longer in danger of imminent demotion
                            outcome_str = f"You gained `{WIN_POINTS_DICT[elo_rank]}` rank points."

                    elif (promo_num + 3) >= 5:  # Won a promo match and successfully promote

                        ranked_points_before_promo = winner["pvp__rank_points_before_promo"]
                        winner_rank_points = ranked_points_before_promo + WIN_POINTS_DICT[elo_rank]
                        await Pvp.filter(user_id=winner["cultivation__user_id"]).update(rank_points=winner_rank_points, pvp_promo=0)  # Promo num resets to zero
                        new_elo_rank, new_elo_sub_rank, _ = elo_from_rank_points(winner_rank_points)
                        outcome_str = f"You have successfully promoted to {new_elo_sub_rank} {new_elo_rank}."
                        promo_emoji_string = '\n' + get_promo_emoji_string(promo_num + 3, True)

                    elif excess_points == MAX_EXCESS_POINTS:  # Won a promo match but still in promos
                        await Pvp.filter(user_id=winner["cultivation__user_id"]).update(pvp_promo=(promo_num + 3))  # Promo num increases by 3
                        outcome_str = f"You won a promo match but are still in promos."
                        promo_emoji_string = '\n' + get_promo_emoji_string(promo_num + 3, True)

                    else:
                        print("This should not be printed :')")

                elif host == loser:  # You lost

                    if promo_num == 0 and excess_points != MAX_EXCESS_POINTS:  # Not a promo match

                        if loser["pvp__pvp_demote"] == 1:  # Demotion (drop a sub-rank and set excess to 75)

                            loser_rank_points = ((loser["pvp__rank_points"] // SUB_RANK_POINTS) * SUB_RANK_POINTS) - DEMOTION_PENALTY
                            await Pvp.filter(user_id=loser["cultivation__user_id"]).update(rank_points=loser_rank_points, pvp_demote=0)  # Set pvp_demote to 0
                            new_elo_rank, new_elo_sub_rank, _ = elo_from_rank_points(loser_rank_points)
                            outcome_str = f"You have demoted to {new_elo_sub_rank} {new_elo_rank}."

                        elif loser["pvp__pvp_demote"] == 0 and (excess_points - LOSS_POINTS_DICT[elo_rank]) < 0 and not (loser["pvp__rank_points"] - LOSS_POINTS_DICT[elo_rank]) < 0:  # About to demote but get one more chance

                            loser_rank_points = ((loser["pvp__rank_points"] // SUB_RANK_POINTS) * SUB_RANK_POINTS) + 1  # Set excess to 0
                            await Pvp.filter(user_id=loser["cultivation__user_id"]).update(rank_points=loser_rank_points, pvp_demote=1)  # Set pvp_demote to 1
                            outcome_str = f"You are about to demote if you lose the next match."

                        else:  # No demotion (either because have enough excess points, or in the lowest rank already)

                            loser_rank_points = 1 if (loser["pvp__rank_points"] - LOSS_POINTS_DICT[elo_rank]) < 1 else (loser["pvp__rank_points"] - LOSS_POINTS_DICT[elo_rank])
                            await Pvp.filter(user_id=loser["cultivation__user_id"]).update(rank_points=loser_rank_points)
                            outcome_str = f"You are now at the bottom of the lowest rank." if (excess_points - LOSS_POINTS_DICT[elo_rank]) < 0 else f"You lost `{LOSS_POINTS_DICT[elo_rank]}` rank points."

                    elif (promo_num - 1) in [1, -2]:  # Lost a promo match and fail promos

                        loser_rank_points = loser["pvp__rank_points"] - PROMOTION_FAIL_PENALTY
                        await Pvp.filter(user_id=loser["cultivation__user_id"]).update(rank_points=loser_rank_points, pvp_promo=0)  # Promo num reset to 0
                        outcome_str = f"You have failed promos and lost `{PROMOTION_FAIL_PENALTY}` rank points."
                        promo_emoji_string = '\n' + get_promo_emoji_string(promo_num - 1, False)

                    else:  # Lost a promo match but still in promos
                        await Pvp.filter(user_id=loser["cultivation__user_id"]).update(pvp_promo=(promo_num - 1))  # Promo num decreases by 1
                        outcome_str = f"You lost a promo match but are still in promos."
                        promo_emoji_string = '\n' + get_promo_emoji_string(promo_num - 1, False)

                # Update rank points FOR OPPONENT
                # Note that for now, an opponent can never start a promo match passively
                # That is, if an opponent reaches max points within High sub-rank,
                # they can no longer be challenged by anyone and so their rank will not change
                # until they initiate promos themselves.
                # Also, opponents cannot be demoted through MAJOR ranks.

                if opponent["pvp__pvp_promo"] == 0:  # Opponent is not in promos
                    if opponent == winner:
                        if opponent_excess_points + WIN_POINTS_DICT[opponent_elo_rank] >= MAX_EXCESS_POINTS and opponent_elo_sub_rank == ELO_SUB_RANKS[-1]:  # Highest or would be starting promos
                            winner_rank_points = winner["pvp__rank_points"] + (MAX_EXCESS_POINTS - opponent_excess_points)
                            await Pvp.filter(user_id=winner["cultivation__user_id"]).update(rank_points=winner_rank_points, rank_points_before_promo=winner["pvp__rank_points"])
                        else:  # Not promoting
                            winner_rank_points = MAX_POINTS if (winner["pvp__rank_points"] + WIN_POINTS_DICT[opponent_elo_rank]) > MAX_POINTS else (winner["pvp__rank_points"] + WIN_POINTS_DICT[opponent_elo_rank])  # Redundant with above
                            await Pvp.filter(user_id=winner["cultivation__user_id"]).update(rank_points=winner_rank_points, pvp_demote=0)
                    elif opponent == loser:
                        if loser["pvp__pvp_demote"] == 1:  # Demotion (drop a sub-rank and set excess to 75)
                            loser_rank_points = ((loser["pvp__rank_points"] // SUB_RANK_POINTS) * SUB_RANK_POINTS) - DEMOTION_PENALTY
                            await Pvp.filter(user_id=loser["cultivation__user_id"]).update(rank_points=loser_rank_points, pvp_demote=0)  # Set pvp_demote to 0
                        elif loser["pvp__pvp_demote"] == 0 and (opponent_excess_points - LOSS_POINTS_DICT[opponent_elo_rank]) < 0:  # Potentially about to demote
                            if opponent_elo_sub_rank == ELO_SUB_RANKS[0] or (loser["pvp__rank_points"] - LOSS_POINTS_DICT[opponent_elo_rank]) <= 0:
                                # Lowest sub-rank, opponent can't drop a major rank (also weird case where unranked player loses as opponent)
                                loser_rank_points = ((loser["pvp__rank_points"] // SUB_RANK_POINTS) * SUB_RANK_POINTS) + 1  # Set excess to 0
                                await Pvp.filter(user_id=loser["cultivation__user_id"]).update(rank_points=loser_rank_points, pvp_demote=0)  # Set pvp_demote to 0 (don't demote)
                            else:  # About to demote
                                loser_rank_points = ((loser["pvp__rank_points"] // SUB_RANK_POINTS) * SUB_RANK_POINTS) + 1  # Set excess to 0
                                await Pvp.filter(user_id=loser["cultivation__user_id"]).update(rank_points=loser_rank_points, pvp_demote=1)  # Set pvp_demote to 1
                        else:  # No demotion (because have enough excess points)
                            loser_rank_points = 1 if (loser["pvp__rank_points"] - LOSS_POINTS_DICT[opponent_elo_rank]) < 1 else (loser["pvp__rank_points"] - LOSS_POINTS_DICT[opponent_elo_rank])
                            await Pvp.filter(user_id=loser["cultivation__user_id"]).update(rank_points=loser_rank_points)

                # Report results
                opponent_dcp = ParamsUtils.format_num_abbr0(opponent_cp)
                host_dcp = ParamsUtils.format_num_abbr0(host_cp)

                await asyncio.sleep(0.5)
                await ctx.edit_original_message(content=f'''{ctx.author.mention} : `{host_dcp}` CP {BASIC_EMOJIS['vs']} <@{opponent["cultivation__user_id"]}> : `{opponent_dcp}` CP

{ctx.author.mention}'s rank: {elo_sub_rank} {elo_rank} `{excess_points + 1}`/`{SUB_RANK_POINTS}`
<@{opponent["cultivation__user_id"]}>'s rank: {opponent_elo_sub_rank} {opponent_elo_rank} `{opponent_excess_points + 1}`/`{SUB_RANK_POINTS}`

**Winner :** <@{winner["cultivation__user_id"]}>

{outcome_str}{promo_emoji_string}

`{win_chance}`% for {ctx.author.mention} to win
`{100 - win_chance}`% for <@{opponent["cultivation__user_id"]}> to win''')
        else:
            embed = BasicEmbeds.exclamation("Reach **Fight Practitioner** to play ranked matches")
            await ctx.response.send_message(embed=embed, ephemeral=True)

    @ranked.sub_command()
    async def top(self, ctx):
        """
        Show the top 10 Rankers
        """
        leaderboard_embeds = []

        users_data = await Pvp.filter(rank_points__gt=1).order_by("-rank_points").values_list("user_id", "rank_points")
        n = 10
        num_entries = len(users_data)
        num_pages = math.ceil(num_entries / n)

        for page_idx in range(num_pages):
            embed = disnake.Embed(
                description=f"Ranked Leaderboard",
                color=disnake.Color(0x2e3135),
                timestamp=datetime.now()
            )
            embed.set_thumbnail(url=ctx.guild.icon.url)
            embed.description = f"Top **10**" if page_idx == 0 else f"Rank #{page_idx * n + 1}-{min(num_entries, (page_idx + 1) * n)}"
            entries = []
            for i in range(page_idx * n, ((page_idx + 1) * n)):
                if i >= num_entries:
                    break
                user_id, rank_points = users_data[i]
                elo_rank, elo_sub_rank, excess_points = elo_from_rank_points(rank_points)
                if elo_rank == "Unranked":
                    continue
                entries.append(f"**#{i + 1}** <@{user_id}> | {elo_sub_rank} {elo_rank} `{excess_points + 1}P`")

            if len(entries) == 0:  # All unranked
                entries = ["*Nobody is ranked yet!*"]

            embed.add_field(name="Points - ", value='\n'.join(entries), inline=False)
            leaderboard_embeds.append(embed)

        await ctx.response.send_message(embed=leaderboard_embeds[0], view=LeaderboardView(leaderboard_embeds, ctx.author))

    @ranked.sub_command()
    async def profile(self, ctx, member: disnake.Member = None):
        """
        Check your own elo (prototype for ranked card)
        """
        if member is None:
            member = ctx.author

        user_data = await Pvp.get_or_none(user_id=member.id).values_list("rank_points", "pvp_promo", "pvp_demote", "pvp_coins")
        rank_points, promo_num, demote_status, pvp_coins = user_data  # Shouldn't be None...

        elo_rank, elo_sub_rank, excess_points = elo_from_rank_points(rank_points)

        if demote_status == 1:
            status_str = "\n" + "*You are about to demote if you lose the next match.*"
        elif is_highest_rank(elo_rank, elo_sub_rank) or (promo_num == 0 and excess_points != MAX_EXCESS_POINTS):
            status_str = ""
        elif promo_num == 0 and excess_points == MAX_EXCESS_POINTS:
            status_str = "\n" + "*Your next match will be your first promo match (BO3).*"
        elif promo_num in [3, -1]:
            status_str = "\n" + "*Your next match will be your second promo match (BO3).*"
        else:  # sus
            status_str = "\n" + "*Your next match will be your third promo match (BO3).*"

        embed = disnake.Embed(
            title="Ranked Profile",
            description=f'''**Username** : {member.name}
**PVP Rank** : {elo_sub_rank} {elo_rank}
`{excess_points + 1}`/`{SUB_RANK_POINTS}` within this sub-rank
**Total Ranked Points** : `{rank_points}`{status_str}
**Arena Coins** : `{pvp_coins:,}`''',
            color=disnake.Color(0x2e3135)
        )
        if member.avatar:
            embed.set_thumbnail(url=member.avatar.url)

        await ctx.response.send_message(embed=embed)


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


def setup(bot):
    bot.add_cog(PvpRanking(bot))
    print("[PvpRanking] Loaded")

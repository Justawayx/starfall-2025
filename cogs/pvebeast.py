import asyncio
import random
from collections import defaultdict
from datetime import timedelta, datetime, time as dt
from time import time
from typing import Any, Optional

import disnake
from disnake.ext import commands, tasks
from tortoise.expressions import F

from utils.loot import merge_loot
from world.bestiary import Bestiary, BeastDefinition, autocomplete_beast_name, AFFINITIES, AFFINITY_BLOOD, AFFINITY_DARK, AFFINITY_DRAGON, AFFINITY_EARTH, AFFINITY_FIRE, AFFINITY_ICE, AFFINITY_LIGHTNING, AFFINITY_MYSTERIOUS, AFFINITY_POISON, \
    AFFINITY_ROCK, AFFINITY_WATER, AFFINITY_WIND, AFFINITY_WOOD, compute_affinity_str, BEAST_FLAME_DROP
from world.continent import Continent
from world.compendium import ItemCompendium, ItemDefinition, PetAmplifierDefinition
from character.player import PlayerRoster, Player, compute_user_exp_bonus
from utils import DatabaseUtils
from utils import ParamsUtils
from utils.CommandUtils import drop_origin_qi, VoteLinkButton, PatreonLinkButton
from utils.Database import AllBeasts, Beast, AllItems, Cultivation, Pet
from utils.Embeds import BasicEmbeds
from utils.EnergySystem import show_energy
from utils.ExpSystem import calculate_hunt_exp
from utils.InventoryUtils import add_to_inventory, check_inv_weight, check_item_in_inv, get_equipped_ring_id, remove_from_inventory, ITEM_TYPE_BEAST_FLAME
from utils.LoggingUtils import log_event
from utils.Styles import MINUS, EXCLAMATION, CROSS, TICK, PLUS
from utils.base import BaseStarfallCog
from world.cultivation import PlayerCultivationStage
from cogs.eventshop import EVENT_CONFIG, EVENT_SHOP, EVENT_MANAGER

RAID_BEAST_SPAWN_TIMES = [dt(11, 0, 0, 0), dt(23, 0, 0, 0)]

BEAST_SPAWN_TIME = {
    7: {"min": 40, "max": 50},
}

BEAST_REGIONS = {
    "Continental Plains": {"type": AFFINITIES, "pass": None},
    "Magma Fields": {"type": [AFFINITY_FIRE], "pass": "inferno_rune"},
    "Underwater Canyons": {"type": [AFFINITY_WATER], "pass": "oceanic_rune"},
    "Mountain Ranges": {"type": [AFFINITY_EARTH, AFFINITY_ROCK], "pass": "earth_rune"},
    "Forest Glades": {"type": [AFFINITY_EARTH, AFFINITY_WOOD], "pass": "earth_rune"},
    "Thunderstorm Valleys": {"type": [AFFINITY_LIGHTNING, AFFINITY_WIND], "pass": "tempest_rune"},
    "Shadow Swamps": {"type": [AFFINITY_DARK, AFFINITY_BLOOD], "pass": "abyss_rune"},
    "Enchanted Grotto": {"type": [AFFINITY_DRAGON, AFFINITY_MYSTERIOUS], "pass": "mythical_rune"},
    "Tainted Marshes": {"type": [AFFINITY_POISON], "pass": "noxious_rune"},
    "Frozen Tundra": {"type": [AFFINITY_ICE], "pass": "glacier_rune"}
}

SOLO_HUNT_ENERGY_COST: int = 12
SOLO_HUNT_COUNT_CHOICES: list[int] = [1, 5, 10, 15, 25]


# Returns probability that a player with Fight class ID major successfully encounters a beast using /hunt
def get_hunt_encounter_rate(major):
    return 100 if major >= 10 else 50 + 5 * major


HUNT_FAIL_STRINGS = ["You did not encounter any beasts.",
                     "You ran around the mountain three times but didn't find anything. Better luck next time!",
                     "You fell into a ravine and spent so much time getting out it was too late in the day to hunt beasts.",
                     "You heard some rustling noises but it turned out to be some random girl picking herbs. No beasts to be found.",
                     "You saw a beast run by you but then it suddenly disappeared. Who knows what happened.",
                     "You laid some traps but they were all broken for some reason.",
                     "You encountered a beast but it was above your level, so you could only run away."]


def beast_list_to_rank_dict(beasts: list[BeastDefinition]):
    beast_rank_dict: dict[int, list[BeastDefinition]] = {}
    for beast in beasts:
        if beast.rank not in beast_rank_dict:
            beast_rank_dict[beast.rank] = []

        beast_rank_dict[beast.rank].append(beast)

    return beast_rank_dict


def get_better_beast_rate(beast_dict: dict[int, list[BeastDefinition]]) -> BeastDefinition:
    rank = random.choice(list(beast_dict.keys()))
    return random.choice(beast_dict[rank])


async def calculate_exp_given(attackers: dict[str, list[int]], total_exp: int, give_exp: bool = True) -> dict[int, int]:
    rewards: dict[int, int] = {}
    total_damage: int = sum([sum(dmg_list) for dmg_list in attackers.values()])
    for user_id_str, dmg in attackers.items():
        user_id: int = int(user_id_str)
        user_dmg: int = sum(dmg)
        exp_given: int = max(user_dmg * total_exp // total_damage, 1)
        if give_exp:
            async with PlayerRoster().get(user_id) as player:
                final_exp, _ = await player.add_experience(exp_given)
        else:
            exp_bonus = await compute_user_exp_bonus(user_id)
            final_exp: int = exp_given + exp_given * exp_bonus // 100

        rewards[user_id] = final_exp

    return rewards


async def spawn_raid_beast(bot: commands.Bot, ch_id: int, beast: BeastDefinition) -> bool:
    ch = bot.get_channel(int(ch_id))

    beast = beast.as_raid()

    des_str = f"**Rank: `{beast.rank}`** \n**Affinity: `{compute_affinity_str(beast.affinities)}`** \n**Total EXP given: `{beast.exp_value:,}`**"
    if beast.name in BEAST_FLAME_DROP:
        _, drop_chance = BEAST_FLAME_DROP[beast.name]
        des_str = des_str + f"\n**Drop rate** (*Flame*) **: `{drop_chance}`% **"

    embed = disnake.Embed(title=f"{beast.name}", description=des_str, color=disnake.Color(0xdcfe7c))
    embed.set_footer(text="Press 'Attack' below to damage the beast")

    file = beast.image
    if file:
        embed.set_image(file=file)

    view = MagicBeastView()
    msg = await ch.send(embed=embed, view=view)

    await Beast.create(beast_id=beast.name, beast_type="raid", msg_id=msg.id, current_health=beast.health, total_health=beast.health, till=(datetime.now() + timedelta(hours=6)))

    log_event(f"CH {ch_id}", "beast", f"Spawned {beast.name}")

    return True


async def slain_raid_beast(msg: disnake.Message):
    boss_data = await Beast.get_or_none(msg_id=msg.id).values_list("beast_id", "attackers")
    beast_name, attackers = boss_data
    beast: BeastDefinition = Bestiary().get(beast_name).as_raid()

    top_attackers: list[str] = sorted(attackers, key=lambda k: sum(attackers[k]), reverse=True)

    embed = disnake.Embed(
        title=f"{beast_name} Ran away",
        description=f"**Max Exp: `{beast.exp_value}`**",
        color=disnake.Color(0x2e3135)
    )

    if beast.image:
        embed.set_thumbnail(file=beast.image)

    fields = []
    m: str = "No one attacked"
    if len(top_attackers) > 0:
        damage_list: list[tuple[int, int]] = [(int(user_id), sum(attackers[user_id])) for user_id in top_attackers]
        top3_str: list[str] = [f"**#{n + 1}** <@{data[0]}> | `{data[1]:,}` **Damage** " for n, data in enumerate(damage_list[:3])]
        m = '\n'.join(top3_str)

    fields.append(("Top Damage - ", m))
    for name, value in fields:
        embed.add_field(name=name, value=value, inline=False)

    if len(top_attackers) > 0:
        await calculate_exp_given(attackers, beast.exp_value)
        compendium: ItemCompendium = ItemCompendium()
        loot: dict[str, int] = beast.loot.roll()
        mat_list: list[tuple[int, str]] = []
        b_flame_given_to: Optional[int] = None

        # Add event token drops for each participant
        for attacker_id in attackers.keys():
            token_text = await add_event_token_drops(int(attacker_id), "beast_drops")
            if token_text:
                embed.add_field(name=f"Event Drop for <@{attacker_id}>", value=token_text)

        # Flame drop, there should be only 1, so force it to 1 in case it's higher from a bug
        flame_drops: list[ItemDefinition] = [compendium[item_id] for item_id in loot.keys() if compendium[item_id].type == ITEM_TYPE_BEAST_FLAME]
        if len(flame_drops) > 0:
            b_flame_id: str = flame_drops[0].id
            b_flame_given_to: int = int(random.choice(list(attackers.keys())))
            await add_to_inventory(b_flame_given_to, b_flame_id, 1)
            embed.add_field(name="Flame Dropped", value=f"> <@{b_flame_given_to}> got {b_flame_id}")
            log_event(f"CH {msg.id}", "beast", f"Given {b_flame_id} to {b_flame_given_to}")

        # Amplifier drop, there should be only 1, so force it to 1 in case it's higher from a bug
        amplifier_drops: list[ItemDefinition] = [compendium[item_id] for item_id in loot.keys() if isinstance(compendium[item_id], PetAmplifierDefinition)]
        if len(amplifier_drops) > 0:
            amplifier_id: str = amplifier_drops[0].id
            amplifier_given_to: int = int(random.choice(list(attackers.keys())))
            mat_list: list[tuple[int, str]] = [(amplifier_given_to, amplifier_drops[0].name)]
            await add_to_inventory(amplifier_given_to, amplifier_id, 1)
            embed.add_field(name="Pet Amp Dropped", value=f"> <@{amplifier_given_to}> got {amplifier_id}")
            log_event(f"CH {msg.id}", "beast", f"Given pet amp {mat_list}")

        await Beast.filter(msg_id=msg.id).update(mat_drops=mat_list, bflame_drop=b_flame_given_to)

    await msg.edit(embed=embed, view=SlainRewardView())

    log_event(f"CH {msg.id}", "beast", f"Slain {beast_name}")


class HealthButton(disnake.ui.Button):
    def __init__(self, label):
        super().__init__(label=str(label), style=disnake.ButtonStyle.grey, disabled=True, emoji="<:Beast_Hp:987586629399109742>", custom_id="beast_health_button")


class MagicBeastView(disnake.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @disnake.ui.button(label="Attack", style=disnake.ButtonStyle.green, custom_id="beast_attack_button")
    async def attack_beast(self, _: disnake.ui.Button, inter: disnake.MessageInteraction):

        boss_data = await Beast.get_or_none(msg_id=inter.message.id).values_list("attackers", flat=True)

        attackers_dict: dict[str, Any] = boss_data

        author_id = str(inter.author.id)

        player_dmg_list = attackers_dict.get(author_id)
        if player_dmg_list is None:
            attackers_dict[author_id] = []

        user_damage_data = attackers_dict[author_id]
        if len(user_damage_data) < 3:
            pass
        elif len(user_damage_data) < 6:
            async with PlayerRoster().get(inter.author.id) as player:
                energy_check = player.consume_energy(36)

            if not energy_check:
                await inter.response.send_message("You dont have enough energy to participate", ephemeral=True)
                return
        else:
            await inter.response.send_message(content="**You have run out of attacks**", ephemeral=True)
            return

        player: Player = PlayerRoster().get(inter.author.id)
        display_cp = await player.compute_total_cp()

        _, _, battle_boost, _ = await DatabaseUtils.compute_pill_bonus(inter.author.id, battle=1)
        display_cp = display_cp * (1 + battle_boost / 100)

        internal_cp = ParamsUtils.display_to_internal_cp(display_cp)
        player_damage = round(ParamsUtils.internal_cp_to_attack(internal_cp))
        display_damage = ParamsUtils.format_num_abbr0(player_damage)

        attackers_dict[author_id].append(player_damage)

        await Beast.filter(msg_id=inter.message.id).update(current_health=F("current_health") - player_damage, attackers=attackers_dict)
        await inter.response.send_message(f"You have dealt **`{display_damage}`** Damage", ephemeral=True)


class SlainRewardView(disnake.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @disnake.ui.button(label="Check Rewards", emoji="🎁", style=disnake.ButtonStyle.blurple, custom_id="raid_beast_rewards")
    async def reward_button(self, _: disnake.ui.Button, inter: disnake.MessageInteraction):
        boss_data = await Beast.get_or_none(msg_id=inter.message.id).values_list("beast_id", "beast__exp_given", "attackers", "beast__drop_rate", "beast__rank", "beast_type", "bflame_drop", "mat_drops")

        embed = BasicEmbeds.wrong_cross("Failed to retrieve beast info. Report this to `Classified154#0008`")
        if boss_data:
            beast_name, exp_given, attackers, drop_rate, rank, beast_type, bflame, mat_drops = boss_data
            if beast_type is None:
                beast_type = "raid"

            if beast_type == "raid":
                exp_given *= 5

            user_id: int = inter.author.id
            awarded_exp: dict[int, int] = await calculate_exp_given(attackers, exp_given, False)

            if user_id in awarded_exp:
                embed.title = "Your Rewards!"
                embed.description = f"**Exp Given : `{awarded_exp[user_id]:,}`**"
                loot = ""
                # Beast Flame Check
                if bflame is not None:
                    if int(bflame) == user_id:
                        loot += f"1x Rank {rank} Beast Flame\n"

                for mat_user_id, drop in mat_drops:
                    if int(mat_user_id) == user_id:
                        loot += f"1x {drop}\n"

                if len(loot) > 0:
                    embed.description += f"\n\n**{PLUS} Loot :**"
                    embed.description += f"\n```{loot}```"
            else:
                embed = BasicEmbeds.exclamation("You didn't contributed in slaying this beast")

        await inter.response.send_message(embed=embed, ephemeral=True)


async def spawn_solo_hunt(inter: disnake.MessageInteraction, hunt_count: int, region: str, beast_data: list[BeastDefinition], major: int):
    content = []
    beasts: list[BeastDefinition] = []
    await drop_origin_qi(inter.guild, inter.author.id)
    ring_id = await get_equipped_ring_id(inter.author.id)

    continue_check, _, _ = await check_inv_weight(inter.channel, inter.author.id, "meat_1", 25 * hunt_count, ring_id=ring_id,
                                                  confirm_text=f"Make sure you have at least {25 * hunt_count}wt worth of free space in your inventory/ring. You may lose some of the items, Continue?")
    if not continue_check:
        embed = BasicEmbeds.cmd_not_continued()
        await inter.edit_original_message(embed=embed)
        return

    energy_cost = SOLO_HUNT_ENERGY_COST * hunt_count
    _, current_energy = await show_energy(inter.author.id)
    if energy_cost > current_energy >= SOLO_HUNT_ENERGY_COST:
        hunt_count = current_energy // SOLO_HUNT_ENERGY_COST
        energy_cost = hunt_count * SOLO_HUNT_ENERGY_COST
        content.append(f"{EXCLAMATION} You can only do {hunt_count} hunts with your current energy\n")

    async with PlayerRoster().get(inter.author.id) as player:
        energy_check = player.consume_energy(energy_cost)

    if not energy_check:
        await inter.edit_original_message("You don't have enough energy to spawn a beast")
        return

    beast_affinity_filter = BEAST_REGIONS[region]["type"]
    region_rune_requirement = BEAST_REGIONS[region]["pass"]  # ID of rune required to enter desired region

    if region_rune_requirement:
        pass_check = await check_item_in_inv(inter.author.id, region_rune_requirement)
        if pass_check is False:
            await inter.edit_original_message(embed=BasicEmbeds.not_enough_item(region_rune_requirement, "craft"))
            return

        await remove_from_inventory(inter.author.id, region_rune_requirement, ring_id=ring_id)

    log_event(inter.author.id, "beast", f"Started {hunt_count}x hunts in region {region}")

    content.append(f"{EXCLAMATION} Used {energy_cost} energy to do {hunt_count} hunts\n")

    all_beasts: list[BeastDefinition] = [beast for beast in beast_data for b_type in beast_affinity_filter if b_type in beast.affinities]

    if region == 'Continental Plains':  # For default region, only encounter beasts up to your rank
        rank_limit: int = major if major != 9 else major - 1
        all_beasts = [beast for beast in all_beasts if beast.rank <= rank_limit]

    all_beast_dict: dict[int, list[BeastDefinition]] = beast_list_to_rank_dict(all_beasts)

    _, _, battle_boost, beast_lure_details = await DatabaseUtils.compute_pill_bonus(inter.author.id, battle=hunt_count, beast_l_remove=True)
    if beast_lure_details:  # Lure used
        min_rank, max_rank, limit = beast_lure_details[0], beast_lure_details[1], beast_lure_details[2]
        lured_beasts: list[BeastDefinition] = [beast for beast in all_beasts if min_rank <= beast.rank <= max_rank]
        if len(lured_beasts) < 1:
            content.append(f"{EXCLAMATION} You have used the lure pill.. but there weren't enough any Rank {max_rank} to Rank {min_rank} beast to lure, hunting all the beasts instead")
            lured_beasts = all_beasts
        else:
            content.append(f"{EXCLAMATION} You have used a lure pill, hunting beast between {min_rank} - {max_rank} Rank")

        lured_beast_dict: dict[int, list[BeastDefinition]] = beast_list_to_rank_dict(lured_beasts)
        for i in range(hunt_count):
            if limit > 0:
                limit -= 1
                beast: BeastDefinition = get_better_beast_rate(lured_beast_dict)
            else:
                beast: BeastDefinition = get_better_beast_rate(all_beast_dict)

            beasts.append(beast)

    else:  # Lure not used, rune may or not have been used, but it already filtered all_beast_dict if a rune was used
        lured_beasts: list[BeastDefinition] = []
        for i in range(hunt_count):
            beast: BeastDefinition = get_better_beast_rate(all_beast_dict)
            beasts.append(beast)

    player: Player = PlayerRoster().get(inter.author.id)

    display_cp: int = await player.compute_total_cp()
    display_cp = display_cp + display_cp * battle_boost // 100

    internal_cp = ParamsUtils.display_to_internal_cp(display_cp)

    total_beast_exp = 0
    total_dmg_done = 0
    start_time = time()

    pet_rank = await Pet.get_or_none(user_id=inter.author.id, main=1).values_list("pet__rank", flat=True)

    for beast in beasts:
        if beast_lure_details:
            if beast not in lured_beasts:
                l_str = f"{EXCLAMATION} Your lure pill limit reached, hunting all beasts"
                if l_str not in content:
                    content.append(l_str)

        player_damage = round(ParamsUtils.internal_cp_to_attack(internal_cp))
        display_damage = ParamsUtils.format_num_abbr0(player_damage)

        encounter_rate = get_hunt_encounter_rate(major)
        if encounter_rate >= 100 or random.randint(1, 100) <= encounter_rate:  # Fail to encounter beast
            if player_damage >= beast.health:
                content.append(f"{TICK} You have killed **Rank `{beast.rank}` {beast.name}**, dealing **`{display_damage}`** dmg!")
                total_beast_exp += beast.exp_value
                total_dmg_done += player_damage

                loot: dict[str, int] = beast.loot.roll()
                for item_id, item_count in loot.items():
                    continue_check, d_ring_id, _ = await check_inv_weight(None, inter.author.id, item_id, item_count, ring_id=ring_id, confirm_prompt=False)
                    if continue_check is True:
                        await add_to_inventory(inter.author.id, item_id, item_count, d_ring_id)

                if pet_rank is not None:
                    pet_exp_amount = calculate_hunt_exp(pet_rank, beast.rank)
                    bestiary: Bestiary = Bestiary()
                    await bestiary.add_pet_experience(inter.author.id, pet_exp_amount)

                await asyncio.sleep(random.uniform(0.1, 0.2))
                await Beast.create(beast_id=beast.name, beast_type="hunt", msg_id=inter.message.id, current_health=(beast.health - player_damage), total_health=beast.health,
                                   attackers=inter.author.id, mat_drops=loot, mcore_drop=None)
            else:
                content.append(f"{CROSS} You have failed to kill **Rank `{beast.rank}` {beast.name}**")
        else:
            fail_string = random.choice(HUNT_FAIL_STRINGS)
            content.append(f"{MINUS} *{fail_string}*")

    async with PlayerRoster().get(inter.author.id) as player:
        await player.add_experience(total_beast_exp)

    embed = disnake.Embed(
        title=f"{hunt_count}x Beast Hunts in {region}",
        description="\n".join(con for con in content),
        color=disnake.Color(0x2e3135)
    )
    # embed.add_field("Exp Gained", f"You got a total of {total_beast_exp} EXP for this hunt")
    embed.add_field("Damage Done", f"You got dealt a total of {ParamsUtils.format_num_abbr0(total_dmg_done)} dmg in this hunt")
    embed.set_footer(text=f"Took {round(time() - start_time, 1)} seconds. Check your rewards below..")
    view = MassHuntRewardView()
    view.add_item(VoteLinkButton())
    view.add_item(PatreonLinkButton())

    log_event(inter.author.id, "beast", f"Finished beast hunt in {region}")
    await inter.edit_original_message(embed=embed, view=view)


class HuntRegionDropdown(disnake.ui.Select):

    def __init__(self, item_list):
        options = [
            *(disnake.SelectOption(label=name, value=name, description=description, emoji=emoji) for name, description, emoji in item_list),
        ]

        super().__init__(custom_id="region_option", placeholder="Choose the hunt region", max_values=1, options=options)

    async def callback(self, inter):
        self.view.region = inter.values[0]
        await inter.response.edit_message(embed=self.view.update_embed(), view=self.view)


class HuntCountDropdown(disnake.ui.Select):

    def __init__(self, item_list):
        options = [
            *(disnake.SelectOption(label=count, value=count, description=f"{count}x Hunting of beast") for count in item_list),
        ]

        super().__init__(custom_id="number_option", placeholder="Choose the hunt count", max_values=1, options=options)

    async def callback(self, inter):
        self.view.hunt_count = int(inter.values[0])
        await inter.response.edit_message(embed=self.view.update_embed(), view=self.view)


class SoloHuntEmbed(disnake.Embed):
    def __init__(self, region: str, count: int):
        super().__init__(title="Hunt Menu", description=f"Region: **`{region}`** \nNo. of Hunts: **`{count}x Hunt`**", color=disnake.Color(0x2e3135))
        self._region: str = region
        self._count: int = count


class SoloHuntView(disnake.ui.View):
    def __init__(self, author: disnake.User, region_list, beasts: list[BeastDefinition], major: int):
        super().__init__(timeout=None)

        self.author: disnake.User = author
        self.beast_data: list[BeastDefinition] = beasts
        self.major: int = major

        self.region = "Continental Plains"
        self.hunt_count = 1

        self.add_item(HuntRegionDropdown(region_list))
        self.add_item(HuntCountDropdown(SOLO_HUNT_COUNT_CHOICES))

    async def interaction_check(self, inter):
        return inter.author == self.author

    def update_embed(self):
        return SoloHuntEmbed(self.region, self.hunt_count)

    @disnake.ui.button(label="Start Hunt", style=disnake.ButtonStyle.secondary)
    async def start_hunt(self, _: disnake.ui.Button, inter: disnake.MessageInteraction):
        self.clear_items()
        await inter.response.edit_message(embed=BasicEmbeds.exclamation(f"Started your {self.hunt_count}x beast hunts in region {self.region}"), view=self)
        await spawn_solo_hunt(inter, self.hunt_count, self.region, self.beast_data, self.major)

    @disnake.ui.button(label="Region Info", style=disnake.ButtonStyle.secondary)
    async def region_info(self, _: disnake.ui.Button, inter: disnake.MessageInteraction):
        content = "Nothing yet"
        await inter.response.send_message(content, ephemeral=True)


class MassHuntRewardView(disnake.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @disnake.ui.button(label="Mass Hunt Rewards", emoji="🎁", style=disnake.ButtonStyle.blurple, custom_id="solo_beast_reward")
    async def reward_button(self, _: disnake.ui.Button, inter: disnake.MessageInteraction):
        beast_data = await Beast.filter(msg_id=inter.message.id).values_list("beast_id", "beast__exp_given", "attackers", "beast__rank", "mat_drops", "mcore_drop")

        embed = BasicEmbeds.wrong_cross("Failed to retrieve beast info. Report this to `Classified154#0008`")

        if inter.author.id == beast_data[0][2]:
            if len(beast_data) > 0:
                drop_list = await AllItems.filter(type__in=["monster", "core", "egg", "misc"]).order_by("type", "-tier").values_list("id", "name")
                total_exp = 0
                drop_dict = defaultdict(int)
                for beast in beast_data:
                    _, exp_given, _, rank, mat_drop, mcore_drop = beast
                    total_exp += exp_given

                    if mcore_drop:
                        m_str = f"mcore_{rank}"
                        drop_dict[m_str] += 1

                    for drop_id, drop_count in mat_drop.items():
                        drop_dict[drop_id] += drop_count

                exp_bonus_num = await compute_user_exp_bonus(inter.author.id)
                exp_bonus = round(exp_bonus_num * total_exp / 100)

                embed.title = "Your Rewards!"
                embed.description = f"**Exp Given (+{exp_bonus_num:,}% Exp bonus) : `{total_exp:,} (+{exp_bonus:,})`**"

                final_drop_list = [f"`{drop_count}x` {d_name}" for d_id, d_name in drop_list for drop_id, drop_count in drop_dict.items() if drop_id == d_id]
                drop_str = "\n".join(d for d in final_drop_list)

                embed.description += f"\n**Loot: ** \n{drop_str}"
            else:
                embed = BasicEmbeds.exclamation("You didn't hunt any beast successfully")
        else:
            embed = BasicEmbeds.exclamation("You didn't contributed in slaying this beast")

        await inter.response.send_message(embed=embed, ephemeral=True)


async def add_event_token_drops(user_id: int, source_type: str) -> Optional[str]:
    if EVENT_SHOP.is_active and hasattr(EVENT_MANAGER, "current_event"):
        current_event = EVENT_MANAGER.current_event
        if current_event and EVENT_CONFIG[current_event]["sources"][source_type]:
            drop_config = EVENT_CONFIG[current_event]["drop_rates"][source_type]
            if random.randint(1, 100) <= drop_config["chance"]:
                token_amount = random.randint(drop_config["min"], drop_config["max"])
                token_id = EVENT_CONFIG[current_event]["token_id"]
                await add_to_inventory(user_id, token_id, token_amount)
                log_event(user_id, "event", f"Gained {token_amount}x {token_id} from {source_type}")
                return f"\nReceived {token_amount}x {token_id} from the event!"
    return None


class PveBeast(BaseStarfallCog):

    def __init__(self, bot):
        super().__init__(bot, "PVE Beast", "beast")
        self.beast_attack_button: bool = False

    async def _do_load(self):
        if not self.beast_spawn_loop.is_running():
            self.beast_spawn_loop.start()
        if not self.raid_slain_loop.is_running():
            self.raid_slain_loop.start()

    def _do_unload(self):
        self.beast_spawn_loop.cancel()
        self.raid_slain_loop.cancel()

    # ////////////////////////////////////////////

    @tasks.loop(time=RAID_BEAST_SPAWN_TIMES)
    async def beast_spawn_loop(self):
        await self._spawn_default_beast_raid()

    @beast_spawn_loop.before_loop
    async def before_number(self):
        await self.bot.wait_until_ready()

    # ////////////////////////////////////////////

    @tasks.loop(minutes=5)
    async def raid_slain_loop(self):
        boss_data = await Beast.all().values_list("msg_id", "till")

        channel_id = Continent().beast_raid_channel_id
        channel = self.bot.get_channel(channel_id)
        if channel:
            for boss in boss_data:
                msg_id, till = boss
                if till:
                    if datetime.now().timestamp() > till.timestamp():
                        try:
                            msg: disnake.Message = await channel.fetch_message(msg_id)
                            await slain_raid_beast(msg)
                            await Beast.filter(msg_id=msg_id).update(till=None)
                        except disnake.errors.NotFound:
                            pass
        else:
            log_event("raid_slain_loop", "beast", f"Couldn't locate the beast raid channel (id = {channel_id})")

    @raid_slain_loop.before_loop
    async def before_beast(self):
        await self.bot.wait_until_ready()

    # ////////////////////////////////////////////

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.beast_attack_button:
            self.bot.add_view(MagicBeastView())
            self.bot.add_view(SlainRewardView())
            self.bot.add_view(MassHuntRewardView())
            self.beast_attack_button = True

    @commands.slash_command(name="beast", description="Hunt beasts")
    async def slash_beast(self, inter):
        pass

    @slash_beast.sub_command(name="hunt", description="Hunt a beast")
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def slash_beast_hunt(self, inter: disnake.CommandInteraction):
        await inter.response.defer()

        player: Player = PlayerRoster().find_player_for(inter)
        cultivation: PlayerCultivationStage = player.cultivation
        if cultivation.major >= 1:  # Fight Practitioner or above
            beasts: list[BeastDefinition] = Bestiary().list(True)

            region_list: list[tuple[str, str, str]] = []
            for region_name, region_settings in BEAST_REGIONS.items():
                affinity_list, region_pass = region_settings["type"], region_settings["pass"]

                description: list[str] = []
                for affinity in affinity_list:
                    for beast in beasts:
                        if affinity in beast.affinities:
                            rank = f"Rank {beast.rank}"
                            if rank not in description:
                                description.append(rank)

                description_str = ", ".join(d for d in description)
                if region_pass:
                    item_check = await check_item_in_inv(inter.author.id, region_pass)
                    if item_check is True:
                        region_list.append((region_name, description_str, "⚔️"))
                else:
                    region_list.append((region_name, description_str, "⚔️"))

            embed = SoloHuntEmbed("All Regions", 1)
            view = SoloHuntView(inter.author, region_list, beasts, cultivation.major)
            await inter.edit_original_message(embed=embed, view=view)

        else:  # Unable to hunt beasts
            embed = BasicEmbeds.exclamation("You have to be at least Fight Practitioner to hunt beasts")
            await inter.edit_original_message(embed=embed)

        # After loot is distributed and before sending the embed
        token_text = await add_event_token_drops(inter.author.id, "beast_drops")
        if token_text:
            embed.description += token_text

        await inter.edit_original_message(embed=embed)

    @commands.slash_command(name="raid_admin")
    @commands.has_permissions(manage_guild=True)
    async def slash_raid_admin(self, ctx):
        pass

    @slash_raid_admin.sub_command(name="spawn", description="Spawn a raid beast")
    async def slash_raid_admin_spawn(self,
                                     inter: disnake.CommandInteraction,
                                     name: Optional[str] = commands.Param(name="name", description="The beast name, must be an exact match", default=None, autocomplete=autocomplete_beast_name),
                                     rank: Optional[int] = commands.Param(name="rank", description="The beast rank, ignored if name is specified", default=None, ge=1, le=9),
                                     affinity: Optional[str] = commands.Param(name="affinity", description="The beast affinity, ignored if name is specified", default=None, choices=AFFINITIES)):
        if name is None and rank is None and affinity is None:
            print(Continent().beast_raid_channel_id)
            await self._spawn_default_beast_raid()
            res = True
        else:
            beast_candidates: list[BeastDefinition] = Bestiary().filter(name=name, rank=rank, affinity=affinity)
            if len(beast_candidates) == 0:
                res = False
            else:
                await spawn_raid_beast(self.bot, ch_id=Continent().beast_raid_channel_id, beast=random.choice(beast_candidates))
                res = True

        if res:
            await inter.send("Done!", ephemeral=True)
        else:
            await inter.send(f"Could not find any beast matching your name={name}, rank={rank}, affinity={affinity} criteria", ephemeral=True)

    @slash_raid_admin.sub_command(name="end", description="Forcefully end a raid beast")
    async def slash_raid_admin_end(self, inter: disnake.CommandInteraction, message_id: str):
        msg: disnake.Message = await inter.channel.fetch_message(message_id)
        await slain_raid_beast(msg)
        await Beast.filter(msg_id=message_id).update(till=None)
        await inter.send("Beast Slain", ephemeral=True)

    @slash_raid_admin.sub_command(name="simulate_drop", description="Compute the raid drop expectation for n raids")
    async def slash_raid_admin_simulate_drop(self, inter: disnake.CommandInteraction, times: int = commands.Param(1, ge=1, le=10000, description=f"The number of times the test should be ran [1, 10,000]")):
        await inter.response.defer()

        loot: dict[str, int] = {}
        for _ in range(0, times):
            beast: BeastDefinition = Bestiary().choose_random_raid_beast()
            merge_loot(loot, beast.loot.roll())

        await inter.followup.send(f"Rolling beast raids {times:,} times yielded:\n{ItemCompendium().describe_dict(loot)}")

    async def _spawn_default_beast_raid(self):
        await spawn_raid_beast(self.bot, ch_id=Continent().beast_raid_channel_id, beast=Bestiary().choose_random_raid_beast())


def setup(bot):
    cog: PveBeast = PveBeast(bot)
    bot.add_cog(cog)
    log_event("system", "beast", f"{cog.name} Created")

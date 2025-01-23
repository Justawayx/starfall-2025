import math
import random
from typing import Optional, cast

import disnake
from disnake.ext import commands

from character.player import PlayerRoster, Player
from utils.Database import Pet

from utils.CommandUtils import VoteLinkButton, PatreonLinkButton


from utils.Embeds import BasicEmbeds
from utils.ExpSystem import calculate_egg_exp
from utils.InventoryUtils import check_item_in_inv, get_equipped_ring_id, remove_from_inventory, mass_check_items, ConfirmDelete
from utils.LoggingUtils import log_event
from utils.Styles import CROSS
from world.bestiary import Bestiary, PetBeastDefinition, PetBeastEvolution
from world.cultivation import BeastCultivationStage
from world.compendium import ItemCompendium, ItemDefinition, EggDefinition, PetAmplifierDefinition


async def create_pet(user_id, parent_beast, pet_name, previous_cp: int = 0, main: int = 0, pet_quality: Optional[int] = None) -> tuple[int, float, int, str]:
    bestiary: Bestiary = Bestiary()
    definition: Optional[PetBeastDefinition] = bestiary.get_pet_definition(pet_name)
    if definition is None:
        raise ValueError(f"Could not find the definition for {pet_name}")

    if pet_quality is None:
        growth_rate, quality = definition.roll_growth_rate()
    else:
        quality: int = pet_quality
        growth_rate: float = definition.growth_from_quality(quality)

    inherited_cp = math.floor(1.1 * previous_cp)

    log_event(user_id, "pet", f"Created Rank {definition.rank} {pet_name} Pet, {growth_rate} Growth rate, with {inherited_cp} inherited CP")

    await Pet.create(user_id=user_id, beast_id=parent_beast, pet_id=pet_name, nickname=pet_name, growth_rate=growth_rate, p_major=definition.initial_stage.major, p_minor=definition.initial_stage.minor, p_cp=inherited_cp, main=main)

    return definition.rank, growth_rate, quality, definition.rarity


def pet_embed(pet_details: tuple[int, PetBeastDefinition, float, int, int, int, int]):
    _id, definition, growth_rate, main, _, _, _ = pet_details
    description: str = (f"\n**Rarity:** {definition.rarity.capitalize()}"
                        f"\n**Pet Rank:** `{definition.rank}`"
                        f"\n**Growth Rate:** `{round(growth_rate, 3)}` ({definition.quality_from_growth(growth_rate)}%)"
                        f"\n\n*Set the as main pet to view more info*")

    embed = disnake.Embed(title=definition.name, description=description, color=disnake.Color(0x2e3135))
    file: Optional[disnake.File] = definition.image
    if file:
        embed.set_image(file=file)

    return embed


class PetDropdown(disnake.ui.Select):
    def __init__(self, pets: list[tuple[int, PetBeastDefinition, float, int, int, int, int]]):
        self.pets: list[tuple[int, PetBeastDefinition, float, int, int, int, int]] = pets
        options: list[disnake.SelectOption] = [self.create_select_option(data) for data in pets]
        super().__init__(placeholder="Choose a pet", max_values=1, options=options)

    @staticmethod
    def create_select_option(data: tuple[int, PetBeastDefinition, float, int, int, int, int]) -> disnake.SelectOption:
        _id, definition, growth_rate, main, _, _, _ = data
        quality: int = definition.quality_from_growth(growth_rate)
        suffix: str = "" if main == 0 or main == 2 else "  (Main Pet)"
        return disnake.SelectOption(label=definition.name, value=str(_id), description=f"PQ {quality}% | R {definition.rank} | {definition.rarity}{suffix}")

    async def callback(self, inter):
        for pet in self.pets:
            if int(pet[0]) == int(inter.values[0]):
                self.view.current_pet = pet
                self.view.button_update()
                await inter.response.edit_message(embed=pet_embed(pet), view=self.view)


class PetInventoryView(disnake.ui.View):
    def __init__(self, author: disnake.User, pets: list[tuple[int, PetBeastDefinition, float, int, int, int, int]]):
        super().__init__(timeout=None)

        self.author: disnake.User = author
        self.pets: list[tuple[int, PetBeastDefinition, float, int, int, int, int]] = pets
        self.current_pet: tuple[int, PetBeastDefinition, float, int, int, int, int] = self.pets[0]

        self.add_item(PetDropdown(pets))
        self.button_update()

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:
        return inter.author == self.author

    async def update_pet_details(self) -> None:
        bestiary: Bestiary = Bestiary()
        pet_details = await Pet.filter(user_id=self.author.id).values_list("id", "pet_id", "growth_rate", "main", "p_major", "p_minor", "p_exp")

        pet_new_details: list[tuple[int, PetBeastDefinition, float, int, int, int, int]] = []
        for pet in pet_details:
            _id, pet_name, growth_rate, main, pet_major, pet_minor, pet_exp = pet
            definition: PetBeastDefinition = bestiary.get_pet_definition(pet_name)
            pet_new_details.append((_id, definition, growth_rate, main, pet_major, pet_minor, pet_exp))

        self.pets = pet_new_details

        current_pet_index: int = self._find_pet_index(self.current_pet[0])
        self.current_pet = self.pets[current_pet_index if current_pet_index >= 0 else 0]
        self.button_update()

    def button_update(self) -> None:
        main: int = self.current_pet[3]
        if main == 1:  # Main Pet
            self.set_main.label = "Already Main Pet"
            self.set_main.disabled = True
            self.release_pet.label = "Locked"
            self.release_pet.disabled = True
            self.release_pet.style = disnake.ButtonStyle.grey
        elif main == 2:  # Locked Pet
            self.set_main.label = "Set Main"
            self.set_main.disabled = False
            self.release_pet.label = "Unlock Pet"
            self.release_pet.style = disnake.ButtonStyle.red
            self.release_pet.disabled = False
        else:
            self.set_main.label = "Set Main"
            self.set_main.disabled = False
            self.release_pet.label = "Lock pet"
            self.release_pet.disabled = False
            self.release_pet.style = disnake.ButtonStyle.blurple

    @disnake.ui.button(label="Set Main", style=disnake.ButtonStyle.green)
    async def set_main(self, _: disnake.ui.Button, inter: disnake.MessageInteraction) -> None:
        await Pet.filter(user_id=inter.author.id, main=1).update(main=0)

        _id, definition, growth_rate, main, pet_major, pet_minor, pet_exp = self.current_pet
        await Pet.filter(id=_id, user_id=inter.author.id, pet_id=definition.name).update(main=1)
        await self.update_pet_details()

        self.children.pop(2)
        self.add_item(PetDropdown(self.pets))

        await inter.response.edit_message(embed=pet_embed(self.current_pet), view=self)
        await inter.send(embed=BasicEmbeds.right_tick(f"Successfully set {definition.name} as your main pet! Check it by doing `/pet view`!"), ephemeral=True)
        log_event(inter.author.id, "pet", f"Changed main pet to {definition.name}")

    @disnake.ui.button(label="Lock Pet", style=disnake.ButtonStyle.blurple)
    async def release_pet(self, _: disnake.ui.Button, inter: disnake.MessageInteraction):
        _id, definition, growth_rate, main, pet_major, pet_minor, pet_exp = self.current_pet

        if main == 2:
            await Pet.filter(id=_id, user_id=inter.author.id, pet_id=definition.name).update(main=0)
            log_event(inter.author.id, "pet", f"Unlocked pet: {definition.name}")
        else:
            await Pet.filter(id=_id, user_id=inter.author.id, pet_id=definition.name).update(main=2)
            log_event(inter.author.id, "pet", f"Locked pet: {definition.name}")

        await self.update_pet_details()

        await inter.response.edit_message(embed=pet_embed(self.current_pet), view=self)

    def _find_pet_index(self, pet_id_pk: int) -> int:
        index: int = 0
        for pet_data in self.pets:
            if pet_id_pk == pet_data[0]:
                return index

            index += 1

        return -1


class Pets(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(name="pet")
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def slash_pet(self, inter: disnake.CommandInteraction):
        """
        Parent Command
        """
        pass

    @slash_pet.sub_command(name="view", description="View everything about your pet")
    async def slash_pet_view(self, inter: disnake.CommandInteraction):
        await inter.response.defer()

        pet_info = await Pet.get_or_none(user_id=inter.author.id, main=1).values("pet_id", "nickname", "p_major", "p_minor", "p_exp", "p_cp", "growth_rate")
        if pet_info is None:
            await inter.edit_original_message(embed=BasicEmbeds.no_main_pet())
            return

        pet_name, pet_nick, pet_major, pet_minor, pet_exp, inherited_cp, growth_rate = pet_info.values()

        bestiary: Bestiary = Bestiary()
        definition: PetBeastDefinition = bestiary.get_pet_definition(pet_name)

        current_cultivation: BeastCultivationStage = BeastCultivationStage(int(pet_major), int(pet_minor), definition.rarity)
        min_rate, max_rate = definition.growth_rate_range
        evolution: PetBeastEvolution = definition.next_evolution
        pet_quality: int = definition.quality_from_growth(growth_rate)
        combat_power: int = definition.combat_power(current_cultivation, growth_rate, inherited_cp)

        values = [
            f'**"{pet_nick}"**' if pet_nick != pet_name else "\n",
            f"\n**Rarity:** {definition.rarity.capitalize()}", f"**Growth Rate:** `{round(growth_rate, 3)}` ({pet_quality}%)", f"**Range:** {min_rate} - {max_rate}",
            f"\n**Evolve after:** {evolution.required_stage}" if definition.can_evolve else f"**Max Realm:** {evolution.required_stage}",
            f"\n**Pet CP:** {combat_power:,}", f"**Rank:** {current_cultivation.name}", f"**Current Exp:** `{pet_exp:,}` / {current_cultivation.breakthrough_experience:,}"
        ]
        embed = disnake.Embed(title=pet_name, description="\n".join(value for value in values), color=disnake.Color(0x2e3135))

        file: Optional[disnake.File] = definition.image
        if file:
            print(file) # DEBUG
            embed.set_image(file=file)

        view = disnake.ui.View()
        view.add_item(VoteLinkButton())
        view.add_item(PatreonLinkButton())

        await inter.edit_original_message(embed=embed, view=view)

    @slash_pet.sub_command(name="manage", description="Manage all your pets")
    async def slash_pet_manage(self, inter: disnake.CommandInteraction):
        await inter.response.defer()
        pet_details = await Pet.filter(user_id=inter.author.id).values_list("id", "pet_id", "growth_rate", "main", "p_major", "p_minor", "p_exp")

        bestiary: Bestiary = Bestiary()

        pet_new_details: list[tuple[int, PetBeastDefinition, float, int, int, int, int]] = []
        for pet in pet_details:
            _id, pet_name, growth_rate, main, pet_major, pet_minor, pet_exp, = pet
            pet_new_details.append((_id, bestiary.get_pet_definition(pet_name), growth_rate, main, pet_major, pet_minor, pet_exp))

        if len(pet_details) > 0:
            embed = pet_embed(pet_new_details[0])
            view = PetInventoryView(inter.author, pet_new_details)
            await inter.edit_original_message(embed=embed, view=view)
        else:
            await inter.edit_original_message(embed=BasicEmbeds.hatch_a_pet())

    @slash_pet.sub_command(name="release_all", description="Release all unlocked pet")
    async def slash_pet_release_all(self, inter: disnake.CommandInteraction):
        await inter.response.defer()

        pet_details = await Pet.filter(user_id=inter.author.id, main=0).values_list("id", "pet_id", "growth_rate", "main", "p_major", "p_minor", "p_exp")

        bestiary: Bestiary = Bestiary()

        exp_list: list[int] = []
        pet_descriptions: list[str] = []

        compendium: ItemCompendium = ItemCompendium()
        for pet in pet_details:
            _id, pet_name, growth_rate, main, pet_major, pet_minor, pet_exp = pet
            definition: PetBeastDefinition = bestiary.get_pet_definition(pet_name)

            # Base EXP given upon release
            if definition.rank >= 12:
                meat_id: str = "divine_meat"
            elif definition.rank >= 9:
                meat_id: str = "meat_9"
            else:
                meat_id: str = f"meat_{definition.rank}"

            meat_definition: ItemDefinition = compendium[meat_id]
            start_cultivation: BeastCultivationStage = definition.initial_stage
            current_cultivation: BeastCultivationStage = BeastCultivationStage(pet_major, pet_minor, definition.rarity)

            exp_list.append(round(2 * meat_definition.pet_food_exp + 0.3 * start_cultivation.required_exp_to_reach(current_cultivation, pet_exp)))
            pet_descriptions.append(f"`R{definition.rank}` {definition.name}")

        exp_to_give: int = sum(exp_list)
        pet_names = ", ".join(pet_descriptions)

        view = ConfirmDelete(inter.author.id)
        await inter.send(f"Your main pet will gain total of `{exp_to_give:,}` exp after you release these {pet_names}, continue?", view=view)
        await view.wait()
        if view.confirm:
            await Pet.filter(user_id=inter.author.id, main=0).delete()
            await bestiary.add_pet_experience(inter.author.id, exp_to_give)
            await inter.send(embed=BasicEmbeds.right_tick(f"Released {pet_names}!"))
            log_event(inter.author.id, "pet", f"Released {pet_names}")
        else:
            await inter.send(embed=BasicEmbeds.right_tick(f"{pet_names} not released"))

    @slash_pet.sub_command(name="nickname", description="Change the name of your pet")
    async def slash_pet_nickname(self, inter: disnake.CommandInteraction, nick: str):
        await inter.response.defer()
        await Pet.filter(user_id=inter.author.id, main=1).update(nickname=nick)

        log_event(inter.author.id, "pet", f"Changed nickname to {nick}")
        embed = BasicEmbeds.right_tick(f"Successfully updated your pet's nickname to **{nick}**")

        view = disnake.ui.View()
        view.add_item(VoteLinkButton())
        view.add_item(PatreonLinkButton())

        await inter.edit_original_message(embed=embed, view=view)

    @slash_pet.sub_command(name="feed", description="Feed your pet")
    async def slash_pet_feed(self, inter: disnake.CommandInteraction,
                             meat_id: str = commands.Param(None, name="meat_id", description="Type the meat id you want to feed"),
                             meat_quantity: int = commands.Param(1, gt=0, name="meat_quantity", description="Type the amount of the item"),
                             egg_id: str = commands.Param(None, name="egg_id", description="Type the egg id you want to feed"),
                             egg_quantity: int = commands.Param(1, gt=0, name="egg_quantity", description="Type the number of eggs to feed")):
        await inter.response.defer()
        exp_to_give = 0

        if not meat_id and not egg_id:
            embed = BasicEmbeds.item_not_found()
            await inter.edit_original_message(embed=embed)
            return

        pet_info = await Pet.get_or_none(user_id=inter.author.id, main=1).values_list("pet_id", "p_cp", "p_major", "p_minor", "p_exp", "growth_rate")
        if not pet_info:
            embed = BasicEmbeds.no_main_pet()
            await inter.edit_original_message(embed=embed)
            return

        pet_name, pet_cp, pet_major, pet_minor, pet_exp, growth_rate = pet_info
        bestiary: Bestiary = Bestiary()
        definition: PetBeastDefinition = bestiary.get_pet_definition(pet_name)

        max_cultivation: BeastCultivationStage = definition.next_evolution.required_stage
        current_cultivation: BeastCultivationStage = BeastCultivationStage(pet_major, pet_minor, definition.rarity)
        if pet_major == max_cultivation.major and pet_minor == max_cultivation.minor and not definition.can_evolve:
            await inter.edit_original_message(embed=BasicEmbeds.exclamation("Failed to feed the pet, your pet has reached its pinnacle potential"))
            return

        compendium: ItemCompendium = ItemCompendium()
        if meat_id:
            item: Optional[ItemDefinition] = compendium.get(meat_id)
            if item is None or not item.pet_food:
                await inter.edit_original_message(embed=BasicEmbeds.item_not_found())
                return

            inv_check = await check_item_in_inv(inter.author.id, meat_id, meat_quantity)
            if not inv_check:
                if meat_id == "divine_beast":
                    embed = BasicEmbeds.not_enough_item(item.name, "shop")
                else:
                    embed = BasicEmbeds.not_enough_item(item.name, "beast")
                await inter.edit_original_message(embed=embed)
                return

            exp_to_give += item.pet_food_exp * meat_quantity

        if egg_id:
            item: Optional[ItemDefinition] = compendium.get(egg_id)
            if item is None or not isinstance(item, EggDefinition):
                await inter.edit_original_message(embed=BasicEmbeds.item_not_found())
                return

            egg: EggDefinition = cast(EggDefinition, item)

            inv_check = await check_item_in_inv(inter.author.id, egg_id, egg_quantity)
            if not inv_check:
                await inter.edit_original_message(embed=BasicEmbeds.not_enough_item(egg.name, "beast"))
                return

            egg_exp: int = calculate_egg_exp(egg.tier) * egg_quantity
            exp_to_give += egg_exp

        exp_to_cap: int = current_cultivation.required_exp_to_reach(max_cultivation, pet_exp)
        if exp_to_give > exp_to_cap:

            excess_exp = exp_to_give - exp_to_cap
            exp_to_give = exp_to_cap

            view = ConfirmDelete(inter.author.id)
            await inter.channel.send(f"Warning: excess amount of {excess_exp:,} exp will be wasted, proceed?", view=view)
            await view.wait()
            if not view.confirm:
                await inter.edit_original_message(embed=BasicEmbeds.exclamation(f"Feeding stopped due to excess exp by user"))
                return

        if meat_id:
            await remove_from_inventory(inter.author.id, meat_id, meat_quantity)
            log_event(inter.author.id, "pet", f"Fed {meat_quantity}x {meat_id} to {pet_info[0]}")
        if egg_id:
            await remove_from_inventory(inter.author.id, egg_id, egg_quantity)
            log_event(inter.author.id, "pet", f"Fed {egg_quantity}x {egg_id} to {pet_info[0]}")

        content = await bestiary.add_pet_experience(inter.author.id, exp_to_give, (definition, growth_rate, current_cultivation, pet_exp))
        embed = BasicEmbeds.add_plus(content, "Done!")

        log_event(inter.author.id, "pet", f"Gaining {exp_to_give:,} EXP")

        await inter.edit_original_message(embed=embed)

    @slash_pet.sub_command(name="evolve", description="Evolve your pet")
    async def slash_pet_evolve(self, inter: disnake.CommandInteraction):
        await inter.response.defer()

        pet_info = await Pet.get_or_none(user_id=inter.author.id, main=1).values_list("pet_id", "p_major", "p_minor", "p_exp", "growth_rate", "p_cp")
        if not pet_info:
            await inter.edit_original_message(embed=BasicEmbeds.no_main_pet())
            return

        pet_name, pet_major, pet_minor, pet_exp, growth_rate, p_cp = pet_info
        bestiary: Bestiary = Bestiary()

        definition: PetBeastDefinition = bestiary.get_pet_definition(pet_name)
        if not definition.can_evolve:
            await inter.edit_original_message(embed=BasicEmbeds.exclamation(f"Your pet has reached its highest evolution."))
            return

        cultivation = BeastCultivationStage(pet_major, pet_minor, definition.rarity)
        evolution: PetBeastEvolution = definition.next_evolution

        evo_requirements: dict[str, int] = evolution.required_items

        fail_content = f"You have not met the conditions to evolve your pet!\n"

        mass_check, check_content = await mass_check_items(inter.author.id, evo_requirements)
        if not mass_check:
            await inter.edit_original_message(embed=BasicEmbeds.exclamation(fail_content + check_content))
            return

        if cultivation < evolution.required_stage:
            await inter.edit_original_message(embed=BasicEmbeds.exclamation(fail_content + f"\n{CROSS} Your pet has not reached the maximum `class`"))
            return

        if pet_exp < cultivation.breakthrough_experience - 1:
            await inter.edit_original_message(embed=BasicEmbeds.exclamation(fail_content + f"\n{CROSS}Not enough `exp`"))
            return

        ring_id = await get_equipped_ring_id(inter.author.id)
        for item_id, item_count in evo_requirements.items():
            await remove_from_inventory(inter.author.id, item_id, item_count, ring_id)

        current_power: int = definition.combat_power(cultivation, growth_rate, p_cp)
        current_quality: int = definition.quality_from_growth(growth_rate)

        evolved_quality: int = random.randint(current_quality - 5, current_quality + 5)
        if evolved_quality > 100:
            evolved_quality = 100
        elif evolved_quality < 0:
            evolved_quality = 0

        await Pet.filter(user_id=inter.author.id, pet_id=pet_name, main=1).delete()

        evo_rank, evo_growth_rate, pet_quality, _ = await create_pet(inter.author.id, evolution.target_pet.parent_beast, evolution.target_pet_name, current_power, 1, evolved_quality)

        embed = BasicEmbeds.add_plus(f"Your {pet_name} has evolved to **Rank `{evo_rank}` {evolution.target_pet_name}**! \nPet quality is `{pet_quality}%` with growth rate of `{evo_growth_rate}`", "Congratulations!")
        log_event(inter.author.id, "pet", f"Evolved the pet from {pet_name} to Rank {evo_rank} {evolution.target_pet_name}")
        await inter.edit_original_message(embed=embed)

    @slash_pet.sub_command(name="reroll", description="Reroll the quality of pet at starting stage")
    async def slash_pet_reroll(self, inter: disnake.CommandInteraction, amp_id: str = commands.Param(None, name="amp_id", description="The id of the pet amplifier to use in the reroll")):
        await inter.response.defer()
        pet_info = await Pet.get_or_none(user_id=inter.author.id, main=1).values_list("pet_id", "p_major", "p_minor", "p_exp", "beast_id", "growth_rate", "reroll_count")
        if not pet_info:
            await inter.edit_original_message(embed=BasicEmbeds.no_main_pet())
            return

        pet_name, pet_major, pet_minor, pet_exp, parent_beast, growth_rate, reroll_count = pet_info
        bestiary: Bestiary = Bestiary()
        definition: PetBeastDefinition = bestiary.get_pet_definition(pet_name)

        cultivation = BeastCultivationStage(pet_major, pet_minor, definition.rarity)
        if cultivation > definition.initial_stage:
            await inter.edit_original_message(embed=BasicEmbeds.exclamation(f"You can only reroll your pet at the starting stage ({definition.initial_stage})."))
            return

        definition.reroll_cost()

        quality_inc: int = 0
        if amp_id is not None:
            compendium: ItemCompendium = ItemCompendium()
            item: Optional[ItemDefinition] = compendium.get(amp_id)
            if item is None or not isinstance(item, PetAmplifierDefinition):
                await inter.edit_original_message(embed=BasicEmbeds.item_not_found())
                return

            if not isinstance(item, PetAmplifierDefinition):
                await inter.edit_original_message(embed=BasicEmbeds.exclamation(f"Please use the correct ID for the item."))
                return

            item_check = await check_item_in_inv(inter.author.id, amp_id, 1)
            if not item_check:
                await inter.edit_original_message(embed=BasicEmbeds.not_enough_item(amp_id, "raid"))
                return

            amplifier: PetAmplifierDefinition = cast(PetAmplifierDefinition, item)
            quality_inc = amplifier.reroll_quality_bonus

        cost = definition.reroll_cost(reroll_count)
        reroll_count = reroll_count + 1

        await Pet.filter(user_id=inter.author.id, main=1).update(reroll_count=reroll_count)

        view = ConfirmDelete(inter.author.id)
        await inter.send(f"This reroll will cost you {cost:,} gold, continue?", view=view)
        await view.wait()
        if not view.confirm:
            await Pet.filter(user_id=inter.author.id, main=1).update(reroll_count=reroll_count - 1)
            await inter.edit_original_message(embed=BasicEmbeds.exclamation(f"Re-rolling stopped by user"))
            return

        current_quality: int = definition.quality_from_growth(growth_rate)
        if current_quality >= 80:
            view = ConfirmDelete(inter.author.id)
            await inter.send(f"Your main pet quality is {current_quality}% are you sure you want to continue?", view=view)
            await view.wait()
            if not view.confirm:
                await Pet.filter(user_id=inter.author.id, main=1).update(reroll_count=reroll_count - 1)
                await inter.edit_original_message(embed=BasicEmbeds.exclamation(f"Re-rolling stopped by user"))
                return

        player: Player = PlayerRoster().get(inter.author.id)
        async with player:
            money_check = player.spend_funds(cost)

        if not money_check:
            await Pet.filter(user_id=inter.author.id, main=1).update(reroll_count=reroll_count - 1)
            await inter.edit_original_message(embed=BasicEmbeds.exclamation(f"You dont have the required {cost:,} gold to pay for the reroll"))
            return

        if amp_id:
            # Redo the item check since there was interruption before, and we want to prevent launching multiple commands to reuse the amplifier on multiple rolls
            item_check: bool = await check_item_in_inv(inter.author.id, amp_id, 1)
            if item_check:
                # Should always be the case except if the player tried to exploit multiple /reroll commands
                await remove_from_inventory(inter.author.id, amp_id, 1)
            else:
                # Probably attempted to exploit to duplicate an amplifier, let punish the player by not warning him and re-rolling anyway
                quality_inc: int = 0

        new_growth_rate, new_quality = definition.roll_growth_rate(quality_inc)

        await Pet.filter(user_id=inter.author.id, main=1).update(growth_rate=new_growth_rate)
        log_event(inter.author.id, "pet", f"Rerolled the pet, {current_quality} -> {new_quality} Quality, {growth_rate} -> {new_growth_rate} Growth Rate \n\nUsed {cost:,} gold on re-rolling")

        await inter.edit_original_message(embed=BasicEmbeds.right_tick(f"Your pet quality changed from {current_quality}% to {new_quality}%, growth rate changed from {growth_rate} to {new_growth_rate}!"))

    @commands.slash_command(name="hatch", description="Hatch your eggs")
    async def hatch(self, inter: disnake.CommandInteraction, egg_id: str = commands.Param(name="egg_id", description="Type your egg id")):
        await inter.response.defer()

        compendium: ItemCompendium = ItemCompendium()
        item: Optional[ItemDefinition] = compendium.get(egg_id)
        if not item or not isinstance(item, EggDefinition):
            await inter.edit_original_message(embed=BasicEmbeds.item_not_found())
            return

        inv_check = await check_item_in_inv(inter.author.id, egg_id, 1)
        if not inv_check:
            await inter.edit_original_message(embed=BasicEmbeds.not_enough_item(item.name, "beast"))
            return

        all_pets = await Pet.filter(user_id=inter.author.id).count()
        if all_pets >= 20:
            await inter.edit_original_message(embed=BasicEmbeds.exclamation("You can only possess a total of 20 pets at a time"))
            return

        egg: EggDefinition = cast(EggDefinition, item)
        hatched_pet_name: str = egg.hatch()

        log_event(inter.author.id, "pet", f"Hatched {hatched_pet_name} from {egg.name}")

        await remove_from_inventory(inter.author.id, egg_id, 1)
        rank, growth_rate, pet_quality, pet_rarity = await create_pet(inter.author.id, egg.parent_beast_name, hatched_pet_name)

        embed = BasicEmbeds.add_plus(f"You got **Rank `{rank}` {hatched_pet_name}** of *{pet_rarity}* rarity from hatching {egg.name}! \nPet quality is `{pet_quality}%` with growth rate of `{growth_rate}`", "Congratulations!")
        await inter.edit_original_message(embed=embed)


def setup(bot):
    bot.add_cog(Pets(bot))
    print("[Pets] Loaded")

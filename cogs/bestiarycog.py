from typing import Union

import disnake

from disnake.ext import commands

from world.bestiary import Bestiary, BeastDefinition, BeastDefinitionEmbed, PetBeastDefinition, PetBeastDefinitionEmbed, autocomplete_beast_name, autocomplete_pet_name, VARIANT_NORMAL, VARIANTS
from world.compendium import ItemCompendium
from utils.LoggingUtils import log_event
from utils.base import BaseStarfallCog


class BestiaryCog(BaseStarfallCog):
    def __init__(self, bot: commands.Bot):
        super().__init__(bot, "Bestiary Cog", "bestiary")

    @commands.slash_command(name="bestiary")
    @commands.default_member_permissions(manage_guild=True)
    async def slash_bestiary(self, _: disnake.CommandInteraction):
        pass

    @slash_bestiary.sub_command(name="info", description="Displays the information about a specific beast")
    async def slash_bestiary_info(self, inter: disnake.CommandInteraction, beast_name: str = commands.Param(description="The beast name", autocomplete=autocomplete_beast_name)):
        bestiary: Bestiary = Bestiary()
        beast: BeastDefinition = bestiary[beast_name]
        if beast is None:
            await inter.response.send_message(f"Cannot find beast `{beast_name}`", ephemeral=True)
        else:
            await inter.response.send_message(embed=BeastDefinitionEmbed(beast))

    @slash_bestiary.sub_command(name="loot_test", description="Test beast loot")
    async def slash_bestiary_loot_test(
            self,
            inter: disnake.CommandInteraction,
            beast_name: str = commands.Param(name="beast", description="The beast name", autocomplete=autocomplete_beast_name),
            variant: str = commands.Param(name="variant", description="The beast variant", default=VARIANT_NORMAL, choices=VARIANTS),
            times: int = commands.Param(name="times", description=f"The number of times the test should be ran [1, 1000]", default=1, ge=1, le=1000)
    ):
        await inter.response.defer()
        bestiary: Bestiary = Bestiary()
        beast: BeastDefinition = bestiary[beast_name].mutate(bestiary.get_variant(variant))
        await inter.followup.send(f"Rolling the loot {times:,} times for a {beast} yielded:\n{ItemCompendium().describe_dict(beast.loot.roll(times))}")

    @slash_bestiary.sub_command(name="pet_info", description="Displays the information about a specific pet archetype")
    async def slash_bestiary_pet_info(self, inter: disnake.CommandInteraction, pet_name: str = commands.Param(description="The pet name", autocomplete=autocomplete_pet_name)):
        bestiary: Bestiary = Bestiary()
        pet: PetBeastDefinition = bestiary.get_pet_definition(pet_name)
        if pet is None:
            await inter.response.send_message(f"Cannot find pet `{pet}`", ephemeral=True)
        else:
            await inter.response.send_message(embed=PetBeastDefinitionEmbed(pet, ItemCompendium()))

    @slash_bestiary.sub_command(name="config_dump", description="Dump the compendium and bestiary into files")
    async def slash_bestiary_config_dump(self, inter: disnake.CommandInteraction):
        bestiary: Bestiary = Bestiary()
        await bestiary.dump_to_file("./data/beasts.json")
        await bestiary.dump_pets_to_file("./data/pets.json")
        await inter.send("Bestiary contents dumped")

    @slash_bestiary.sub_command(name="update_database", description="Update the database with the values from in-memory bestiary")
    async def slash_bestiary_update_database(self, inter: disnake.CommandInteraction):
        bestiary: Bestiary = Bestiary()
        beast_created_count, beast_updated_count, beast_deleted_count = await bestiary.update_beast_database()
        pet_created_count, pet_updated_count, pet_deleted_count = await bestiary.update_pet_database()
        await inter.send(f"Beast and pet database updated."
                         f"\nBeast Created: {beast_created_count}, Beast Updated: {beast_updated_count}, Beast Deleted: {beast_deleted_count}."
                         f"\nPet Created: {pet_created_count}, Pet Updated: {pet_updated_count}, Pet Deleted: {pet_deleted_count}")


def _log(user_id: Union[int, str], message: str):
    log_event(user_id, "bestiary", message)


# The bootstrap code
def setup(bot: commands.Bot):
    cog = BestiaryCog(bot)
    bot.add_cog(cog)
    _log("system", f"{cog.name} Created")

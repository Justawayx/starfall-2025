import json
from typing import Union, Optional, Any, cast

import disnake
from disnake.ext import commands

from character.player import PlayerRoster, Player
from utils.Embeds import BasicEmbeds
from utils.InventoryUtils import ConfirmDelete, ITEM_TYPE_MAP_FRAGMENT, mass_check_items, remove_from_inventory, add_to_inventory, check_inv_weight
from utils.ParamsUtils import as_discord_list
from utils.loot import is_pseudo_item_id
from world.compendium import ItemCompendium, ItemDefinition, ItemDefinitionEmbed, MapFragmentDefinition
from utils.LoggingUtils import log_event
from utils.base import BaseStarfallCog, PlayerInputException


class ItemCompendiumCog(BaseStarfallCog):
    def __init__(self, bot: commands.Bot):
        super().__init__(bot, "Item Compendium Cog", "compendium")

    # ============================================== Discord commands ===========================================
    @commands.slash_command(name="info", description="Shows you detail view for an item")
    async def slash_info(self,
                         inter: disnake.CommandInteraction,
                         item_id: str = commands.Param(name="item_id", description="Type an Item's id")):
        definition: Optional[ItemDefinition] = ItemCompendium().get(item_id)
        if definition is not None:
            embed: disnake.Embed = ItemDefinitionEmbed(definition)
        else:
            embed: disnake.Embed = disnake.Embed(title="Item Not Found", description="Item not found", color=disnake.Color(0x2e3135))

        await inter.response.send_message(embed=embed)

    @commands.slash_command(name="map")
    async def slash_map(self, _: disnake.CommandInteraction):
        pass

    @slash_map.sub_command(name="combine", description="Combine map pieces to get the treasure")
    async def slash_map_combine(self,
                                inter: disnake.CommandInteraction,
                                fragment_id: str = commands.Param(name="fragment_id", description="The id of one of the fragment")) -> None:
        compendium: ItemCompendium = ItemCompendium()
        fragment_item: Optional[ItemDefinition] = compendium.find_one(item_type=ITEM_TYPE_MAP_FRAGMENT, item_id=fragment_id)
        if fragment_item is None:
            await inter.send(f"{fragment_id} is not a valid map fragment id", ephemeral=True)
            return

        fragment: MapFragmentDefinition = cast(MapFragmentDefinition, fragment_item)
        target_item: ItemDefinition = compendium[fragment.target_item_id]

        required_items: dict[str, int] = {fragment_id: 1}
        for sibling in fragment.sibling_fragments:
            required_items[sibling.id] = 1

        await inter.response.defer()
        continue_check, ring_id, add_check = await check_inv_weight(inter.channel, inter.author.id, target_item.id, 1)
        if not continue_check:
            await inter.edit_original_message(embed=BasicEmbeds.cmd_not_continued(), view=None)
            return

        mat_check, _ = await mass_check_items(inter.author.id, required_items)
        if mat_check:
            for item_id, item_count in required_items.items():
                await remove_from_inventory(inter.author.id, item_id, item_count)

            await add_to_inventory(inter.author.id, target_item.id, 1, ring_id, add_check)
            self._log(inter.author.id, f"Combined {len(required_items)} map fragments to acquire {target_item.id}")

            embed = BasicEmbeds.add_plus(f"After combining the {len(required_items)} all the map parts you could finally figure where to find the {target_item.name} and be the first to get it")
            await inter.edit_original_message(embed=embed, view=None)

        else:
            self._log(inter.author.id, f"Attempted to combine the map for {target_item.name} without owning all the parts")
            embed = BasicEmbeds.exclamation(f"You dont have all the parts of the map for {target_item.name}")
            await inter.edit_original_message(embed=embed, view=None)

    @commands.slash_command(name="inventory_admin")
    @commands.default_member_permissions(manage_guild=True)
    async def slash_inventory_admin(self, _: disnake.CommandInteraction):
        pass

    @slash_inventory_admin.sub_command(name="give_loot", description="Give multiple items to someone")
    async def slash_inventory_admin_give_loot(self, inter: disnake.CommandInteraction, member: disnake.Member):
        await inter.response.send_modal(GiveLootModal(inter, member))
        pass

    @slash_inventory_admin.sub_command(name="update_database", description="Update the database with the values from in-memory compendium")
    async def slash_inventory_admin_update_database(self, inter: disnake.CommandInteraction):
        created_count, updated_count, deleted_count = await ItemCompendium().update_database()
        await inter.send(f"Item database updated. Created: {created_count}, Updated: {updated_count}, Deleted: {deleted_count}")


class GiveLootModal(disnake.ui.Modal):
    DATA_FIELD: str = "item_json"

    def __init__(self, inter: disnake.CommandInteraction, member: disnake.Member):
        super().__init__(title="Item Set Setup", custom_id=f"loot_modal-{inter.id}",
                         components=[disnake.ui.TextInput(label="Items", placeholder="Specify a valid JSON-serialized object of {<item_id>: <quantity>}", custom_id=self.DATA_FIELD, style=disnake.TextInputStyle.multi_line, required=True)])

        self._member: disnake.Member = member

    async def callback(self, inter: disnake.ModalInteraction) -> None:
        await inter.response.defer(ephemeral=True)

        try:
            compendium: ItemCompendium = ItemCompendium()
            items: dict[str, int] = self.get_items(inter)
            unknown_items: set[str] = {item for item in items.keys() if item not in compendium and not is_pseudo_item_id(item)}
            if len(unknown_items) > 0:
                await inter.send(f"The following item ids or pseudo item ids could don't exist:\n{as_discord_list(unknown_items)}", ephemeral=True)
            else:
                view = ConfirmDelete(inter.author.id)
                await inter.send(f"You're about to give the following to {self._member.name}:\n{compendium.describe_dict(items)}\n\nContinue?", view=view, ephemeral=True)
                await view.wait()
                if view.confirm:
                    roster: PlayerRoster = PlayerRoster()
                    player: Player = roster.get(self._member.id)
                    async with player:
                        await player.acquire_loot(items)

                    await inter.send(f"Loot was given to {self._member.name}", ephemeral=True)
                else:
                    await inter.send("Action canceled", ephemeral=True)
        except PlayerInputException as e:
            await e.send(inter)
        except ValueError:
            await inter.send(f"Please enter a valid value", ephemeral=True)

    def get_items(self, inter: disnake.ModalInteraction) -> dict[str, int]:
        user_input: str = inter.text_values[self.DATA_FIELD]
        if user_input is None:
            raise PlayerInputException(f"Loot data must be specified")

        try:
            parsed: Any = json.loads(user_input)
        except ValueError:
            raise PlayerInputException(f"Loot should be specified as a JSON object (dict), found {user_input}")

        if not isinstance(parsed, dict):
            raise PlayerInputException(f"Loot should be specified as a JSON object (dict), found {type(parsed)}")

        return parsed


def _log(user_id: Union[int, str], message: str):
    log_event(user_id, "compendium", message)


# The bootstrap code
def setup(bot: commands.Bot):
    cog = ItemCompendiumCog(bot)
    bot.add_cog(cog)
    _log("system", f"{cog.name} Created")

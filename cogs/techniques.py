import disnake

from disnake.ext import commands

from utils.InventoryUtils import check_inv_weight, check_item_in_inv, get_equipped_ring_id, add_to_inventory, remove_from_inventory
from utils.Embeds import BasicEmbeds
from utils.Effects import equip_qi_method, equip_technique
from utils.LoggingUtils import log_event

from utils.ParamsUtils import format_num_full, tier_id_to_name, is_technique_learnable, compute_technique_cp_bonus
from utils.Database import AllItems, Cultivation, Users
from world.cultivation import MAJOR_CULTIVATION_REALMS


class UnLearnButton(disnake.ui.Button):

    def __init__(self, label):
        super().__init__(label=str(label), style=disnake.ButtonStyle.grey)
        self.label = label

    async def callback(self, inter):
        self.view.itemid = self.label
        self.view.clear_items()
        await inter.response.edit_message(view=self.view)
        self.view.stop()


class SwapItemView(disnake.ui.View):

    def __init__(self, ids, author):
        super().__init__(timeout=None)
        for _id in ids:
            self.add_item(UnLearnButton(_id))
        self.itemid = None
        self.author = author

    async def interaction_check(self, inter):
        return inter.author == self.author


class Techniques(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    # //////////////////////////////////////// #

    @commands.slash_command(name="learn", description="Learn a technique or qi method")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def slash_learn(self, inter: disnake.CommandInteraction, item_id: str = commands.Param(name="item_id", description="Type the item id to use it")):
        await inter.response.defer()

        item_check = await AllItems.get_or_none(id=item_id).values_list("type", "properties", "name", "tier")
        if item_check is None:
            embed = BasicEmbeds.item_not_found()
            await inter.edit_original_message(embed=embed)
            return

        major, minor, equipped = await Cultivation.get_or_none(user_id=inter.author.id).values_list("major", "minor", "user__equipped")

        item_type, properties, name, tier = item_check

        type_check = item_type.split("_")[-1]

        if type_check == "technique":
            learn_check, min_realm_id_major = is_technique_learnable(tier, major)
            if learn_check is False:
                min_realm = MAJOR_CULTIVATION_REALMS[min_realm_id_major]
                embed = BasicEmbeds.exclamation(f"You cannot learn this technique (minimum class: {min_realm}).")
                await inter.edit_original_message(embed=embed)
                return
            # Dict of all techniques
            tech_method = equipped["techniques"]

            # If already learned
            if item_id in tech_method.keys():
                embed = BasicEmbeds.exclamation("Already learned this technique.")
                await inter.send(embed=embed)
                return

            item_check = await check_item_in_inv(inter.author.id, item_id)
            if item_check is False:
                embed = BasicEmbeds.not_enough_item("shop")
                await inter.edit_original_message(embed=embed)
                return

            ring_id = await get_equipped_ring_id(inter.author.id)

            max_technique = 3
            if len(tech_method) < max_technique:
                # Adding technique
                item_info = (properties["cp"], tier, name)
                await equip_technique(inter.author.id, item_id, item_info)

                total_cp = compute_technique_cp_bonus(properties["cp"], tier, major)
                content = f"Learned {name} *({tier_id_to_name(tier)})*! \nCP increased by `{format_num_full(total_cp)}`"

                log_event(inter.author.id, "technique", f"Learned {name}")
                embed = BasicEmbeds.right_tick(content)
                await inter.send(embed=embed)
            else:
                embed = BasicEmbeds.exclamation("**Limit reached** \nPlease choose a technique to swap out")
                view = SwapItemView(tech_method.keys(), inter.author)
                await inter.send(embed=embed, view=view)

                await view.wait()
                if view.itemid:
                    item_info = (properties["cp"], tier, name)
                    await equip_technique(inter.author.id, item_id, item_info, remove=view.itemid)

                    await add_to_inventory(inter.author.id, view.itemid, 1, ring_id)

                    total_cp = compute_technique_cp_bonus(properties["cp"], tier, major)
                    embed = BasicEmbeds.right_tick(f"Swapped a technique for {name}! \nCP increased by `{format_num_full(total_cp)}`")

                    log_event(inter.author.id, "technique", f"Learned {name}, removed {view.itemid}")
                    await inter.edit_original_message(embed=embed)
            await remove_from_inventory(inter.author.id, item_id, 1, ring_id)

        elif type_check == "method":

            learn_check, min_realm_id_major = is_technique_learnable(tier, major)
            if learn_check is False:
                min_realm = MAJOR_CULTIVATION_REALMS[min_realm_id_major]
                embed = BasicEmbeds.exclamation(f"You cannot learn this Qi Method (minimum class: {min_realm}).")
                await inter.edit_original_message(embed=embed)
                return

            method = equipped["method"]
            ring_id = await get_equipped_ring_id(inter.author.id)

            if not method:
                item_check = await check_item_in_inv(inter.author.id, item_id)
                if item_check is False:
                    embed = BasicEmbeds.not_enough_item("shop")
                    await inter.edit_original_message(embed=embed)
                    return

                total_cp = properties["cp_pct"]
                item_info = [item_id, total_cp, tier, name]
                await equip_qi_method(inter.author.id, item_info)
                await remove_from_inventory(inter.author.id, item_id, 1, ring_id)

                content = f"Learned {name} *({tier_id_to_name(tier)})*! \nCP increased by `{round(total_cp)}`%"
                log_event(inter.author.id, "qi_method", f"Learned {name}")

                embed = BasicEmbeds.right_tick(content)
                await inter.edit_original_message(embed=embed)

            else:
                if item_id == method[0]:
                    embed = BasicEmbeds.exclamation("Already learned this Qi Method")
                    await inter.edit_original_message(embed=embed)
                else:
                    embed = BasicEmbeds.right_tick(f"Use `/unlearn itemid:{method[0]}` to unlearn the qi method first")
                    await inter.edit_original_message(embed=embed)

        else:
            content = "You can only learn Fight Techniques or Qi Methods"
            embed = BasicEmbeds.exclamation(content)
            await inter.edit_original_message(embed=embed)

    @commands.slash_command(name="unlearn", description="Unlearn a technique or qi method")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def slash_unlearn(self, inter: disnake.CommandInteraction, item_id: str = commands.Param(name="item_id", description="Type the item id to unlearn it")):
        await inter.response.defer()

        item_check = await AllItems.get_or_none(id=item_id).values_list("type", "properties", "name", "tier")
        if item_check is None:
            embed = BasicEmbeds.item_not_found()
            await inter.edit_original_message(embed=embed)
            return

        user_data = await Cultivation.get_or_none(user_id=inter.author.id).values_list("major", "minor", "user__equipped")

        major, minor, equipped = user_data
        item_type, properties, name, tier = item_check

        type_check = item_type.split("_")[-1]

        if type_check == "technique":
            techniques = equipped["techniques"]

            if item_id in techniques.keys():

                continue_check, ringid, add_check = await check_inv_weight(inter.channel, inter.author.id, item_id, 1)
                if continue_check is False:
                    embed = BasicEmbeds.cmd_not_continued()
                    await inter.edit_original_message(embed=embed)
                    return

                equipped["techniques"].pop(item_id)

                total_cp = compute_technique_cp_bonus(properties["cp"], tier, major)
                content = f"Unlearned {name} *({tier_id_to_name(tier)})*! \n CP decreased by `{format_num_full(total_cp)}`"

                await add_to_inventory(inter.author.id, item_id, 1, ringid, add_check)
                log_event(inter.author.id, "technique", f"Unlearned {name}")

                embed = BasicEmbeds.right_tick(content)
                await inter.edit_original_message(embed=embed)
            else:
                content = "Technique not learned"
                embed = BasicEmbeds.exclamation(content)
                await inter.edit_original_message(embed=embed)

        elif type_check == "method":
            method = equipped["method"]
            if method is not None and item_id == method[0]:

                continue_check, ringid, add_check = await check_inv_weight(inter.channel, inter.author.id, item_id, 1)
                if continue_check is False:
                    embed = BasicEmbeds.cmd_not_continued()
                    await inter.edit_original_message(embed=embed)
                    return

                equipped["method"] = None

                total_cp = properties["cp_pct"]
                content = f"Unlearned {name} *({tier_id_to_name(tier)})*! \n CP decreased by `{format_num_full(total_cp)}`%"
                await add_to_inventory(inter.author.id, item_id, 1, ringid, add_check)
                log_event(inter.author.id, "qi_method", f"Unlearned {name}")

                embed = BasicEmbeds.right_tick(content)
                await inter.edit_original_message(embed=embed)
            else:
                content = "Qi Method not learned"
                embed = BasicEmbeds.exclamation(content)
                await inter.edit_original_message(embed=embed)

        else:
            await inter.edit_original_message("Only Fight Techniques or Qi Methods can be unlearned")

        await Users.filter(user_id=inter.author.id).update(equipped=equipped)


def setup(bot):
    bot.add_cog(Techniques(bot))
    print("[Techniques] Loaded")

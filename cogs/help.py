import disnake
import platform
import traceback
from time import time
from utils.LoggingUtils import log_event
from disnake.ext import commands

from utils.Styles import C_Nothing, RIGHT, LEFT

# Command IDs for Starfall Main
cmd_ID_dict = {
    "alchemy": 1024566199528468501,  # mentioned
    "balance": 1024566199528468505,  # mentioned
    "beast hunt": 1024566199733981200,  # mentioned
    "board carve": 1137329700482601061,
    "board view": 1137329700482601061,
    "breakthrough": 1024566199528468509,  # mentioned
    "buy": 1024566199733981195,  # mentioned
    "consume": 1024566199733981197,  # mentioned
    "craft menu": 1067016004141592657,  # mentioned
    "craft profile": 1067016004141592657,  # mentioned
    "cultivate exp": 1024566199528468508,  # mentioned
    "cultivate cp": 1024566199528468508,  # mentioned
    "daily": 1024566199528468504,  # mentioned
    "dismantle": 1077866297716658207,  # mentioned
    "energy": 1024566199595585544,  # mentioned
    "equip": 1024566199733981198,  # mentioned
    "exchange": 1086540121723109387,  # mentioned
    "hatch": 1077866297716658209,  # mentioned
    "help": 1024566199595585542,  # N/A
    "info": 1024566199595585545,  # mentioned
    "inventory view": 1024566199595585543,  # mentioned
    "inventory search": 1024566199595585543,  # mentioned
    "leaderboard": 1024566199595585540,  # mentioned
    "learn": 1024566199733981203,  # mentioned
    "market add": 1024566199859806259,
    "market items": 1024566199859806259,
    "market profile": 1024566199859806259,
    "market search": 1024566199859806259,
    "pet view": 1077866297716658208,  # mentioned
    "pet manage": 1077866297716658208,  # mentioned
    "pet nickname": 1077866297716658208,  # mentioned
    "pet feed": 1077866297716658208,  # mentioned
    "pet evolve": 1077866297716658208,  # mentioned
    "pet reroll": 1077866297716658208,  # mentioned
    "pills": 1024566199528468502,  # mentioned
    "profile": 1024566199595585539,  # mentioned
    "rank": 1024566199528468507,  # mentioned
    "ranked match": 1024566199733981201,  # mentioned
    "ranked top": 1024566199733981201,  # mentioned
    "ranked profile": 1024566199733981201,  # mentioned
    "ring transfer": 1067016004141592658,  # mentioned
    "ring equip": 1067016004141592658,  # mentioned
    "search": 1024566199528468503,  # mentioned
    "sell": 1024566199733981196,  # mentioned
    "shop": 1024566199733981194,  # mentioned
    "stone_store": 1088724690920542248,  # mentioned
    "swallow": 1024566199733981199,  # mentioned
    "transcend": 1077866297716658206,  # mentioned
    "unlearn": 1024566199859806258,  # mentioned
}

HELP_PAGES = {
    "Cultivation": [
        """
        You begin your cultivation journey as a mere mortal. By sending messages in the server and interacting with Starfall, you gain experience points (EXP) that allow you to rank up and become stronger. 

Various Starfall interactions grant **cultivation EXP**. These actions may consume **energy**, which regenerates over time and can be checked using </energy:1024566199595585544>.
- </cultivate exp:1024566199528468508>: Use to gain a small amount of EXP, up to once every minute.
- </beast hunt:1024566199733981200>: Hunting beasts grants EXP; available after you breakthrough to <@&825908022933061664>.
- You can also gain EXP by attacking raid beasts in <#1013308720639385620> channel. EXP given scales with damage done to the beast.
- Each message sent or Starfall command used grants EXP up to a certain limit, which is refreshed daily.

You can check your cultivation progress by using the </rank:1024566199528468507> command.

Once you have accumulated enough EXP, you will be able to break through to the next **Fight sublevel**. To do so, use the </breakthrough:1024566199528468509> command.

After successfully breaking through to the next sublevel, a temporary timeout begins during which you cannot gain EXP and cannot use commands. Therefore, choose breakthrough times carefully.""",

        """The **ranks** in Starfall are modelled after Battle Through The Heavens, with 12 initial major classes (**Fight Disciple** to **Fight Saint**), culminating in the highest rank on the Dou Qi Continent, **Fight God**.

To break through to Fight God, **Origin Qi** (`originqi`) is additionally required. Origin Qi rarely drops from certain basic commands. If you have reached the EXP limit before Fight God, you may find </cultivate cp:1024566199528468508> useful for transforming excess EXP to CP.

The road doesn't end there, however. By becoming both a Fight God and Tier 10 Alchemist, you may </transcend:1077866297716658206> to a **Heavenly Sovereign** in the Great Thousand World, a higher realm above the Dou Qi Continent. The ultimate cultivation rank is **Ruler**, with the top three Rulers (based on EXP) bearing the title of **The Great Ruler**.

All ranks are described in https://discord.com/channels/352517656814813185/1010020397640585256/1013323939260411914. You can check the server's cultivator ranking using </leaderboard:1024566199595585540> with `type:Exp`.

*Best wishes on your cultivation journey!*"""
    ],

    "Alchemy and Crafting": ["""In Starfall, you have the ability to practice **alchemy**. Alchemy involves refining **pills** using medicinal herbs and other ingredients. Successfully refined pills can then be consumed to grant special effects such as combat buffs.

To begin, acquire **herbs** by using the </search:1024566199528468503> command. You will also need a **cauldron** to perform alchemy. Cauldrons can be crafted using </craft menu:1067016004141592657> from materials dropped by beasts in </beast hunt:1024566199733981200>. Equip a cauldron using </equip:1024566199733981198>.

Once you've equipped a cauldron and have enough ingredients, use </pills:1024566199528468502> to select a pill to refine. Upon successfully refining a pill, you gain **alchemy EXP**. Accumulating enough alchemy EXP automatically levels up your **alchemy tier**, which affects your pill refinement success rate. Check the alchemy profile of yourself or others using the </alchemy:1024566199528468501> command.
""",

                             """Possessing a **flame** can greatly aid in pill refinement. You get a **Dou Qi flame** by default that upgrades with your Fight class. After acquiring a **beast flame** or **Heavenly Flame**, you have the option of swallowing it in order to use it via the </swallow:1024566199733981199> command. If you want to possess more than one flame, you will need to firstly </ring equip:1067016004141592658> an **Acceptance Stone** (`accept_stone`), which is craftable, and then </stone_store:1088724690920542248> the extra flame.

Consume pills using the </consume:1024566199733981197> command. You can also earn quite a bit of money by selling your pills using the </sell:1024566199733981196> command. Detailed information about pill requirements, effects and sell price can be found via </info:1024566199595585545>.

In addition to **cauldrons**, **runes** (used to access specific areas in </beast hunt:1024566199733981200>), **Divine Meat** (to feed to pets), **rings** (for additional storage) and more can be crafted using </craft menu:1067016004141592657>. A percentage of materials can be refunded for cauldrons using </dismantle:1077866297716658207>.

Unlike refining pills through alchemy, crafting is guaranteed to succeed. However, you can only craft items at most one tier above your **crafting tier**. Craft to gain **crafting EXP**, which automatically levels up crafting tier, and check your progress using </craft profile:1067016004141592657>."""
                             ],
    "Combat and Pets": [
        """
        There are two modes of combat in Starfall: **beast PVE** and **PVP**. In both forms of combat, your strength depends on a value called **Combat Power (CP)** derived from your Fight class, main pet, as well as learned **Qi Method** and **Fight Techniques**.

        To learn a Qi Method or Fight Technique, use the </learn:1024566199733981203> command. Currently, you can have a limit of 3 Fight Techniques and 1 Qi Method learned at any point in time. Unlearn a technique to make room for others using </unlearn:1024566199859806258>. View your combat stats in </profile:1024566199595585539>.
        """,
        """
        **PVE :**\nCurrently, you can hunt beasts using the </beast hunt:1024566199733981200> command, which automatically seeks out and deals one attack to a beast of equal or lesser rank relative to your Fight class. Player attack damage scales with CP. If you are unable to kill the beast in one hit, you gain EXP proportional to damage dealt. If you are able to kill the beast, it has a chance of dropping **beast materials** and at most one **Monster Core** and **egg**.

        Every 12 hours, powerful beasts raid the <#1013308720639385620> channel. You can attack raid beasts within a short period up to three times for free, plus an additional three times costing energy. EXP rewards are granted based on proportion of damage dealt to the beast by all players. Raid beasts can drop **beast flames** and **Beast Amplifiers** (used to reroll pet stats).
        """,
        """
        If you obtain a beast egg, you can use </hatch:1077866297716658209> to hatch it into your very own **pet**! You can keep up to 20 pets. From </pet manage:1077866297716658208>, you can view information about your pets, release pets, and set your **main pet**.

        Once you've set a main pet, you can feed it using </pet feed:1077866297716658208>, which increases your pet's EXP. Gaining EXP allows your pet to increase its rank. At certain stages, you can </pet evolve:1077866297716658208> it into its next evolution. View information about your main pet using </pet view:1077866297716658208>; set its nickname using </pet nickname:1077866297716658208>.

        Your main pet helps you in combat by contributing its CP to yours. Its CP growth rate is randomly determined within a range; this can be rerolled using </pet reroll:1077866297716658208> with a Beast Amplifier (dropped by raid beasts).

        If you'd like to turn some of your eggs into beast drops of equivalent tier, you can do that using </exchange:1086540121723109387>.
        """,
        """
        **PVP :**\nTo participate in ranked PVP, use the </ranked match:1024566199733981201> command. Matchmaking is randomized within 1 subrank of your current elo. You can check your elo using </ranked profile:1024566199733981201>, and you can see the leaderboard using </ranked top:1024566199733981201>. Currently, the winner of each match is determined OHKO-style with your win probability depending only on your CP during the match. If you win, you gain a certain number of “rank points”; otherwise, you lose points.
        
        The elo system consists of the following four ranks: **Huang**, **Xuan**, **Di**, and **Tian**, each split into Low, Middle and High subranks. Each subrank takes 100 points to advance. Once you reach the top of the High subrank of a rank, your next three matches constitute BO3 (best of 3) promos to advance to the next rank. If you fail to promote, you drop back to 75 points. If instead you reach the bottom of a subrank, losing the next match causes you to demote to 75 points in the subrank below.
        """,
        """
        Note that opponents in PVP matches passively gain/lose rank points simply by being matched with players who submit the </ranked match:1024566199733981201> command. However, once an opponent user would otherwise enter promos, their rank points are frozen at the top of the High subrank and they can no longer be matched against until they initiate promos themselves. Additionally, opponent users cannot be demoted through major ranks.
        
        One daily reward for PVP is given at a set time each day (12 AM EST/UTC-5), based only on your subrank. There will also be seasonal rewards. All PVP rewards consist of gold and **Arena Coins**, a second type of currency only obtainable through PVP. Arena Coins can be used to purchase items in the **Arena Shop**, accessed via </shop:1024566199733981194>.
        """
    ],
    "Inventory and Economy": [
        """
        The primary currency in Starfall is called **gold**. Gold can be used to purchase various useful items from the shop, accessed through the </shop:1024566199733981194> command. You can find out detailed information about items using the </info:1024566199595585545> command in combination with the item’s ID. Purchase items from the shop using </buy:1024566199733981195>.
        
        The </daily:1024566199528468504> command provides a daily stipend of a randomized amount of gold that increases with Fight class. Other sources of gold include selling items and combat rewards. You can check your gold balance using the </balance:1024566199528468505> command.

        Aside from gold, you can purchase certain items using **Arena Coins** in the Arena Shop section of `/shop`. Arena Coins are a special currency only obtainable from PVP daily and seasonal rewards.
        """,
        """
        Inventory management is an important part of Starfall. Each item is associated with a **weight** that represents how much space it takes in your inventory. All players have a **base inventory** of capacity 80wt. To get more storage space, you must acquire **Storage Rings** either from the shop or through crafting. Rings reside in your base inventory and can be equipped using </ring equip:1067016004141592658>.
        
        To view all items in your base inventory or equipped ring inventory, use </inventory view:1024566199595585543> (can filter items by category). To search for a specific item by item ID, use </inventory search:1024566199595585543>.

        You can only add, view and sell items in your equipped ring. However, items may be transferred directly from one ring to another using </ring transfer:1067016004141592658>, regardless of your currently equipped ring.
        """,
        """
        Players may sell and buy items from each other in the **market**. List item(s) for sale using </market add:1024566199859806259>. To check your active listings, use </market items:1024566199859806259>. Browse other players’ listings using </market search:1024566199859806259>, where you can also buy anything you like.

        Market transactions are subject to taxes, and there is a cap on the number of listings you can have at any one time. By participating in the market frequently, you will gain **points** that increase your **market tier**, which affects these taxes. Check your market tier using </market profile:1024566199859806259>.
        """
    ],
    "Full Command List": [
        """
- </alchemy:1024566199528468501>: Check alchemy profile
- </balance:1024566199528468505>: Check gold/Arena Coin balance
- </beast hunt:1024566199733981200>: Hunt beasts for EXP, drops
- </breakthrough:1024566199528468509>: Breakthrough to next Fight sublevel
- </buy:1024566199733981195>: Buy an item from the shop
- </consume:1024566199733981197>: Consume a pill
- </craft menu:1067016004141592657>: View crafting options
- </craft profile:1067016004141592657>: Check crafting profile
- </cultivate exp:1024566199528468508>: Answer simple question to cultivate EXP
- </cultivate cp:1024566199528468508>: Transform unneeded EXP to CP
- </daily:1024566199528468504>: Get daily gold reward
- </dismantle:1077866297716658207>: Refund cauldron mats
- </energy:1024566199595585544>: Check energy
- </equip:1024566199733981198>: Equip a storage ring
- </exchange:1086540121723109387>: Exchange pet egg for beast drop
- </hatch:1077866297716658209>: Hatch a pet egg
""",
        """
- </help:1024566199595585542>: Show help
- </info:1024566199595585545>: Show info for specific item
- </inventory view:1024566199595585543>: View base/equipped ring inventory
- </inventory search:1024566199595585543>: Search inventory by item ID
- </leaderboard:1024566199595585540>: View leaderboards
- </learn:1024566199733981203>: Learn a Qi Method/Fight Technique
- </market add:1024566199859806259>: Add item to the market
- </market items:1024566199859806259>: Show items listed on the market
- </market profile:1024566199859806259>: Check market profile
- </market search:1024566199859806259>: Browse market
- </pet view:1077866297716658208>: Show main pet info
- </pet manage:1077866297716658208>: View pets, set main pet, release pets
- </pet nickname:1077866297716658208>: Set nickname for main pet
- </pet feed:1077866297716658208>: Feed main pet
- </pet evolve:1077866297716658208>: Evolve main pet
- </pet reroll:1077866297716658208>: Reroll quality of main pet
""",
        """
- </pills:1024566199528468502>: View pill refining options
- </profile:1024566199595585539>: Check overall profile
- </rank:1024566199528468507>: Check cultivation progress
- </ranked match:1024566199733981201>: Engage in PVP match
- </ranked top:1024566199733981201>: View PVP leaderboard
- </ranked profile:1024566199733981201>: Check PVP profile
- </ring transfer:1067016004141592658>: Transfer item between rings
- </ring equip:1067016004141592658>: Equip a ring
- </search:1024566199528468503>: Search for herbs
- </sell:1024566199733981196>: Sell an item
- </shop:1024566199733981194>: View the shop
- </stone_store:1088724690920542248>: Store flame in Acceptance Stone
- </swallow:1024566199733981199>: Swallow a flame
- </transcend:1077866297716658206>: Transcend beyond Fight God
- </unlearn:1024566199859806258>: Unlearn a Qi Method/Fight Technique
"""
    ],
}


class HelpDropdown(disnake.ui.Select):

    def __init__(self):
        options = [
            *(disnake.SelectOption(label=name, value=name) for name in HELP_PAGES.keys()),
        ]

        super().__init__(
            custom_id="help_categories",
            placeholder="Select a category",
            max_values=1,
            options=options,
        )

    async def callback(self, inter):
        self.view.embeds = self.view.prepare_embeds(inter.values[0])
        self.view.embed_count = 0
        self.view.prev_page.disabled = True
        self.view.next_page.disabled = False
        if len(self.view.embeds) <= 1:
            self.view.next_page.disabled = True
        await inter.response.edit_message(embed=self.view.embeds[0], view=self.view)


class HelpMenu(disnake.ui.View):
    def __init__(self, bot, author):
        super().__init__(timeout=None)
        self.add_item(HelpDropdown())

        self.author = author
        self.bot = bot
        self.embeds = self.prepare_embeds(list(HELP_PAGES.keys())[0])
        self.embed_count = 0

        self.prev_page.disabled = True
        if len(self.embeds) <= 1:
            self.next_page.disabled = True

        for i, embed in enumerate(self.embeds):
            embed.set_footer(text=f"Page {i + 1} of {len(self.embeds)}")

    async def interaction_check(self, inter):
        return inter.author == self.author

    @disnake.ui.button(emoji=LEFT, style=disnake.ButtonStyle.secondary)
    async def prev_page(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        self.embed_count -= 1

        embed = self.embeds[self.embed_count]

        self.next_page.disabled = False
        if self.embed_count == 0:
            self.prev_page.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

    @disnake.ui.button(emoji=RIGHT, style=disnake.ButtonStyle.secondary)
    async def next_page(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        self.embed_count += 1
        embed = self.embeds[self.embed_count]

        self.prev_page.disabled = False
        if self.embed_count == len(self.embeds) - 1:
            self.next_page.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

    def prepare_embeds(self, category):
        embeds = []
        raw_text_list = HELP_PAGES[category]

        for text in raw_text_list:
            embed = disnake.Embed(
                title=category,
                description=text,
                color=disnake.Color(0x2e3135)
            )
            embeds.append(embed)

        for i, embed in enumerate(embeds):
            embed.set_footer(text=f"Page {i + 1} of {len(embeds)}")

        return embeds


class Help(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    # //////////////////////////////////////// #

    @commands.slash_command(name="help", description="Shows the help page")
    async def slash_help(self, inter: disnake.CommandInteraction):
        value = """
        **Starfall** is a Discord RPG bot based on the story of **Battle Through The Heavens** (斗破苍穹) by Tian Can Tu Dou (天蚕土豆). Cultivate, fight beasts, refine pills, craft items, learn techniques, enter ranked matches with other players and more in your journey to reach the peak of the **Dou Qi Continent**.

        Want more information? Use the dropdown below to select a category.
- Cultivation
- Alchemy and Crafting
- Combat and Pets
- Inventory and Economy
- **Full Command List**
        """
        embed = disnake.Embed(
            title="Help Page",
            description=value,
            color=disnake.Color(0x2e3135)
        )
        view = HelpMenu(self.bot, inter.author)
        await inter.response.send_message(embed=embed, view=view)

    @commands.command()
    @commands.default_member_permissions(manage_guild=True)
    async def system_stats(self):
        machine = platform.machine()
        comp_name = platform.node()
        sys_os = platform.platform()
        processor = platform.processor()
        py_version = platform.python_version()


    @commands.Cog.listener()
    async def on_slash_command_error(self, inter: disnake.ApplicationCommandInteraction, error: Exception):

        if isinstance(error, commands.errors.CommandOnCooldown):
            try:
                await inter.response.defer(ephemeral=True)
            except disnake.NotFound:
                return

            e_time = round(error.retry_after, 1)
            content = f"Command under cooldown, try again after <t:{int(time() + e_time)}:R>"

            await inter.edit_original_message(content=content)

        elif isinstance(error, commands.errors.MissingPermissions):
            try:
                await inter.response.defer(ephemeral=True)
            except disnake.NotFound:
                return

            await inter.edit_original_message(content="The command is locked")

        elif isinstance(error, commands.errors.CheckFailure):
            try:
                await inter.response.defer(ephemeral=True)
            except disnake.NotFound:
                return

            await inter.edit_original_message(content="❕ You can **not** do that here.")

        else:
            log_event(inter.author.id, "command", f"Encountered error while invoking /{inter.application_command.qualified_name}: {error} ({type(error)})")
            try:
                er_guild = self.bot.get_guild(352517656814813185)
                er_channel = er_guild.get_channel(1010451695274315836)
            except:
                er_guild = self.bot.get_guild(779435063678861383)
                er_channel = er_guild.get_channel(998876223256154112)

            etype = type(error)
            trace = error.__traceback__

            lines = traceback.format_exception(etype, error, trace)
            traceback_text = ''.join(lines)

            embed = disnake.Embed(
                title="Error",
                description=f"Author : {inter.author.mention} \n\n Command : `/{inter.data.name}` \n\n```Python\n{traceback_text[:3500]}```",
                color=disnake.Color(C_Nothing)
            )
            await er_channel.send(embed=embed)

        """elif isinstance(error, commands.errors.CommandInvokeError):
            try:
                await ctx.response.defer(ephemeral=True)
            except disnake.NotFound:
                return

            await ctx.edit_original_message(content="Send a message once to get registered! \n*Still getting this? Contact `Classified154#0008`*")
        """


def setup(bot):
    bot.add_cog(Help(bot))
    print("[Help] Loaded")

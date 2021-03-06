import discord
from discord.ext import commands

from Cogs.BaseCog import BaseCog
from Util import GearbotLogging, Utils, Configuration, Pages, MessageUtils
from Util.Converters import UserID, Guild, DiscordUser


class Admin(BaseCog):

    def __init__(self, bot):
        super().__init__(bot)

    async def cog_check(self, ctx):
        return ctx.author.id in Configuration.get_master_var("BOT_ADMINS", [])

    @commands.command()
    async def setstatus(self, ctx, type:int, *, status:str):
        await self.bot.change_presence(activity=discord.Activity(name=status, type=type))
        await ctx.send("Status updated")

    @commands.command()
    async def reloadconfigs(self, ctx:commands.Context):
        async with ctx.typing():
            Configuration.load_master()
            await Configuration.initialize(self.bot)
        await ctx.send("Configs reloaded")

    @commands.command()
    async def mutuals(self, ctx, user:UserID):
        mutuals = []
        for guild in self.bot.guilds:
            if guild.get_member(user) is not None:
                mutuals.append(guild)
        for page in Pages.paginate("\n".join(f"{guild.id} - {Utils.clean_name(guild.name)}" for guild in mutuals), prefix="```py\n", suffix="```"):
            await ctx.send(page)

    @commands.command()
    async def block_server(self, ctx, guild: Guild):
        blocked = Configuration.get_persistent_var("server_blocklist", [])
        blocked.append(guild.id)
        Configuration.set_persistent_var("server_blocklist", blocked)
        await guild.leave()
        await MessageUtils.send_to(ctx, "YES", f"{Utils.escape_markdown(guild.name)} (``{guild.id}``) has been added to the blocked servers list", translate=False)
        await GearbotLogging.bot_log(
            f"{Utils.escape_markdown(guild.name)} (``{guild.id}``) has been added to the blocked server list by {Utils.clean_user(ctx.author)}")

    @commands.command()
    async def block_user(self, ctx, user:DiscordUser):
        for guild in self.bot.guilds:
            if guild.owner is not None and guild.owner.id == user.id:
                await guild.leave()
        blocked = Configuration.get_persistent_var("user_blocklist", [])
        blocked.append(user.id)
        Configuration.set_persistent_var("user_blocklist", blocked)
        await MessageUtils.send_to(ctx, "YES", f"{Utils.clean_user(user)} (``{user.id}``) has been added to the blocked users list", translate=False)
        await GearbotLogging.bot_log(f"{Utils.clean_user(user)} (``{user.id}``) has been added to the blocked users list by {Utils.clean_user(ctx.author)}")

def setup(bot):
    bot.add_cog(Admin(bot))

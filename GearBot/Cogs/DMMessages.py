import discord
from discord.ext import commands

from Cogs.BaseCog import BaseCog
from Util import Configuration


class DMMessages(BaseCog):

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is not None or len(message.content) > 1800 or message.author.id == self.bot.user.id:
            return
        if message.author.id in Configuration.get_persistent_var("user_blocklist", []):
            return
        ctx: commands.Context = await self.bot.get_context(message)
        if ctx.command is not None:
            return
        channel = self.bot.get_channel(Configuration.get_master_var("inbox", 0))
        if channel is None:
            return
        await channel.send(f"[`{message.created_at.strftime('%c')}`] {message.author} (`{message.author.id}`) said: {message.clean_content}")
        for attachement in message.attachments:
            await channel.send(attachement.url)


def setup(bot):
    bot.add_cog(DMMessages(bot))

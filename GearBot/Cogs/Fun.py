import asyncio
import time
from datetime import datetime

import discord
from discord.ext import commands

from Cogs.BaseCog import BaseCog
from Util import Configuration, MessageUtils, Translator, Utils
from Util.Converters import ApexPlatform
from Util.JumboGenerator import JumboGenerator


class Fun(BaseCog):

    def __init__(self, bot):
        super().__init__(bot)

    @commands.command()
    @commands.bot_has_permissions(attach_files=True)
    async def jumbo(self, ctx, *, emojis: str):
        """jumbo_help"""
        await JumboGenerator(ctx, emojis).generate()

def setup(bot):
    bot.add_cog(Fun(bot))

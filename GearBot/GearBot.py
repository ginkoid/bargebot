# force it to use v6 instead of v7
import discord.http
discord.http.Route.BASE = 'https://discord.com/api/v6'

import os
from argparse import ArgumentParser

from Bot import TheRealGearBot
from Bot.GearBot import GearBot
from Util import Configuration, GearbotLogging
from discord import Intents, MemberCacheFlags

def prefix_callable(bot, message):
    return TheRealGearBot.prefix_callable(bot, message)


if __name__ == '__main__':
    GearbotLogging.init_logger()
    token = Configuration.get_master_var("LOGIN_TOKEN")
    args = {
        "command_prefix": prefix_callable,
        "case_insensitive": True,
        "max_messages": None,
        "intents": Intents(
            guilds=True,
            members=True,
            bans=True,
            emojis=True,
            integrations=False,
            webhooks=False,
            invites=False,
            voice_states=True,
            presences=False,
            messages=True,
            reactions=True,
            typing=False,
        ),
        "member_cache_flags": MemberCacheFlags(
            online=False,
            voice=True,
            joined=True,
        )
    }
    gearbot = GearBot(**args)
    gearbot.remove_command("help")
    GearbotLogging.info("Ready to go, spinning up the gears")
    gearbot.run(token)
    GearbotLogging.info("GearBot shutting down, cleaning up")
    gearbot.database_connection.close()
    GearbotLogging.info("Cleanup complete")

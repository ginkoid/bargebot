from Bot import TheRealGearBot
from Bot.GearBot import GearBot
from Util import Configuration, GearbotLogging
from discord import Intents, MemberCacheFlags

def prefix_callable(bot, message):
    return TheRealGearBot.prefix_callable(bot, message)

if __name__ == '__main__':
    GearbotLogging.init_logger()
    token = Configuration.get_master_var("LOGIN_TOKEN")
    gearbot = GearBot(
        command_prefix=prefix_callable,
        case_insensitive=True,
        max_messages=None,
        intents=Intents(
            guilds=True,
            members=True,
            bans=True,
            emojis=True,
            voice_states=True,
            messages=True,
            reactions=True
        ),
        member_cache_flags=MemberCacheFlags(
            online=False,
            voice=True,
            joined=True,
        ),
        chunk_guilds_at_startup=False
    )
    gearbot.remove_command("help")
    GearbotLogging.info("Ready to go, spinning up the gears")
    gearbot.run(token)

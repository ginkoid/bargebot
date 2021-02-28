import asyncio
import concurrent
import signal
from concurrent.futures._base import CancelledError

import sys
import time
import traceback
from datetime import datetime

import aiohttp
import aioredis
from aiohttp import ClientOSError, ServerDisconnectedError
from discord import Activity, Embed, Colour, Message, TextChannel, Forbidden, ConnectionClosed, Guild
from discord.abc import PrivateChannel
from discord.ext import commands

from Util import Configuration, GearbotLogging, Emoji, Pages, Utils, Translator, InfractionUtils, MessageUtils, \
    ServerInfo
from Util.Permissioncheckers import NotCachedException
from Util.Utils import to_pretty_time
from database import DatabaseConnector


def prefix_callable(bot, message):
    user_id = bot.user.id
    prefixes = [f'<@!{user_id}> ', f'<@{user_id}> '] #execute commands by mentioning
    if message.guild is None:
        prefixes.append('!') #use default ! prefix in DMs
    elif bot.STARTUP_COMPLETE:
        prefixes.append(Configuration.get_var(message.guild.id, "GENERAL", "PREFIX"))
    return prefixes

async def initialize(bot, startup=False):
    #lock event handling while we get ready
    bot.locked = True
    try:
        #database
        GearbotLogging.info("Connecting to the database.")
        await DatabaseConnector.init()
        GearbotLogging.info("Database connection established.")

        Emoji.initialize(bot)
        Utils.initialize(bot)
        InfractionUtils.initialize(bot)
        bot.data = {
            "forced_exits": set(),
            "unbans": set(),
            "message_deletes": set(),
            "nickname_changes": set()
        }
        await GearbotLogging.initialize(bot, Configuration.get_master_var("BOT_LOG_CHANNEL"))
        if startup:
            GearbotLogging.info(f"GearBot spinning up")
            await GearbotLogging.bot_log(f"{Emoji.get_chat_emoji('ALTER')} GearBot spinning up")

        if bot.redis_pool is None:
            try:
                socket = Configuration.get_master_var("REDIS_SOCKET", "")
                if socket == "":
                    bot.redis_pool = await aioredis.create_redis_pool((Configuration.get_master_var('REDIS_HOST', "localhost"), Configuration.get_master_var('REDIS_PORT', 6379)), encoding="utf-8", db=0)
                else:
                    bot.redis_pool = await aioredis.create_redis_pool(socket, encoding="utf-8", db=0)
            except OSError:
                GearbotLogging.error("==============Failed to connect to redis==============")
                await GearbotLogging.bot_log(f"{Emoji.get_chat_emoji('NO')} Failed to connect to redis, caching unavailable")
            else:
                GearbotLogging.info("Redis connection established")
                await GearbotLogging.bot_log(f"{Emoji.get_chat_emoji('YES')} Redis connection established, let's go full speed!")

        if bot.aiosession is None:
            bot.aiosession = aiohttp.ClientSession()

        await Translator.initialize(bot)
        bot.being_cleaned.clear()
        await Configuration.initialize(bot)
    except Exception as ex:
        #make sure we always unlock, even when something went wrong!
        bot.locked = False
        raise ex
    bot.locked = False



async def on_ready(bot):
    try:
        if not bot.STARTUP_COMPLETE:
            await initialize(bot, True)
            #shutdown handler for clean exit on linux
            try:
                for signame in ('SIGINT', 'SIGTERM'):
                    asyncio.get_event_loop().add_signal_handler(getattr(signal, signame),
                                            lambda: asyncio.ensure_future(Utils.cleanExit(bot, signame)))
            except Exception as e:
                pass #doesn't work on windows


            bot.start_time = datetime.utcnow()
            GearbotLogging.info("Loading cogs...")
            for extension in Configuration.get_master_var("COGS"):
                try:
                    bot.load_extension("Cogs." + extension)
                except Exception as e:
                    await handle_exception(f"Failed to load cog {extension}", bot, e)
            GearbotLogging.info("Cogs loaded")

            to_unload = Configuration.get_master_var("DISABLED_COMMANDS", [])
            for c in to_unload:
                bot.remove_command(c)

            bot.STARTUP_COMPLETE = True
            info = await bot.application_info()
            gears = [Emoji.get_chat_emoji(e) for e in ["WOOD", "STONE", "IRON", "GOLD", "DIAMOND"]]
            a = " ".join(gears)
            b = " ".join(reversed(gears))
            await GearbotLogging.bot_log(message=f"{a} All gears turning at full speed, {info.name} ready to go! {b}")
            await bot.change_presence(activity=Activity(type=3, name='the gears turn'))
        else:
            await bot.change_presence(activity=Activity(type=3, name='the gears turn'))

        bot.missing_guilds = []
        bot.missing_guilds = {g.id for g in bot.guilds}
        if bot.loading_task is not None:
            bot.loading_task.cancel()
        bot.loading_task = asyncio.create_task(fill_cache(bot))

    except Exception as e:
        await handle_exception("Ready event failure", bot, e)


async def fill_cache(bot):
    try:
        while len(bot.missing_guilds) > 0:
            await GearbotLogging.bot_log(f"{Emoji.get_chat_emoji('CLOCK')} Requesting member info for {len(bot.missing_guilds)} guilds")
            start_time = time.time()
            old = len(bot.missing_guilds)
            while len(bot.missing_guilds) > 0:
                tasks = []
                try:
                    tasks = [asyncio.create_task(cache_guild(bot, guild_id)) for guild_id in bot.missing_guilds]
                    await asyncio.wait_for(asyncio.gather(*tasks), 600)
                except (CancelledError, concurrent.futures._base.CancelledError):
                    pass
                except concurrent.futures._base.TimeoutError:
                    if old == len(bot.missing_guilds):
                        await GearbotLogging.bot_log(f"{Emoji.get_chat_emoji('NO')} Timed out fetching member chunks canceling all pending fetches to try again!")
                        for task in tasks:
                            task.cancel()
                        await asyncio.sleep(1)
                        continue
                except Exception as e:
                    await handle_exception("Fetching member info", bot, e)
                else:
                    if old == len(bot.missing_guilds):
                        await GearbotLogging.bot_log(f"{Emoji.get_chat_emoji('NO')} Timed out fetching member chunks canceling all pending fetches to try again!")
                        for task in tasks:
                            task.cancel()
                        continue
            end = time.time()
            pretty_time = to_pretty_time(end - start_time, None)
            await GearbotLogging.bot_log(f"{Emoji.get_chat_emoji('YES')} Finished fetching member info in {pretty_time}")
            bot.initial_fill_complete=True
    except Exception as e:
        await handle_exception("Guild fetching failed", bot, e)
    finally:
        bot.loading_task = None

async def cache_guild(bot, guild_id):
    guild = bot.get_guild(guild_id)
    await guild.chunk(cache=True)
    if guild_id in bot.missing_guilds:
        bot.missing_guilds.remove(guild_id)

async def on_message(bot, message:Message):
    if message.author.bot:
        if message.author.id == bot.user.id:
            bot.self_messages += 1
        else:
            bot.bot_messages += 1
        return
    ctx: commands.Context = await bot.get_context(message)
    bot.user_messages += 1
    if ctx.valid and ctx.command is not None:
        bot.commandCount += 1
        if isinstance(ctx.channel, TextChannel) and not ctx.channel.permissions_for(ctx.channel.guild.me).send_messages:
            try:
                await ctx.author.send("Hey, you tried triggering a command in a channel I'm not allowed to send messages in. Please grant me permissions to reply and try again.")
            except Forbidden:
                pass  # closed DMs
            return
        if ctx.author.id in Configuration.get_persistent_var("user_blocklist", []):
            return
        await bot.invoke(ctx)


async def on_guild_join(bot, guild: Guild):
    blocked = Configuration.get_persistent_var("server_blocklist", [])
    if guild.id in blocked:
        await guild.leave()
        await GearbotLogging.bot_log(f"Someone tried to add me to blocked guild {await Utils.clean(guild.name)} ({guild.id})")
    elif guild.owner_id in Configuration.get_persistent_var("user_blocklist", []):
        await guild.leave()
        await GearbotLogging.bot_log(f"Someone tried to add me to {await Utils.clean(guild.name)} ({guild.id}) but the owner {guild.owner_id} is blocked")
    else:
        bot.missing_guilds.add(guild.id)
        await guild.chunk(cache=True)
        bot.missing_guilds.remove(guild.id)
        GearbotLogging.info(f"A new guild came up: {guild.name} ({guild.id}).")
        Configuration.load_config(guild.id)
        await GearbotLogging.bot_log(f"{Emoji.get_chat_emoji('JOIN')} A new guild came up: {await Utils.clean(guild.name)} ({guild.id}).", embed=ServerInfo.server_info_embed(guild))

async def on_guild_remove(guild):
    blocked = Configuration.get_persistent_var("server_blocklist", [])
    blocked_users = Configuration.get_persistent_var("user_blocklist", [])
    if guild.id not in blocked and guild.owner_id not in blocked_users:
        GearbotLogging.info(f"I was removed from a guild: {guild.name} ({guild.id}).")
        await GearbotLogging.bot_log(f"{Emoji.get_chat_emoji('LEAVE')} I was removed from a guild: {await Utils.clean(guild.name)} ({guild.id}).", embed=ServerInfo.server_info_embed(guild))


async def on_guild_update(before, after):
    if after.owner is not None and after.owner_id in Configuration.get_persistent_var("user_blocklist", []):
        await after.leave()
        await GearbotLogging.bot_log(f"Someone transferred {await Utils.clean(after.name)} ({after.id}) to {after.owner_id} but they are blocked")

class PostParseError(commands.BadArgument):

    def __init__(self, type, error):
        super().__init__(None)
        self.type = type
        self.error=error


async def on_command_error(bot, ctx: commands.Context, error):
    if isinstance(error, NotCachedException):
        if bot.loading_task is not None:
            if bot.initial_fill_complete:
                await ctx.send(f"{Emoji.get_chat_emoji('CLOCK')} Due to a earlier connection failure the cached data for this guild is no longer up to date and is being rebuild. Please try again in a few minutes.")
            else:
                await ctx.send(f"{Emoji.get_chat_emoji('CLOCK')} GearBot is in the process of starting up and has not received the member info for this guild. Please try again in a few minutes.")
        else:
            await ctx.send(f"{Emoji.get_chat_emoji('CLOCK')} GearBot only just joined this guild and is still receiving the initial member info for this guild, please try again in a few seconds")
    if isinstance(error, commands.BotMissingPermissions):
        GearbotLogging.error(f"Encountered a permission error while executing {ctx.command}: {error}")
        await ctx.send(error)
    elif isinstance(error, commands.CheckFailure):
        if ctx.command.qualified_name != "latest" and ctx.guild is not None and Configuration.get_var(ctx.guild.id, "GENERAL", "PERM_DENIED_MESSAGE"):
            await MessageUtils.send_to(ctx, 'LOCK', 'permission_denied')
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(error)
    elif isinstance(error, commands.MissingRequiredArgument):
        param = list(ctx.command.params.values())[min(len(ctx.args) + len(ctx.kwargs), len(ctx.command.params))]
        bot.help_command.context = ctx
        await ctx.send(
            f"{Emoji.get_chat_emoji('NO')} {Translator.translate('missing_arg', ctx, arg=param._name, error=Utils.replace_lookalikes(str(error)))}\n{Emoji.get_chat_emoji('WRENCH')} {Translator.translate('command_usage', ctx, usage=bot.help_command.get_command_signature(ctx.command))}")
    elif isinstance(error, PostParseError):
        bot.help_command.context = ctx
        await ctx.send(f"{Emoji.get_chat_emoji('NO')} {Translator.translate('bad_argument', ctx, type=error.type, error=Utils.replace_lookalikes(str(error.error)))}\n{Emoji.get_chat_emoji('WRENCH')} {Translator.translate('command_usage', ctx, usage=bot.help_command.get_command_signature(ctx.command))}")
    elif isinstance(error, commands.BadArgument):
        param = list(ctx.command.params.values())[min(len(ctx.args) + len(ctx.kwargs), len(ctx.command.params))]
        bot.help_command.context = ctx
        await ctx.send(f"{Emoji.get_chat_emoji('NO')} {Translator.translate('bad_argument', ctx, type=param._name, error=Utils.replace_lookalikes(str(error)))}\n{Emoji.get_chat_emoji('WRENCH')} {Translator.translate('command_usage', ctx, usage=bot.help_command.get_command_signature(ctx.command))}")
    elif isinstance(error, commands.CommandNotFound):
        return

    else:
        await handle_exception("Command execution failed", bot, error.original if hasattr(error, "original") else error, ctx=ctx)
        # notify caller
        e = Emoji.get_chat_emoji('BUG')
        if ctx.channel.permissions_for(ctx.me).send_messages:
            await ctx.send(f"{e} Something went wrong while executing that command {e}")



def extract_info(o):
    info = ""
    if hasattr(o, "__dict__"):
        info += str(o.__dict__)
    elif hasattr(o, "__slots__"):
        items = dict()
        for slot in o.__slots__:
            try:
                items[slot] = getattr(o, slot)
            except AttributeError:
                pass
        info += str(items)
    else:
        info += str(o) + " "
    return info

async def on_error(bot, event, *args, **kwargs):
    t, exception, info = sys.exc_info()
    await handle_exception("Event handler failure", bot, exception, event, None, None, *args, **kwargs)

async def handle_exception(exception_type, bot, exception, event=None, message=None, ctx = None, *args, **kwargs):
    bot.errors = bot.errors + 1
    embed = Embed(colour=Colour(0xff0000), timestamp=datetime.utcfromtimestamp(time.time()))

    # something went wrong and it might have been in on_command_error, make sure we log to the log file first
    lines = [
        "\n===========================================EXCEPTION CAUGHT, DUMPING ALL AVAILABLE INFO===========================================",
        f"Type: {exception_type}"
    ]

    arg_info = ""
    for arg in list(args):
        arg_info += extract_info(arg) + "\n"
    if arg_info == "":
        arg_info = "No arguments"

    kwarg_info = ""
    for name, arg in kwargs.items():
        kwarg_info += "{}: {}\n".format(name, extract_info(arg))
    if kwarg_info == "":
        kwarg_info = "No keyword arguments"

    lines.append("======================Exception======================")
    lines.append(f"{str(exception)} ({type(exception)})")

    lines.append("======================ARG INFO======================")
    lines.append(arg_info)

    lines.append("======================KWARG INFO======================")
    lines.append(kwarg_info)

    lines.append("======================STACKTRACE======================")
    tb = "".join(traceback.format_tb(exception.__traceback__))
    lines.append(tb)

    if message is None and event is not None and hasattr(event, "message"):
        message = event.message

    if message is None and ctx is not None:
        message = ctx.message

    if message is not None and hasattr(message, "content"):
        lines.append("======================ORIGINAL MESSAGE======================")
        lines.append(message.content)
        if message.content is None or message.content == "":
            content = "<no content>"
        else:
            content = message.content
        embed.add_field(name="Original message", value=Utils.trim_message(content, 1000), inline=False)

        lines.append("======================ORIGINAL MESSAGE (DETAILED)======================")
        lines.append(extract_info(message))

    if event is not None:
        lines.append("======================EVENT NAME======================")
        lines.append(event)
        embed.add_field(name="Event", value=event)


    if ctx is not None:
        lines.append("======================COMMAND INFO======================")

        lines.append(f"Command: {ctx.command.name}")
        embed.add_field(name="Command", value=ctx.command.name)

        channel_name = 'Private Message' if isinstance(ctx.channel, PrivateChannel) else f"{ctx.channel.name} (`{ctx.channel.id}`)"
        lines.append(f"Channel: {channel_name}")
        embed.add_field(name="Channel", value=channel_name, inline=False)

        sender = f"{str(ctx.author)} (`{ctx.author.id}`)"
        lines.append(f"Sender: {sender}")
        embed.add_field(name="Sender", value=sender, inline=False)

    lines.append("===========================================DATA DUMP COMPLETE===========================================")
    GearbotLogging.error("\n".join(lines))

    for t in [ConnectionClosed, ClientOSError, ServerDisconnectedError]:
        if isinstance(exception, t):
            return
    #nice embed for info on discord

    embed.set_author(name=exception_type)
    embed.add_field(name="Exception", value=f"{str(exception)} (`{type(exception)}`)", inline=False)
    parts = Pages.paginate(tb, max_chars=1024)
    num = 1
    for part in parts:
        embed.add_field(name=f"Traceback {num}/{len(parts)}", value=part)
        num += 1
    try:
        await GearbotLogging.bot_log(embed=embed)
    except Exception as ex:
        GearbotLogging.error(
            f"Failed to log to botlog, either Discord broke or something is seriously wrong!\n{ex}")
        GearbotLogging.error(traceback.format_exc())

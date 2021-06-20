import asyncio
import json
import os
import subprocess
from collections import namedtuple, OrderedDict
from datetime import datetime
from json import JSONDecodeError
from subprocess import Popen
from pyseeyou import format

import discord
import math
from discord import NotFound, DiscordException

from Util import GearbotLogging, Translator, Emoji, Configuration, MessageUtils
from Util.Matchers import ROLE_ID_MATCHER, CHANNEL_ID_MATCHER, ID_MATCHER, EMOJI_MATCHER, URL_MATCHER
from database import DatabaseConnector

BOT = None

def initialize(actual_bot):
    global BOT
    BOT = actual_bot


def fetch_from_disk(filename, alternative=None):
    try:
        with open(f"{filename}.json", encoding="UTF-8") as file:
            return json.load(file)
    except FileNotFoundError:
        if alternative is not None:
            return fetch_from_disk(alternative)
    except JSONDecodeError:
        if alternative is not None:
            return fetch_from_disk(alternative)
    return dict()

def save_to_disk(filename, dict):
    with open(f"{filename}.json", "w", encoding="UTF-8") as file:
        json.dump(dict, file, indent=4, skipkeys=True, sort_keys=True)


async def cleanExit(bot, trigger):
    await GearbotLogging.bot_log(f"Shutdown triggered by {trigger}.")
    await DatabaseConnector.close()
    GearbotLogging.info("Closed database connection")
    await bot.aiosession.close()
    GearbotLogging.info("Closed http session")
    await bot.close()
    GearbotLogging.info("Closed gateway connection")


def trim_message(message, limit):
    if len(message) < limit - 3:
        return message
    return f"{message[:limit-3]}..."

def chunk_message(message, limit):
    result = []
    r = range(0, len(message), limit-6)
    for i, pos in enumerate(r):
        chunk = ""
        if i > 0:
            chunk = "..."
        chunk += message[pos:pos+limit-6]
        if i < len(r) - 1:
            chunk += "..."
        result.append(chunk)
    return result

async def empty_list(ctx, action):
    message = await ctx.send(Translator.translate('m_nobody', ctx, action=action))

replacements = {
    "`": "ˋ"
}

def replace_lookalikes(text):
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text


async def clean(text, guild:discord.Guild=None, markdown=True, links=True, emoji=True, lookalikes=True):
    text = str(text)

    if guild is not None:
        # resolve user mentions
        for uid in set(ID_MATCHER.findall(text)):
            name = "@" + await username(int(uid), False, False)
            text = text.replace(f"<@{uid}>", name)
            text = text.replace(f"<@!{uid}>", name)

        # resolve role mentions
        for uid in set(ROLE_ID_MATCHER.findall(text)):
            role = discord.utils.get(guild.roles, id=int(uid))
            if role is None:
                name = "@UNKNOWN ROLE"
            else:
                name = "@" + role.name
            text = text.replace(f"<@&{uid}>", name)

        # resolve channel names
        for uid in set(CHANNEL_ID_MATCHER.findall(text)):
            channel = guild.get_channel(uid)
            if channel is None:
                name = "#UNKNOWN CHANNEL"
            else:
                name = "#" + channel.name
            text = text.replace(f"<@#{uid}>", name)

        # re-assemble emoji so such a way that they don't turn into twermoji

    urls = set(URL_MATCHER.findall(text))

    if lookalikes:
        text = replace_lookalikes(text)

    if markdown:
        text = escape_markdown(text)
    else:
        text = text.replace("@", "@\u200b").replace("**", "*​*").replace("``", "`​`")

    if emoji:
        for e in set(EMOJI_MATCHER.findall(text)):
            a, b, c = zip(e)
            text = text.replace(f"<{a[0]}:{b[0]}:{c[0]}>", f"<{a[0]}\\:{b[0]}\\:{c[0]}>")

    if links:
        #find urls last so the < escaping doesn't break it
        for url in urls:
            text = text.replace(escape_markdown(url), f"<{url}>")

    return text

def escape_markdown(text):
    text = str(text)
    for c in ["\\", "*", "_", "~", "|", "{", ">"]:
        text = text.replace(c, f"\\{c}")
    return text.replace("@", "@\u200b")

def clean_name(text):
    if text is None:
        return None
    return str(text).replace("@","@\u200b").replace("**", "*\u200b*").replace("``", "`\u200b`")


known_invalid_users = []
user_cache = OrderedDict()


async def username(uid, fetch=True, clean=True):
    user = await get_user(uid, fetch)
    if user is None:
        return "UNKNOWN USER"
    if clean:
        return clean_user(user)
    else:
        return f"{user.name}#{user.discriminator}"


async def get_user(uid, fetch=True):
    UserClass = namedtuple("UserClass", "name id discriminator bot avatar_url created_at is_avatar_animated mention")
    user = BOT.get_user(uid)
    if user is None:
        if uid in known_invalid_users:
            return None

        if BOT.redis_pool is not None:
            userCacheInfo = await BOT.redis_pool.hgetall(f"users:{uid}")

            if len(userCacheInfo) == 8: # It existed in the Redis cache, check length cause sometimes somehow things are missing, somehow
                userFormed = UserClass(
                    userCacheInfo["name"],
                    userCacheInfo["id"],
                    userCacheInfo["discriminator"],
                    userCacheInfo["bot"] == "1",
                    userCacheInfo["avatar_url"],
                    datetime.fromtimestamp(float(userCacheInfo["created_at"])),
                    bool(userCacheInfo["is_avatar_animated"]) == "1",
                    userCacheInfo["mention"]
                )

                return userFormed
            if fetch:
                try:
                    user = await BOT.fetch_user(uid)
                    pipeline = BOT.redis_pool.pipeline()
                    pipeline.hmset_dict(f"users:{uid}",
                        name = user.name,
                        id = user.id,
                        discriminator = user.discriminator,
                        bot = int(user.bot),
                        avatar_url = str(user.avatar_url),
                        created_at = user.created_at.timestamp(),
                        is_avatar_animated = int(user.is_avatar_animated()),
                        mention = user.mention
                    )

                    pipeline.expire(f"users:{uid}", 3000) # 5 minute cache life

                    BOT.loop.create_task(pipeline.execute())

                except NotFound:
                    known_invalid_users.append(uid)
                    return None
        else: # No Redis, using the dict method instead
            if uid in user_cache:
                return user_cache[uid]
            if fetch:
                try:
                    user = await BOT.fetch_user(uid)
                    if len(user_cache) >= 10: # Limit the cache size to the most recent 10
                        user_cache.popitem()
                    user_cache[uid] = user
                except NotFound:
                    known_invalid_users.append(uid)
                    return None
    return user


def clean_user(user):
    if user is None:
        return "UNKNOWN USER"
    return f"{escape_markdown(replace_lookalikes(user.name))}#{user.discriminator}"

def username_from_user(user):
    if user is None:
        return "UNKNOWN USER"
    return user.name

def pad(text, length, char=' '):
    return f"{text}{char * (length-len(text))}"

async def execute(command):
    p = Popen(command, cwd=os.getcwd(), shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    while p.poll() is None:
        await asyncio.sleep(1)
    out, error = p.communicate()
    return p.returncode, out.decode('utf-8').strip(), error.decode('utf-8').strip()

def find_key(data, wanted):
    for k, v in data.items():
        if v == wanted:
            return k

def chunks(l, n):
    for i in range(0, len(l), n):
        yield l[i:i+n]

def to_pretty_time(seconds, guild_id):
    seconds = max(round(seconds, 2), 0)
    partcount = 0
    parts = {
        'weeks': 60 * 60 * 24 * 7,
        'days': 60 * 60 * 24,
        'hours_solo': 60 * 60,
        'minutes': 60,
        'seconds': 1
    }
    duration = ""

    if seconds < 1:
       return Translator.translate("seconds", guild_id, amount=seconds)


    for k, v in parts.items():
        if seconds / v >= 1:
            amount = math.floor(seconds / v)
            seconds -= amount * v
            if partcount == 1:
                duration += ", "
            duration += " " + Translator.translate(k, guild_id, amount=amount)
        if seconds == 0:
            break
    return duration.strip()



def assemble_attachment(channel, aid, name):
    return f"https://media.discordapp.net/attachments/{channel}/{aid}/{name}"


async def get_member(bot, guild, user_id):
    member = guild.get_member(user_id)
    if member is None and guild.id in bot.missing_guilds:
        try:
            member = await guild.fetch_member(user_id)
        except DiscordException:
            return None
    return member


async def send_infraction(bot, user, guild, emoji, type, reason, **kwargs):
    if await get_member(bot, guild, user.id) is None:
        return
    try:
        override = Configuration.get_var(guild.id, "INFRACTIONS", type.upper())
        kwargs.update(
            reason=reason,
            server=guild.name,
            guild_id=guild.id
        )
        if override is not None:
            message = f"{Emoji.get_chat_emoji(emoji)} {format(override, kwargs, Configuration.get_var(guild.id, 'GENERAL', 'LANG'))}```{reason}```"
        else:
           message = f"{Emoji.get_chat_emoji(emoji)} {Translator.translate(f'{type.lower()}_dm', guild.id, **kwargs)}```{reason}```"
        parts = message.split("```")
        out = ""
        wrap = False
        while len(parts) > 0:
            temp = parts.pop(0)
            added = 6 if wrap else 0
            chars = "```" if wrap else ""
            if (len(out) + len(temp) + added) > 2000:
                await user.send(out)
                temp = ""
            out = f"{out}{chars}{temp}{chars}"
            wrap = not wrap
        if len(out) > 0:
            await user.send(out)
    except (discord.HTTPException, AttributeError):
        GearbotLogging.log_key(guild.id, f'{type}_could_not_dm', user=clean_user(user), userid=user.id)
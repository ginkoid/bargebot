import datetime
import io

import discord
import pytz

from Util import Utils, GearbotLogging, Translator, Emoji, Configuration

async def archive_purge(bot, guild_id, messages):
    channel = bot.get_channel(list(messages.values())[0].channel)
    out = f"purged at {datetime.datetime.now()} from {channel.name}\n"
    out += await pack_messages(messages.values(), guild_id)
    buffer = io.BytesIO()
    buffer.write(out.encode())
    GearbotLogging.log_key(guild_id, 'purged_log', count=len(messages), channel=channel.mention, file=(buffer, "purged_messages_archive.txt"))

async def pack_messages(messages, guild_id):
    out = ""
    for message in messages:
        name = await Utils.username(message.author, clean=False)
        reply = ""
        if message.reply_to is not None:
            reply = f" | In reply to https://discord.com/channels/{message.server}/{message.channel}/{message.reply_to}"
        timestamp = datetime.datetime.strftime(discord.Object(message.messageid).created_at.astimezone(pytz.timezone(Configuration.get_var(guild_id, 'GENERAL', 'TIMEZONE'))),'%H:%M:%S')
        out += f"{timestamp} {message.server} - {message.channel} - {message.messageid} | {name} ({message.author}) | {message.content}{reply} | {(', '.join(Utils.assemble_attachment(message.channel, attachment.id, attachment.name) for attachment in message.attachments))}\r\n"
    return out

async def ship_messages(ctx, messages, response_content):
    if len(messages) > 0:
        message_list = dict()
        for message in messages:
            message_list[message.messageid] = message
        messages = []
        for mid, message in sorted(message_list.items()):
            messages.append(message)
        out = await pack_messages(messages, ctx.guild.id)
        buffer = io.BytesIO()
        buffer.write(out.encode())
        buffer.seek(0)
        file = discord.File(fp=buffer, filename="message_archive.txt")
        await ctx.send(f"{Emoji.get_chat_emoji('YES')} {response_content}", file=file)
    else:
        await ctx.send(f"{Emoji.get_chat_emoji('WARNING')} {response_content}")

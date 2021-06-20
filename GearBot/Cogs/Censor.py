import re
from collections import namedtuple
import fnmatch
from urllib import parse
from urllib.parse import urlparse

import discord
import emoji
from discord import DMChannel
from discord.ext import commands

from Cogs.BaseCog import BaseCog
from Util import Configuration, GearbotLogging, Permissioncheckers, Utils, MessageUtils, Translator
from Util.Matchers import INVITE_MATCHER, URL_MATCHER
from Util.Utils import assemble_jumplink
from database.DatabaseConnector import LoggedAttachment

EMOJI_REGEX = re.compile('([^<]*)<a?:(?:[^:]+):([0-9]+)>')
messageholder = namedtuple('censored_message', 'id author channel guild')
class Censor(BaseCog):

    def __init__(self, bot):
        super().__init__(bot)
        self.regexes = dict()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.webhook_id is not None or message.channel is None or isinstance(message.channel, DMChannel) or not Configuration.get_var(message.channel.guild.id, "CENSORING", "ENABLED") or self.bot.user.id == message.author.id:
            return
        member = message.guild.get_member(message.author.id) #d.py is weird
        if member is None:
            return
        if message.reference is not None and message.reference.channel_id == message.channel.id:
            reply = message.reference.message_id
        else:
            reply = None
        await self.check_message(member, message.content, message.channel, message.id, False, reply, message.attachments)

    @commands.Cog.listener()
    async def on_raw_message_edit(self, event: discord.RawMessageUpdateEvent):
        channel = self.bot.get_channel(int(event.data["channel_id"]))
        m = await MessageUtils.get_message_data(self.bot, event.message_id)
        if channel is None or isinstance(channel, DMChannel) or not Configuration.get_var(channel.guild.id, "CENSORING", "ENABLED") or "content" not in event.data:
            return
        author_id=None
        if m is not None:
            author_id = m.author
            reply = m.reply_to
        else:
            permissions = channel.permissions_for(channel.guild.me)
            if permissions.read_message_history:
                try:
                    message = await channel.fetch_message(event.message_id)
                except (discord.NotFound, discord.Forbidden): # we should never get forbidden, be we do, somehow
                    return
                else:
                    author_id = message.author.id
                    if message.reference is not None and message.reference.channel_id == message.channel.id:
                        reply = message.reference.message_id

        member = await Utils.get_member(self.bot, channel.guild, author_id)
        if member is not None and author_id != self.bot.user.id:
            await self.check_message(member, event.data["content"], channel, event.message_id, True, reply, None)

    async def check_message(self, member, content, channel, message_id, edit, reply, attachments):
        if Permissioncheckers.get_user_lvl(member.guild, member) >= 2:
            return
        censorlist = Configuration.get_var(member.guild.id, "CENSORING", "TOKEN_CENSORLIST")
        word_censorlist = Configuration.get_var(member.guild.id, "CENSORING", "WORD_CENSORLIST")
        guilds = Configuration.get_var(member.guild.id, "CENSORING", "ALLOWED_INVITE_LIST")
        domain_list = Configuration.get_var(member.guild.id, "CENSORING", "DOMAIN_LIST")
        domains_allowed = Configuration.get_var(member.guild.id, "CENSORING", "DOMAIN_LIST_ALLOWED")
        full_message_list = Configuration.get_var(member.guild.id, "CENSORING", "FULL_MESSAGE_LIST")
        censor_emoji_message = Configuration.get_var(member.guild.id, "CENSORING", "CENSOR_EMOJI_ONLY_MESSAGES")
        content = content.replace('\\', '')
        decoded_content = parse.unquote(content)

        if len(guilds) != 0:
            codes = INVITE_MATCHER.findall(decoded_content)
            for code in codes:
                try:
                    invite: discord.Invite = await self.bot.fetch_invite(code)
                except discord.NotFound:
                    await self.censor_invite(member, message_id, channel, code, "INVALID INVITE", content, edit, reply, attachments)
                    return
                if invite.guild is None:
                    await self.censor_invite(member, message_id, channel, code, "DM group", content, edit, reply, attachments)
                    return
                else:
                    if invite.guild is None or (not invite.guild.id in guilds and invite.guild.id != member.guild.id):
                        await self.censor_invite(member, message_id, channel, code, invite.guild.name, content, edit, reply, attachments)
                        return

        content = content.lower()

<<<<<<< HEAD
        for bad in full_message_list:
            if fnmatch.fnmatchcase(content, bad.lower()):
                await self.censor_message(message_id, content, channel, member, "", "_content", edit=edit)
                return

        for bad in censorlist:
            if fnmatch.fnmatchcase(content, f'*{bad.lower()}*'):
                await self.censor_message(message_id, content, channel, member, bad, edit=edit)
=======
        if content in full_message_list:
            await self.censor_message(message_id, content, channel, member, "", "_content", edit=edit, reply=reply, attachments=attachments)
            return

        for bad in (w.lower() for w in censorlist):
            if bad in content:
                await self.censor_message(message_id, content, channel, member, bad, edit=edit, reply=reply, attachments=attachments)
>>>>>>> f2c416a (add replies and attachments in censor messages)
                return

        if len(word_censorlist) > 0:
            if channel.guild.id not in self.regexes:
                regex = re.compile(r"\b(" + '|'.join(re.escape(word) for word in word_censorlist) + r")\b", re.IGNORECASE)
                self.regexes[channel.guild.id] = regex
            else:
                regex = self.regexes[channel.guild.id]
            match = regex.findall(content)
            if len(match):
                await self.censor_message(message_id, content, channel, member, match[0], "_word", edit=edit, reply=reply, attachments=attachments)
                return

        if len(domain_list) > 0:
            link_list = URL_MATCHER.findall(content)
            for link in link_list:
                url = urlparse(link)
                domain = url.hostname
                if (domain in domain_list) is not domains_allowed:
                    await self.censor_message(message_id, content, channel, member, url.hostname, "_domain_blocked", edit=edit, reply=reply, attachments=attachments)
                    return

        if censor_emoji_message and content is not None and len(content) > 0:
            new_content = ''.join(c for c in content if c not in emoji.UNICODE_EMOJI)
            new_content = re.sub(EMOJI_REGEX, '', new_content)
            if new_content == '':
                await self.censor_message(message_id, content, channel, member, '', "_emoji_only", edit=edit, reply=reply, attachments=attachments)
                return




    async def censor_message(self, message_id, content, channel, member, bad, key="", edit=False, reply="", attachments=""):
        e = '_edit' if edit else ''
        clean_message = await Utils.clean(content, channel.guild, markdown=False)
        reply_str = ""
        if reply is not None:
            reply_str = f"\n**{Translator.translate('in_reply_to', member.guild.id)}: **<{assemble_jumplink(member.guild.id, channel, reply)}>"

        if attachments is None:
            attachments = await LoggedAttachment.filter(message=message_id)

        if len(attachments) > 0:
            attachments_str = f"**{Translator.translate('attachments', member.guild.id, count=len(attachments))}:** "
            attachments_str += ', '.join(Utils.assemble_attachment(channel, attachment.id, attachment.filename if hasattr(attachment, "filename") else attachment.name) for attachment in attachments)
        else:
            attachments_str = ""
        clean_message = Utils.trim_message(clean_message, 1600 - len(attachments_str) - len(reply_str))
        if channel.permissions_for(channel.guild.me).manage_messages:
            try:
                self.bot.data["message_deletes"].add(message_id)
                await channel.delete_messages([discord.Object(message_id)])
            except discord.NotFound as ex:
                pass
            else:
                GearbotLogging.log_key(channel.guild.id, f'censored_message{key}{e}', user=member, user_id=member.id,
                                       message=clean_message, sequence=bad, channel=channel.mention,
                                       reply=reply_str, attachments=attachments_str)
        else:
            GearbotLogging.log_key(channel.guild.id, f'censored_message_failed{key}{e}', user=member,
                                   user_id=member.id, message=clean_message, sequence=bad,
<<<<<<< HEAD
                                   link=f'https://discord.com/channels/{channel.guild.id}/{channel.id}/{message_id}')
=======
                                   link='https://discord.com/channels/{0}/{1}/{2}'.format(channel.guild.id, channel.id, message_id),
                                   reply=reply_str, attachments=attachments_str)
>>>>>>> f2c416a (add replies and attachments in censor messages)
        self.bot.dispatch("user_censored", messageholder(message_id, member, channel, channel.guild))

    async def censor_invite(self, member, message_id, channel, code, server_name, content, edit, reply, attachments):
        # Allow for users with a trusted role, or trusted users, to post invite links
        if Configuration.get_var(member.guild.id, "CENSORING", "ALLOW_TRUSTED_BYPASS") and Permissioncheckers.is_trusted(
                member):
            return

        e = '_edit' if edit else ''

        self.bot.data["message_deletes"].add(message_id)
        clean_message = await Utils.clean(content, member.guild)
        clean_name = Utils.clean_user(member)
        reply_str = ""
        if reply is not None:
            reply_str = f"\n**{Translator.translate('in_reply_to', member.guild.id)}: **<{assemble_jumplink(member.guild.id, channel, reply)}>"

        if attachments is None:
            attachments = await LoggedAttachment.filter(message=message_id)

        if len(attachments) > 0:
            attachments_str = f"**{Translator.translate('attachments', member.guild.id, count=len(attachments))}:** "
            attachments_str += ', '.join(Utils.assemble_attachment(channel, attachment.id, attachment.filename if hasattr(attachment, "filename") else attachment.name) for attachment in attachments)
        else:
            attachments_str = ""
        clean_message = Utils.trim_message(clean_message, 1600 - len(attachments_str) - len(reply_str))
        try:
            await channel.delete_messages([discord.Object(message_id)])
            GearbotLogging.log_key(member.guild.id, f'censored_invite{e}', user=clean_name, code=code, message=clean_message,
                                   server_name=server_name, user_id=member.id,
                                   channel=channel.mention, attachments=attachments_str,
                                   reply=reply_str)
        except discord.NotFound:
            # we failed? guess we lost the race, log anyways
            GearbotLogging.log_key(member.guild.id, f'invite_censor_fail{e}', user=clean_name, code=code,
                                   message=clean_message, server_name=server_name, user_id=member.id,
                                   channel=channel.mention)
            if message_id in self.bot.data["message_deletes"]:
                self.bot.data["message_deletes"].remove(message_id)
        except discord.Forbidden:
            GearbotLogging.log_key(member.guild.id, f'invite_censor_forbidden{e}', user=clean_name, code=code,
                                   message=clean_message, server_name=server_name, user_id=member.id,
                                   channel=channel.mention, attachments=attachments_str,
                                   reply=reply_str)
            if message_id in self.bot.data["message_deletes"]:
                self.bot.data["message_deletes"].remove(message_id)

        self.bot.dispatch("user_censored", messageholder(message_id, member, channel, channel.guild))

def setup(bot):
    bot.add_cog(Censor(bot))

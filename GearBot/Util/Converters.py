import discord
from discord import NotFound, Forbidden, HTTPException
from discord.ext.commands import UserConverter, BadArgument, Converter, NoPrivateMessage, UserNotFound

from Bot.TheRealGearBot import PostParseError
from Util import Utils, Configuration, Translator, Confirmation
from Util.Matchers import *
from database.DatabaseConnector import LoggedMessage, Infraction, Reminder, ReminderStatus


class TranslatedBadArgument(BadArgument):
    def __init__(self, key, ctx, arg=None, **kwargs):
        super().__init__(
            Translator.translate(key, ctx, arg=Utils.trim_message(Utils.clean_name(str(arg)), 1000), **kwargs))


class BannedMember(Converter):
    async def convert(self, ctx, argument):
        try:
            entity = await ctx.guild.fetch_ban(await DiscordUser().convert(ctx, argument))
        except NotFound:
            raise TranslatedBadArgument("not_banned", ctx)
        return entity

class ServerMember(Converter):
    async def convert(self, ctx, argument):
        if ctx.guild is None:
            raise NoPrivateMessage()
        member = None
        user_id = None
        username = None
        discrim = None

        match = ID_MATCHER.match(argument)
        if match is not None:
            argument = match.group(1)

        try:
            user_id = int(argument)
            member = ctx.guild.get_member(user_id)
        except ValueError:
            parts = argument.split('#')
            if len(parts) == 2 and parts[1].isnumeric():
                username = parts[0]
                discrim = parts[1]
            elif len(parts) == 1:
                username = argument

        if member is not None:
            return member

        if user_id is not None:
            a = await getMessageAuthor(ctx, ctx.guild.id, user_id)
            if a is not None:
                member = await Utils.get_member(ctx.bot, ctx.guild, a.id)
            if member is not None:
                return member
            else:
                raise UserNotFound(argument)



        for m in ctx.guild.members:
            if username is not None:
                potential = None
                if (discrim is None and (m.name.startswith(username)  or (m.nick is not None and m.nick.startswith(username)))) or \
                    (discrim is not None and (m.name == username or m.nick == username)):
                    potential = m
                if potential is not None:
                    if member is not None:
                        raise TranslatedBadArgument('multiple_potential_targets', ctx)
                    member = potential
                    if discrim is not None:
                        break
        if member is not None:
            return member
        return m


async def getMessageAuthor(ctx, guild_id, message_id):
    message = await LoggedMessage.get_or_none(server=guild_id, messageid=message_id)
    if message is not None:
        user = ctx.bot.get_user(message.author)
        if user is not None:
            ok = False

            async def yes():
                nonlocal ok
                ok = True
            await Confirmation.confirm(ctx, Translator.translate('use_message_author', ctx, user=Utils.clean_user(user), user_id=user.id), on_yes=yes, confirm_cancel=False)
            if ok:
                return user
    return None

class DiscordUser(Converter):

    def __init__(self, id_only=False) -> None:
        super().__init__()
        self.id_only = id_only

    async def convert(self, ctx, argument):
        user = None
        user_id = None
        match = ID_MATCHER.match(argument)
        if match is not None:
            argument = match.group(1)
        try:
            user = await UserConverter().convert(ctx, argument)
        except BadArgument:
            try:
                user_id = await RangedInt(min=20000000000000000, max=9223372036854775807).convert(ctx, argument)
                user = await Utils.get_user(user_id)
            except (ValueError, HTTPException):
                pass

        if user is None:
            if user_id is not None:
                user = await getMessageAuthor(ctx, ctx.guild.id, argument)
            if user is None or (self.id_only and str(user.id) != argument):
                raise TranslatedBadArgument('user_conversion_failed', ctx, arg=argument)

        return user

class UserID(Converter):
    async def convert(self, ctx, argument):
        return (await DiscordUser().convert(ctx, argument)).id


class Reason(Converter):
    async def convert(self, ctx, argument):
        argument = await Utils.clean(argument.strip("|").strip(), markdown=False, links=False, emoji=False)
        for match in EMOJI_MATCHER.finditer(argument):
            argument = argument.replace(match.group(0), f":{match.group(2)}:")
        if len(argument) > 1800:
            raise TranslatedBadArgument('reason_too_long', ctx)
        return argument


class PotentialID(Converter):
    async def convert(self, ctx, argument):
        match = ID_MATCHER.match(argument)
        if match is not None:
            argument = match.group(1)
        try:
            argument = int(argument)
        except ValueError:
            raise TranslatedBadArgument("no_potential_id", ctx, arg=argument)
        else:
            return argument


class LoggingChannel(Converter):
    async def convert(self, ctx, argument):
        channels = Configuration.get_var(ctx.guild.id, "LOG_CHANNELS")
        match = CHANNEL_ID_MATCHER.match(argument)
        if match is not None:
            argument = match.group(1)
        if argument not in channels:
            raise TranslatedBadArgument('no_log_channel', ctx, arg=argument)
        return argument


class RoleMode(Converter):
    async def convert(self, ctx, argument):
        argument = argument.lower()
        options = [
            "alphabetic",
            "hierarchy",
        ]
        if argument in options:
            return argument
        raise BadArgument(f"Unknown mode, valid modes: {', '.join(options)}")


class Guild(Converter):

    async def convert(self, ctx, argument):
        try:
            argument = int(argument)
        except ValueError:
            raise BadArgument(f"Not a server ID")
        else:
            guild = ctx.bot.get_guild(argument)
            if guild is None:
                raise TranslatedBadArgument("unknown_server", ctx, arg=argument)
            else:
                return guild


class PendingReminder(Converter):
    async def convert(self, ctx, argument):
        try:
            id = int(argument)
        except ValueError:
            raise TranslatedBadArgument("reminder_unknown", ctx)
        reminder = await Reminder.get_or_none(user_id=ctx.author.id, status=ReminderStatus.Pending, id=id)
        if not reminder:
            raise TranslatedBadArgument("reminder_unknown", ctx)
        return reminder

class Message(Converter):

    def __init__(self, local_only=False) -> None:
        self.local_only = local_only

    async def convert(self, ctx, argument):
        message_id, channel_id = self.extract_ids(ctx, argument)
        message = await self.fetch_message(ctx, message_id, channel_id)
        if message is None:
            raise TranslatedBadArgument('unknown_message', ctx)
        if message.channel != ctx.channel and self.local_only:
            raise TranslatedBadArgument('message_wrong_channel', ctx)
        return message

    @staticmethod
    def extract_ids(ctx, argument):
        message_id = None
        channel_id = None
        if "-" in argument:
            parts = argument.split("-")
            if len(parts) == 2:
                try:
                    channel_id = int(parts[0].strip(" "))
                    message_id = int(parts[1].strip(" "))
                except ValueError:
                    pass
            else:
                parts = argument.split(" ")
                if len(parts) == 2:
                    try:
                        channel_id = int(parts[0].strip(" "))
                        message_id = int(parts[1].strip(" "))
                    except ValueError:
                        pass
        else:
            result = JUMP_LINK_MATCHER.match(argument)
            if result is not None:
                channel_id = int(result.group(1))
                message_id = int(result.group(2))
            else:
                try:
                    message_id = int(argument)
                except ValueError:
                    pass
        if message_id is None:
            raise TranslatedBadArgument('message_invalid_format', ctx)
        return message_id, channel_id

    @staticmethod
    async def fetch_message(ctx, message_id, channel_id):
        if channel_id is None:
            logged_message = await LoggedMessage.get_or_none(messageid=message_id)
            if logged_message is not None:
                channel_id = logged_message.channel

        if channel_id is None:
            channel = ctx.channel
        else:
            channel = ctx.bot.get_channel(channel_id)

        if not isinstance(channel, discord.TextChannel):
            raise TranslatedBadArgument('unknown_channel', ctx)

        permissions = channel.permissions_for(channel.guild.me)
        if not permissions.read_message_history:
            return
        try:
            return await channel.fetch_message(message_id)
        except (NotFound, Forbidden):
            if channel_id is None:
                raise TranslatedBadArgument('message_missing_channel', ctx)

class RangedInt(Converter):

    def __init__(self, min=None, max=None) -> None:
        self.min = min
        self.max = max

    async def convert(self, ctx, argument) -> int:
        try:
            argument = int(argument)
        except ValueError:
            raise TranslatedBadArgument('NaN', ctx)
        else:
            if self.min is not None and argument < self.min:
                raise TranslatedBadArgument('number_too_small', ctx, min=self.min)
            elif self.max is not None and argument > self.max:
                raise TranslatedBadArgument('number_too_big', ctx, max=self.max)
            else:
                return argument


class RangedIntBan(RangedInt):

    def __init__(self, ) -> None:
        super().__init__(1, 7)


class ListMode(Converter):
    async def convert(self, ctx, argument):
        argument = argument.lower()
        if argument == "allow" or argument == "allowed":
            return True
        elif argument == "block" or argument == "censor" or argument == "blocked" or argument == "deny":
            return False
        else:
            raise TranslatedBadArgument("invalid_mode", ctx)


class ReminderText(Converter):
    async def convert(self, ctx, argument):
        if len(argument) > 1800:
            raise TranslatedBadArgument('reminder_too_long', ctx)
        return argument


class InfSearchLocation(Converter):
    async def convert(self, ctx, argument):
        values = ["[mod]", "[reason]", "[user]"]
        if argument.lower() in values:
            return argument.lower()
        raise BadArgument("Does this even show up?")


class CommandModifier(Converter):
    def __init__(self, allowed_values, should_lower=True) -> None:
        self.allowed_values = allowed_values
        self.should_lower = should_lower
        super().__init__()

    async def convert(self, ctx, argument):
        if self.should_lower:
            argument = argument.lower()
        match = MODIFIER_MATCHER.match(argument)
        if match is None:
            raise BadArgument("Not a modifier")
        key = match.group(1)
        value = match.group(2)
        if key not in self.allowed_values:
            raise BadArgument("Invalid key")
        for v in self.allowed_values[key]:
            if isinstance(v, Converter):
                return key, v.convert(ctx, value)
            elif v == value:
                return key, value
        raise BadArgument("Not an acceptable value")


class InfSearchModifiers(CommandModifier):
    def __init__(self) -> None:
        super().__init__(allowed_values=dict(search=["mod", "reason", "user"]))


class ServerInfraction(Converter):

    async def convert(self, ctx, argument):
        argument = argument.strip('#')
        try:
            argument = int(argument)
        except ValueError:
            raise TranslatedBadArgument('NaN', ctx)
        infraction = await Infraction.get_or_none(id=argument, guild_id=ctx.guild.id)
        if infraction is None:
            raise TranslatedBadArgument('inf_not_found', ctx, id=argument)
        else:
            return infraction


class DurationHolder:

    def __init__(self, length, unit=None) -> None:
        super().__init__()
        self.length = length
        self.unit = unit

    def to_seconds(self, ctx):
        if self.unit is None:
            self.unit = "seconds"
        unit = self.unit.lower()
        length = self.length
        if len(unit) > 1 and unit[-1] == 's':  # plural -> singular
            unit = unit[:-1]
        if unit == 'mo' or unit == 'month':
            length = length * 30
            unit = 'd'
        if unit == 'w' or unit == 'wk' or unit == 'week':
            length = length * 7
            unit = 'd'
        if unit == 'd' or unit == 'day':
            length = length * 24
            unit = 'h'
        if unit == 'h' or unit == 'hr' or unit == 'hour':
            length = length * 60
            unit = 'm'
        if unit == 'm' or unit == 'min' or unit == 'minute':
            length = length * 60
            unit = 's'
        if unit != 's' and unit != 'sec' and unit != 'second':
            raise PostParseError('Duration', 'Not a valid duration identifier')
        if length > 60 * 60 * 24 * 365:
            raise PostParseError('Duration', Translator.translate('max_duration', ctx))
        else:
            return int(round(length))

    def __str__(self):
        if len(self.unit) == 1:
            return f"{self.length}{self.unit}"
        if self.unit[-1] != "s":
            return f"{self.length} {self.unit}s"
        return f"{self.length} {self.unit}"


class Duration(Converter):
    async def convert(self, ctx, argument):
        match = START_WITH_NUMBER_MATCHER.match(argument)
        if match is None:
            raise TranslatedBadArgument('NaN', ctx)
        group = match.group(1)
        holder = DurationHolder(float(group))
        if len(argument) > len(group):
            holder.unit = await DurationIdentifier().convert(ctx, argument[len(group):])
        return holder


class DurationIdentifier(Converter):
    async def convert(self, ctx, argument):
        if argument is None:
            argument = "seconds"
        if argument.lower() not in ["month", "months", "week", "weeks", "day", "days", "hour", "hours", "minute", "minutes", "second",
                                    "seconds", "mo", "w", "wk", "d", "h", "hr", "m", "min", "s", "sec"]:
            raise BadArgument("Invalid duration, valid identifiers: month(s), week(s), day(s), hour(s), minute(s), second(s)")
        return argument


class EmojiName(Converter):
    async def convert(self, ctx, argument):
        if len(argument) < 2 or len(argument) > 32:
            raise TranslatedBadArgument('emoji_name_too_short', ctx, argument)
        if len(argument) > 32:
            raise TranslatedBadArgument('emoji_name_too_long', ctx, argument)
        if " " in argument:
            raise TranslatedBadArgument('emoji_name_space', ctx, argument)
        return argument


class VerificationLevel(Converter):
    async def convert(self, ctx, argument):
        level = discord.VerificationLevel.__members__.get(argument.lower())
        if level is None:
            raise TranslatedBadArgument('unknown_verification_level', ctx)
        return level

class Nickname(Converter):
    async def convert(self, ctx, argument):
        if len(argument) > 32:
            raise TranslatedBadArgument('nickname_too_long', ctx)
        return argument

anti_spam_types = {
    "duplicates",
    "max_messages",
    "max_newlines",
    "max_mentions",
    "max_links",
    "max_emoji",
    "censored",
    "voice_joins"
}

class SpamType(Converter):
    async def convert(self, ctx, argument):
        if argument not in anti_spam_types:
            raise TranslatedBadArgument('invalid_anti_spam_type', ctx, types=",".join(anti_spam_types))
        return argument

anti_spam_punishments = {
    "mute",
    "kick",
    "temp_ban",
    "ban"
}

class AntiSpamPunishment(Converter):
    async def convert(self, ctx, argument):
        if argument not in anti_spam_punishments:
            raise TranslatedBadArgument('invalid_anti_spam_punishment', ctx, types=",".join(anti_spam_punishments))
        return argument

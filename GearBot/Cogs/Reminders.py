import asyncio
import time
from datetime import datetime
from tortoise.query_utils import Q

from discord import Embed, User, NotFound, Forbidden, DMChannel
from discord.ext import commands

from Bot import TheRealGearBot
from Cogs.BaseCog import BaseCog
from Util import Utils, GearbotLogging, Emoji, Translator, MessageUtils, ServerInfo
from Util.Converters import Duration, DurationHolder, ReminderText
from database.DatabaseConnector import Reminder, ReminderStatus
class Reminders(BaseCog):

    def __init__(self, bot) -> None:
        super().__init__(bot)

        self.running = True
        self.handling = set()
        self.bot.loop.create_task(self.delivery_service())

    def cog_unload(self):
        self.running = False

    @commands.group(aliases=["r", "reminder", "reminders"])
    async def remind(self, ctx):
        """remind_help"""
        if ctx.invoked_subcommand is None:
            await ctx.invoke(self.bot.get_command("help"), query="remind")

    @commands.bot_has_permissions(add_reactions=True)
    @remind.command("me", aliases=["add", "m", "a"])
    async def remind_me(self, ctx, duration: Duration, *, reminder: ReminderText):
        """remind_me_help"""
        if duration.unit is None:
            parts = reminder.split(" ")
            duration.unit = parts[0]
            reminder = " ".join(parts[1:])
        duration_seconds = duration.to_seconds(ctx)
        if duration_seconds <= 0:
            await MessageUtils.send_to(ctx, "NO", "reminder_time_travel")
            return
        if ctx.guild is not None:
            message = f'{Emoji.get_chat_emoji("QUESTION")} {Translator.translate("remind_question", ctx)}'
            one = str(Emoji.get_emoji("1"))
            two = str(Emoji.get_emoji("2"))
            no = str(Emoji.get_emoji("NO"))
            embed = Embed(description=f"""
{Emoji.get_chat_emoji("1")} {Translator.translate("remind_option_here", ctx)}
{Emoji.get_chat_emoji("2")} {Translator.translate("remind_option_dm", ctx)}
{Emoji.get_chat_emoji("NO")} {Translator.translate("remind_option_cancel", ctx)}
""")
            m = await ctx.send(message, embed=embed)
            for e in [one, two, no]:
                await m.add_reaction(e)

            try:
                reaction = await ctx.bot.wait_for('raw_reaction_add', timeout=30, check=lambda reaction: reaction.user_id == ctx.message.author.id and str(reaction.emoji) in [one, two, no] and reaction.message_id == m.id)
            except asyncio.TimeoutError:
                await MessageUtils.send_to(ctx, "NO", "confirmation_timeout", timeout=30)
                return
            else:
                if str(reaction.emoji) == no:
                    await MessageUtils.send_to(ctx, "NO", "command_canceled")
                    return
                else:
                    dm = str(reaction.emoji) == two
            finally:
                try:
                    await m.delete()
                except (NotFound, Forbidden):
                    pass

        else:
            dm = True
        r = await Reminder.create(user_id=ctx.author.id, channel_id=ctx.channel.id, dm=dm,
                        to_remind=await Utils.clean(reminder, markdown=False, links=False, emoji=False),
                        time=time.time() + duration_seconds, send=datetime.now().timestamp(), status=ReminderStatus.Pending,
                        guild_id=ctx.guild.id if ctx.guild is not None else "@me", message_id=ctx.message.id)
        if duration_seconds <= 10:
            self.handling.add(r.id)
            self.bot.loop.create_task(
                self.run_after(duration_seconds, self.deliver(r)))
        mode = "dm" if dm else "here"
        await MessageUtils.send_to(ctx, "YES", f"reminder_confirmation_{mode}", duration=duration.length,
                                     duration_identifier=duration.unit)

    @remind.command(aliases=["s"])
    async def snooze(self, ctx, duration: Duration = DurationHolder(5, 'm'), unit: str = None):
        """remind_snooze_help"""
        if duration.unit is None:
            duration.unit = unit
        duration_seconds = duration.to_seconds(ctx)
        if duration_seconds <= 0:
            await MessageUtils.send_to(ctx, "NO", "reminder_time_travel")
            return
        if isinstance(ctx.channel, DMChannel):
            target_criteria = Q(dm=1, status=ReminderStatus.DeliveredFirst) | Q(dm=0, status=ReminderStatus.DeliveredAlternative)
        else:
            target_criteria = Q(channel_id=ctx.channel.id) & (Q(dm=0, status=ReminderStatus.DeliveredFirst) | Q(dm=1, status=ReminderStatus.DeliveredAlternative))
        target_reminder = await Reminder.get_or_none(Q(user_id=ctx.author.id) & target_criteria).order_by('-time').limit(1)
        if target_reminder is None:
            await MessageUtils.send_to(ctx, "NO", "reminder_not_found")
            return
        new_reminder = target_reminder.clone()
        new_reminder._custom_generated_pk = False
        new_reminder.status = ReminderStatus.Pending
        new_reminder.send = datetime.now().timestamp()
        new_reminder.time = time.time() + duration_seconds
        await new_reminder.save()
        if duration_seconds <= 10:
            self.handling.add(new_reminder.id)
            self.bot.loop.create_task(
                self.run_after(duration_seconds, self.deliver(new_reminder)))
        mode = "dm" if new_reminder.dm else "here"
        await MessageUtils.send_to(ctx, "YES", f"reminder_confirmation_{mode}", duration=duration.length,
                                     duration_identifier=duration.unit)

    async def delivery_service(self):
        GearbotLogging.info("Starting reminder delivery background task")
        while self.running:
            now = time.time()
            limit = datetime.fromtimestamp(time.time() + 30).timestamp()

            for r in await Reminder.filter(time__lt=limit, status=ReminderStatus.Pending):
                if r.id not in self.handling:
                    self.handling.add(r.id)
                    self.bot.loop.create_task(
                        self.run_after(r.time - now, self.deliver(r)))
            await asyncio.sleep(10)
        GearbotLogging.info("Reminder delivery background task terminated")

    async def run_after(self, delay, action):
        if delay > 0:
            await asyncio.sleep(delay)
        if self.running:  # cog got terminated, new cog is now in charge of making sure this gets handled
            await action

    async def deliver(self, r):
        channel = None
        try:
            channel = await self.bot.fetch_channel(r.channel_id)
        except (Forbidden, NotFound):
            pass
        dm = await self.bot.fetch_user(r.user_id)
        first = dm if r.dm else channel
        alternative = channel if r.dm else dm

        if await self.attempt_delivery(first, r):
            r.status = ReminderStatus.DeliveredFirst
        elif await self.attempt_delivery(alternative, r):
            r.status = ReminderStatus.DeliveredAlternative
        else:
            r.status = ReminderStatus.Failed
        await r.save()

    async def attempt_delivery(self, location, package):
        try:
            if location is None:
                return False
            if package.guild_id is None:
                jumplink_available = "Unavailable"
            else:
                jumplink_available = MessageUtils.construct_jumplink(package.guild_id, package.channel_id, package.message_id)
            mode = "dm" if isinstance(location, User) else "channel"
            now = datetime.utcfromtimestamp(time.time())
            send_time = datetime.utcfromtimestamp(package.send)
            parts = {
                "date": send_time.strftime('%c'),
                "timediff": ServerInfo.time_difference(now, send_time, None if isinstance(location, User) or isinstance(location, DMChannel) else location.guild.id),
                "now_date": now.strftime('%c'),
                "jump_link": jumplink_available,
                "recipient": None if isinstance(location, User) else (await Utils.get_user(package.user_id)).mention
            }
            parcel = Translator.translate(f"reminder_delivery_{mode}", None if isinstance(location, User) or isinstance(location, DMChannel) else location, **parts)
            content = f"```\n{package.to_remind}\n```"
            try:
                if len(parcel) + len(content) < 2000:
                    await location.send(parcel + content)
                else:
                    await location.send(parcel)
                    await location.send(content)
            except (Forbidden, NotFound):
                return False
            else:
                return True
        except Exception as ex:
            await TheRealGearBot.handle_exception("Reminder delivery", self.bot, ex, None, None, None, location, package)
            return False


def setup(bot):
    bot.add_cog(Reminders(bot))

import random
import time
from datetime import datetime

import discord
from discord.ext import commands
from discord.ext.commands import clean_content, BadArgument

from Cogs.BaseCog import BaseCog
from Util import Configuration, Pages, HelpGenerator, Emoji, Translator, Utils, GearbotLogging, \
    MessageUtils, Selfroles, ReactionManager
from Util.Converters import Message, DiscordUser
from Util.Matchers import NUMBER_MATCHER, ID_NUMBER_MATCHER
from database.DatabaseConnector import LoggedAttachment


class Basic(BaseCog):

    def __init__(self, bot):
        super().__init__(bot)

        Pages.register("help", self.init_help, self.update_help)
        self.running = True
        self.bot.loop.create_task(self.selfrole_updater())

    def cog_unload(self):
        # cleanup
        Pages.unregister("help")
        self.running = False

    @commands.command()
    @commands.bot_has_permissions(embed_links=True)
    async def about(self, ctx):
        """about_help"""
        uptime = datetime.utcnow() - self.bot.start_time
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        days, hours = divmod(hours, 24)
        minutes, seconds = divmod(remainder, 60)
        user_messages = str(self.bot.user_messages)
        bot_messages = str(self.bot.bot_messages)
        self_messages = str(self.bot.self_messages)
        total = str(sum(len(guild.members) for guild in self.bot.guilds))
        unique = str(len(self.bot.users))
        embed = discord.Embed(colour=discord.Colour(0x00cea2),
                              timestamp=datetime.utcfromtimestamp(time.time()),
                              description=
                              MessageUtils.assemble(ctx, 'DIAMOND', 'about_spinning_gears', duration=Translator.translate('dhms', ctx, days=days, hours=hours, minutes=minutes, seconds=seconds)) + "\n"+
                              MessageUtils.assemble(ctx, 'GOLD', 'about_messages', user_messages=user_messages, bot_messages=bot_messages, self_messages=self_messages) + "\n"+
                              MessageUtils.assemble(ctx, 'IRON', 'about_grinders', errors=self.bot.errors) + "\n" +
                              MessageUtils.assemble(ctx, 'STONE', 'about_commands', commandCount=self.bot.commandCount, custom_command_count=self.bot.custom_command_count) + "\n" +
                              MessageUtils.assemble(ctx, 'WOOD', 'about_guilds', guilds=len(self.bot.guilds)) + "\n" +
                              MessageUtils.assemble(ctx, 'INNOCENT', 'about_users', total=total, unique=unique) + "\n" +
                              "\n[bargebot](https://github.com/ginkoid/bargebot), a fork of [GearBot](https://github.com/gearbot/GearBot)")

        embed.set_footer(text=self.bot.user.name, icon_url=self.bot.user.avatar_url)
        await ctx.send(embed=embed)

    @commands.command(hidden=True)
    async def ping(self, ctx: commands.Context):
        """ping_help"""
        t1 = time.perf_counter()
        message = await ctx.send(":ping_pong:")
        t2 = time.perf_counter()
        rest = round((t2 - t1) * 1000)
        latency = round(self.bot.latency*1000, 2)
        await message.edit(content=f":hourglass: {Translator.translate('ping_pong', ctx, rest=rest, latency=latency)} :hourglass:")


    @commands.command(aliases=["q"])
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    async def quote(self, ctx: commands.Context, *, message:Message):
        """quote_help"""
        if ctx.message.author is None:
            await MessageUtils.send_to(ctx, 'NO', 'quote_not_visible_to_user')
        else:
            try:
                member = await message.guild.fetch_member(ctx.message.author.id)
            except discord.NotFound:
                await MessageUtils.send_to(ctx, 'NO', 'quote_not_visible_to_user')
                return
            permissions = message.channel.permissions_for(member)
            if permissions.read_message_history:
                if message.channel.is_nsfw() and not ctx.channel.is_nsfw():
                    await MessageUtils.send_to(ctx, 'NO', 'quote_nsfw_refused')
                else:
                    attachment = None
                    attachments = await LoggedAttachment.filter(message_id=message.id)
                    if len(attachments) == 1:
                        attachment = attachments[0]
                    embed = discord.Embed(colour=discord.Color(0xd5fff),
                                          timestamp=message.created_at)
                    if message.content is None or message.content == "":
                        if attachment is not None:
                            url = Utils.assemble_attachment(message.channel.id, attachment.id, attachment.name)
                            if attachment.isImage:
                                embed.set_image(url=url)
                            else:
                                embed.add_field(name=Translator.translate("attachment_link", ctx),
                                                value=url)
                    else:
                        description = message.content
                        embed = discord.Embed(colour=discord.Color(0xd5fff), description=description,
                                              timestamp=message.created_at)
                        embed.add_field(name="​",
                                        value=f"[Jump to message]({message.jump_url})")
                        if attachment is not None:
                            url = Utils.assemble_attachment(message.channel.id, attachment.id, attachment.name)
                            if attachment.isImage:
                                embed.set_image(url=url)
                            else:
                                embed.add_field(name=Translator.translate("attachment_link", ctx),
                                                value=url)
                    user = message.author
                    embed.set_author(name=user.name, icon_url=user.avatar_url)
                    embed.set_footer(
                        text=Translator.translate("quote_footer", ctx,
                                                  channel=message.channel.name,
                                                  user=Utils.clean_user(ctx.author), message_id=message.id))
                    await ctx.send(embed=embed)

            else:
                await MessageUtils.send_to(ctx, 'NO', 'quote_not_visible_to_user')




    @commands.command()
    async def coinflip(self, ctx, *, thing: str = ""):
        """coinflip_help"""
        if thing == "":
            thing = Translator.translate("coinflip_default", ctx)
        else:
            thing = await Utils.clean(thing, ctx.guild)
        outcome = random.randint(1, 2)
        if outcome == 1 or ("mute" in thing and "vos" in thing):
            await ctx.send(Translator.translate("coinflip_yes", ctx, thing=thing))
        else:
            await ctx.send(Translator.translate("coinflip_no", ctx, thing=thing))




    @commands.command(aliases=["selfrole", "self_roles", "selfroles"])
    @commands.bot_has_permissions(embed_links=True, external_emojis=True, add_reactions=True)
    @commands.guild_only()
    async def self_role(self, ctx: commands.Context, *, role: str = None):
        """role_help"""
        if role is None:
            await Selfroles.create_self_roles(self.bot, ctx)
        else:
            try:
                role = await commands.RoleConverter().convert(ctx, role)
            except BadArgument as ex:
                await ctx.send(Translator.translate("role_not_found", ctx))
            else:
                roles = Configuration.get_var(ctx.guild.id, "ROLES", "SELF_ROLES")
                if role.id in roles:
                    try:
                        if role in ctx.author.roles:
                            await ctx.author.remove_roles(role)
                            await MessageUtils.send_to(ctx.channel, "YES", "role_left", role_name=await Utils.clean(role.name), user=ctx.author.name)
                        else:
                            await ctx.author.add_roles(role)
                            await MessageUtils.send_to(ctx.channel, "YES", "role_joined", role_name=await Utils.clean(role.name), user=ctx.author.name)
                    except discord.Forbidden:
                        await ctx.send(
                            f"{Emoji.get_chat_emoji('NO')} {Translator.translate('role_too_high_add', ctx, role=role.name)}")
                else:
                    await ctx.send(Translator.translate("role_not_allowed", ctx))


    @commands.command()
    @commands.bot_has_permissions(external_emojis=True, add_reactions=True)
    async def help(self, ctx, *, query: str = None):
        """help_help"""
        if query is not None and len(query) > 100:
            return #bye bye spammers
        if query is not None:
            query = ''.join(query.splitlines())
        data = {
            "trigger": ctx.message.id
        }
        if query is not None:
            data["query"] = query
        await Pages.create_new(self.bot, "help", ctx, **data)

    async def init_help(self, ctx, query=None, **kwargs):
        pages = await self.get_help_pages(ctx, query)
        if pages is None:
            query_clean = await clean_content().convert(ctx, query)
            return await clean_content().convert(ctx, Translator.translate(
                "help_not_found" if len(query) < 1500 else "help_no_wall_allowed", ctx,
                query=query_clean)), None, False
        eyes = Emoji.get_chat_emoji('EYES')
        return f"{eyes} **{Translator.translate('help_title', ctx, page_num=1, pages=len(pages))}** {eyes}```diff\n{pages[0]}```", None, len(pages) > 1

    async def update_help(self, ctx, message, page_num, action, data):
        pages = await self.get_help_pages(ctx, data.get("query", None))
        page, page_num = Pages.basic_pages(pages, page_num, action)
        eyes = Emoji.get_chat_emoji('EYES')
        data["page"] = page_num
        return f"{eyes} **{Translator.translate('help_title', ctx, page_num=page_num + 1, pages=len(pages))}**{eyes}```diff\n{page}```", None, data

    async def get_help_pages(self, ctx, query):
        if query is None:
            return await HelpGenerator.command_list(self.bot, ctx)
        else:
            if query in self.bot.cogs:
                return await HelpGenerator.gen_cog_help(self.bot, ctx, query)
            else:
                target = self.bot
                layers = query.split(" ")
                while len(layers) > 0:
                    layer = layers.pop(0)
                    if hasattr(target, "all_commands") and layer in target.all_commands.keys():
                        target = target.all_commands[layer]
                    else:
                        target = None
                        break
                if target is not None and target is not self.bot.all_commands:
                    return await HelpGenerator.gen_command_help(self.bot, ctx, target)

        return None

    @commands.command()
    async def uid(self, ctx, *, text:str):
        """uid_help"""
        parts = set()
        for p in set(ID_NUMBER_MATCHER.findall(text)):
            try:
                id = int(p)
                if id not in parts:
                    if await Utils.get_user(id) is not None:
                        parts.add(p)
            except ValueError:
                pass
        if len(parts) > 0:
            await ctx.send("\n".join(parts))
        else:
            await MessageUtils.send_to(ctx, "NO", "no_uids_found")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        roles = Configuration.get_var(role.guild.id, "ROLES", "SELF_ROLES")
        if role.id in roles:
            roles.remove(role.id)
            Configuration.save(role.guild.id)

    async def selfrole_updater(self):
        GearbotLogging.info("Selfrole view updater enabled")
        while self.running:
            guild_id = await self.bot.wait_for("self_roles_update")
            #make sure we shouldn't have terminated yet
            if not self.running:
                return
            todo = await Selfroles.self_cleaner(self.bot, guild_id)
            for t in sorted(todo, key=lambda l: l[0], reverse=True):
                await ReactionManager.on_reaction(self.bot, t[0], t[1], 0, "🔁")


def setup(bot):
    bot.add_cog(Basic(bot))

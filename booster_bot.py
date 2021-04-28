import logging
from logging import handlers
import discord
from discord.ext import commands
from discord.ext.commands.errors import CommandNotFound, MissingRequiredArgument, BadArgument, MissingAnyRole
import traceback
import asyncio
from typing import Union

from helper_functions import *
from event_objects import Boost, Booster
import config
import db_handling
import constants
import globals
import cogs

#TODO move to a better place
BOOSTER_RANKS = ['M+Booster', 'M+Blaster', 'Advertiser', 'Trial Advertiser', 'Alliance Booster', 'SL Booster', 'SL Blaster']
MNG_RANKS = ['Management', 'Support']
if config.get('debug', default=False):
    MNG_RANKS.append('Tester')
__VERSION__ = config.get('version')

if __name__ == '__main__':
    QUIT_CALLED = False

    intents = discord.Intents.default()
    intents.members = True
    intents.emojis = True
    intents.reactions = True

    logging.basicConfig(level=logging.DEBUG, format='%(asctime)-23s %(name)-12s %(levelname)-8s %(message)s')
    handler = handlers.RotatingFileHandler('logs/log', maxBytes=50 * 10 ** 20, backupCount=10, encoding='utf-8')
    formatter = logging.Formatter('%(asctime)-23s %(name)-12s %(levelname)-8s %(message)s')
    handler.setFormatter(formatter)
    logging.getLogger('').addHandler(handler)
    logging.getLogger('discord').setLevel(logging.INFO)
    logging.getLogger('websockets').setLevel(logging.INFO)
    LOG = logging.getLogger(__name__)
    client = commands.Bot(command_prefix='!', intents=intents)

    globals.init()

# --------------------------------------------------------------------------------------------------------------------------------------------

    @client.event
    async def on_ready():
        LOG.debug('Connected')
        async for guild in client.fetch_guilds():
            if guild.name == 'bot_testing' or guild.id in config.get('deployed_guilds'):
                LOG.debug(guild.id)

        await client.change_presence(activity=discord.Game(name='!help for commands'))
        globals.init_custom_emojis(client)

# --------------------------------------------------------------------------------------------------------------------------------------------

    @client.event
    async def on_message(ctx):
        if isinstance(ctx.channel, discord.channel.DMChannel):
            return
        LOG.debug(f'{ctx.content} {ctx.id}')

        if not ctx.author.bot and not QUIT_CALLED and (ctx.channel.name in config.get('cmd_channels') or (config.get('debug', default=False) and 'testing' in ctx.channel.name)):
            await client.process_commands(ctx)
        else:
            LOG.debug(f'skipping processing of msg: {ctx.author} {QUIT_CALLED} {ctx.channel}')

# --------------------------------------------------------------------------------------------------------------------------------------------

    @client.command(name='quit')
    @commands.is_owner()
    async def shutdown(ctx):
        global QUIT_CALLED

        await ctx.message.channel.send('Leaving...')
        QUIT_CALLED = True
        #to process anything in progress
        await asyncio.sleep(15)
        await client.logout()

# --------------------------------------------------------------------------------------------------------------------------------------------

    @client.command(name='gold', aliases=['g'])
    @commands.has_any_role(*MNG_RANKS)
    async def gold_add(ctx, *args):
        """
        Expected format: !g add|deduct|payout user_mention1 ... user_mentionN gold_amount [comment]
        Adds/deducts gold for specified user[s]. More than one user mention per command is allowed. Optional transaction comment can be included.
        """
        LOG.debug(f'{ctx.message.author}: {ctx.message.content}')
        mentions = []
        last_mention_idx = -1
        for idx, arg in enumerate(args):
            if is_mention(arg):
                mentions.append(arg)
                #check if mentions are continuous
                if last_mention_idx >= 0 and (idx - last_mention_idx) > 1:
                    raise BadArgument('Mentions are expected to be in a row.')
                    return

                last_mention_idx = idx

        try:
            transaction_type = args[0]
        except:
            raise BadArgument(f'Transaction type was not found in arguments: {args}')
            return

        if transaction_type not in db_handling.TRANSACTIONS:
            raise BadArgument('Unknown transaction type!')
            return

        try:
            amount = args[last_mention_idx+1]
        except:
            raise BadArgument(f'Gold amount to process was not found in arguments {args}.')
            return

        if gold_str2int(amount) > 2 ** 31 - 1:
            raise BadArgument('Only amounts between -2147483647 and 2147483647 are accepted.')
            return

        try:
            comment = args[last_mention_idx + 2]
        except IndexError:
            comment = None

        if len(args) > last_mention_idx + 2:
            raise BadArgument(f'Got too many arguments: {args}.')

        results = []
        for mention in mentions:
            nick = ctx.guild.get_member(mention2id(mention)).nick
            if nick is None:
                nick = ctx.guild.get_member(mention2id(mention)).name

            usr = client.get_user(mention2id(mention))
            try:
                db_handling.add_user(usr.id, parse_nick2realm(nick))
            except BadArgument as e:
                results.append(f':x:{mention}: Transaction with type {transaction_type}, amount {gold_str2int(amount):00} failed: {e}.')
                continue
            except:
                LOG.error(f'Database Error: {traceback.format_exc()}')
                await ctx.message.author.send(f'Critical error occured, contant administrator.')
                return

            try:
                db_handling.add_tranaction(transaction_type, usr.id, ctx.author.id, gold_str2int(amount), ctx.guild.id, comment)
            except BadArgument as e:
                results.append(f':x:{mention}: Transaction with type {transaction_type}, amount {gold_str2int(amount)} failed: {e}.')
                continue
            except:
                LOG.error(f'Database Error: {traceback.format_exc()}')
                await ctx.message.author.send('Critical error occured, contact administrator.')
                return

            results.append(f':white_check_mark:{mention}: Transaction with type {transaction_type}, amount {gold_str2int(amount)} was processed.')

        await send_channel_embed(ctx.message.channel, '\n'.join(results))

# --------------------------------------------------------------------------------------------------------------------------------------------

    @client.command(name='list-transactions', aliases=['lt'])
    @commands.has_any_role(*(BOOSTER_RANKS + MNG_RANKS))
    async def list_transactions(ctx, limit: int = 10):
        """
        Lists your past 10 transactions. Limit of transactions can be overwritten by additional parameter.
        """
        LOG.debug(f'{ctx.message.author}: {ctx.message.content}')
        if limit < 1:
            await ctx.message.author.send(f'{limit} is an invalid value to limit number of transactions!.')
            raise BadArgument(f'{limit} is an invalid value to limit number of transactions!.')
            return

        transactions = db_handling.list_transactions(ctx.message.author.id, limit)

        transactions_string = ''
        for res_t, author_id in transactions:
            author = client.get_user(author_id)
            if author is not None:
                transactions_string += res_t + f' author:{client.get_user(author_id).name}\n'
            else:
                transactions_string += res_t + f' author:{author_id}\n'

        await send_channel_embed(ctx.message.channel, transactions_string)

# --------------------------------------------------------------------------------------------------------------------------------------------

    @client.command(name='alist-transactions', alaises=['alt'])
    @commands.has_any_role(*MNG_RANKS)
    async def admin_list_transactions(ctx, mention, limit: int=10):
        """
        Lists past 10 transactions for specified user. Limit of transactions can be overwritten by additional parameter.
        """
        LOG.debug(f'{ctx.message.author}: {ctx.message.content}')
        if limit < 1:
            await ctx.message.author.send(f'{limit} is an invalid value to limit number of transactions!.')
            raise BadArgument(f'{limit} is an invalid value to limit number of transactions!.')
            return
        usr_id = mention2id(mention)
        transactions = db_handling.list_transactions(usr_id, limit)

        transactions_string = f'Last {limit} transactions for user: {ctx.guild.get_member(usr_id).name}\n'
        for res_t, author_id in transactions:
            transactions_string += res_t + f' author:{client.get_user(author_id).name}\n'

        await send_channel_embed(ctx.message.channel, transactions_string)

# --------------------------------------------------------------------------------------------------------------------------------------------

    @client.command(name='top', aliases=['t'])
    @commands.has_any_role(*(BOOSTER_RANKS + MNG_RANKS))
    async def top(ctx, limit: int = 10, *roles):
        """
        Lists top 10 boosters. Limit of listed top boosters can be overwritten by additional parameter.
        If limit is specified there are accepted role names/mentions for filtering.
        """
        LOG.debug(f'{ctx.message.author}: {ctx.message.content}')
        if limit < 1:
            await ctx.message.author.send(f'{limit} is an invalid value to limit number of boosters!.')
            raise BadArgument(f'{limit} is an invalid value to limit number of transactions!.')
            return

        role_objects = []
        for role in roles:
            if is_mention(role):
                role_object = ctx.guild.get_role(mention2id(role))
                if role_object is not None:
                    role_objects.append(role_object)
            else:
                for guild_role in ctx.guild.roles:
                    if guild_role.name == role:
                        role_objects.append(guild_role)

        top_ppl = db_handling.list_top_boosters(limit, ctx.guild.id)

        if len(role_objects) == 0:
            res_str = f'Current top {limit} boosters:\n'
        else:
            res_str = f'Current top {limit} boosters with ranks {[role.name for role in role_objects]}:\n'

        filtered_idx = 0
        result_data = []
        for idx, data in enumerate(top_ppl):
            try:
                member = ctx.guild.get_member(data[1])
                if role_objects:
                    for role in role_objects:
                        if role in member.roles:
                            result_data.append((filtered_idx + 1, member.mention, data[0]))
                            filtered_idx += 1
                            break
                else:
                    result_data.append((idx + 1, member.mention, data[0]))
            # some users can leave and still be in DB
            except AttributeError:
                LOG.warning(f'Unknown user ID: {data[1]}')
                if role_objects:
                    result_data.append((filtered_idx + 1, data[1], data[0]))
                    filtered_idx += 1
                else:
                    result_data.append((idx + 1, data[1], data[0]))

        for result in result_data:
            res_str += f'#{result[0]} {result[1]} : {result[2]}\n'
        res_str += f'Top total: {sum([x[2] for x in result_data])}'

        await send_channel_embed(ctx.message.channel, res_str)

# --------------------------------------------------------------------------------------------------------------------------------------------

    @client.command(name='realm-top', aliases=['rt', 'rtop'])
    @commands.has_any_role(*(BOOSTER_RANKS + MNG_RANKS))
    async def realm_top(ctx, realm_name: str, limit: int = 10):
        """
        Lists top 10 boosters for specific realm. Limit of listed top boosters can be overwritten by additional parameter.
        """
        LOG.debug(f'{ctx.message.author}: {ctx.message.content}')
        if limit < 1:
            await ctx.message.author.send(f'{limit} is an invalid value to limit number of boosters!')
            raise BadArgument(f'{limit} is an invalid value to limit number of transactions!')
            return

        try:
            realm_name = constants.is_valid_realm(realm_name, True)
        except:
            await ctx.message.author.send(f'{realm_name} is not a known EU realm!')
            raise BadArgument(f'{realm_name} is not a known EU realm!')
            return

        top_ppl = db_handling.list_top_boosters(limit, ctx.guild.id, realm_name)

        res_str = f'Current top boosters for realm {realm_name}:\n'
        for idx, data in enumerate(top_ppl):
            try:
                res_str += f'#{idx + 1}{ctx.guild.get_member(data[1]).mention} : {data[0]}\n'
            # some users can leave and still be in DB
            except AttributeError:
                LOG.warning(f'Unknown user ID: {data[1]}')
                res_str += f'#{idx + 1} {data[1]} : {data[0]}\n'
                continue

        res_str += f'Top total: {sum([x[0] for x in top_ppl])}'
        await send_channel_embed(ctx.message.channel, res_str)

# --------------------------------------------------------------------------------------------------------------------------------------------

    @client.command('balance', aliases=['b', 'bal'])
    @commands.has_any_role(*(BOOSTER_RANKS + MNG_RANKS))
    async def balance(ctx):
        """
        Lists your current balance.
        """
        LOG.debug(f'{ctx.message.author}: {ctx.message.content}')
        user_id = ctx.message.author.id

        try:
            balance = db_handling.get_balance(user_id, ctx.guild.id)
        except:
            LOG.error(f'Balance command error {traceback.format_exc()}')
            await client.get_user(config.get('my_id')).send(f'Balance command error {traceback.format_exc()}')
            return
    
        await ctx.message.channel.send(embed=discord.Embed(title='', description=f'Balance for {ctx.guild.get_member(user_id).mention}:\n' + balance))

# --------------------------------------------------------------------------------------------------------------------------------------------

    @client.command('abalance', aliases=['ab', 'abal'])
    @commands.has_any_role(*MNG_RANKS)
    async def admin_balance(ctx, mention: str):
        """
        Lists current balance for specified user.
        """
        LOG.debug(f'{ctx.message.author}: {ctx.message.content}')
        if is_mention(mention):
            user_id = mention2id(mention)
        else:
            raise BadArgument(f'"{mention}" is not a mention!')
            return

        try:
            balance = db_handling.get_balance(user_id, ctx.guild.id)
        except:
            LOG.error(f'Balance command error {traceback.format_exc()}')
            await client.get_user(config.get('my_id')).send(f'Balance command error {traceback.format_exc()}')
            return
    
        await ctx.message.channel.send(embed=discord.Embed(title='', description=f'Balance for {ctx.guild.get_member(user_id).mention}:\n' + balance))

# -------------------------------------------------------------------------------------------------------------------------------------------

    @client.command('alias')
    @commands.has_any_role(*MNG_RANKS)
    async def alias(ctx, alias: str, realm_name: str):
        """
        Creates/overwrites alias for a specific realm name.
        """
        LOG.debug(f'{ctx.message.author}: {ctx.message.content}')
        realm_name = constants.is_valid_realm(realm_name)
        try:
            if db_handling.add_alias(realm_name, alias):
                await ctx.message.channel.send(f'Added alias "{alias}"="{realm_name}"')
        except db_handling.DatabaseError:

            await ctx.message.channel.send(f'"{alias}" already exists overwrite[y/n]?')
            msg = await client.wait_for('message', check=msg_author_check(ctx.message.author), timeout=15)

            if msg.content not in ('y', 'n') or msg.content == 'n':
                return
            else:
                if db_handling.add_alias(realm_name, alias, update=True):
                    await ctx.message.channel.send(f'Overwritten alias "{alias}"="{realm_name}"')

# --------------------------------------------------------------------------------------------------------------------------------------------

    @client.command('remove-user', aliases=['ru'])
    @commands.has_any_role(*MNG_RANKS)
    async def remove_user(ctx, mention_or_id: Union[str, int]):
        """
        Remove user from current active users list. Does not affect past transactions for user. Can be added by a new transaction in future.
        """
        LOG.debug(f'{ctx.message.author}: {ctx.message.content}')
        if is_mention(mention_or_id):
            id = mention2id(mention_or_id)
        else:
            id = mention_or_id

        db_handling.remove_user(id)

        await ctx.message.channel.send(f'Removed user with id {id}')

# --------------------------------------------------------------------------------------------------------------------------------------------

    @client.command('attendance', aliases=['att'])
    @commands.has_any_role(*MNG_RANKS)
    async def attendance(ctx, channel_name: str):
        """
        Prints all users in a specific voice channel in a way that copied user names are transormed to mentions.
        """
        channel = discord.utils.get(ctx.message.guild.channels, name=channel_name, type=discord.ChannelType.voice)
        if channel is None:
            await ctx.message.channel.send(f'Voice channel with name "{channel_name}" not found!')
            return

        res = ' '.join([f'@{member.name}#{member.discriminator}' for member in channel.members])
        await ctx.message.channel.send(embed=discord.Embed(title=f'{len(channel.members)} member{"s" if len(channel.members) > 1 else ""} in {channel_name}:', description=f'{res}'))

# --------------------------------------------------------------------------------------------------------------------------------------------

    @client.command('track')
    @commands.has_any_role(*MNG_RANKS)
    async def track(ctx, msg_url: str, track_for: int = 24):
        """
        Starts reactions tracking (added or removed by users) for limited amount of time (hours). You can get message URL by opening extra menu by right-clicking on specific message.
        For mobile users enabling developer mode is needed to see the "copy URL" option.
        """
        #TODO validate url
        _, g_id, ch_id, msg_id = msg_url.rsplit('/', 3)
        if msg_id not in globals.tracked_msgs:
            globals.tracked_msgs[msg_id] = {'added': [], 'removed': [], 'author_id': ctx.message.author.id, 'guild_id': ctx.guild.id, 'limit': track_for, 'track_start': str(datetime.datetime.utcnow()), 'url': msg_url}

        # to be addedd in ver1.5
        # msg_ref = discord.MessageReference(message_id=msg_id, guild_id=g_id, channel_id=ch_id)
        await ctx.message.author.send(f'{msg_url}\n Tracking started for {track_for} hours.')

# --------------------------------------------------------------------------------------------------------------------------------------------

    @client.command('list-tracked')
    @commands.has_any_role(*MNG_RANKS)
    async def list_tracked(ctx, msg_url: str = None):
        """
        Lists all currently tracked messages. By supplying specific message url as additional argument only specific message tracking info is displayed.
        """
        LOG.debug(globals.tracked_msgs)

        if msg_url is not None:
            data = {msg_url.rsplit('/', 1)[1]: globals.tracked_msgs.get(msg_url.rsplit('/', 1)[1], {})}
        else:
            data = globals.tracked_msgs

        formatted_data = format_tracking_data(data, ctx.guild)

        await send_channel_message(ctx.message.author, formatted_data if len(formatted_data) > 0 else 'There are no messages currently tracked.')

# --------------------------------------------------------------------------------------------------------------------------------------------
    @client.command('boost')
    @commands.has_any_role(*(MNG_RANKS + ['Advertiser']))
    async def boost(ctx, timeout: int = 15):
        try:
            await ctx.message.channel.send('Boost pot size?')
            gold_pot = await client.wait_for('message', check=msg_author_check(ctx.message.author), timeout=timeout)
            gold_pot = gold_str2int(gold_pot.content)

            #TODO check for corrent role
            await ctx.message.channel.send('Boost advertiser?')
            advertiser_mention = await client.wait_for('message', check=msg_author_check(ctx.message.author), timeout=timeout)
            advertiser = ctx.guild.get_member(mention2id(advertiser_mention.content))
            advertiser_name = advertiser.nick if advertiser.nick is not None else advertiser.name

            realm_name = None
            while realm_name is None:
                await ctx.message.channel.send('Realm name?')
                realm_name = await client.wait_for('message', check=msg_author_check(ctx.message.author), timeout=timeout)
                try:
                    realm_name = constants.is_valid_realm(realm_name.content, check_aliases=True)
                except BadArgument as e:
                    await ctx.message.channel.send(f'{e}')
                    realm_name = None

            await ctx.message.channel.send('Want to have anyone already signed for the boost? use mention')
            boosters = await client.wait_for('message', check=msg_author_check(ctx.message.author), timeout=timeout)
            boosters = [booster for booster in boosters.content.split() if is_mention(booster)]

            boosters_objects = []
            is_anyone_keyholder = False
            for booster in boosters:
                await ctx.message.channel.send(embed=discord.Embed(description=f'Role for {booster}? One or more from: tank/dps/healer', title=''))
                roles = await client.wait_for('message', check=msg_author_check(ctx.message.author), timeout=timeout)
                roles = [role.lower() for role in roles.content.split()]
                if roles[0] in ('tank', 'dps', 'healer'):
                    boosters_objects.append(Booster(mention=booster, **{f'is_{roles[0]}': True}))
                    for role in roles[1:]:
                        boosters_objects[0].__setattr__(f'is_{role}', True)

                if not is_anyone_keyholder:
                    await ctx.message.channel.send(f'Keyholder? [y]es/[n]o')
                    keyholder = await client.wait_for('message', check=msg_author_check(ctx.message.author), timeout=timeout)
                    if keyholder.content in ('y', 'yes'):
                        boosters_objects[-1].is_keyholder = True
                        is_anyone_keyholder = True

            await ctx.message.channel.send('Dungeon key?')
            dungeon = await client.wait_for('message', check=msg_author_check(ctx.message.author), timeout=timeout)
            dungeon = dungeon.content

            await ctx.message.channel.send('Armor stack? Use role mention or "no"')
            armor_stack = await client.wait_for('message', check=msg_author_check(ctx.message.author), timeout=timeout)
            armor_stack = armor_stack.content
            if is_mention(armor_stack):
                armor_stack = ctx.guild.get_role(mention2id(armor_stack)).name
            else:
                armor_stack = 'no'

            number_of_boosts = None
            while number_of_boosts is None:
                await ctx.message.channel.send('Number of boosts?')
                number_of_boosts = await client.wait_for('message', check=msg_author_check(ctx.message.author), timeout=timeout)
                try:
                    number_of_boosts = int(number_of_boosts.content)
                except ValueError:
                    await ctx.message.channel.send(f'{number_of_boosts.content} if not a number!')
                    number_of_boosts = None

            await ctx.message.channel.send('Character to whisper?')
            char_to_whisper = await client.wait_for('message', check=msg_author_check(ctx.message.author), timeout=timeout)
            char_to_whisper = char_to_whisper.content

            await ctx.message.channel.send('Anything else to add? If not type "no".')
            note = await client.wait_for('message', check=msg_author_check(ctx.message.author), timeout=timeout)
            note = note.content
            if note in ('no', 'n'):
                note = None

        except asyncio.TimeoutError:
            await ctx.message.channel.send(f'Got no response in {timeout}s, canceling event creation.')
            return

        boost_obj = Boost(boost_author=ctx.message.author.nick, advertiser=advertiser_name, boosters=boosters_objects, realm_name=realm_name, armor_stack=armor_stack,
                          character_to_whisper=char_to_whisper, boosts_number=number_of_boosts, note=note, pot=gold_pot, key=dungeon)

        boost_msg = await ctx.message.channel.send(embed=boost_obj.embed())

        # reactions for controls
        await boost_msg.add_reaction(globals.emojis['tank'])
        await boost_msg.add_reaction(globals.emojis['healer'])
        await boost_msg.add_reaction(globals.emojis['dps'])
        await boost_msg.add_reaction(config.get('emojis')['keyholder'])
        await boost_msg.add_reaction(config.get('emojis')['process'])

        globals.open_boosts[boost_obj.uuid] = (boost_msg, boost_obj)

# --------------------------------------------------------------------------------------------------------------------------------------------

    @client.command('about')
    async def print_info(ctx):
        await ctx.message.channel.send(f'Key Blasters boosting bot version {__VERSION__}')

# --------------------------------------------------------------------------------------------------------------------------------------------

    @client.command('test')
    @commands.has_any_role(*(MNG_RANKS + BOOSTER_RANKS))
    async def add_or_remove_tester_role(ctx):
        """
        Add tester role if member does not have it or removes the tester role if already present.
        """
        tester_role = None
        for role in ctx.guild.roles:
            if 'Tester' == role.name:
                tester_role = role
                break

        if any([tester_role.name == role.name for role in ctx.message.author.roles]):
            await ctx.message.author.remove_roles(tester_role)
        else:
            await ctx.message.author.add_roles(tester_role)

# --------------------------------------------------------------------------------------------------------------------------------------------


    @client.command('test-cmd')
    @commands.is_owner()
    async def test_cmd(ctx):
        #msg = '\n'.join(['some very long test message that bot should never be sending but it can happen sometimes anyway'] * 30)
        await send_channel_message(ctx.message.channel, str(globals.emojis['tank']))

# --------------------------------------------------------------------------------------------------------------------------------------------


    @client.event
    async def on_member_update(before, after):
        if len(after.roles) == 1 or before.nick == after.nick:
            return

        to_check = None
        if after.nick is not None:
            to_check = after.nick

        elif after.nick is None and before.nick is not None:
            LOG.debug(f'To {after.nick}/{after.name}: You have changed nickname to a bad format, please use <character_name>-<realm_name>.')
            await after.send(f'You have changed nickname to a bad format, please use <character_name>-<realm_name>.')
            return

        try:
            _ = parse_nick2realm(to_check)
        except BadArgument as e:
            LOG.debug(f'To {after.nick}/{after.name}: You have changed nickname to a bad format, please use <character_name>-<realm_name>. {e}')
            await after.send(f'You have changed nickname to a bad format, please use <character_name>-<realm_name>. {e}')
            return

        db_handling.add_user(after.id, parse_nick2realm(to_check))

# --------------------------------------------------------------------------------------------------------------------------------------------

    @client.event
    async def on_command_error(ctx, error):
        if not ctx.message.author.id != config.get('my_id'):
            if isinstance(error, CommandNotFound):
                await ctx.message.author.send(f'{error} is not a valid command')
                return
            elif isinstance(error, MissingRequiredArgument):
                await ctx.message.author.send(f'"{ctx.command}" is missing arguments, {error}')
                return
            elif isinstance(error, MissingAnyRole):
                await ctx.message.author.send(f'Insufficient priviledges to execute "{ctx.message.content}". {error}.\n')
                return
            else:
                await ctx.message.author.send(f'{ctx.command} failed. Reason: {error}')

        if isinstance(error, (CommandNotFound, MissingRequiredArgument, MissingAnyRole, BadArgument)):
            return

        original_error = getattr(error, 'original', error)
        original_tb = original_error.__traceback__
        tb_list = traceback.format_exception(original_error, original_error, original_tb)
        exc_str = ''
        for ln in tb_list:
            exc_str += ln

        LOG.error(f'Command error: {ctx.author}@{ctx.channel} : "{ctx.message.content}"\n{error}\n{exc_str}')
    
        usr = client.get_user(config.get('my_id'))
        await usr.send(f'{ctx.author}@{ctx.channel} : "{ctx.message.content}"\n{error}\n{exc_str}')

# --------------------------------------------------------------------------------------------------------------------------------------------

    @client.event
    async def on_reaction_add(reaction, user):
        if user.bot:
            return

        # tracking logic
        LOG.debug(f'{user} added reaction for msg {reaction.message.id}')
        msg_id = str(reaction.message.id)

        if msg_id in globals.tracked_msgs:
            globals.tracked_msgs[msg_id]['added'].append((str(datetime.datetime.utcnow()), user.id, reaction.emoji if isinstance(reaction.emoji, str) else f'<:{reaction.emoji.name}:{reaction.emoji.id}>'))

        boost_uuid = msg_id2boost_uuid(reaction.message.id)
        if boost_uuid is not None:
            # check if the emoji is one of used
            id_or_emoji = reaction.emoji if isinstance(reaction.emoji, str) else reaction.emoji.id
            for emoji_name, emoji_id in config.get('emojis').items():
                if id_or_emoji == emoji_id:
                    break

            #TODO check armor stack role
            if user_has_any_role(user.roles, BOOSTER_RANKS) and ('dps', 'tank', 'healer', 'keyholder'):
                boost_msg, boost = globals.open_boosts[boost_uuid]
                armor_stack = boost_msg.embeds[0].fields[2].value
                if armor_stack != 'no' and not user_has_any_role(user.roles, [armor_stack]) and emoji_name not in ('tank', 'healer'):
                    await user.send(f'You need to have {armor_stack} role to sign up for this boost!')
                    await reaction.remove(user)
                else:
                    boost.add_booster(Booster(mention=user.mention, **{'is_{}'.format(emoji_name): True}))
                    globals.open_boosts[boost_uuid] = boost_msg, boost
                    await boost_msg.edit(embed=boost.embed())
            else:
                await reaction.remove(user)


# --------------------------------------------------------------------------------------------------------------------------------------------


    @client.event
    async def on_reaction_remove(reaction, user):
        if user.bot:
            return

        LOG.debug(f'{user} removed reaction for msg {reaction.message.id}')
        msg_id = str(reaction.message.id)
        if msg_id in globals.tracked_msgs:
            globals.tracked_msgs[msg_id]['removed'].append((str(datetime.datetime.utcnow()), user.id, reaction.emoji if isinstance(reaction.emoji, str) else f'<:{reaction.emoji.name}:{reaction.emoji.id}>'))

        boost_uuid = msg_id2boost_uuid(reaction.message.id)
        if boost_uuid is not None:
            # check if the emoji is one of used
            id_or_emoji = reaction.emoji if isinstance(reaction.emoji, str) else reaction.emoji.id
            for emoji_name, emoji_id in config.get('emojis').items():
                if id_or_emoji == emoji_id:
                    break

        if user_has_any_role(user.roles, BOOSTER_RANKS) and emoji_name in ('dps', 'tank', 'healer', 'keyholder'):
            boost_msg, boost = globals.open_boosts[boost_uuid]
            boost.remove_booster(Booster(mention=user.mention, **{'is_{}'.format(emoji_name): True}))
            await boost_msg.edit(embed=boost.embed())
            globals.open_boosts[boost_uuid] = boost_msg, boost

# --------------------------------------------------------------------------------------------------------------------------------------------


def process_boost(msg):
    """
    current format:
    comment: str
    boost_ttl: parsable int (gold_str2int)
    adv_cut: parsable int (gold_str2int)
    booster list: one mention per line, advertiser is last
    """
    advertiser = None
    price = 0
    adv_cut = 0
    comment = ''
    boosters = []

    to_parse = msg.content.splitlines()
    mentions = [is_mention(line.strip()) for line in to_parse]

    if not mentions[-1]:
        raise BadArgument('Boost post run message should end in mention!')
        return

    args_num = 0
    for idx, bool_is_mention in enumerate(mentions):
        if bool_is_mention:
            args_num = idx
            break

    if args_num < 2:
        raise BadArgument('At least two arguments should be present in post run message!')
        return

    if args_num == 2:
        comment = str(msg.id)
        price = gold_str2int(to_parse[0].strip())
        adv_cut = gold_str2int(to_parse[1].strip())

    elif args_num == 3:
        comment = to_parse[0].strip()
        price = gold_str2int(to_parse[1].strip())
        adv_cut = gold_str2int(to_parse[2].strip())

    if adv_cut > price:
        raise BadArgument('Advertiser cut cannot be bigger than boost price!')
        return

    boosters = [mention2id(booster_mention.strip()) for booster_mention in to_parse[args_num:-1]]

    if adv_cut == 0:
        boosters.append(mention2id(to_parse[-1].strip()))
    else:
        advertiser = mention2id(to_parse[-1].strip())

    return f'boost {comment}: boosters: {[str(client.get_user(booster)) for booster in boosters]}\nbooster_cut: {(price-adv_cut) // len(boosters)}\nadvertiser: {client.get_user(advertiser)}\nadvertiser_cut:{adv_cut}'

# --------------------------------------------------------------------------------------------------------------------------------------------


if __name__ == '__main__':
    client.add_cog(cogs.TrackerCallback(client))
    client.run(config.get('token'))

import logging
from logging import handlers
import discord
from discord.ext import commands
from discord.ext.commands.errors import CommandNotFound, MissingRequiredArgument, BadArgument, MissingAnyRole
import traceback
import asyncio
from typing import Union
import pickle
from datetime import datetime

from helper_functions import *
from event_objects import Boost, Booster
import config
import db_handling
import constants
import globals
import cogs
from custom_commands import edit_boost

#TODO move to a better place
#BOOSTER_RANKS = ['M+Booster', 'Staff', 'Trial', 'Alliance Booster', 'SL Booster', 'SL Blaster']
BOOSTER_RANKS = [707893146419200070, 707850979059564554, 817901110152921109, 804838552625217619, 790528382588157962, 1004889816443392000]
#MNG_RANKS = ['Management', 'Support']
MNG_RANKS = [706853081178046524, 756582609232068668]
if config.get('debug', default=False):
    #tester rank
    MNG_RANKS.append(835892359651917834)
__VERSION__ = config.get('version')

if __name__ == '__main__':
    QUIT_CALLED = False

    intents = discord.Intents.default()
    intents.members = True
    intents.emojis = True
    intents.reactions = True

    logging.basicConfig(level=logging.DEBUG, format='%(asctime)-23s %(name)-12s %(levelname)-8s %(message)s')
    handler = handlers.RotatingFileHandler(config.get('log_path'), maxBytes=50 * 2 ** 20, backupCount=10, encoding='utf-8')
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
        if not globals.loaded:
            await globals.init_discord_objects(client)

# --------------------------------------------------------------------------------------------------------------------------------------------

    @client.event
    async def on_message(ctx):
        if isinstance(ctx.channel, discord.channel.DMChannel):
            return
        LOG.debug(f'{ctx.content} {ctx.id}')

        if not ctx.author.bot and not QUIT_CALLED and (ctx.channel.name in config.get('cmd_channels') or (config.get('debug', default=False) and 'testing' in ctx.channel.name)):
            await client.process_commands(ctx)

# --------------------------------------------------------------------------------------------------------------------------------------------

    @client.command(name='quit')
    @commands.is_owner()
    async def shutdown(ctx):
        #TODO save open boosts and unprocessed transactions
        global QUIT_CALLED

        with open('cache.pickle', 'wb') as f:
            pickle.dump(({(msg_obj.channel.id, msg_obj.id): boost for uuid, (msg_obj, (boost, _)) in globals.open_boosts.items()}, globals.unprocessed_transactions), f)

        await ctx.message.channel.send('Leaving...')
        QUIT_CALLED = True
        #to process anything in progress
        await asyncio.sleep(5)
        await client.close()

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
            msg = await client.wait_for('message', check=msg_author_check(ctx.message.author, ctx.message.channel), timeout=15)

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

    @client.command('payout')
    @commands.has_any_role(*MNG_RANKS)
    async def payout(ctx):
        results = db_handling.execute_end_cycle(ctx.guild.id, ctx.message.author.id)
        results_str = '------ END OF CYCLE TRANSACTIONS PROCESSED ------\n'
        for user_id, result in results:
            member = ctx.guild.get_member(user_id)
            member_mention = member.mention if member is not None else user_id
            if result == 'failed':
                results_str += f'{member_mention} failed to process\n'
            else:
                results_str += f'{member_mention} {result}g\n'

        await send_channel_message(ctx.message.channel, results_str)

# --------------------------------------------------------------------------------------------------------------------------------------------

    @client.command('boost')
    @commands.has_any_role(*(MNG_RANKS + [707850979059564554]))
    async def boost(ctx, channel_mention, timeout: int = 120):
        LOG.debug(f'{ctx.message.author}: {ctx.message.content}')
        #TODO what about alliance?
        #TODO validate dungeon names
        if not is_mention(channel_mention):
            raise BadArgument(f'{channel_mention} is not a channel mention!')

        channel_id = mention2id(channel_mention)
        channel = client.get_channel(channel_id)
        if channel is None:
            raise BadArgument(f'{channel_mention} is not a channel!')
            return

        try:
            await ctx.message.channel.send('Boost pot size?')
            gold_pot = await client.wait_for('message', check=msg_author_check(ctx.message.author, ctx.message.channel), timeout=timeout)
            gold_pot = gold_str2int(gold_pot.content)

            if gold_pot > 2 ** 31 - 1:
                raise BadArgument('Only amounts between -2147483647 and 2147483647 are accepted.')

            #TODO check for current role
            advertiser = None
            bigger_adv_cuts = False
            while advertiser is None:
                await ctx.message.channel.send('Boost advertiser?')
                advertiser_mention = await client.wait_for('message', check=msg_author_check(ctx.message.author, ctx.message.channel), timeout=timeout)
                if is_mention(advertiser_mention.content):
                    advertiser = ctx.guild.get_member(mention2id(advertiser_mention.content))
                    if user_has_any_role(advertiser.roles, ['HUGE Advertiser']):
                        bigger_adv_cuts = True

            include_adv_cut = None
            while include_adv_cut is None:
                await ctx.message.channel.send('Keep ([y]es) advertiser cut or not ([n]o)?')
                keep_cut = await client.wait_for('message', check=msg_author_check(ctx.message.author, ctx.message.channel), timeout=timeout)
                if keep_cut.content in ('y', 'yes'):
                    include_adv_cut = False
                if keep_cut.content in ('n', 'no'):
                    include_adv_cut = True

            realm_name = None
            while realm_name is None:
                await ctx.message.channel.send('Realm name?')
                realm_name = await client.wait_for('message', check=msg_author_check(ctx.message.author, ctx.message.channel), timeout=timeout)
                try:
                    realm_name = constants.is_valid_realm(realm_name.content, check_aliases=True)
                except BadArgument as e:
                    await ctx.message.channel.send(f'{e}')
                    realm_name = None

            await ctx.message.channel.send('Want to have anyone already signed for the boost? use mention')
            boosters = await client.wait_for('message', check=msg_author_check(ctx.message.author, ctx.message.channel), timeout=timeout)
            boosters = [booster for booster in boosters.content.split() if is_mention(booster)]

            boosters_objects = []
            is_anyone_keyholder = False
            for booster in boosters:
                role = None
                while role is None:
                    await ctx.message.channel.send(embed=discord.Embed(description=f'Role for {booster}? One or more from: tank/dps/healer', title=''))
                    roles = await client.wait_for('message', check=msg_author_check(ctx.message.author, ctx.message.channel), timeout=timeout)
                    roles = [role.lower() for role in roles.content.split()]
                    if roles[0] in ('tank', 'dps', 'healer'):
                        boosters_objects.append(Booster(mention=booster, is_locked=True))
                        for role in roles:
                            boosters_objects[-1].__setattr__(f'is_{role}', True)

                if not is_anyone_keyholder:
                    await ctx.message.channel.send(f'Keyholder? [y]es/[n]o')
                    keyholder = await client.wait_for('message', check=msg_author_check(ctx.message.author, ctx.message.channel), timeout=timeout)
                    if keyholder.content in ('y', 'yes'):
                        boosters_objects[-1].is_keyholder = True
                        is_anyone_keyholder = True

            await ctx.message.channel.send('Limit signup only for Blasters for 2min?')
            blaster_resp = await client.wait_for('message', check=msg_author_check(ctx.message.author, ctx.message.channel), timeout=timeout)
            blaster_resp = blaster_resp.content
            if blaster_resp in ('no', 'n'):
                blaster_resp = 0
            else:
                blaster_resp = 24

            await ctx.message.channel.send('Dungeon key?')
            dungeon = await client.wait_for('message', check=msg_author_check(ctx.message.author, ctx.message.channel), timeout=timeout)
            dungeon = dungeon.content

            armor_stack = None
            while armor_stack is None:
                await ctx.message.channel.send('Armor stack? Use role mention or "no"')
                armor_stack = await client.wait_for('message', check=msg_author_check(ctx.message.author, ctx.message.channel), timeout=timeout)
                armor_stack = armor_stack.content
                if is_mention(armor_stack):
                    armor_stack = ctx.guild.get_role(mention2id(armor_stack))
                    if armor_stack and armor_stack.name not in ('Cloth', 'Leather', 'Mail', 'Plate'):
                        await ctx.message.channel.send('Unknown armor role please try again.')
                        armor_stack = None
                        continue
                    armor_stack = armor_stack
                else:
                    armor_stack = 'no'

            number_of_boosts = None
            while number_of_boosts is None:
                await ctx.message.channel.send('Number of boosts?')
                number_of_boosts = await client.wait_for('message', check=msg_author_check(ctx.message.author, ctx.message.channel), timeout=timeout)
                try:
                    number_of_boosts = int(number_of_boosts.content)
                except ValueError:
                    await ctx.message.channel.send(f'{number_of_boosts.content} is not a number!')
                    number_of_boosts = None

            await ctx.message.channel.send('Character to whisper?')
            char_to_whisper = await client.wait_for('message', check=msg_author_check(ctx.message.author, ctx.message.channel), timeout=timeout)
            char_to_whisper = char_to_whisper.content

            await ctx.message.channel.send('Ping anyone?')
            pings = await client.wait_for('message', check=msg_author_check(ctx.message.author, ctx.message.channel), timeout=timeout)
            parsed_pings = []
            for ping in pings.content.split():
                if is_mention(ping):
                    parsed_pings.append(ping)

            await ctx.message.channel.send('Anything else to add? If not type "no".')
            note = await client.wait_for('message', check=msg_author_check(ctx.message.author, ctx.message.channel), timeout=timeout)
            note = note.content
            if note in ('no', 'n'):
                note = None

        except asyncio.TimeoutError:
            await ctx.message.channel.send(f'Got no response in {timeout}s, canceling event creation.')
            return

        boost_obj = Boost(author_dc_id=ctx.message.author.id, boost_author=ctx.message.author.nick, advertiser_mention=advertiser.mention, advertiser_display_name=advertiser.display_name, boosters=boosters_objects,
                          realm_name=realm_name, armor_stack=armor_stack, pings=' '.join(parsed_pings), character_to_whisper=char_to_whisper, boosts_number=number_of_boosts, note=note, pot=gold_pot, key=dungeon,
                          blaster_only_clock=blaster_resp, include_advertiser_in_payout=include_adv_cut, bigger_adv_cuts=bigger_adv_cuts)

        pings_msg = ''
        if boost_obj.pings or boost_obj.armor_stack != 'no':
            pings_msg = f' {boost_obj.armor_stack_mention}' + boost_obj.pings if boost_obj.armor_stack != 'no' else boost_obj.pings
        boost_msg = await channel.send(pings_msg, embed=boost_obj.embed())

        #async with globals.lock:
        globals.open_boosts[boost_obj.uuid] = (boost_msg, (boost_obj, asyncio.Lock()))
        # reactions for controls
        await boost_msg.add_reaction(globals.emojis['tank'])
        await boost_msg.add_reaction(globals.emojis['healer'])
        await boost_msg.add_reaction(globals.emojis['dps'])
        await boost_msg.add_reaction(config.get('emojis')['keyholder'])
        await boost_msg.add_reaction(config.get('emojis')['team'])
        await boost_msg.add_reaction(config.get('emojis')['process'])


# --------------------------------------------------------------------------------------------------------------------------------------------

    @client.command('edit')
    @commands.has_any_role(*(MNG_RANKS + [707850979059564554]))
    async def edit_cmd(ctx, boost_id: str, timeout: int = 15):
        LOG.debug(f'{ctx.message.author}: {ctx.message.content}')
        boost_msg, (boost_obj, lock) = globals.open_boosts.get(boost_id, (None, (None, None)))

        if boost_obj is not None:
            async with lock:
                if boost_obj.status != 'closed':
                    await edit_boost(ctx, boost_obj, boost_msg, boost_id, client, timeout)

    # --------------------------------------------------------------------------------------------------------------------------------------------

    @client.command('aedit')
    @commands.has_any_role(*MNG_RANKS)
    async def admin_edit_cmd(ctx, boost_id: str, timeout: int = 15):
        LOG.debug(f'{ctx.message.author}: {ctx.message.content}')
        boost_msg, (boost_obj, lock) = globals.open_boosts.get(boost_id, (None, (None, None)))

        if boost_obj is not None:
            async with lock:
                await edit_boost(ctx, boost_obj, boost_msg, boost_id, client, timeout)

    # --------------------------------------------------------------------------------------------------------------------------------------------

    @client.command('cancel')
    @commands.has_any_role(*(MNG_RANKS + [707850979059564554]))
    async def cancel(ctx, boost_id: str):
        LOG.debug(f'{ctx.message.author}: {ctx.message.content}')
        #async with globals.lock:
        try:
            boost_msg, (boost_obj, _) = globals.open_boosts.get(boost_id, (None, (None, None)))
        except discord.errors.NotFound:
            LOG.error('Message with id %s no longer exists (404)', boost_id)
            globals.open_boosts.pop(boost_id)
            await ctx.message.channel.send(f'Boost {boost_id} cancelled.')
            return
        if boost_obj is not None:
            boost_obj.status = 'closed'
            globals.open_boosts.pop(boost_id)
            await boost_msg.edit(embed=boost_obj.embed())
            await ctx.message.channel.send(f'Boost {boost_id} cancelled.')

# --------------------------------------------------------------------------------------------------------------------------------------------

    @client.command('kick')
    @commands.has_any_role(*(MNG_RANKS + [707850979059564554]))
    async def kick(ctx, boost_id: str, booster_mention: str):
        LOG.debug(f'{ctx.message.author}: {ctx.message.content}')
        if not is_mention(booster_mention):
            await ctx.message.channel.send(f'{booster_mention} is not a mention!')
            return

        boost_msg, (boost_obj, lock) = globals.open_boosts.get(boost_id, (None, (None, None)))
        if boost_obj is not None:
            async with lock:
                for idx, booster in enumerate(boost_obj.boosters):
                    if booster.mention == booster_mention:
                        boost_obj.boosters.pop(idx)
                        break

                await boost_msg.edit(embed=boost_obj.embed())

# --------------------------------------------------------------------------------------------------------------------------------------------

    @client.command('list-boosts')
    @commands.has_any_role(*MNG_RANKS)
    async def list_boosts(ctx):
        #async with globals.lock:
        for _, boost_obj in globals.open_boosts.values():
            await ctx.channel.send(boost_obj)

        for msg_id, uuid in globals.unprocessed_transactions.items():
            await ctx.channel.send(f'{uuid}:{msg_id}')

# --------------------------------------------------------------------------------------------------------------------------------------------

    @client.command('add-post-run')
    @commands.is_owner()
    async def add_post_run(ctx, msg_id):
        channel = client.get_channel(config.get('channels', 'post-run'))
        msg = await channel.fetch_message(msg_id)
        title = msg.embeds[0].to_dict().get('title')
        if title:
            uuid = title.split()[1]
            globals.unprocessed_transactions[msg_id] = uuid

    # --------------------------------------------------------------------------------------------------------------------------------------------

    @client.command('test')
    @commands.has_any_role(*(MNG_RANKS + BOOSTER_RANKS))
    async def add_or_remove_tester_role(ctx):
        """
        Adds tester role if member does not have it or removes the tester role if already present.
        """
        tester_role = discord.utils.get(ctx.guild.roles, name="Tester")

        if any([tester_role.name == role.name for role in ctx.message.author.roles]):
            await ctx.message.author.remove_roles(tester_role)
        else:
            await ctx.message.author.add_roles(tester_role)

    # --------------------------------------------------------------------------------------------------------------------------------------------

    @client.command('run-sql')
    @commands.is_owner()
    async def run_sql(ctx, sql: str):
        sql = sql.lower()
        if 'select' not in sql or any([db_str in sql for db_str in ('drop', 'create', 'alter', 'update', 'delete')]):
            LOG.error('Exploit detected: %s', sql)
            return

        res = []
        conn = db_handling._db_connect()
        with conn as crs:
            crs.execute(sql)

            for row in crs:
                res.append(str(tuple(row)))

        await send_channel_message(ctx.channel, '\n'.join(res))

# --------------------------------------------------------------------------------------------------------------------------------------------

    @client.command('add-basic-roles')
    @commands.is_owner()
    async def add_basic_ranks(ctx, dry_run: bool = True):
        basic_role = discord.utils.get(ctx.guild.roles, name="Member")

        for member in ctx.guild.members:
            if len(member.roles) == 1:
                if dry_run:
                    LOG.info('Adding rank for %s', member.name)
                else:
                    await member.add_roles(basic_role)

# --------------------------------------------------------------------------------------------------------------------------------------------

    @client.command('show-boost-ads')
    @commands.has_any_role(*(MNG_RANKS + BOOSTER_RANKS))
    async def add_or_remove_tester_role(ctx):
        """
        Adds member role if member does not have it or removes the member role if already present.
        All ads should tag this rank.
        """
        member_role = discord.utils.get(ctx.guild.roles, name="Member")

        if any([member_role.name == role.name for role in ctx.message.author.roles]):
            await ctx.message.author.remove_roles(member_role)
            await ctx.message.author.send('You have been successfully unsubscribed from ad channels.')
        else:
            await ctx.message.author.add_roles(member_role)
            await ctx.message.author.send('You have been successfully subscribed to ad channels.')

# --------------------------------------------------------------------------------------------------------------------------------------------

    @client.command('test-cmd')
    @commands.is_owner()
    async def test_cmd(ctx, foo: bool = True):
        for role in ctx.guild.roles:
            LOG.info('%s %s', role.name, role.id)

# --------------------------------------------------------------------------------------------------------------------------------------------

    @client.event
    async def on_member_join(member):
        if len(member.roles) == 1:
            basic_role = discord.utils.get(member.guild.roles, name="Member")
            try:
                await member.add_roles(basic_role)
            except:
                LOG.exception('Failed to add role for %s', member)

# --------------------------------------------------------------------------------------------------------------------------------------------

    @client.event
    async def on_member_update(before, after):
        # only everyone role add Member role
        if len(after.roles) == 1:
            basic_role = discord.utils.get(after.guild.roles, name="Member")
            await after.add_roles(basic_role)
            return

        if not user_has_any_role(after.roles, BOOSTER_RANKS + MNG_RANKS) or before.nick == after.nick:
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
    async def on_raw_reaction_add(payload):
        LOG.debug(payload)
        user = payload.member
        if user is None:
            user = client.get_user(payload.user_id)
        if user.bot:
            return

        emoji = payload.emoji
        LOG.debug('Reaction added by %s', user.nick if user.nick else user.name)

        # tracking logic
        msg_id = payload.message_id
        channel = payload.member.guild.get_channel(payload.channel_id)
        message = await channel.fetch_message(msg_id)

        if isinstance(channel, discord.DMChannel) and emoji.name == config.get('emojis', 'yes'):
            registration_channel = payload.member.guild.get_channel(861919086354366474)
            if registration_channel:
                LOG.info('Sending registration form from %s', f'{user.name}#{user.discriminator}')
                await registration_channel.send(f'Registration from {user.name}#{user.discriminator} @ {datetime.datetime.now()}', embed=discord.Embed(title='', description=message.content))

        if str(msg_id) in globals.tracked_msgs:
            globals.tracked_msgs[str(msg_id)]['added'].append((str(datetime.datetime.utcnow()), user.id, emoji if isinstance(emoji, str) else f'<:{emoji.name}:{emoji.id}>'))

        if msg_id in globals.unprocessed_transactions:
            LOG.debug('Transaction reaction: %s', emoji)
            yes_emoji = config.get('emojis', 'yes')

            if (emoji.name == yes_emoji and user_has_any_role(user.roles, [706853081178046524])) or (config.get('debug', default=False) and user_has_any_role(user.roles, ['Tester'])):

                # async with globals.lock:
                # add transactions
                LOG.debug(message.embeds[0].to_dict())
                comment = message.embeds[0].to_dict()['title'].split()[1]
                transaction_data = message.embeds[0].to_dict()['fields'][-1]

                results = []
                for ln in transaction_data['value'].splitlines():
                    mention, amount = ln.split()
                    amount = amount.split('.')[0]

                    booster = payload.member.guild.get_member(mention2id(mention))
                    if booster is None:
                        LOG.warning(f'User {mention} no logner present in server!')
                        continue

                    if booster.nick is None:
                        nick = payload.member.guild.get_member(mention2id(mention)).name
                    else:
                        nick = booster.nick

                    usr = client.get_user(mention2id(mention))
                    try:
                        db_handling.add_user(usr.id, parse_nick2realm(nick))
                    except BadArgument as e:
                        LOG.error(f':x:{mention}: Transaction with type add, amount {int(amount)} failed: {e}.')
                        results.append(f':x:{mention}: Transaction with type add, amount {int(amount)} failed: {e}.')
                        continue
                    except:
                        LOG.error(f'Database Error: {traceback.format_exc()}')
                        await user.send(f'Critical error occured, contant administrator.')
                        return

                    try:
                        db_handling.add_tranaction('add', usr.id, user.id, int(amount), payload.member.guild.id, comment)
                    except BadArgument as e:
                        LOG.error(f':x:{mention}: Transaction with type add, amount {int(amount)} failed: {e}.')
                        results.append(f':x:{mention}: Transaction with type add, amount {int(amount)} failed: {e}.')
                        continue
                    except:
                        LOG.error(f'Database Error: {traceback.format_exc()}')
                        await user.send('Critical error occured, contact administrator.')
                        return

                    results.append(f':white_check_mark:{mention}: Transaction with type add, amount {int(amount)} was processed.')

                # TODO send to #attendance
                if not config.get('debug', default=False):
                    attendance_channel = client.get_channel(config.get('channels', 'attendance'))
                    await send_channel_embed(attendance_channel, '\n'.join(results))
                else:
                    await send_channel_embed(message.channel, '\n'.join(results))
                globals.unprocessed_transactions.pop(msg_id)
            elif emoji.name == yes_emoji and not user_has_any_role(user.roles, [706853081178046524]):
                await message.remove_reaction(emoji, user)

        boost_uuid = msg_id2boost_uuid(msg_id)
        if boost_uuid is not None:
            # check if the emoji is one of used
            id_or_emoji = emoji.id if emoji.id is not None else emoji.name
            found = False
            for emoji_name, emoji_id in config.get('emojis').items():
                if id_or_emoji == emoji_id:
                    found = True
                    break

            if not found:
                return

            boost_msg, (boost, lock) = globals.open_boosts[boost_uuid]
            async with lock:
                if emoji_name == 'team' and boost.team_take is None and user_has_any_role(user.roles, BOOSTER_RANKS) and boost.status == 'open':
                    team_role = None
                    for role in user.roles:
                        if role.color == discord.Color.gold():
                            team_role = role
                            break

                    if team_role is not None:
                        if team_role.name in boost.past_team_takes:
                            await user.send(f'Your team have failed to fill this boost in the past already!')
                            return

                        boost.team_take = team_role
                        boost.team_take_clock = 24
                        boost.past_team_takes.append(team_role.name)

                        boosters_to_keep = []
                        for booster in boost.boosters:
                            booster_dsc_user = payload.member.guild.get_member(mention2id(booster.mention))
                            if booster_dsc_user is None:
                                LOG.debug('Failed to get booster %s for boost %s', booster, boost.uuid)
                                return

                            if user_has_any_role(booster_dsc_user.roles, [team_role.name]) or booster.is_locked:
                                boosters_to_keep.append(booster)
                        boost.boosters = boosters_to_keep

                        LOG.debug(f'{boost_uuid} taken by {team_role.name}!')
                        await boost_msg.edit(embed=boost.embed())
                        await boost_msg.channel.send(team_role.mention)
                        return

                if user_has_any_role(user.roles, BOOSTER_RANKS) and emoji_name in ('dps', 'tank', 'healer', 'keyholder'):
                    LOG.debug(f'%s reacted to %s with %s', user.nick if not None else user.name, boost.uuid, emoji_name)

                    if boost.team_take is not None and not user_has_any_role(user.roles, [boost.team_take.id]):
                        await user.send(f'This boost is currently reserved for {boost.team_take} team, wait {boost.team_take_clock * 5}s until it\'s open again.')
                        await message.remove_reaction(emoji, user)
                        return

                    if boost.status != 'open':
                        await message.remove_reaction(emoji, user)
                        return

                    armor_stack = boost.armor_stack
                    if armor_stack != 'no':
                        armor_stack = armor_stack
                        excluded_roles = ['keyholder']
                        if armor_stack.name in ('Cloth', 'Mail'):
                            excluded_roles.append('tank')

                        if (not user_has_any_role(user.roles, [armor_stack.id]) and emoji_name not in excluded_roles) and len(boost.boosters) != 4:
                            LOG.debug('%s %s %s', not user_has_any_role(user.roles, [armor_stack.id]), emoji_name not in excluded_roles, len(boost.boosters) != 4)
                            await user.send(f'You need to have {armor_stack.name} role to sign up for this boost!')
                            await message.remove_reaction(emoji, user)
                            return

                    if boost.blaster_only_clock > 0 and not user_has_any_role(user.roles, [1004889816443392000]):
                        await user.send(f'This boost is currently reserved for SL Blaster rank, wait {boost.blaster_only_clock * 5}s until it\'s open for Boosters.')
                        await message.remove_reaction(emoji, user)
                        return

                    if (not user_has_any_role(user.roles, ['DPS']) and emoji_name == 'dps') or (not user_has_any_role(user.roles, ['Healer']) and emoji_name == 'healer') or (
                            not user_has_any_role(user.roles, ['Tank']) and emoji_name == 'tank'):
                        await user.send(f'You are missing {emoji_name} specialization role!')
                        await message.remove_reaction(emoji, user)
                        return

                    LOG.debug('Adding booster: %s', Booster(mention=user.mention, **{'is_{}'.format(emoji_name): True}))
                    if boost.add_booster(Booster(mention=user.mention, **{'is_{}'.format(emoji_name): True})):
                        await boost_msg.edit(embed=boost.embed())

                if user_has_any_role(user.roles, MNG_RANKS + [707850979059564554]) and emoji_name == 'process':
                    boost_msg, (boost, _) = globals.open_boosts[boost_uuid]
                    if boost.status == 'open' or boost.author_dc_id != user.id:
                        return

                    embed = boost.process()
                    if embed is not None:
                        # TODO send to #post-run
                        if not config.get('debug', default=False):
                            post_run_channel = client.get_channel(config.get('channels', 'post-run'))
                            transaction_msg = await post_run_channel.send(embed=embed)
                            await transaction_msg.add_reaction(config.get('emojis', 'yes'))
                        else:
                            transaction_msg = await boost_msg.channel.send(embed=embed)
                            await transaction_msg.add_reaction(config.get('emojis', 'yes'))
                        # async with globals.lock:
                        globals.unprocessed_transactions[transaction_msg.id] = boost.uuid

                    # async with globals.lock:
                    globals.open_boosts.pop(boost_uuid)


# --------------------------------------------------------------------------------------------------------------------------------------------


    @client.event
    async def on_raw_reaction_remove(payload):
        user = await client.get_guild(payload.guild_id).fetch_member(payload.user_id)
        if user.bot:
            return

        emoji = payload.emoji
        LOG.debug('Reaction removed by %s', user.nick if user.nick else user.name)

        # tracking logic
        msg_id = payload.message_id
        message = await client.get_guild(payload.guild_id).get_channel(payload.channel_id).fetch_message(msg_id)

        msg_id = str(message.id)
        if msg_id in globals.tracked_msgs:
            globals.tracked_msgs[msg_id]['removed'].append((str(datetime.datetime.utcnow()), user.id, emoji if isinstance(emoji, str) else f'<:{emoji.name}:{emoji.id}>'))

        boost_uuid = msg_id2boost_uuid(message.id)
        if boost_uuid is not None:
            # check if the emoji is one of used
            id_or_emoji = emoji.id if emoji.id is not None else emoji.name
            for emoji_name, emoji_id in config.get('emojis').items():
                if id_or_emoji == emoji_id:
                    break

            if user_has_any_role(user.roles, BOOSTER_RANKS) and emoji_name in ('dps', 'tank', 'healer', 'keyholder'):
                boost_msg, (boost, lock) = globals.open_boosts[boost_uuid]
                async with lock:
                    boost.remove_booster(Booster(mention=user.mention, **{'is_{}'.format(emoji_name): True}))
                    await boost_msg.edit(embed=boost.embed())

# --------------------------------------------------------------------------------------------------------------------------------------------


if __name__ == '__main__':
    client.add_cog(cogs.TrackerCallback(client))
    client.add_cog(cogs.BoostCallback(client))
    client.run(config.get('token'))

import logging
from logging import handlers
import discord
from discord.ext import commands
from discord.ext.commands.errors import CommandNotFound, MissingRequiredArgument, BadArgument, MissingAnyRole
import traceback
import re
import asyncio

import config
import db_handling
import constants

QUIT_CALLED = False

logging.basicConfig(level=logging.DEBUG, format='%(asctime)-23s %(name)-12s %(levelname)-8s %(message)s')
handler = handlers.RotatingFileHandler('logs/log', maxBytes=10 * 50 ** 20, backupCount=10, encoding='utf-8')
formatter = logging.Formatter('%(asctime)-23s %(name)-12s %(levelname)-8s %(message)s')
handler.setFormatter(formatter)
logging.getLogger('').addHandler(handler)
logging.getLogger('discord').setLevel(logging.INFO)
logging.getLogger('websockets').setLevel(logging.INFO)
LOG = logging.getLogger(__name__)
client = commands.Bot(command_prefix='!')

#--------------------------------------------------------------------------------------------------------------------------------------------

@client.event
async def on_ready():
    LOG.debug('Connected')
    async for guild in client.fetch_guilds():
        if guild.name == 'bot_testing' or guild.id in config.get('deployed_guilds'):
            LOG.debug(guild.id)

    await client.change_presence(activity=discord.Game(name='!help for commands'))

#--------------------------------------------------------------------------------------------------------------------------------------------

@client.event
async def on_message(message):
    if isinstance(message.channel, discord.channel.DMChannel):
        return

    if message.author.bot or QUIT_CALLED or message.channel.name not in config.get('cmd_channels'):
        LOG.debug(f'skipping processing of msg: {message.author} {QUIT_CALLED} {message.channel}')
        return

    await client.process_commands(message)

#--------------------------------------------------------------------------------------------------------------------------------------------

@client.command(name='quit')
@commands.is_owner()
async def shutdown(ctx):
    global QUIT_CALLED

    await ctx.message.channel.send('Leaving...')
    QUIT_CALLED = True
    #to process anything in progress
    await asyncio.sleep(60)
    await client.logout()

#--------------------------------------------------------------------------------------------------------------------------------------------

@client.command(name='gold')
@commands.has_role('Management')
async def gold_add(ctx, *args):
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
            results.append(f'{mention}: Transaction with type {transaction_type}, amount {gold_str2int(amount):00} failed: {e}.')
            continue
        except:
            LOG.error(f'Database Error: {traceback.format_exc()}')
            await ctx.message.author.send(f'Critical error occured, contant administrator.')
            return

        try:
            db_handling.add_tranaction(transaction_type, usr.id, ctx.author.id, gold_str2int(amount), ctx.guild.id, comment)
        except BadArgument as e:
            results.append(f'{mention}: Transaction with type {transaction_type}, amount {gold_str2int(amount):00} failed: {e}.')
            continue
        except:
            LOG.error(f'Database Error: {traceback.format_exc()}')
            await ctx.message.author.send('Critical error occured, contact administrator.')
            return

        results.append(f'{mention}: Transaction with type {transaction_type}, amount {gold_str2int(amount):00} was processed.')

    await ctx.message.channel.send('\n'.join(results))

#--------------------------------------------------------------------------------------------------------------------------------------------

@client.command(name='list-transactions')
@commands.has_any_role('Management', 'M+Booster', 'M+Blaster', 'Advertiser', 'Trial Advertiser', 'Jaina')
async def list_transactions(ctx, limit: int=10):
    LOG.debug(f'{ctx.message.author}: {ctx.message.content}')
    if limit < 1:
        await ctx.message.author.send(f'{limit} is an invalid value to limit number of transactions!.')
        raise BadArgument(f'{limit} is an invalid value to limit number of transactions!.')
        return

    transactions = db_handling.list_transactions(ctx.message.author.id, limit)

    transactions_string = ''
    for t in transactions:
        transactions_string += t+'\n'

    await ctx.message.channel.send(transactions_string)

#--------------------------------------------------------------------------------------------------------------------------------------------

@client.command(name='alist-transactions')
@commands.has_role('Management')
async def admin_list_transactions(ctx, mention, limit: int=10):
    LOG.debug(f'{ctx.message.author}: {ctx.message.content}')
    if limit < 1:
        await ctx.message.author.send(f'{limit} is an invalid value to limit number of transactions!.')
        raise BadArgument(f'{limit} is an invalid value to limit number of transactions!.')
        return
    usr_id = mention2id(mention)
    transactions = db_handling.list_transactions(usr_id, limit)

    await ctx.message.channel.send(f'Last {limit} transactions for user: {ctx.guild.get_member(usr_id).name}')

    transactions_string = ''
    for t in transactions:
        transactions_string += t+'\n'

    await ctx.message.channel.send(transactions_string)

#--------------------------------------------------------------------------------------------------------------------------------------------

@client.command(name='top')
@commands.has_any_role('Management', 'M+Booster', 'M+Blaster', 'Advertiser', 'Trial Advertiser', 'Jaina')
async def list_transactions(ctx, limit: int=10):
    LOG.debug(f'{ctx.message.author}: {ctx.message.content}')
    if limit < 1:
        await ctx.message.author.send(f'{limit} is an invalid value to limit number of boosters!.')
        raise BadArgument(f'{limit} is an invalid value to limit number of transactions!.')
        return

    top_ppl = db_handling.list_top_boosters(limit, ctx.guild.id)

    res_str = 'Current top boosters:\n'
    for idx, data in enumerate(top_ppl):
        res_str += f'#{idx + 1}{ctx.guild.get_member(data[1]).mention} : {data[0]}\n'

    res_str += f'Top total: {sum([x[0] for x in top_ppl])}'
    await ctx.message.channel.send(res_str)

#--------------------------------------------------------------------------------------------------------------------------------------------

@client.command(name='realm-top')
@commands.has_any_role('Management', 'M+Booster', 'M+Blaster', 'Advertiser', 'Trial Advertiser', 'Jaina')
async def list_transactions(ctx, realm_name: str, limit: int=10):
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
        res_str += f'#{idx + 1}{ctx.guild.get_member(data[1]).mention} : {data[0]}\n'

    res_str += f'Top total: {sum([x[0] for x in top_ppl])}'
    await ctx.message.channel.send(res_str)

#--------------------------------------------------------------------------------------------------------------------------------------------

@client.command('balance')
@commands.has_any_role('Management', 'M+Booster', 'M+Blaster', 'Advertiser', 'Trial Advertiser', 'Jaina')
async def balance(ctx):
    LOG.debug(f'{ctx.message.author}: {ctx.message.content}')
    user_id = ctx.message.author.id

    try:
        balance = db_handling.get_balance(user_id, ctx.guild.id)
    except:
        LOG.error(f'Balance command error {traceback.format_exc()}')
        await client.get_user(config.get('my_id')).send(f'Balance command error {traceback.format_exc()}')
        return
    
    await ctx.message.channel.send(f'Balance for {ctx.guild.get_member(user_id).mention}:\n' + balance)

#--------------------------------------------------------------------------------------------------------------------------------------------

@client.command('abalance')
@commands.has_role('Management')
async def admin_balance(ctx, mention):
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
    
    await ctx.message.channel.send(f'Balance for {ctx.guild.get_member(user_id).mention}:\n' + balance)

#-------------------------------------------------------------------------------------------------------------------------------------------

@client.command('alias')
@commands.has_role('Management')
async def alias(ctx, alias, realm_name):
    LOG.debug(f'{ctx.message.author}: {ctx.message.content}')
    realm_name = constants.is_valid_realm(realm_name)
    try:
        if db_handling.add_alias(realm_name, alias):
            await ctx.message.channel.send(f'Added alias "{alias}"="{realm_name}"')
    except db_handling.DatabaseError:

        await ctx.message.channel.send(f'"{alias}" already exists overwrite[y/n]?')
        msg = await client.wait_for('message', check=_msg_author_check(ctx.message.author), timeout=15)

        if msg.content not in ('y', 'n') or msg.content == 'n':
            return
        else:
            if db_handling.add_alias(realm_name, alias, update=True):
                await ctx.message.channel.send(f'Overwritten alias "{alias}"="{realm_name}"')

#--------------------------------------------------------------------------------------------------------------------------------------------

@client.event
async def on_member_update(before, after):
    if len(after.roles) == 1 or before.nick == after.nick:
        return

    usr = client.get_user(after.id)
    
    if after.nick is not None:
        to_check = after.nick

    elif after.nick is None and before.nick is not None:
        LOG.debug(f'To {after.nick}/{after.name}: You have changed nickname to a bad format, please use <character_name>-<realm_name>.')
        await after.send(f'You have changed nickname to a bad format, please use <character_name>-<realm_name>.')
        return

    try:
        realm_name = parse_nick2realm(to_check)
    except BadArgument as e:
        LOG.debug(f'To {after.nick}/{after.name}: You have changed nickname to a bad format, please use <character_name>-<realm_name>. {e}')
        await after.send(f'You have changed nickname to a bad format, please use <character_name>-<realm_name>. {e}')
        return

    db_handling.add_user(f'{usr.name}#{usr.discriminator}', after.id, parse_nick2realm(to_check))

#--------------------------------------------------------------------------------------------------------------------------------------------

@client.event
async def on_command_error(ctx, error):
    if isinstance(error, CommandNotFound):
        await ctx.message.author.send(f'{error} is not a valid command')
        return
    elif isinstance(error, MissingRequiredArgument):
        await ctx.message.author.send(f'"{ctx.command}" is missing arguments, {error}')
        return
    elif isinstance(error, MissingAnyRole):
        await ctx.message.author.send(f'Insufficient priviledges to execute "{ctx.message.content}". {error}.')
        return
    else:
        await ctx.message.author.send(f'{ctx.command} failed. Reason: {error}')

    LOG.error(f'Command error: {ctx.author}@{ctx.channel} : "{ctx.message.content}"\n{error}\n{traceback.format_exc()}')
    
    usr = client.get_user(config.get('my_id'))
    await usr.send(f'{ctx.author}@{ctx.channel} : "{ctx.message.content}"\n{error}')

#--------------------------------------------------------------------------------------------------------------------------------------------

def process_boost(msg):
    boostee = None
    advertiser = None
    price = 0
    comment = ''
    boosters = []

    for idx, ln in enumerate(msg.splitlines()):
        LOG.debug(f'line {idx}: {ln}')
        if idx == 0:
            boostee = ln.split()[1].strip()
            continue

        if idx == 1:
            raw_comment, raw_price = ln.split('-')
            price = int(raw_price.strip('k'))
            comment = raw_comment[3:].strip()
            continue

        if 'Advertiser' in ln or 'advertiser' in ln:
            advertiser = parse_mention(ln)
            continue

        booster = parse_mention(ln)
        if booster is not None:
            boosters.append(booster)
        else:
            raise RuntimeError(f'{ln} contains no mention.')

    LOG.debug(f'Processed boost: boostee:{boostee}, advertiser:{advertiser}, run:{comment}, price:{price}, boosters:{boosters}')
    return boostee, advertiser, comment, price, boosters

#--------------------------------------------------------------------------------------------------------------------------------------------

def is_mention(msg):
    return bool(re.match(r'^\<@!([0-9])+\>$', msg))

#--------------------------------------------------------------------------------------------------------------------------------------------

def parse_mention(msg):
    m = re.match(r'^(.+)?(\<@![0-9]+\>)(.+)?$', msg)
    if m:
        return m.group(2)

#--------------------------------------------------------------------------------------------------------------------------------------------

def mention2id(mention):
    return int(mention[3:-1])

#--------------------------------------------------------------------------------------------------------------------------------------------

def parse_nick2realm(nick):
    try:
        realm_name = nick.split('-')[1].strip()
    except:
        raise BadArgument(f'Nick "{nick}" is not in correct format, please use <character_name>-<realm_name>.')
    realm_name = constants.is_valid_realm(realm_name, True)
    return realm_name

#--------------------------------------------------------------------------------------------------------------------------------------------

def _msg_author_check(author):
    def inner_check(msg):
        return msg.author == author
    return inner_check

#--------------------------------------------------------------------------------------------------------------------------------------------

def gold_str2int(gold_str):
    gold_str = gold_str.lower()
    
    m = re.match('^([0-9]+)([kKmM]?)$', gold_str)
    if not m:
        raise BadArgument(f'"{gold_str}" not not a valid gold amount. Accepted formats: <int_value>[mk]')

    int_part = int(m.group(1))
    if int(m.group(1)) < 1:
        raise BadArgument('Only positive amounts are accepted.')
    
    if m.group(2) == 'k':
        return int_part * 1000
    elif m.group(2) == 'm':
        return int_part * 1e6

    return int(int_part)

#--------------------------------------------------------------------------------------------------------------------------------------------

client.run(config.get('token'))

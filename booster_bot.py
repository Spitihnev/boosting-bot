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
handler = handlers.RotatingFileHandler('logs/log', maxBytes=10 * 50 ** 20, backupCount=10)
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
    #LOG.debug(f'{client.user}')
    #LOG.debug(f'Registered message from {message.author} with content {message.content}')
    LOG.debug(config.get('cmd_channels'))
    if message.author == client.user or message.author.bot or QUIT_CALLED or message.channel.name not in config.get('cmd_channels'):
        LOG.debug(f'skipping processing of msg: {message.author} {QUIT_CALLED} {message.channel}')
        return

    await client.process_commands(message)

#--------------------------------------------------------------------------------------------------------------------------------------------

@commands.is_owner()
@client.command(name='quit')
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
async def gold_add(ctx, transaction_type:str, mention: str, amount: str, comment: str=None):
    if not is_mention(mention):
        await ctx.message.author.send(f'"{mention}" is not a mention')
        raise BadArgument(f'"{mention}" is not a mention')

    if transaction_type not in db_handling.TRANSACTIONS:
        raise BadArgument('Unknown transaction type!')
        await ctx.message.author.send('Unknown transaction type!')

    nick = ctx.guild.get_member(mention2id(mention)).nick

    usr = client.get_user(mention2id(mention))
    try:
        exist_check = db_handling.name2dsc_id(f'{usr.name}#{usr.discriminator}')
    except db_handling.UserNotFoundError:
        db_handling.add_user(f'{usr.name}#{usr.discriminator}', usr.id, parse_nick2realm(nick))
    except db_handling.UserAlreadyExists:
        pass

    try:
        db_handling.add_tranaction(transaction_type, usr.id, ctx.author.id, gold_str2int(amount), ctx.guild.id, comment)
    except BadArgument as e:
        await ctx.message.author.send(e)
        return

    except:
        LOG.error(f'Database Error: {traceback.format_exc()}')
        await ctx.message.author.send('Critical error occured, contact administrator.')
        return

    await ctx.message.channel.send(f'Transaction with type {transaction_type}, amount {gold_str2int(amount):00} was added to {mention} balance.')

#--------------------------------------------------------------------------------------------------------------------------------------------

@commands.has_any_role('Management', 'M+Booster', 'M+Blaster', 'Advertiser', 'Trial Advertiser', 'Jaina')
@client.command(name='list-transactions')
async def list_transactions(ctx, limit: int=10):
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

@commands.has_role('Management')
@client.command(name='top')
async def list_transactions(ctx, limit: int=10):
    if limit < 1:
        await ctx.message.author.send(f'{limit} is an invalid value to limit number of boosters!.')
        raise BadArgument(f'{limit} is an invalid value to limit number of transactions!.')
        return

    top_ppl = db_handling.list_top_boosters(limit)

    res_str = 'Current top boosters:\n'
    for idx, data in enumerate(top_ppl): 
        res_str += f'#{idx + 1}{ctx.guild.get_member(data[1]).mention} : {data[0]}\n'

    await ctx.message.channel.send(res_str)

#--------------------------------------------------------------------------------------------------------------------------------------------

@commands.has_role('Management')
@client.command(name='realm-top')
async def list_transactions(ctx, realm_name: str, limit: int=10):
    if limit < 1:
        await ctx.message.author.send(f'{limit} is an invalid value to limit number of boosters!')
        raise BadArgument(f'{limit} is an invalid value to limit number of transactions!')
        return

    if realm_name not in constants.EU_REALM_NAMES:
        await ctx.message.author.send(f'{realm_name} is not a known EU realm!')
        raise BadArgument(f'{realm_name} is not a known EU realm!')
        return

    top_ppl = db_handling.list_top_boosters(limit, realm_name)

    res_str = f'Current top boosters for realm {realm_name}:\n'
    for idx, data in enumerate(top_ppl): 
        res_str += f'#{idx + 1}{ctx.guild.get_member(data[1]).mention} : {data[0]}\n'

    await ctx.message.channel.send(res_str)

#--------------------------------------------------------------------------------------------------------------------------------------------

@commands.has_role('Management')
@client.command(name='alist-transactions')
async def admin_list_transactions(ctx, mention, limit: int=10):
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

@client.command('balance')
@commands.has_any_role('Management', 'M+Booster', 'M+Blaster', 'Advertiser', 'Trial Advertiser', 'Jaina')
async def balance(ctx, mention=None):
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
    user_id = mention2id(mention)

    try:
        balance = db_handling.get_balance(user_id, ctx.guild.id)
    except:
        LOG.error(f'Balance command error {traceback.format_exc()}')
        await client.get_user(config.get('my_id')).send(f'Balance command error {traceback.format_exc()}')
        return
    
    await ctx.message.channel.send(f'Balance for {ctx.guild.get_member(user_id).mention}:\n' + balance)

#-------------------------------------------------------------------------------------------------------------------------------------------

@client.event
async def on_member_update(before, after):
    if before.nick != after.nick and after.nick is not None:
        try:
            realm_name = parse_nick2realm(after.nick)
        except BadArgument as e:
            await after.send(f'You have changed nickname to a bad format, please use <character_name>-<realm>. {e}')
        else:
            db_handling.add_user(after.name, after.id, parse_nick2realm(after.nick))

    elif after.nick is None:
        await after.send(f'You have changed nickname to a bad format, please use <character_name>-<realm>.')

#--------------------------------------------------------------------------------------------------------------------------------------------

@client.event
async def on_error(event, *args, **kwargs):
    msg = args[0]
    LOG.error(f'{msg.author}@{msg.channel} : "{msg.content}"\n{traceback.format_exc()}')
    usr = client.get_user(config.get('my_id'))
    await usr.send(f'{msg.author}@{msg.channel} : "{msg.content}"\n{traceback.format_exc()}')

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
        raise BadArgument(f'{nick} is not in correct format.')
    if realm_name not in constants.EU_REALM_NAMES:
        raise BadArgument(f'{realm_name} is not a known EU realm name.')

    return realm_name

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

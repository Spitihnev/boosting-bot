import logging
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
MNG_ROLE_ID = None

logging.basicConfig(level=logging.INFO, format='%(asctime)-23s %(levelname)-8s %(message)s')
LOG = logging.getLogger(__name__)
LOG.setLevel(level=logging.DEBUG)
client = commands.Bot(command_prefix='!')

#--------------------------------------------------------------------------------------------------------------------------------------------

@client.event
async def on_ready():
    global MNG_ROLE_ID
    LOG.debug('Connected')
    async for guild in client.fetch_guilds():
        if guild.name == 'bot_testing' or guild.id in config.get('deployed_guilds'):
            LOG.debug(guild.id)
            roles = await guild.fetch_roles()
            for role in roles:
                if role.name == 'Management':
                    MNG_ROLE_ID = role.id
        else:
            LOG.warn('Unknown guild found!')

    await client.change_presence(activity=discord.Game(name='!help for commands'))

#--------------------------------------------------------------------------------------------------------------------------------------------

@client.event
async def on_message(message):
    #LOG.debug(f'{client.user}')
    #LOG.debug(f'Registered message from {message.author} with content {message.content}')
    LOG.debug(f'Quit called: {QUIT_CALLED}')
    if message.author == client.user or message.author.bot or QUIT_CALLED:
        return

    await client.process_commands(message)
    return
    #usr = await client.fetch_user(str(config.get('my_id')))
    #LOG.info(f'{usr.id} {usr.name}#{usr.discriminator}')

    if not isinstance(message.channel, discord.DMChannel) and message.channel.name == 'generall':
        
        LOG.debug('Got boost message to process')
        res = process_boost(message.content)
        if res:
            await message.channel.send(f'Processed boost: boostee:{res[0]}, advertiser:{res[1]}, run:{res[2]}, price:{res[3]}, boosters:{res[4]}')
        if not res:
            LOG.debug('Boost not processed')

#--------------------------------------------------------------------------------------------------------------------------------------------

@client.command(name='quit')
async def shutdown(ctx):
    global QUIT_CALLED
    if ctx.author.id == config.get('my_id'):
        await ctx.message.channel.send('Leaving...')
        QUIT_CALLED = True
        #to process anything in progress
        await asyncio.sleep(60)
        await client.logout()

#--------------------------------------------------------------------------------------------------------------------------------------------

@client.command(name='gold')
@commands.has_role('Management')
async def gold_add(ctx, transaction_type:str, mention: str, amount: str, comment: str, realm_name: str=None):
    if not is_mention(mention):
        await ctx.message.author.send(f'"{mention}" is not a mention')
        raise BadArgument(f'"{mention}" is not a mention')

    if realm_name not in constants.EU_REALM_NAMES and realm_name is not None:
        await ctx.message.author.send(f'"{realm_name}" is not a known EU realm')
        raise BadArgument(f'"{realm_name}" is not a known EU realm')

    if transaction_type not in db_handling.TRANSACTIONS:
        raise BadArgument('Unknown transaction type!')
        await ctx.message.author.send('Unknown transaction type!')

    usr = client.get_user(mention2id(mention))
    try:
        exist_check = db_handling.name2dsc_id(f'{usr.name}#{usr.discriminator}')
    except db_handling.UserNotFoundError:
        db_handling.add_user(f'{usr.name}#{usr.discriminator}', usr.id)
    except db_handling.UserAlreadyExists:
        pass

    try:
        db_handling.add_tranaction(transaction_type, usr.id, ctx.author.id, gold_str2int(amount), realm_name, ctx.guild.id, comment)
    except BadArgument as e:
        await ctx.message.author.send(e)
        return

    except:
        LOG.error(f'Database Error: {traceback.format_exc()}')
        await ctx.message.author.send('Critical error occured, contact administrator.')
        return

    await ctx.message.channel.send(f'Transaction with type {transaction_type}, amount {gold_str2int(amount):00} was added to {mention} balance.')

#--------------------------------------------------------------------------------------------------------------------------------------------

@client.command(name='list-transactions')
async def list_transactions(ctx, limit: int=10):
    if limit < 1:
        await ctx.message.author.send(f'{limit} is an invalid value to limit number of transactions!.')
        raise BadArgument(f'{limit} is an invalid value to limit number of transactions!.')
        return

    transactions = db_handling.list_transactions(ctx.message.author.id, limit)

    for t in transactions:
        await ctx.message.channel.send(t)

#--------------------------------------------------------------------------------------------------------------------------------------------

@commands.has_role('Management')
@client.command(name='admin-list-transactions')
async def list_transactions(ctx, mention, limit: int=10):
    if limit < 1:
        await ctx.message.author.send(f'{limit} is an invalid value to limit number of transactions!.')
        raise BadArgument(f'{limit} is an invalid value to limit number of transactions!.')
        return
    usr_id = mention2id(mention)
    transactions = db_handling.list_transactions(usr_id, limit)
    
    member_name = ctx.guild.get_member(usr_id).name
    await ctx.message.channel.send(f'Last {limit} transactions for user: {member_name}')

    for t in transactions:
        await ctx.message.channel.send(t)

#--------------------------------------------------------------------------------------------------------------------------------------------

@client.command('balance')
@commands.has_any_role('Management', 'M+Booster', 'M+Blaster', 'Advertiser', 'Trial Advertiser', 'Jaina')
async def balance(ctx, mention=None):
    extended = ctx.guild.get_role(MNG_ROLE_ID) == ctx.message.author.top_role
    LOG.debug(f'balance cmd by {ctx.message.author.id} is_admin:{extended} {MNG_ROLE_ID}')

    if extended and mention is not None:
        user_id = mention2id(mention)
    else:
        user_id = ctx.message.author.id

    try:
        balance = db_handling.get_balance(user_id, ctx.guild.id)
    except:
        LOG.error(f'Balance command error {traceback.format_exc()}')
        await client.get_user(config.get('my_id')).send(f'Balance command error {traceback.format_exc()}')
        return
    
    await ctx.message.channel.send(f'Balance for {ctx.guild.get_member(user_id).mention}:\n'+balance[1])

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

client.run(config.get('token'))

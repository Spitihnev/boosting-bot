import logging
import discord
from discord.ext import commands
from discord.ext.commands.errors import CommandNotFound, MissingRequiredArgument, BadArgument, MissingAnyRole
import traceback
import re

import config
import db_handling
import constants

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)
LOG.setLevel(level=logging.DEBUG)
client = commands.Bot(command_prefix='!')

#--------------------------------------------------------------------------------------------------------------------------------------------

@client.event
async def on_ready():
    LOG.debug('Connected')
    await client.change_presence(activity=discord.Game(name='Boosting Day \'n Night '))

#--------------------------------------------------------------------------------------------------------------------------------------------

@client.event
async def on_message(message):
    #LOG.debug(f'{client.user}')
    #LOG.debug(f'Registered message from {message.author} with content {message.content}')
    if message.author == client.user or message.author.bot:
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
    await client.process_commands(message)

#--------------------------------------------------------------------------------------------------------------------------------------------

@client.command(name='quit')
async def shutdown(ctx):
    if ctx.author.id == config.get('my_id'):
        LOG.debug('Leaving...')
        await client.logout()

#--------------------------------------------------------------------------------------------------------------------------------------------

@client.command(name='gold-add')
async def gold_add(ctx, mention: str, amount: int, realm_name: str, comment: str):
    if not is_mention(mention):
        await ctx.message.channel.send(f'"{mention}" is not a mention')
        raise BadArgument(f'"{mention}" is not a mention')

    if realm_name not in constants.EU_REALM_NAMES:
        await ctx.message.channel.send(f'"{realm_name}" is not a known EU realm')
        raise BadArgument(f'"{realm_name}" is not a known EU realm')

    usr = client.get_user(mention2id(mention))
    try:
        exist_check = db_handling.name2id(f'{usr.name}#{usr.discriminator}')
    except db_handling.UserNotFoundError:
        db_handling.add_user(f'{usr.name}#{usr.discriminator}', usr.id)
    except db_handling.UserAlreadyExists:
        pass

    try:
        db_handling.add_tranaction('add', f'{ctx.author.name}#{ctx.author.discriminator}', f'{usr.name}#{usr.discriminator}', amount, realm_name, comment)
    except:
        LOG.error(f'Database Error: {traceback.format_exc()}')
        return
    await ctx.message.channel.send(f'Added {amount} to {mention} balance.')

#--------------------------------------------------------------------------------------------------------------------------------------------

@client.command('balance')
async def balance(ctx):
    LOG.debug(f'balance cmd by {ctx.message.author.id}')
    try:
        balance = db_handling.get_balance(ctx.message.author.id)
    except:
        LOG.error(f'Balance command error {traceback.format_exc()}') 
    
    await ctx.message.channel.send(balance)

@client.command('gold-subtract')
async def gold_subtract():
    raise NotImplementedError

#--------------------------------------------------------------------------------------------------------------------------------------------

@client.command('admin-command')
@commands.has_any_role('Managment', 'M+ Blaster')
async def admin_command(ctx):
    await ctx.message.channel.send('Admin command executed.')

#--------------------------------------------------------------------------------------------------------------------------------------------

@client.event
async def on_reaction_add(reaction, user):
    if reaction.message.author == client.user:
        await reaction.message.channel.send(f'Glad to see your {reaction} to my message {user.name}.')

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
        await ctx.message.channel.send(f'Insufficient priviledges to execute "{ctx.message.content}". {error}.')
        return
    else:
        await ctx.message.channel.send(f'{ctx.command} failed. Reason: {error}')

    LOG.error(f'Command error: {ctx.author}@{ctx.channel} : "{ctx.message.content}"\n{error}')
    
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

client.run(config.get('token'))

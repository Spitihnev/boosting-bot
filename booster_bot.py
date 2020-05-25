import logging
import discord
from discord.ext import commands
from discord.ext.commands.errors import CommandNotFound, MissingRequiredArgument, BadArgument
import traceback
import re

import config
import db_handling

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)
LOG.setLevel(level=logging.DEBUG)
client = commands.Bot(command_prefix='!')

@client.event
async def on_ready():
    LOG.debug('Connected')
    await client.change_presence(activity=discord.Game(name='Boosting Day \'n Night '))

@client.event
async def on_message(message):
    LOG.debug(f'{client.user}')
    LOG.debug(f'Registered message from {message.author} with content {message.content}')
    if message.author == client.user or message.author.bot:
        return

    if message.channel.name == 'general':
        LOG.debug('Got boost message to process')
        res = process_boost(message.content)
        if res:
            await message.channel.send(f'Processed boost: boostee:{res[0]}, advertiser:{res[1]}, run:{res[2]}, price:{res[3]}, boosters:{res[4]}')
        if not res:
            LOG.debug('Boost not processed')
    await client.process_commands(message)

@client.command(name='quit')
async def shutdown(ctx):
    if ctx.author.id == config.get('my_id'):
        LOG.debug('Leaving...')
        await client.logout()

@client.command(name='gold-add')
async def gold_add(ctx, mention, amount):
    if not is_mention(mention):
        raise BadArgument(f'"{mention}" is not a mention')

    LOG.debug(f'{ctx.author} {type(mention)}{mention}|{amount}')
    #TODO add gold to DB
    await ctx.message.channel.send(f'Added {amount} to {mention} balance.')

@client.command('gold')
async def gold(ctx):
    raise NotImplementedError

@client.command('gold-subtract')
async def gold_subtract():
    raise NotImplementedError

@client.event
async def on_reaction_add(reaction, user):
    if reaction.message.author == client.user:
        await reaction.message.channel.send(f'Glad to see your {reaction} to my message {user.name}.')

@client.event
async def on_error(event, *args, **kwargs):
    msg = args[0]
    LOG.error(f'{msg.author}@{msg.channel} : "{msg.content}"\n{traceback.format_exc()}')
    usr = client.get_user(config.get('my_id'))
    await usr.send(f'{msg.author}@{msg.channel} : "{msg.content}"\n{traceback.format_exc()}')

@client.event
async def on_command_error(ctx, error):
    if isinstance(error, CommandNotFound):
        await ctx.message.author.send(f'{error} is not a valid command')
        return
    elif isinstance(error, MissingRequiredArgument):
        await ctx.message.author.send(f'"{ctx.command}" is missing arguments, {error}')
        return

    LOG.debug(f'Command error: {error}')

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

def is_mention(msg):
    return bool(re.match(r'^\<@!([0-9])+\>$', msg))

def parse_mention(msg):
    m = re.match(r'^(.+)?(\<@![0-9]+\>)(.+)?$', msg)
    if m:
        return m.group(2)

client.run(config.get('token'))

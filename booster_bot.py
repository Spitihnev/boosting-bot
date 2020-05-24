import logging
import discord
from discord.ext import commands
import traceback

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)
LOG.setLevel(level=logging.DEBUG)
TOKEN = r'NzA3MjQwNDkyNTIxMzU3MzQ1.XrbyfQ.Y1viasyuAFtWflsi4MeS9rTdpbI'
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
        LOG.debug('yaay i said something')
        return

    if message.content == 'error':
        raise RuntimeError()

    if message.author.id == 233632440177000448:
        LOG.debug('sending response')
        resp = 'Jurko je kokot'
        await message.channel.send(resp)
    else:
        LOG.debug('I dont know you')

    await client.process_commands(message)

@client.command(name='quit')
async def shutdown(ctx):
    if ctx.author.id == 233632440177000448:
        LOG.debug('Leaving...')
        await client.logout()

@client.event
async def on_reaction_add(reaction, user):
    if reaction.message.author == client.user:
        await reaction.message.channel.send(f'Glad to see your {reaction} to my message {user.name}.')

@client.event
async def on_error(event, *args, **kwargs):
    msg = args[0]
    LOG.error(traceback.format_exc())
    await msg.channel.send(f'Grats {msg.author} you caused an error!')


client.run(TOKEN)

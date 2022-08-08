import config
import asyncio
import pickle
import os
import logging

LOG = logging.getLogger(__name__)


def init():
    global tracked_msgs
    global open_boosts
    global unprocessed_transactions
    global known_roles
    #TODO rewrite to remove global lock object
    global lock
    global loaded

    tracked_msgs = {}
    open_boosts = {}
    unprocessed_transactions = {}
    lock = asyncio.Lock()
    known_roles = {}
    loaded = False


async def init_discord_objects(client):
    global emojis
    global known_roles
    global open_boosts
    global unprocessed_transactions
    global loaded

    emojis = {'dps': client.get_emoji(config.get('emojis', 'dps')),
              'tank': client.get_emoji(config.get('emojis', 'tank')),
              'healer': client.get_emoji(config.get('emojis', 'healer'))}

    #TODO ugly
    keyblasters_roles = [guild for guild in client.guilds if guild.id == 442319306030710785][0].roles
    known_roles = {'blaster': [role for role in keyblasters_roles if role.id == 1004889816443392000][0],
                   'booster': [role for role in keyblasters_roles if role.id == 790528382588157962][0],
                   'alliance_booster': [role for role in keyblasters_roles if role.id == 804838552625217619][0]
                   }

    if os.path.exists('cache.pickle'):
        with open('cache.pickle', 'rb') as f:
            open_boosts_data, unprocessed_transactions = pickle.load(f)

        for (channel_id, message_id), boost in open_boosts_data.items():
            try:
                msg_obj = await client.get_channel(channel_id).fetch_message(message_id)
                LOG.debug('Boost msg: %s', msg_obj)
                open_boosts[boost.uuid] = (msg_obj, (boost, asyncio.Lock()))
            except:
                LOG.error('Failed to load boost message from channel: %s msg_id: %s for boost %s', channel_id, message_id, boost)

    loaded = True

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

    tracked_msgs = {}
    open_boosts = {}
    unprocessed_transactions = {}
    lock = asyncio.Lock()
    known_roles = {}


async def init_discord_objects(client):
    global emojis
    global known_roles
    global open_boosts
    global unprocessed_transactions

    emojis = {'dps': client.get_emoji(config.get('emojis', 'dps')),
              'tank': client.get_emoji(config.get('emojis', 'tank')),
              'healer': client.get_emoji(config.get('emojis', 'healer'))}

    #TODO ugly
    keyblasters_roles = [guild for guild in client.guilds if guild.id == 442319306030710785][0].roles
    known_roles = {'blaster': [role for role in keyblasters_roles if role.name == 'SL Blaster'][0],
                   'booster': [role for role in keyblasters_roles if role.name == 'SL Booster'][0],
                   'alliance_booster': [role for role in keyblasters_roles if role.name == 'Alliance Booster'][0]
                   }

    if os.path.exists('cache.pickle'):
        with open('cache.pickle', 'rb') as f:
            open_boosts_data, unprocessed_transactions = pickle.load(f)

        for (k1, k2), boost in open_boosts_data.items():
            msg_obj = await client.get_channel(k1).fetch_message(k2)
            LOG.debug('Boost msg: %s', msg_obj)
            open_boosts[boost.uuid] = (msg_obj, (boost, asyncio.Lock()))

import re
import logging
import datetime
from typing import List, Union
import asyncio

import discord
from discord.ext.commands.errors import BadArgument
from dateutil import tz

import constants
import globals

LOG = logging.getLogger(__name__)


def is_mention(msg, include_roles=True):
    if include_roles:
        return bool(re.match(r'^<@?[#!&]?([0-9])+>$', msg))
    else:
        return bool(re.match(r'^<@([0-9])+>$', msg))


# --------------------------------------------------------------------------------------------------------------------------------------------

def parse_mention(msg):
    m = re.match(r'^(.+)?(<@![0-9]+>)(.+)?$', msg)
    if m:
        return m.group(2)


# --------------------------------------------------------------------------------------------------------------------------------------------

def mention2id(mention):
    id_str = ''
    for char in mention:
        if char in '0123456789':
            id_str += char
    return int(id_str)


# --------------------------------------------------------------------------------------------------------------------------------------------

def parse_nick2realm(nick):
    try:
        realm_name = nick.split('-')[1].strip()
    except:
        raise BadArgument(f'Nick "{nick}" is not in correct format, please use <character_name>-<realm_name>.')
    realm_name = constants.is_valid_realm(realm_name, True)
    return realm_name


# --------------------------------------------------------------------------------------------------------------------------------------------

def msg_author_check(author, channel=None):
    def inner_check(msg):
        if channel is None:
            return msg.author == author
        else:
            return msg.author == author and msg.channel == channel

    return inner_check


# --------------------------------------------------------------------------------------------------------------------------------------------

async def send_channel_message(channel, msg):
    for sendable_msg in chunk_message(msg):
        await channel.send(sendable_msg)


async def send_channel_embed(channel, msg, title=''):
    for sendable_msg in chunk_message(msg):
        await channel.send(embed=discord.Embed(title=title, description=sendable_msg))


# --------------------------------------------------------------------------------------------------------------------------------------------

def chunk_message(msg, limit=2000):
    tmp_msg = ''
    for line in msg.split('\n'):
        if len(line) + len(tmp_msg) + 1 < limit:
            tmp_msg += '\n' + line
        else:
            yield tmp_msg
            tmp_msg = line

    if tmp_msg:
        yield tmp_msg


# --------------------------------------------------------------------------------------------------------------------------------------------

def gold_str2int(gold_str):
    gold_str = gold_str.lower()

    m = re.match('^([0-9]+)([kKmM]?)$', gold_str)
    if not m:
        raise BadArgument(f'"{gold_str}" not not a valid gold amount. Accepted formats: <int_value>[mk]')

    int_part = int(m.group(1))
    if int(m.group(1)) < 0:
        raise BadArgument('Only non-negative amounts are accepted.')

    if m.group(2) == 'k':
        return int(float(int_part * 1000))
    elif m.group(2) == 'm':
        return int(float(int_part * 1e6))

    return int(float(int_part))


# --------------------------------------------------------------------------------------------------------------------------------------------

def utc2local_time(utc_datetime: str):
    dt = datetime.datetime.strptime(utc_datetime, '%Y-%m-%d %H:%M:%S.%f').replace(tzinfo=tz.tzutc())
    return dt.astimezone(tz.gettz('Europe/Bratislava')).strftime('%Y-%m-%d %H:%M:%S')


# --------------------------------------------------------------------------------------------------------------------------------------------

def format_tracking_data(data: dict, guild):
    res = ''
    for tracked_msg in data.values():
        res += f'---- {tracked_msg["url"]} ----\n'
        res += 'Added reactions:\n'
        for dt, id, emoji in tracked_msg['added']:
            member = guild.get_member(id)
            res += f'{emoji} {utc2local_time(dt)}: {member.nick if member.nick is not None else f"{member.name}#{member.discriminator}"}\n'

        res += '\nRemoved reactions:\n'
        for dt, id, emoji in tracked_msg['removed']:
            member = guild.get_member(id)
            res += f'{emoji} {utc2local_time(dt)}: {member.nick if member.nick is not None else f"{member.name}#{member.discriminator}"}\n'

    return res

# --------------------------------------------------------------------------------------------------------------------------------------------


def user_has_any_role(user_roles: List[discord.Role], roles_to_check: List[Union[str, int]]):
    try:
        for role in user_roles:
            if role.name in roles_to_check or role.id in roles_to_check:
                return True
    except:
        LOG.debug(f'user roles: {user_roles} checked roles: {roles_to_check}')
    return False


def msg_id2boost_uuid(msg_id):
    for boost_uuid, boost in globals.open_boosts.items():
        if boost[0].id == msg_id:
            return boost_uuid

# --------------------------------------------------------------------------------------------------------------------------------------------


async def query_user(client: discord.Client, query: str,  channel: discord.TextChannel, author: discord.User, timeout: int = 15, on_query_fail_msg: str = None):
    msg = None

    await channel.send(query)
    try:
        msg = await client.wait_for('message', check=msg_author_check(author, channel), timeout=timeout)
    except asyncio.TimeoutError:
        if on_query_fail_msg is not None:
            await channel.send(on_query_fail_msg)

    return msg

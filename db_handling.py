import logging
import traceback
import typing
from collections import defaultdict

import discord
import pymysql

import config
import constants

LOG = logging.getLogger(__name__)
TRANSACTIONS = ('add', 'deduct', 'payout')

#--------------------------------------------------------------------------------------------------------------------------------------------

class DatabaseError(Exception):
    pass
class UserAlreadyExists(Exception):
    pass
class UserNotFoundError(Exception):
    pass
class RealmAlreadyExists(Exception):
    pass
class UnknownRealmName(Exception):
    pass

#--------------------------------------------------------------------------------------------------------------------------------------------

def get_balance(discord_id, guild_id):
    ttl = 0
    with _db_connect() as crs:
        crs.execute('select amount from transactions as t where booster_id=%s and guild_id=%s', (discord_id, guild_id))
        for amount, in crs:
            ttl += amount

    if not ttl:
        return 'Total: 0'
    else:
        return f'Total: {ttl}'

#--------------------------------------------------------------------------------------------------------------------------------------------

def list_transactions(user_id, limit):
    res = []
    with _db_connect() as crs:
        crs.execute('select type, amount, date_added, comment, author_id from transactions where booster_id=%s order by id desc limit {}'.format(limit), user_id)
        for type, amount, date_added, comment, author_id in crs:
            res.append((f'transaction_type: {type}, amount:{amount}, date_added: {date_added}, comment: "{comment}"', author_id))

    return res

#--------------------------------------------------------------------------------------------------------------------------------------------

def list_top_boosters(limit, guild_id, realm_name=None):
    LOG.info(f'Listing top boosters for {realm_name}')

    res = []
    with _db_connect() as crs:
        if realm_name is None:
            crs.execute('select sum(amount) as s, booster_id from transactions where guild_id=%s and booster_id in (select dsc_id from users) group by booster_id having s != 0 order by s desc limit {}'.format(limit), guild_id)
        else:
            crs.execute('select sum(amount) as s, booster_id from transactions join users on (booster_id = dsc_id) where home_realm=%s and guild_id=%s and booster_id in (select dsc_id from users) group by booster_id having s != 0 order by s desc limit {}'.format(limit), (realm_name, guild_id))
        for amount, name in crs:
            LOG.debug((amount, name))
            res.append((amount, name))

    return res
    
#--------------------------------------------------------------------------------------------------------------------------------------------

def execute_end_cycle(guild_id, author_id):
    payout = {}
    results = []
    with _db_connect() as crs:
        crs.execute('select sum(amount) as s, booster_id from transactions where guild_id=%s and booster_id in (select dsc_id from users) group by booster_id having s > 0 order by s desc', guild_id)
        for amount, dsc_id in crs:
            payout[dsc_id] = amount

        for booster_id, amount in payout.items():
            try:
                add_tranaction('payout', booster_id, author_id, amount, guild_id)
                results.append((booster_id, amount))
            except DatabaseError as e:
                LOG.error('Payout exception %s', e)
                results.append((booster_id, 'failed'))

    return results

#--------------------------------------------------------------------------------------------------------------------------------------------

def add_tranaction(type, booster_id, transaction_author_id, amount, guild_id, comment=None):
    if type in ('deduct', 'payout'):
        amount  = -amount

    with _db_connect() as crs:
        try:
            crs.execute('insert into transactions (`type`, `author_id`, `booster_id`, `amount`, `comment`, `guild_id`) values (%s, %s, %s, %s, %s, %s)', (type, transaction_author_id, booster_id, amount, comment, guild_id))
        except:
            raise DatabaseError(f'Failed to add transaction with parameters {type} {booster_id} {amount} {comment}, reason: {traceback.format_exc()}')

#--------------------------------------------------------------------------------------------------------------------------------------------

def get_realm_balance(realm_name, dsc_id):
    realm_id = realm_name2id(realm_name)
    all_transactions = []
    with _db_connect() as crs:
        try:
            crs.execute('select type, amount from transactions where booster_id=%s and realm_id=%s', (dsc_id, realm_id))
            for tt, amount in crs:
                all_transactions.append((tt, amount))
        except:
            raise DatabaseError(f'Failed to get all transactions for user with id {dsc_id} on realm {realm_name}.')

        ttl = 0
        for tt, amount in all_transactions:
            if tt in ('transfer_to', 'add'):
                ttl += amount
            elif tt in ('transfer_from', 'deduct'):
                ttl -= amount

        return amount

#--------------------------------------------------------------------------------------------------------------------------------------------

def alias2realm(alias):
    LOG.info(f'Getting alias for {alias}')

    with _db_connect() as crs:
        ret = crs.execute('select realm_name from aliases where alias=%s', alias)
        if ret == 0:
            return alias
        else:
            return crs.fetchone()[0]

#--------------------------------------------------------------------------------------------------------------------------------------------

def add_user(discord_id, home_realm):
    LOG.info(f'adding user with id {discord_id} {home_realm}')

    conn = _db_connect()
    with conn.cursor() as crs:
        try:
            crs.execute('insert into users (`dsc_id`, `home_realm`) values (%s, %s) on duplicate key update home_realm=%s', (discord_id, home_realm, home_realm))
        except:
            raise DatabaseError(f'Failed to add new user with id {discord_id}: {traceback.format_exc()}')
        conn.commit()

#--------------------------------------------------------------------------------------------------------------------------------------------

def remove_user(discord_id):
    LOG.info(f'Removing user with id {discord_id}')

    conn = _db_connect()
    with conn.cursor() as crs:
        try:
            crs.execute('delete from users where dsc_id = %s', discord_id)
        except:
            raise DatabaseError(f'Failed to remove new user with id {discord_id}: {traceback.format_exc()}')
        conn.commit()

#--------------------------------------------------------------------------------------------------------------------------------------------

def add_alias(realm_name, alias, update=False):
    LOG.info(f'adding alias {realm_name} as {alias}')

    conn = _db_connect()
    with conn as crs:
        if not update:
            try:
                crs.execute('insert into aliases (`realm_name`, `alias`) values(%s, %s)', (realm_name, alias))
                conn.commit()
                return True
            except pymysql.IntegrityError as e:
                raise DatabaseError(e)
        else:
            try:
                crs.execute('insert into aliases (`realm_name`, `alias`) values(%s, %s) on duplicate key update alias=%s', (realm_name, alias, alias))
                conn.commit()
                return True
            except Exception as e:
                LOG.error(f'{e}, {traceback.format_exc()}')
                raise DatabaseError('Critical error occurred, contact administrator.')

#--------------------------------------------------------------------------------------------------------------------------------------------

def add_realm(name):
    if name not in constants.EU_REALM_NAMES:
        raise UnknownRealmName(f'Realm {name} is not a known EU realm.')

    conn = _db_connect()
    with conn.cursor() as crs:
        try:
            crs.execute('insert into realms (`name`) values (%s)', name)
        except:
            raise DatabaseError(f'Failed to add new realm with name {name}: {traceback.format_exc()}')
        conn.commit()
        crs.execute('select id from realms where name=%s', name)
        return crs.fetchone()

#--------------------------------------------------------------------------------------------------------------------------------------------

def realm_name2id(name):
    if name is None:
        return None

    with _db_connect() as crs:
        ret = crs.execute('select id from realms where name=%s', name)
        if ret == 0:
            new_realm = add_realm(name)
            if new_realm:
                return new_realm
            else:
                raise DatabaseError(f'Failed to add new realm with name {name}, {traceback.format_exc()}')
        elif ret > 1:
            raise DatabaseError(f'More realms with the same id (wtf did you do?)')
        else:
            return crs.fetchone()

#--------------------------------------------------------------------------------------------------------------------------------------------

def user_list2tuple(users: typing.List[discord.User]):
    res = []
    with _db_connect() as crs:
        for user in users:
            rows = crs.execute('select id, dsc_id, name from users where name=%s', f'{user.name}#{user.discriminator}')
            if rows == 1:
                id, discord_id, name = crs.fetchone()
            elif rows == 0:
                id, discord_id, name = add_user(f'{user.name}#{user.discriminator}', user.id)

            res.append((id, discord_id, name))
    return res

#--------------------------------------------------------------------------------------------------------------------------------------------

def _db_connect():
    try:
        return pymysql.connect(**config.get('db_creds'))
    except:
        raise DatabaseError(f'Unable connect to DB! : {traceback.format_exc()}')

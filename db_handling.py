import pymysql
import logging
import traceback
import typing
import discord
from collections import defaultdict
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
        crs.execute('select type, amount, date_added, comment, name from transactions join users on (dsc_id = author_id) where booster_id=%s order by id desc limit {}'.format(limit), user_id)
        for type, amount, date_added, comment, name in crs:
            res.append(f'transaction_type: {type}, amount:{amount}, date_added: {date_added}, comment: "{comment}", transaction_author: {name}')

    return res

#--------------------------------------------------------------------------------------------------------------------------------------------

def list_top_boosters(limit, realm_name=None):
    LOG.info(f'Listing top boosters for {realm_name}')

    res = []
    with _db_connect() as crs:
        if realm_name is None:
            crs.execute('select sum(amount), booster_id from transactions group by booster_id order by amount desc limit {}'.format(limit))
        else:
            crs.execute('select sum(amount), booster_id from transactions join users on (booster_id = dsc_id) where home_realm=%s group by booster_id order by amount desc limit {}'.format(limit), realm_name)
        for amount, name in crs:
            res.append((amount, name))

    return res
    
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

def add_boost(raw_boostee: str, advertisers: typing.List[discord.User], boosters:typing.List[discord.User], price: int, comment: str):
    boostee, boostee_realm_name = raw_boostee.split('-')
    boostee_realm_id = realm2id(boostee_realm_name)
    advertisers_str = ','.join([db_user[0] for db_user in user_list2tuple(advertisets)])
    boosters_str = ','.join([db_user[0] for db_user in user_list2tuple(boosters)])

    with _db_connect() as crs:
        try:
            crs.execute('insert into boosts (`boostee`, `boostee_realm_id`, `advertisers`, `boosters`, `price`, `comment`) values (%s, %s, %s, %s, %s)', (boostee, boostee_realm_id, advertisers_str, boosters_str, price, comment))
        except:
            raise DatabaseError(f'Failed to add boost, last_query: {crs._last_executed}, {traceback.format_exc()}')

    advertiser_price = int(amount * config.get('adv_cut') / len(advertisers))
    managment_price = int(amount * config.get('mng_cut') / len(config.get('managers')))
    booster_price = int(amount * (1 - config.get('adv_cut') - config.get('mng_cut')) / len(boosters))

    for advertiser in advertisers_str.split(','):
        add_tranaction('add', int(advertiser), advertiser_price, boostee_realm_id, comment='advertiser cut')

    for manager in config.get('managment'):
        add_tranaction('add', manager, managment_price, boostee_realm_id, comment='managment cut')

    for booster in boosters_str.split(','):
        add_tranaction('add', booster, booster_price, boostee_realm_id, comment='booster cut')

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

def add_user(name, discord_id, home_realm):
    LOG.info(f'adding user {name} with id {discord_id} {home_realm}')

    conn = _db_connect()
    with conn.cursor() as crs:
        try:
            crs.execute('insert into users (`name`, `dsc_id`, `home_realm`) values (%s, %s, %s) on duplicate key update home_realm=%s', (name, discord_id, home_realm, home_realm))
        except:
            raise DatabaseError(f'Failed to add new user with name {name}: {traceback.format_exc()}')
        conn.commit()
        crs.execute('select * from users where dsc_id=%s', discord_id)
        return crs.fetchone()

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
                raise DatabaseError('Critical error occured, contact administrator.')

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

def name2dsc_id(name):
    with _db_connect() as crs:
        ret = crs.execute('select dsc_id from users where name=%s', name)
        if ret == 0:
            raise UserNotFoundError(f'User {name} not found!')
        else:
            for user_dsc_id in crs:
                return user_dsc_id

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

            res.append((id, dsc_id, name))
    return res

#--------------------------------------------------------------------------------------------------------------------------------------------

def _db_connect():
    try:
        return pymysql.connect(**config.get('db_creds'))
    except:
        raise DatabaseError(f'Unable connect to DB! : {traceback.format_exc()}')

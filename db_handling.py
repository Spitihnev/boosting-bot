import pymysql
import logging
import traceback
import typing
import discord
from collections import defaultdict
import config
import constants

LOG = logging.getLogger(__name__)

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

def get_balance(discord_id):
    ttl = defaultdict(int)
    with _db_connect() as crs:
        crs.execute('select type, amount, r.name from transactions as t left join realms as r on (r.id = t.realm_id) left join users as u on (t.booster_id = u.id) where u.dsc_id=%s', discord_id)
        for t_type, amount, realm_name in crs:
            if t_type in ('deduct', 'payout', 'transfer_from'):
                ttl[realm_name] -= amount
            elif t_type in ('add', 'transfer_to'):
                ttl[realm_name] += amount

    if not ttl:
        return 'Your total balance is: 0'
    else:
        res = ''
        for k, v in ttl.items():
            res += f'{k: v}\n----------------\n'
        res += f'Total: {sum(ttl.values())}'
        return res

#--------------------------------------------------------------------------------------------------------------------------------------------

def add_tranaction(type, booster_name, amount, realm_name, comment=None):
    booster_id = name2id(booster_name)
    realm_id = realm_name2id(realm_name)
    with _db_connect() as crs:
        try:
            crs.execute('insert into transactions (`type`, `booster_id`, `amount`, `comment`)', (type, booster_id, amount, comment))
        except:
            raise DatabaseError(f'Failed to add transaction with parameters {type} {booster_name} (translated into {booster_id}) {realm_name} (translated into {realm_id}) {amount} {comment}, reason: {traceback.format_exc()}')

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

def add_user(name, discord_id):
    LOG.info(f'adding user {name} with id {discord_id}')
    exist_check = None
    try:
        exist_check = name2id(name)
    except UserNotFoundError:
        pass
    if exist_check:
        raise UserAlreadyExists(f'User with name {name} already exists')

    conn = _db_connect()
    with conn.cursor() as crs:
        try:
            crs.execute('insert into users (`name`, `dsc_id`) values (%s, %s)', (name, discord_id))
        except:
            raise DatabaseError(f'Failed to add new user with name {name}: {traceback.format_exc()}')
        conn.commit()
        crs.execute('select * from users where dsc_id=%s', discord_id)
        return crs.fetchone()

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

def name2id(name_or_id):
    with _db_connect() as crs:
        if isinstance(name_or_id, str):
            ret = crs.execute('select id from users where name=%s', name_or_id)
        else:
            ret = crs.execute('select id from users where dsc_id=%s', name_or_id)
        if ret == 0:
            raise UserNotFoundError(f'User {name_or_id} not found!')
        elif ret > 1:
            raise DatabaseError(f'More users with the same dsc_id (wtf did you do?)')
        else:
            for user_id in crs:
                return user_id

#--------------------------------------------------------------------------------------------------------------------------------------------

def name2dsc_id(name):
    with _db_connect() as crs:
        ret = crs.execute('select dsc_id from users where name=%s', name)
        if ret == 0:
            raise UserNotFoundError(f'User {name} not found!')
        elif ret > 1:
            raise DatabaseError(f'More users with the same id (wtf did you do?)')
        else:
            for user_dsc_id in crs:
                return user_dsc_id

#--------------------------------------------------------------------------------------------------------------------------------------------

def realm_name2id(name):
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

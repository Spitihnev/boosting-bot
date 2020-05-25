import pymysql
import logging
import traceback

import config
import constants

LOG = logging.getLogger(__name__)

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

def add_tranaction(type, booster_name, amount, realm_name, comment=None):
    booster_id = name2id(booster_name)
    realm_id = realm_name2id(realm_name)
    with _db_connect() as conn:
        crs = conn.cursor()
        try:
            crs.execute('insert into transactions ("type", "booster_id", "amount", "comment")', (type, booster_id, amount, comment))
        except:
            raise DatabaseError(f'Failed to add transaction with parameters {type} {booster_name} (translated into {booster_id}) {realm_name} (translated into {realm_id}) {amount} {comment}, reason: {traceback.format_exc()}')

def add_boost(raw_boostee, advertisers, boosters, price, comment):
    raise NotImplementedError

def get_realm_balance(realm_name):
    raise NotImplementedError

def add_user(name, discord_id):
    exist_check = None
    try:
        exist_check = name2id(name)
    except UserNotFoundError:
        pass
    if exist_check:
        raise UserAlreadyExists(f'User with name {name} already exists')

    with _db_connect() as conn:
        crs = conn.cursor()
        try:
            crs.execute('insert into users ("name", "dsc_id") values ("%s", "%s")', (name, discord_id))
            conn.commit()
        except:
            raise DatabaseError(f'Failed to add new realm with name {name}: {traceback.format_exc()}')

def add_realm(name):
    if name not in constants.EU_REALM_NAMES:
        raise UnknownRealmName(f'Realm {name} is not a known EU realm.')

    with _db_connect() as conn:
        try:
            crs.execute('insert into realms ("name") values ("%s")', name)
            conn.commit()
        except:
            raise DatabaseError(f'Failed to add new realm with name {name}: {traceback.format_exc()}')

def name2id(name):
    with _db_connect() as conn:
        crs = conn.cursor()
        ret = crs.execute('select id from users where name="%s"', name)
        if ret == 0:
            raise UserNotFoundError(f'User {name} not found!')
        elif res > 1:
            raise DatabaseError(f'More users with the same dsc_id (wtf did you do?)')
        else:
            for user_id in crs:
                return user_id

def name2dsc_id(name):
    with _db_connect() as conn:
        crs = conn.cursor()
        ret = crs.execute('select dsc_id from users where name="%s"', name)
        if ret == 0:
            raise UserNotFoundError(f'User {name} not found!')
        elif res > 1:
            raise DatabaseError(f'More users with the same id (wtf did you do?)')
        else:
            for user_dsc_id in crs:
                return user_dsc_id

def realm_name2id(name):
    with _db_connect() as conn:
        crs = conn.cursor()
        ret = crs.execute('select id from realms where name="%s"', name)
        if ret == 0:
            new_realm = add_realm(name)
            if new_realm:
                return new_realm
            else:
                raise DatabaseError(f'Failed to add new realm with name {name}, {traceback.format_exc()}')
        elif res > 1:
            raise DatabaseError(f'More realms with the same id (wtf did you do?)')
        else:
            for realm_id in crs:
                return realm_id

def _db_connect():
    try:
        return pymysql.connect(**config.get('db_creds'))
    except:
        raise DatabaseError(f'Unable connect to DB! : {traceback.format_exc()}')

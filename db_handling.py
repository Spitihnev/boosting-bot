
import pymysql
import logging
import traceback

import config

LOG = logging.getLogger(__name__)

class DatabaseError(Exception):
    pass

class UserNotFoundError(Exception):
    pass

def add_tranaction(type, booster_name, amount, comment=None):
    raise NotImplementedError

def add_boost(raw_boostee, advertisers, boosters, price, comment):
    raise NotImplementedError

def add_user(name, discord_id):
    with _db_connect() as conn:
        try:
            crs.execute('insert into users ("name", "dsc_id") values ("%s", "%s")', (name, discord_id))
            conn.commit()
        except:
            raise DatabaseError(f'Failed to add new realm with name {name}: {traceback.format_exc()}')

def add_realm(name):
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

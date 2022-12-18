from datetime import datetime, timedelta
import logging
import traceback
import asyncio

import discord.errors
from discord.ext import tasks, commands

import globals
import booster_bot
import config

LOG = logging.getLogger(__name__)


class TrackerCallback(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.update_tracked.start()

    def cog_unload(self):
        self.update_tracked.cancel()

    @tasks.loop(minutes=15.0)
    async def update_tracked(self):
        try:
            now = datetime.utcnow()
            to_pop = []

            for msg_id in globals.tracked_msgs:
                if datetime.strptime(globals.tracked_msgs[msg_id]['track_start'], '%Y-%m-%d %H:%M:%S.%f') + timedelta(hours=globals.tracked_msgs[msg_id]['limit']) < datetime.utcnow():
                    to_pop.append(msg_id)

            for msg_id in to_pop:
                guild = self.bot.get_guild(globals.tracked_msgs[msg_id]['guild_id'])
                member = self.bot.get_user(globals.tracked_msgs[msg_id]['author_id'])

                data = booster_bot.format_tracking_data({msg_id: globals.tracked_msgs[msg_id]}, guild)
                await booster_bot.send_channel_message(member.dm_channel, 'Tracking expired:\n' + data)

                _ = globals.tracked_msgs.pop(msg_id)
        except:
            LOG.error('Error in updating tracked msgs: %s', traceback.format_exc())

    @update_tracked.before_loop
    async def before_update_tracked(self):
        LOG.debug('calling before update tracked')
        await self.bot.wait_until_ready()


class BoostCallback(commands.Cog):
    """
    Counts down time for reserved boosts and starts boosts when full
    """
    def __init__(self, bot):
        self.bot = bot
        self.update_boosts.start()

    def cog_unload(self):
        self.update_boosts.cancel()

    @tasks.loop(seconds=5.0)
    async def update_boosts(self):
        LOG.debug('boost callback called')
        #async with globals.lock:
        try:
            for boost_uuid, (msg, (boost_obj, lock)) in globals.open_boosts.items():
                async with lock:
                    old_tick = boost_obj.blaster_only_clock
                    should_update = boost_obj.clock_tick()

                    if old_tick != 0 and boost_obj.blaster_only_clock == 0 and boost_obj.status == 'open':
                        booster = globals.known_roles.get('booster', '')
                        await msg.channel.send(f'Boost {boost_obj.uuid} now open for {booster.mention}')

                    if should_update:
                        edited_msg = await msg.edit(embed=boost_obj.embed())
                        globals.open_boosts[boost_uuid] = edited_msg, (boost_obj, lock)
                    if boost_obj.start_boost():
                        edited_msg = await msg.edit(embed=boost_obj.embed())
                        globals.open_boosts[boost_uuid] = edited_msg, (boost_obj, lock)
                        await edited_msg.channel.send(f'Boost {boost_obj.uuid} started: ' + ' '.join([b.mention for b in boost_obj.boosters]), reference=edited_msg)
        except (RuntimeError, discord.errors.HTTPException):
            LOG.exception('update_boosts exception! ')
            await self.bot.get_user(config.get('my_id')).send(f'Cog exception: {traceback.format_exc()}')
            #TODO make some nice fix not this shit

        except Exception:
            LOG.exception('Unknown exception in update_boosts!')
            await self.bot.get_user(config.get('my_id')).send(f'Unknown cog exception:  {traceback.format_exc()}')

    @update_boosts.before_loop
    async def before_update_boosts(self):
        await self.bot.wait_until_ready()

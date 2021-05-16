from discord.ext import tasks, commands
from datetime import datetime, timedelta
import logging
import traceback

import globals
import booster_bot


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
        for msg, boost_obj in globals.open_boosts.values():
            should_update =  boost_obj.clock_tick()
            if boost_obj.start_boost() or should_update:
                await msg.edit(embed=boost_obj.embed())

    @update_boosts.before_loop
    async def before_update_boosts(self):
        await self.bot.wait_until_ready()

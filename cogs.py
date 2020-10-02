from discord.ext import tasks, commands
from datetime import datetime, timedelta
import logging

import globals
import booster_bot


LOG = logging.getLogger(__name__)


class TrackerCallback(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.update_tracked.start()

    def cog_unload(self):
        self.update_tracked.cancel()

    @tasks.loop(seconds=10.0)
    async def update_tracked(self):
        now = datetime.utcnow()
        to_pop = []

        for msg_id in globals.tracked_msgs:
            if datetime.strptime(globals.tracked_msgs[msg_id]['track_start'], '%Y-%m-%d %H:%M:%S.%f') + timedelta(hours=globals.tracked_msgs[msg_id]['limit']) < datetime.utcnow():
                to_pop.append(msg_id)

        for msg_id in to_pop:
            guild = self.bot.get_guild(globals.tracked_msgs[msg_id]['guild_id'])
            member = self.bot.get_user(globals.tracked_msgs[msg_id]['author_id'])

            data = booster_bot.format_tracking_data({msg_id: globals.tracked_msgs[msg_id]}, guild)
            await member.dm_channel.send(data)

            _ = globals.tracked_msgs.pop(msg_id)

    async def before_update(self):
        await self.bot.wait_until_ready()

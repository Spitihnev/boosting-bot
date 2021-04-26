import discord
from dataclasses import dataclass
from typing import List
import uuid

import config
import globals

@dataclass
class Booster:
    """
    Booster representation for dungeon boosts.
    """
    mention: str
    is_dps: bool = False
    is_tank: bool = False
    is_healer: bool = False
    is_keyholder: bool = False

    def __post_init__(self):
        if not self.has_any_role():
            raise ValueError('Need at least one role for booster!')

    def has_any_role(self):
        return any([self.is_dps, self.is_tank, self.is_healer])


@dataclass
class Boost:
    """
    Base abstract boost class
    """

    pot: int
    boost_author: str
    advertiser: str
    boosters: List[Booster]
    realm_name: str
    character_to_whisper: str
    key: str
    armor_stack: str = 'NO'
    boosts_number: int = 1
    note: str = None
    team_take: str = None
    uuid: str = str(uuid.uuid4())

    def __post_init__(self):
        cuts = config.get('cuts')
        if self.realm_name in cuts:
            self._adv_cut = cuts[self.realm_name]['adv']
            self._mng_cut = cuts[self.realm_name]['mng']
        else:
            self._adv_cut = cuts['default']['adv']
            self._mng_cut = cuts['default']['mng']

    def embed(self):
        embed = discord.Embed(title=self.advertiser)
        embed.set_thumbnail(url='https://logos-download.com/wp-content/uploads/2016/02/WOW_logo-700x701.png')
        embed.add_field(name='Pot', value=f'{self.pot:6d}g', inline=True)
        embed.add_field(name='Booster cut', value=f'{(self.pot * (1 - (self._adv_cut + self._mng_cut)) / 4):6.0f}g', inline=True)
        embed.add_field(name='Armor stack', value=self.armor_stack, inline=False)
        embed.add_field(name='Number of boosts', value=f'{self.boosts_number:1d}', inline=True)
        embed.add_field(name='Realm name', value=self.realm_name, inline=True)
        embed.add_field(name='Dungeon key', value=self.key, inline=False)
        embed.add_field(name='Boosters', value=self.format_boosters(), inline=False)
        if self.note is not None:
            embed.add_field(name='Note', value=f'```{self.note}```', inline=False)
        if self.team_take is not None:
            embed.add_field(name='Team boost', value=self.team_take)
        embed.add_field(name='Advertiser', value=self.advertiser, inline=False)
        embed.add_field(name='Character to whisper', value='/w ' + self.character_to_whisper, inline=True)
        embed.set_footer(text=self.uuid)
        return embed

    def format_boosters(self):
        res_string = ''
        for booster in self.boosters:
            res_string += booster.mention

            if booster.is_dps:
                res_string += str(globals.emojis['dps'])
            if booster.is_healer:
                res_string += str(globals.emojis['healer'])
            if booster.is_tank:
                res_string += str(globals.emojis['tank'])
            if booster.is_keyholder:
                res_string += config.get('emojis', 'keyholder')

            res_string += '\n'

        return res_string

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

    def has_any_role(self):
        return any([self.is_dps, self.is_tank, self.is_healer])

    def __add__(self, other):
        if self.mention != other.mention:
            raise ValueError('Only roles for same booster can be added!')

        self.is_dps = self.is_dps or other.is_dps
        self.is_healer = self.is_healer or other.is_healer
        self.is_tank = self.is_tank or other.is_tank
        self.is_keyholder = self.is_keyholder or other.is_keyholder

        return self

    def __sub__(self, other):
        if self.mention != other.mention:
            raise ValueError('Only roles for same booster can be subtracted!')

        if self.is_dps:
            self.is_dps = self.is_dps ^ other.is_dps
        if self.is_healer:
            self.is_healer = self.is_healer ^ other.is_healer
        if self.is_tank:
            self.is_tank = self.is_tank ^ other.is_tank
        if self.is_keyholder:
            self.is_keyholder = self.is_keyholder ^ other.is_keyholder

        return self

    def __len__(self):
        obj_length = 0
        if self.is_dps:
            obj_length += 1
        if self.is_tank:
            obj_length += 1
        if self.is_healer:
            obj_length += 1

        return obj_length


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
    armor_stack: str
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

        if not res_string:
            return '-'
        return res_string

    def add_booster(self, booster):
        for booster_idx, signed_booster in enumerate(self.boosters):
            if signed_booster.mention == booster.mention:
                self.boosters[booster_idx] += booster
                return True

        if len(self.boosters) < 4:
            self.boosters.append(booster)
            if not self.is_this_valid_setup():
                self.boosters.pop(-1)
            else:
                return True

        return False

    def remove_booster(self, booster):
        for booster_idx, signed_booster in enumerate(self.boosters):
            if signed_booster.mention == booster.mention:
                self.boosters[booster_idx] -= booster

                if not self.is_this_valid_setup(True):
                    self.boosters.pop(booster_idx)
                    return

                if not self.boosters[booster_idx].has_any_role() or not self.is_this_valid_setup(True):
                    self.boosters.pop(booster_idx)

    def is_this_valid_setup(self, check_keyholder=False):

        if not any([booster.is_healer for booster in self.boosters]) and len(self.boosters) == 4:
            return False
        if not any([booster.is_tank for booster in self.boosters]) and len(self.boosters) == 4:
            return False
        if not any([booster.is_keyholder for booster in self.boosters]) and len(self.boosters) == 4 and check_keyholder:
            return False

        tank = None
        healer = None
        dps = []
        for booster in sorted(self.boosters, key=len):
            if booster.is_tank and tank is None:
                tank = booster
                continue
            if booster.is_healer and healer is None:
                healer = booster
                continue
            if booster.is_dps and len(dps) < 3:
                dps.append(booster)
                continue
            return False

        return True

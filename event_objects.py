from dataclasses import dataclass
from typing import List, Union
import uuid
import logging

import discord

from helper_functions import mention2id
import config
import globals

LOG = logging.getLogger(__name__)


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
    is_locked: bool = False

    def __post_init__(self):
        self.id = mention2id(self.mention)

    def has_any_role(self):
        return any([self.is_dps, self.is_tank, self.is_healer])

    def __add__(self, other):
        if self.id != other.id:
            raise ValueError('Only roles for same booster can be added!')

        self.is_dps = self.is_dps or other.is_dps
        self.is_healer = self.is_healer or other.is_healer
        self.is_tank = self.is_tank or other.is_tank
        self.is_keyholder = self.is_keyholder or other.is_keyholder

        return self

    def __sub__(self, other):
        if self.id != other.id:
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
class DummyRole:
    mention: str
    name: str
    id: int

@dataclass
class Boost:
    """
    Base abstract boost class
    """

    author_dc_id: int
    pot: int
    boost_author: str
    advertiser_mention: str
    advertiser_display_name: str
    boosters: List[Booster]
    realm_name: str
    character_to_whisper: str
    key: str
    armor_stack: Union[discord.Role, str, DummyRole]
    pings: str = ''
    uuid: Union[str, None] = None
    boosts_number: int = 1
    note: Union[str, None] = None
    team_take: Union[discord.Role, None] = None
    status: str = 'open'
    blaster_only_clock: int = 24
    team_take_clock: int = 0
    include_advertiser_in_payout: bool = True
    bigger_adv_cuts: bool = False
    temp_booster_slot: Union[None, Booster] = None
    temp_booster_clock: int = 0

    def __post_init__(self):
        if self.uuid is None:
            self.uuid = str(uuid.uuid4())

        cuts = config.get('cuts')
        if self.realm_name in cuts and self.bigger_adv_cuts:
            self._adv_cut = cuts[self.realm_name]['adv']
            self._mng_cut = cuts[self.realm_name]['mng']
        else:
            self._adv_cut = cuts['default']['adv']
            self._mng_cut = cuts['default']['mng']

        self.past_team_takes = []
        if self.armor_stack != 'no':
            self.armor_stack = DummyRole(self.armor_stack.mention, self.armor_stack.name, self.armor_stack.id)

    @property
    def color(self):
        if self.team_take is not None and self.status == 'open':
            return discord.Color.gold()

        if self.status == 'open':
            return discord.Color.green()

        if self.status == 'editing':
            return discord.Color.orange()

        return discord.Color.red()

    @property
    def armor_stack_mention(self):
        if self.armor_stack != 'no':
            return self.armor_stack.mention

        return self.armor_stack

    def embed(self):
        embed = discord.Embed(title=self.advertiser_display_name, color=self.color)
        embed.set_thumbnail(url='https://logos-download.com/wp-content/uploads/2016/02/WOW_logo-700x701.png')
        embed.add_field(name='Pot', value=f'{self.pot:6,d}g', inline=True)
        embed.add_field(name='Booster cut', value=f'{(self.pot * (1 - (self._adv_cut + self._mng_cut)) // 4):6,.0f}g', inline=True)
        embed.add_field(name='Armor stack', value=self.armor_stack_mention, inline=False)
        embed.add_field(name='Number of boosts', value=f'{self.boosts_number:1d}', inline=True)
        embed.add_field(name='Realm name', value=self.realm_name, inline=True)
        embed.add_field(name='Dungeon key', value=self.key, inline=False)
        embed.add_field(name='Boosters', value=self.format_boosters(), inline=False)
        if self.note is not None:
            embed.add_field(name='Note', value=f'```{self.note}```', inline=False)
        if self.team_take is not None:
            embed.add_field(name='Team boost', value=self.team_take.mention, inline=False)
        embed.add_field(name='Advertiser', value=self.advertiser_mention, inline=True)
        if self.include_advertiser_in_payout:
            embed.add_field(name='Advertiser cut', value=f'{(self.pot * self._adv_cut):6,.0f}g')
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
        """
        Returns should_edit value for boost embed
        """
        if self.status != 'open':
            return False

        for booster_idx, signed_booster in enumerate(self.boosters):
            if signed_booster.id == booster.id:
                self.boosters[booster_idx] += booster
                return True

        if len(self.boosters) < 4:
            self.boosters.append(booster)
            if not self.is_this_valid_setup():
                self.boosters.pop(-1)
            else:
                return True

        # keyholder override
        if not any([signed_booster.is_keyholder for signed_booster in self.boosters]) and booster.is_keyholder and self.temp_booster_slot is None and all(
                [booster.id != signed_booster.id for signed_booster in self.boosters]):
            LOG.debug('Adding temp booster %s', booster)
            self.temp_booster_slot = booster
            self.temp_booster_clock = 2
            return False

        if not any([signed_booster.is_keyholder for signed_booster in self.boosters]) and booster.has_any_role() and self.temp_booster_slot is not None:
            if self.temp_booster_slot.id == booster.id:
                self.temp_booster_slot += booster

                for booster_idx in range(len(self.boosters) - 1, -1, -1):
                    temp_setup = [b for b in self.boosters]
                    temp_setup[booster_idx] = self.temp_booster_slot
                    if self.is_this_valid_setup(True, alternative_setup=temp_setup):
                        self.boosters = temp_setup
                        LOG.debug(f'{booster} used keyholder override.')
                        self.temp_booster_slot = None
                        self.temp_booster_clock = 0
                        return True

    def remove_booster(self, booster: Booster):
        if self.status != 'open':
            return False

        for booster_idx, signed_booster in enumerate(self.boosters):
            if signed_booster.id == booster.id:
                self.boosters[booster_idx] -= booster

                if not self.is_this_valid_setup(True):
                    self.boosters.pop(booster_idx)
                    return

                if not self.boosters[booster_idx].has_any_role() or not self.is_this_valid_setup(True):
                    self.boosters.pop(booster_idx)

    def is_this_valid_setup(self, check_keyholder=False, alternative_setup: Union[None, List[Booster]] = None):
        if alternative_setup is not None:
            boosters = alternative_setup
        else:
            boosters = self.boosters

        if not any([booster.is_healer for booster in boosters]) and len(boosters) == 4:
            return False
        if not any([booster.is_tank for booster in boosters]) and len(boosters) == 4:
            return False
        if not any([booster.is_keyholder for booster in boosters]) and len(boosters) == 4 and check_keyholder:
            return False

        tank = None
        healer = None
        dps = []
        for booster in sorted(boosters, key=len):
            if booster.is_tank and tank is None:
                tank = booster
                continue
            if booster.is_healer and healer is None:
                healer = booster
                continue
            if booster.is_dps and len(dps) < 2:
                dps.append(booster)
                continue
            return False

        return True

    def process(self):
        if self.status == 'open':
            return

        embed = discord.Embed(title=f'Boost {self.uuid}')
        transactions = []
        booster_cut = self.pot * (1 - (self._adv_cut + self._mng_cut)) // 4
        adv_cut = self.pot * self._adv_cut
        for booster in self.boosters:
            transactions.append(f'{booster.mention} {booster_cut}')

        if self.include_advertiser_in_payout:
            transactions.append(f'{self.advertiser_mention} {adv_cut}')

        embed.add_field(name='Pot', value=f'{self.pot:6,d}g', inline=True)
        embed.add_field(name='Realm name', value=self.realm_name, inline=True)
        embed.add_field(name='Dungeon key', value=self.key, inline=False)
        embed.add_field(name='Advertiser', value=self.advertiser_mention, inline=True)
        embed.add_field(name='Advertiser cut', value=f'{(self.pot * self._adv_cut):6,.0f}g', inline=True)
        embed.add_field(name='Advertiser cut kept', value=str(not self.include_advertiser_in_payout), inline=True)
        if self.note is not None:
            embed.add_field(name='Note', value=f'```{self.note}```', inline=False)
        # transaction info is expected last
        embed.add_field(name='Transactions to be processed:', value='\n'.join([f'{transaction}' for transaction in transactions]))
        return embed

    def clock_tick(self):
        should_update = False

        if self.blaster_only_clock > 0:
            self.blaster_only_clock -= 1

        if self.team_take_clock > 0 and self.status == 'open':
            self.team_take_clock -= 1
            if self.team_take_clock == 0:
                self.team_take = None
                should_update = True

        if self.temp_booster_clock > 0:
            self.temp_booster_clock -= 1
            if self.temp_booster_clock == 0:
                self.temp_booster_slot = None

        return should_update

    def start_boost(self):
        if len(self.boosters) == 4 and self.is_this_valid_setup(check_keyholder=True) and self.status == 'open':
            self.status = 'started'
            return True

        return False

    def change_armor_stack(self, new_armor_role: discord.Role):
        if new_armor_role == 'no':
            self.armor_stack = new_armor_role
            return

        self.armor_stack = DummyRole(new_armor_role.mention, new_armor_role.name, new_armor_role.id)

import operator
from difflib import SequenceMatcher

from discord.ext.commands.errors import BadArgument

import db_handling


EU_REALM_NAMES = ("Aegwynn", "Aerie Peak", "Agamaggan", "Aggra (Português)", "Aggramar", "Ahn'Qiraj", "Al'Akir", "Alexstrasza", "Alleria", "Alonsus", "Aman'Thul",
"Ambossar", "Anachronos", "Anetheron", "Antonidas", "Anub'arak", "Arak-arahm", "Arathi", "Arathor", "Archimonde", "Area 52", "Argent Dawn", "Arthas",
"Arygos", "Ashenvale", "Aszune", "Auchindoun", "Azjol-Nerub", "Azshara", "Azuregos", "Azuremyst", "Baelgun", "Balnazzar", "Blackhand", "Blackmoore",
"Blackrock", "Blackscar", "Blade's Edge", "Bladefist", "Bloodfeather", "Bloodhoof", "Bloodscalp", "Blutkessel", "Booty Bay", "Borean Tundra", "Boulderfist",
"Bronze Dragonflight", "Bronzebeard", "Burning Blade", "Burning Legion", "Burning Steppes", "C'Thun", "Chamber of Aspects", "Chants éternels", "Cho'gall",
"Chromaggus", "Colinas Pardas", "Confrérie du Thorium", "Conseil des Ombres", "Crushridge", "Culte de la Rive noire", "Daggerspine", "Dalaran", "Dalvengyr",
"Darkmoon Faire", "Darksorrow", "Darkspear", "Das Konsortium", "Das Syndikat", "Deathguard", "Deathweaver", "Deathwing", "Deepholm", "Defias Brotherhood",
"Dentarg", "Der Mithrilorden", "Der Rat von Dalaran", "Der abyssische Rat", "Destromath", "Dethecus", "Die Aldor", "Die Arguswacht", "Die Nachtwache",
"Die Silberne Hand", "Die Todeskrallen", "Die ewige Wacht", "Doomhammer", "Draenor", "Dragonblight", "Dragonmaw", "Drak'thul", "Drek'Thar", "Dun Modr",
"Dun Morogh", "Dunemaul", "Durotan", "Earthen Ring", "Echsenkessel", "Eitrigg", "Eldre'Thalas", "Elune", "Emerald Dream", "Emeriss", "Eonar", "Eredar",
"Eversong", "Executus", "Exodar", "Festung der Stürme", "Fordragon", "Forscherliga", "Frostmane", "Frostmourne", "Frostwhisper", "Frostwolf", "Galakrond",
"Garona", "Garrosh", "Genjuros", "Ghostlands", "Gilneas", "Goldrinn", "Gordunni", "Gorgonnash", "Greymane", "Grim Batol", "Grom", "Gul'dan", "Hakkar",
"Haomarush", "Hellfire", "Hellscream", "Howling Fjord", "Hyjal", "Illidan", "Jaedenar", "Kael'thas", "Karazhan", "Kargath", "Kazzak", "Kel'Thuzad", "Khadgar",
"Khaz Modan", "Khaz'goroth", "Kil'jaeden", "Kilrogg", "Kirin Tor", "Kor'gall", "Krag'jin", "Krasus", "Kul Tiras", "Kult der Verdammten", "La Croisade écarlate",
"Laughing Skull", "Les Clairvoyants", "Les Sentinelles", "Lich King", "Lightbringer", "Lightning's Blade", "Lordaeron", "Los Errantes", "Lothar", "Madmortem",
"Magtheridon", "Mal'Ganis", "Malfurion", "Malorne", "Malygos", "Mannoroth", "Marécage de Zangar", "Mazrigos", "Medivh", "Minahonda", "Moonglade", "Mug'thol",
"Nagrand", "Nathrezim", "Naxxramas", "Nazjatar", "Nefarian", "Nemesis", "Neptulon", "Ner'zhul", "Nera'thor", "Nethersturm", "Nordrassil", "Norgannon", "Nozdormu",
"Onyxia", "Outland", "Perenolde", "Pozzo dell'Eternità", "Proudmoore", "Quel'Thalas", "Ragnaros", "Rajaxx", "Rashgarroth", "Ravencrest", "Ravenholdt", "Razuvious",
"Rexxar", "Runetotem", "Sanguino", "Sargeras", "Saurfang", "Scarshield Legion", "Sen'jin", "Shadowsong", "Shattered Halls", "Shattered Hand", "Shattrath", "Shen'dralar",
"Silvermoon", "Sinstralis", "Skullcrusher", "Soulflayer", "Spinebreaker", "Sporeggar", "Steamwheedle Cartel", "Stormrage", "Stormreaver", "Stormscale", "Sunstrider",
"Suramar", "Sylvanas", "Taerar", "Talnivarr", "Tarren Mill", "Teldrassil", "Temple noir", "Terenas", "Terokkar", "Terrordar", "The Maelstrom", "The Sha'tar",
"The Venture Co", "Theradras", "Thermaplugg", "Thrall", "Throk'Feroth", "Thunderhorn", "Tichondrius", "Tirion", "Todeswache", "Trollbane", "Turalyon", "Twilight's Hammer",
"Twisting Nether", "Tyrande", "Uldaman", "Ulduar", "Uldum", "Un'Goro", "Varimathras", "Vashj", "Vek'lor", "Vek'nilash", "Vol'jin", "Wildhammer", "Wrathbringer", "Xavius",
"Ysera", "Ysondre", "Zenedar", "Zirkel des Cenarius", "Zul'jin", "Zuluhed")


def is_valid_realm(realm_name, check_aliases=False):
    if realm_name is None:
        return
    if realm_name in EU_REALM_NAMES:
        return realm_name
    elif check_aliases:
        return is_valid_realm(db_handling.alias2realm(realm_name))
    else:
        similar = {valid_realm_name: SequenceMatcher(None, realm_name, valid_realm_name).quick_ratio() for valid_realm_name in EU_REALM_NAMES}
        most_similar = max(similar.items(), key=operator.itemgetter(1))[0]
        raise BadArgument(f'"{realm_name}" is not a known EU realm name. Did you mean "{most_similar}"?')

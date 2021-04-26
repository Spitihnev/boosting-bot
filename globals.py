import config


def init():
    global tracked_msgs
    global open_boosts

    tracked_msgs = {}
    open_boosts = {}


def init_custom_emojis(client):
    global emojis

    emojis = {'dps': client.get_emoji(config.get('emojis', 'dps')),
                     'tank': client.get_emoji(config.get('emojis', 'tank')),
                     'healer': client.get_emoji(config.get('emojis', 'healer'))}

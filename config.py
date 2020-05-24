import json
import copy

_CONFIG = {}

def get(*keys, default=None):
    data = _CONFIG
    keys = list(keys)
    try:
        while keys:
            k = keys.pop(0)
            data = data[k]
        if isinstance(data, dict) or isinstance(data, list):
            return copy.deepcopy(data)
        return data

    except KeyError:
        return default

def _load_config():
    global _CONFIG
    with open('config.json') as f:
        _CONFIG = copy.deepcopy(json.load(f))

if not _CONFIG:
    _load_config()
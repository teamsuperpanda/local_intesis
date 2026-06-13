from datetime import timedelta

DOMAIN = "local_intesis"

DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin"

API_LOGIN = "login"
API_GET_INFO = "getinfo"
API_GET_DP = "getavailabledatapoints"
API_GET_VALUE = "getdatapointvalue"
API_SET_VALUE = "setdatapointvalue"

UID_POWER = 1
UID_MODE = 2
UID_FAN_SPEED = 4
UID_VVANE = 5
UID_HVANE = 6
UID_SETPOINT = 9
UID_TEMPERATURE = 10
UID_SETPOINT_MIN = 35
UID_SETPOINT_MAX = 36
UID_OUTDOOR_TEMP = 37
UID_CONFIG_FAN_MAP = 67
UID_CONFIG_VVANE = 63
UID_CONFIG_HVANE = 64

MODE_MAP = {
    0: "auto",
    1: "heat",
    2: "dry",
    3: "fan",
    4: "cool",
}

MODE_REVERSE = {v: k for k, v in MODE_MAP.items()}

HVAC_MODE_MAP = {
    "auto": "heat_cool",
    "heat": "heat",
    "dry": "dry",
    "fan": "fan_only",
    "cool": "cool",
}

HVAC_MODE_REVERSE = {v: k for k, v in HVAC_MODE_MAP.items()}

SCAN_INTERVAL = timedelta(seconds=30)

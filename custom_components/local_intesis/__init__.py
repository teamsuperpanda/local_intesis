from __future__ import annotations

import logging

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    API_GET_DP,
    API_GET_INFO,
    API_GET_VALUE,
    API_LOGIN,
    API_SET_VALUE,
    DOMAIN,
    FAN_SPEED_TABLES,
    PRESET_MODE_MAP,
    UID_ALARM_STATUS,
    UID_AQUAREA_COOL_CONSUMPTION,
    UID_AQUAREA_HEAT_CONSUMPTION,
    UID_CLIMATE_WORKING_MODE,
    UID_CONFIG_HVANE,
    UID_CONFIG_VVANE,
    UID_ERROR_CODE,
    UID_FAN_SPEED,
    UID_HVANE,
    UID_RSSI,
    UID_VVANE,
)

PLATFORMS = ["climate"]

_LOGGER = logging.getLogger(__name__)


class IntesisGateway:
    def __init__(self, host: str, username: str, password: str, session: aiohttp.ClientSession) -> None:
        self._host = host
        self._username = username
        self._password = password
        self._session = session
        self._base = f"http://{host}/api.cgi"
        self._session_id: str | None = None
        self._devices: dict = {}
        self._datapoints: dict = {}
        self._config_fan_map: dict[int, str] = {}
        self._config_vvane_list: list[int] = []
        self._config_hvane_list: list[int] = []
        self._has_climate_working_mode = False
        self._has_alarm_status = False
        self._has_error_code = False
        self._has_rssi = False
        self._has_aquarea_cool = False
        self._has_aquarea_heat = False

    async def _request(self, command: str, _retry: bool = True, **kwargs) -> dict | None:
        if not self._session_id:
            if not await self._authenticate():
                _LOGGER.error("Not authenticated for %s", self._host)
                return None
        payload = {"command": command, "data": {"sessionID": self._session_id, **kwargs}}
        try:
            async with self._session.post(self._base, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                json_resp = await resp.json(content_type=None)
                if json_resp.get("success"):
                    return json_resp.get("data")
                if "error" in json_resp:
                    code = json_resp["error"].get("code")
                    if code in (1, 5) and _retry:
                        self._session_id = None
                        if command != API_LOGIN:
                            return await self._request(command, _retry=False, **kwargs)
                    _LOGGER.warning("API error %s: %s", code, json_resp["error"].get("message"))
                    return None
                _LOGGER.warning("Unexpected response from %s: %s", self._host, json_resp)
                return None
        except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
            _LOGGER.error("Request failed for %s: %s", self._host, exc)
            return None

    async def _authenticate(self) -> bool:
        payload = {"command": API_LOGIN, "data": {"username": self._username, "password": self._password}}
        try:
            async with self._session.post(self._base, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                json_resp = await resp.json(content_type=None)
                if json_resp.get("success"):
                    self._session_id = json_resp["data"]["id"]["sessionID"]
                    _LOGGER.debug("Authenticated with %s", self._host)
                    return True
                _LOGGER.warning("Auth failed for %s: %s", self._host, json_resp.get("error", {}).get("message", "unknown"))
        except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
            _LOGGER.error("Auth failed for %s: %s", self._host, exc)
        return False

    async def connect(self) -> bool:
        result = await self._request(API_GET_INFO)
        if result is None:
            return False
        info = result.get("info", {})
        raw_id = info.get("sn", "")
        device_id = raw_id.split(" ")[0] if raw_id else "unknown"
        self._devices[device_id] = {
            "name": info.get("ownSSID", f"Intesis_{device_id}"),
            "model": info.get("deviceModel", ""),
            "fw": info.get("wlanFwVersion", ""),
        }
        dp_result = await self._request(API_GET_DP)
        if dp_result:
            for dp in dp_result.get("dp", {}).get("datapoints", []):
                self._datapoints[dp["uid"]] = dp
            self._parse_config_datapoints()
        return True

    def _parse_config_datapoints(self) -> None:
        self._has_climate_working_mode = UID_CLIMATE_WORKING_MODE in self._datapoints
        self._has_alarm_status = UID_ALARM_STATUS in self._datapoints
        self._has_error_code = UID_ERROR_CODE in self._datapoints or 144 in self._datapoints
        self._has_rssi = UID_RSSI in self._datapoints
        self._has_aquarea_cool = UID_AQUAREA_COOL_CONSUMPTION in self._datapoints
        self._has_aquarea_heat = UID_AQUAREA_HEAT_CONSUMPTION in self._datapoints

        self._config_fan_map = self._get_fan_map()

        vvane_cfg = self._datapoints.get(UID_CONFIG_VVANE)
        vvane_dp = self._datapoints.get(UID_VVANE)
        self._config_vvane_list = []
        if vvane_dp and "descr" in vvane_dp:
            states = vvane_dp["descr"].get("states", [])
            if states:
                self._config_vvane_list = states
        if not self._config_vvane_list and vvane_cfg and "descr" in vvane_cfg:
            self._config_vvane_list = vvane_cfg["descr"].get("states", [])

        hvane_cfg = self._datapoints.get(UID_CONFIG_HVANE)
        hvane_dp = self._datapoints.get(UID_HVANE)
        self._config_hvane_list = []
        if hvane_dp and "descr" in hvane_dp:
            states = hvane_dp["descr"].get("states", [])
            if states:
                self._config_hvane_list = states
        if not self._config_hvane_list and hvane_cfg and "descr" in hvane_cfg:
            self._config_hvane_list = hvane_cfg["descr"].get("states", [])

    def _get_fan_map(self) -> dict[int, str]:
        if UID_FAN_SPEED not in self._datapoints:
            return {}
        fan_values = sorted(self._datapoints[UID_FAN_SPEED]["descr"]["states"])
        device_model = self._devices.get(self.device_id, {}).get("model", "")
        if 0 not in fan_values and "MH-AC-WIFI" in device_model:
            fan_values = [0] + fan_values
        for table_key in sorted(FAN_SPEED_TABLES.keys(), reverse=True):
            table = FAN_SPEED_TABLES[table_key]
            if sorted(table.keys()) == fan_values:
                return table
        labels = ["auto", "low", "medium", "high", "max"]
        return {s: labels[i] if i < len(labels) else f"speed_{s}" for i, s in enumerate(fan_values)}

    async def poll_values(self) -> dict[int, int]:
        result = await self._request(API_GET_VALUE, uid="all")
        if result is None:
            return {}
        values = {}
        dpval = result.get("dpval", [])
        if isinstance(dpval, list):
            for item in dpval:
                values[item["uid"]] = item["value"]
        elif isinstance(dpval, dict):
            values[dpval["uid"]] = dpval["value"]
        return values

    async def set_value(self, uid: int, value: int) -> bool:
        result = await self._request(API_SET_VALUE, uid=uid, value=value)
        return result is not None

    @property
    def devices(self) -> dict:
        return self._devices

    @property
    def device_id(self) -> str:
        return next(iter(self._devices), "unknown")

    @property
    def device_name(self) -> str:
        return self._devices.get(self.device_id, {}).get("name", "Intesis Gateway")

    @property
    def device_model(self) -> str:
        return self._devices.get(self.device_id, {}).get("model", "")

    @property
    def fan_modes(self) -> list[str]:
        return list(dict.fromkeys(self._config_fan_map.values()))

    def get_fan_value(self, label: str) -> int | None:
        for k, v in self._config_fan_map.items():
            if v == label:
                return k
        return None

    def get_fan_label(self, value: int) -> str:
        return self._config_fan_map.get(value, "auto")

    @property
    def vvane_list(self) -> list[int]:
        return self._config_vvane_list

    @property
    def hvane_list(self) -> list[int]:
        return self._config_hvane_list

    def supports_vvane(self) -> bool:
        return bool(self._config_vvane_list)

    def supports_hvane(self) -> bool:
        return bool(self._config_hvane_list)

    def has_datapoint(self, uid: int) -> bool:
        return uid in self._datapoints

    @property
    def has_climate_working_mode(self) -> bool:
        return self._has_climate_working_mode

    @property
    def has_alarm_status(self) -> bool:
        return self._has_alarm_status

    @property
    def has_error_code(self) -> bool:
        return self._has_error_code

    @property
    def has_rssi(self) -> bool:
        return self._has_rssi

    @property
    def has_aquarea_cool(self) -> bool:
        return self._has_aquarea_cool

    @property
    def has_aquarea_heat(self) -> bool:
        return self._has_aquarea_heat

    @property
    def preset_modes(self) -> list[str]:
        return list(PRESET_MODE_MAP.values()) if self._has_climate_working_mode else []

    def get_preset_value(self, label: str) -> int | None:
        for k, v in PRESET_MODE_MAP.items():
            if v == label:
                return k
        return None

    def get_preset_label(self, value: int) -> str | None:
        return PRESET_MODE_MAP.get(value)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    host = entry.data[CONF_HOST]
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    session = async_get_clientsession(hass)
    gateway = IntesisGateway(host, username, password, session)
    if not await gateway.connect():
        raise ConfigEntryNotReady(f"Could not connect to gateway at {host}")
    hass.data[DOMAIN][entry.entry_id] = gateway
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok

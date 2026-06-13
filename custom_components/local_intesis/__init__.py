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
    UID_CONFIG_FAN_MAP,
    UID_CONFIG_HVANE,
    UID_CONFIG_VVANE,
    UID_FAN_SPEED,
    UID_VVANE,
    UID_HVANE,
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
        uid_67 = self._datapoints.get(UID_CONFIG_FAN_MAP)
        if uid_67 and "descr" in uid_67:
            states = uid_67["descr"].get("states", [0, 1, 2, 3])
            labels = ["auto", "low", "medium", "high", "max"]
            self._config_fan_map = {s: labels[i] if i < len(labels) else f"speed_{s}" for i, s in enumerate(states)}
        else:
            dp = self._datapoints.get(UID_FAN_SPEED)
            if dp:
                states = dp.get("descr", {}).get("states", [0, 1, 2, 3])
                labels = ["auto", "low", "medium", "high", "max"]
                self._config_fan_map = {s: labels[i] if i < len(labels) else f"speed_{s}" for i, s in enumerate(states)}

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

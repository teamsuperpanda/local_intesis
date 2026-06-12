from __future__ import annotations

import asyncio
import logging

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import IntesisGateway
from .const import (
    DOMAIN,
    HVAC_MODE_MAP,
    HVAC_MODE_REVERSE,
    MODE_MAP,
    MODE_REVERSE,
    SCAN_INTERVAL,
    UID_FAN_SPEED,
    UID_HVANE,
    UID_MODE,
    UID_OUTDOOR_TEMP,
    UID_POWER,
    UID_SETPOINT,
    UID_SETPOINT_MAX,
    UID_SETPOINT_MIN,
    UID_TEMPERATURE,
    UID_VVANE,
)

_LOGGER = logging.getLogger(__name__)

VANE_MAP = {
    0: "auto/stop",
    1: "manual1",
    2: "manual2",
    3: "manual3",
    4: "manual4",
    5: "manual5",
    6: "manual6",
    7: "manual7",
    8: "manual8",
    9: "manual9",
    10: "swing",
}

VANE_REVERSE = {v: k for k, v in VANE_MAP.items()}


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    gateway: IntesisGateway = hass.data[DOMAIN][entry.entry_id]

    async def _async_update():
        values = await gateway.poll_values()
        if not values:
            raise UpdateFailed("No data from gateway")
        return values

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=_async_update,
        update_interval=SCAN_INTERVAL,
    )
    await coordinator.async_refresh()

    async_add_entities([LocalIntesisClimate(coordinator, gateway)])


class LocalIntesisClimate(ClimateEntity):
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_precision = 1
    _attr_target_temperature_step = 1
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, coordinator: DataUpdateCoordinator, gateway: IntesisGateway) -> None:
        self.coordinator = coordinator
        self._gateway = gateway
        self._local_values: dict[int, int] = {}
        self._attr_unique_id = f"{DOMAIN}_{gateway.device_id}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, gateway.device_id)},
            "name": gateway.device_name,
            "model": gateway.device_model,
            "manufacturer": "IntesisHome",
            "sw_version": gateway.devices.get(gateway.device_id, {}).get("fw", ""),
        }
        self._attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.DRY, HVACMode.FAN_ONLY, HVACMode.HEAT_COOL]
        self._attr_fan_modes = gateway.fan_modes
        self._attr_supported_features = (
            ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TARGET_TEMPERATURE
        )
        if gateway.fan_modes:
            self._attr_supported_features |= ClimateEntityFeature.FAN_MODE
        if gateway.supports_vvane() or gateway.supports_hvane():
            self._attr_supported_features |= ClimateEntityFeature.SWING_MODE

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_coordinator_update))

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    async def async_update(self) -> None:
        await self.coordinator.async_request_refresh()

    def _value(self, uid: int) -> int | None:
        if uid in self._local_values:
            return self._local_values[uid]
        return self.coordinator.data.get(uid) if self.coordinator.data else None

    def _optimistic_set(self, uid: int, value: int) -> None:
        self._local_values[uid] = value

    async def _schedule_sync(self, delay: float = 1.5) -> None:
        async def _do_sync():
            await asyncio.sleep(delay)
            await self.coordinator.async_refresh()
            self._local_values.clear()

        asyncio.ensure_future(_do_sync())

    @property
    def current_temperature(self) -> float | None:
        val = self._value(UID_TEMPERATURE)
        if val is not None:
            return val / 10
        return None

    @property
    def target_temperature(self) -> float | None:
        val = self._value(UID_SETPOINT)
        if val is not None:
            return val / 10
        return None

    @property
    def target_temperature_high(self) -> float | None:
        val = self._value(UID_SETPOINT_MAX)
        if val is not None:
            return val / 10
        return None

    @property
    def target_temperature_low(self) -> float | None:
        val = self._value(UID_SETPOINT_MIN)
        if val is not None:
            return val / 10
        return None

    @property
    def hvac_mode(self) -> HVACMode:
        power = self._value(UID_POWER)
        if power == 0:
            return HVACMode.OFF
        mode = self._value(UID_MODE)
        if mode is not None:
            ih_mode = MODE_MAP.get(mode)
            if ih_mode:
                ha_mode = HVAC_MODE_MAP.get(ih_mode)
                if ha_mode:
                    return HVACMode(ha_mode)
        return HVACMode.OFF

    @property
    def fan_mode(self) -> str | None:
        val = self._value(UID_FAN_SPEED)
        if val is not None:
            return self._gateway.get_fan_label(val)
        return None

    @property
    def swing_mode(self) -> str:
        if not self._gateway.supports_vvane() and not self._gateway.supports_hvane():
            return "off"
        vvane = self._value(UID_VVANE)
        hvane = self._value(UID_HVANE)
        if vvane is not None and VANE_MAP.get(vvane) == "swing":
            if hvane is not None and VANE_MAP.get(hvane) == "swing":
                return "both"
            return "vertical"
        if hvane is not None and VANE_MAP.get(hvane) == "swing":
            return "horizontal"
        return "off"

    @property
    def swing_modes(self) -> list[str] | None:
        if not self._gateway.supports_vvane() and not self._gateway.supports_hvane():
            return None
        modes = ["off"]
        if self._gateway.supports_vvane():
            modes.append("vertical")
        if self._gateway.supports_hvane():
            modes.append("horizontal")
        if self._gateway.supports_vvane() and self._gateway.supports_hvane():
            modes.append("both")
        return modes

    @property
    def extra_state_attributes(self) -> dict:
        attrs = {}
        ot = self._value(UID_OUTDOOR_TEMP)
        if ot is not None:
            attrs["outdoor_temperature"] = ot / 10
        return attrs

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self._gateway.set_value(UID_POWER, 0)
            self._optimistic_set(UID_POWER, 0)
        else:
            ih_mode = HVAC_MODE_REVERSE.get(hvac_mode)
            if ih_mode:
                uid = MODE_REVERSE.get(ih_mode)
                if uid is not None:
                    await self._gateway.set_value(UID_POWER, 1)
                    await self._gateway.set_value(UID_MODE, uid)
                    self._optimistic_set(UID_POWER, 1)
                    self._optimistic_set(UID_MODE, uid)
        self.async_write_ha_state()
        await self._schedule_sync()

    async def async_set_temperature(self, **kwargs) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            val = int(temp * 10)
            await self._gateway.set_value(UID_SETPOINT, val)
            self._optimistic_set(UID_SETPOINT, val)
        self.async_write_ha_state()
        await self._schedule_sync()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        val = self._gateway.get_fan_value(fan_mode)
        if val is not None:
            await self._gateway.set_value(UID_FAN_SPEED, val)
            self._optimistic_set(UID_FAN_SPEED, val)
        self.async_write_ha_state()
        await self._schedule_sync()

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        if not self._gateway.supports_vvane() and not self._gateway.supports_hvane():
            return
        vvane_val = 0
        hvane_val = 0
        if swing_mode == "off":
            vvane_val = VANE_REVERSE.get("auto/stop", 0)
            hvane_val = VANE_REVERSE.get("auto/stop", 0)
        elif swing_mode == "vertical":
            vvane_val = VANE_REVERSE.get("swing", 10)
            hvane_val = VANE_REVERSE.get("auto/stop", 0)
        elif swing_mode == "horizontal":
            vvane_val = VANE_REVERSE.get("auto/stop", 0)
            hvane_val = VANE_REVERSE.get("swing", 10)
        elif swing_mode == "both":
            vvane_val = VANE_REVERSE.get("swing", 10)
            hvane_val = VANE_REVERSE.get("swing", 10)
        if self._gateway.supports_vvane():
            if vvane_val in self._gateway.vvane_list or not self._gateway.vvane_list:
                await self._gateway.set_value(UID_VVANE, vvane_val)
                self._optimistic_set(UID_VVANE, vvane_val)
        if self._gateway.supports_hvane():
            if hvane_val in self._gateway.hvane_list or not self._gateway.hvane_list:
                await self._gateway.set_value(UID_HVANE, hvane_val)
                self._optimistic_set(UID_HVANE, hvane_val)
        self.async_write_ha_state()
        await self._schedule_sync()

    async def async_turn_on(self) -> None:
        await self._gateway.set_value(UID_POWER, 1)
        self._optimistic_set(UID_POWER, 1)
        self.async_write_ha_state()
        await self._schedule_sync()

    async def async_turn_off(self) -> None:
        await self._gateway.set_value(UID_POWER, 0)
        self._optimistic_set(UID_POWER, 0)
        self.async_write_ha_state()
        await self._schedule_sync()

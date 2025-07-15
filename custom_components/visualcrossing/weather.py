"""Precipitation Sensors for Visual Crossing."""

import datetime
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.config_entries import ConfigEntry

# Only this import (no more from .weather...)
from . import VCPrecipCoordinator, DOMAIN

ICON_PAST = "mdi:water"
ICON_FUTURE = "mdi:weather-rainy"


class VCLast24hSensor(CoordinatorEntity, SensorEntity):
    _attr_name = "VC Rainfall Last 24 h"
    _attr_native_unit_of_measurement = "mm"
    _attr_icon = ICON_PAST

    def __init__(self, coord: VCPrecipCoordinator):
        super().__init__(coord)
        self._state = None

    async def _handle_coordinator_update(self):
        data = self.coordinator.data
        now = datetime.datetime.utcnow()
        cutoff = now - datetime.timedelta(hours=24)
        total = 0.0
        for day in data.get("days", []):
            for hour in day.get("hours", []):
                ts = datetime.datetime.fromisoformat(hour["datetime"])
                if cutoff <= ts < now:
                    total += hour.get("precip", 0) or 0
        self._state = round(total, 2)
        self.async_write_ha_state()

    @property
    def available(self):
        return self.coordinator.last_update_success

    @property
    def native_value(self):
        return self._state


class VCLast7dSensor(CoordinatorEntity, SensorEntity):
    _attr_name = "VC Rainfall Last 7 Days"
    _attr_native_unit_of_measurement = "mm"
    _attr_icon = ICON_PAST

    def __init__(self, coord: VCPrecipCoordinator):
        super().__init__(coord)
        self._state = None

    async def _handle_coordinator_update(self):
        data = self.coordinator.data
        today = datetime.date.today()
        cutoff = today - datetime.timedelta(days=7)
        total = 0.0
        for day in data.get("days", []):
            d = datetime.date.fromisoformat(day["datetime"])
            if cutoff < d < today:
                total += day.get("precip", 0) or 0
        self._state = round(total, 2)
        self.async_write_ha_state()

    @property
    def available(self):
        return self.coordinator.last_update_success

    @property
    def native_value(self):
        return self._state


class VCNext24hSensor(CoordinatorEntity, SensorEntity):
    _attr_name = "VC Rainfall Next 24 h"
    _attr_native_unit_of_measurement = "mm"
    _attr_icon = ICON_FUTURE

    def __init__(self, coord: VCPrecipCoordinator):
        super().__init__(coord)
        self._state = None

    async def _handle_coordinator_update(self):
        data = self.coordinator.data
        now = datetime.datetime.utcnow()
        cutoff = now + datetime.timedelta(hours=24)
        total = 0.0
        for day in data.get("days", []):
            for hour in day.get("hours", []):
                ts = datetime.datetime.fromisoformat(hour["datetime"])
                if now <= ts < cutoff:
                    total += hour.get("precip", 0) or 0
        self._state = round(total, 2)
        self.async_write_ha_state()

    @property
    def available(self):
        return self.coordinator.last_update_success

    @property
    def native_value(self):
        return self._state


class VCNext7dSensor(CoordinatorEntity, SensorEntity):
    _attr_name = "VC Rainfall Next 7 Days"
    _attr_native_unit_of_measurement = "mm"
    _attr_icon = ICON_FUTURE

    def __init__(self, coord: VCPrecipCoordinator):
        super().__init__(coord)
        self._state = None

    async def _handle_coordinator_update(self):
        data = self.coordinator.data
        today = datetime.date.today()
        cutoff = today + datetime.timedelta(days=7)
        total = 0.0
        for day in data.get("days", []):
            d = datetime.date.fromisoformat(day["datetime"])
            if today < d <= cutoff:
                total += day.get("precip", 0) or 0
        self._state = round(total, 2)
        self.async_write_ha_state()

    @property
    def available(self):
        return self.coordinator.last_update_success

    @property
    def native_value(self):
        return self._state


async def async_setup_entry(hass, entry: ConfigEntry, async_add_entities):
    """Set up the four precipitation sensors."""
    precip_coord = hass.data[DOMAIN][entry.entry_id + "_precip"]
    async_add_entities(
        [
            VCLast24hSensor(precip_coord),
            VCLast7dSensor(precip_coord),
            VCNext24hSensor(precip_coord),
            VCNext7dSensor(precip_coord),
        ],
        update_before_add=True,
    )

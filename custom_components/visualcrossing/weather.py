"""Support for WeatherFlow Forecast weather service."""

from __future__ import annotations

import logging
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from homeassistant.components.weather import (
    DOMAIN as WEATHER_DOMAIN,
    Forecast,
    SingleCoordinatorWeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.unit_system import METRIC_SYSTEM

from . import VCDataUpdateCoordinator
from .const import ATTR_DESCRIPTION, ATTR_LAST_UPDATED, CONDITIONS_MAP, DOMAIN

DEFAULT_NAME = "Visual Crossing Weather"

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add a weather entity from a config_entry."""
    coordinator: VCDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    entity_registry = er.async_get(hass)

    name: str | None = config_entry.data.get(CONF_NAME) or DEFAULT_NAME
    is_metric = hass.config.units is METRIC_SYSTEM

    entities: list[SingleCoordinatorWeatherEntity] = [
        VCWeather(coordinator, config_entry.data, False, name, is_metric)
    ]

    # Add hourly entity to legacy config entries
    if entity_registry.async_get_entity_id(
        WEATHER_DOMAIN, DOMAIN, _calculate_unique_id(config_entry.data, True)
    ):
        name_hourly = f"{name} hourly"
        entities.append(
            VCWeather(coordinator, config_entry.data, True, name_hourly, is_metric)
        )

    async_add_entities(entities)


def _calculate_unique_id(config: MappingProxyType[str, Any], hourly: bool) -> str:
    """Calculate unique ID."""
    suffix = "-hourly" if hourly else ""
    return f"{config[CONF_LATITUDE]}-{config[CONF_LONGITUDE]}{suffix}"


def format_condition(condition: str) -> str:
    """Return condition name from CONDITIONS_MAP."""
    for key, values in CONDITIONS_MAP.items():
        if condition in values:
            return key
    return condition


class VCWeather(SingleCoordinatorWeatherEntity[VCDataUpdateCoordinator]):
    """Implementation of a Visual Crossing weather condition."""

    _attr_attribution = "Weather Data delivered by Visual Crossing"
    _attr_has_entity_name = True
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_DAILY | WeatherEntityFeature.FORECAST_HOURLY
    )

    def __init__(
        self,
        coordinator: VCDataUpdateCoordinator,
        config: MappingProxyType[str, Any],
        hourly: bool,
        name: str,
        is_metric: bool,
    ) -> None:
        """Initialise the platform with a data instance and station."""
        super().__init__(coordinator)
        self._attr_unique_id = _calculate_unique_id(config, hourly)
        self._config = config
        self._is_metric = is_metric
        self._hourly = hourly
        self._attr_entity_registry_enabled_default = not hourly
        self._attr_device_info = DeviceInfo(
            name="Visual Crossing",
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN,)},  # type: ignore[arg-type]
            manufacturer="Visual Crossing",
            model="Forecast",
            configuration_url="https://www.visualcrossing.com/weather-api",
        )
        self._attr_name = name

    @property
    def condition(self) -> str | None:
        """Return the current condition."""
        icon = self.coordinator.data.current_weather_data.icon
        return format_condition(icon) if icon else None

    @property
    def native_temperature(self) -> float | None:
        """Return the temperature."""
        return self.coordinator.data.current_weather_data.temperature

    @property
    def native_pressure(self) -> float | None:
        """Return the pressure."""
        return self.coordinator.data.current_weather_data.pressure

    @property
    def humidity(self) -> float | None:
        """Return the humidity."""
        return self.coordinator.data.current_weather_data.humidity

    @property
    def native_wind_speed(self) -> float | None:
        """Return the wind speed."""
        return self.coordinator.data.current_weather_data.wind_speed

    @property
    def wind_bearing(self) -> float | str | None:
        """Return the wind direction."""
        return self.coordinator.data.current_weather_data.wind_bearing

    @property
    def native_wind_gust_speed(self) -> float | None:
        """Return the wind gust speed."""
        return self.coordinator.data.current_weather_data.wind_gust_speed

    @property
    def native_dew_point(self) -> float | None:
        """Return the dew point."""
        return self.coordinator.data.current_weather_data.dew_point

    @property
    def cloud_coverage(self) -> float | None:
        """Return the cloud coverage."""
        return self.coordinator.data.current_weather_data.cloud_cover

    @property
    def native_visibility(self) -> float | None:
        """Return the visibility."""
        return self.coordinator.data.current_weather_data.visibility

    @property
    def extra_state_attributes(self):
        """Return non-standard attributes."""
        return {
            ATTR_DESCRIPTION: self.coordinator.data.current_weather_data.description,
            ATTR_LAST_UPDATED: self.coordinator.data.current_weather_data.datetime.isoformat(),
        }

    def _forecast(self, hourly: bool) -> list[Forecast] | None:
        """Return the forecast array."""
        ha_forecast: list[Forecast] = []
        if hourly:
            for item in self.coordinator.data.hourly_forecast:
                cond = format_condition(item.icon) if item.icon else None
                ha_forecast.append(
                    {
                        "condition": cond,
                        "datetime": item.datetime.isoformat(),
                        "humidity": item.humidity,
                        "precipitation_probability": item.precipitation_probability,
                        "native_precipitation": item.precipitation,
                        "cloud_coverage": item.cloud_cover,
                        "native_pressure": item.pressure,
                        "native_temperature": item.temperature,
                        "native_apparent_temperature": item.apparent_temperature,
                        "wind_bearing": item.wind_bearing,
                        "native_wind_gust_speed": item.wind_gust_speed,
                        "native_wind_speed": item.wind_speed,
                        "uv_index": item.uv_index,
                    }
                )
        else:
            for item in self.coordinator.data.daily_forecast:
                cond = format_condition(item.icon) if item.icon else None
                ha_forecast.append(
                    {
                        "condition": cond,
                        "datetime": item.datetime.isoformat(),
                        "precipitation_probability": item.precipitation_probability,
                        "native_precipitation": item.precipitation,
                        "cloud_coverage": item.cloud_cover,
                        "native_temperature": item.temperature,
                        "native_templow": item.temp_low,
                        "wind_bearing": int(item.wind_bearing),
                        "native_wind_speed": item.wind_speed,
                    }
                )
        return ha_forecast

    @callback
    def _async_forecast_daily(self) -> list[Forecast] | None:
        """Return the daily forecast."""
        return self._forecast(False)

    @callback
    def _async_forecast_hourly(self) -> list[Forecast] | None:
        """Return the hourly forecast."""
        return self._forecast(True)

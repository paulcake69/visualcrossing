"""Visual Crossing Weather Platform (with Precipitation Sensors)."""

from __future__ import annotations

import datetime
import logging
from random import randrange
from types import MappingProxyType
from typing import Any, Self

from pyVisualCrossing import (
    VisualCrossing,
    ForecastData,
    ForecastDailyData,
    ForecastHourlyData,
    VisualCrossingTooManyRequests,
    VisualCrossingBadRequest,
    VisualCrossingInternalServerError,
    VisualCrossingUnauthorized,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    Platform,
    CONF_API_KEY,
    CONF_LANGUAGE,
    CONF_LATITUDE,
    CONF_LONGITUDE,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, CONF_DAYS

_LOGGER = logging.getLogger(__name__)

# 1) We have both weather and sensor platforms now
PLATFORMS = [Platform.WEATHER, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up Visual Crossing from a config entry."""
    # — weather coordinator
    coordinator = VCDataUpdateCoordinator(hass, config_entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[config_entry.entry_id] = coordinator

    # reload on options change
    config_entry.async_on_unload(
        config_entry.add_update_listener(async_update_entry)
    )

    # — precipitation coordinator (past 1 day → next 7 days)
    api_key = config_entry.data[CONF_API_KEY]
    lat = config_entry.data[CONF_LATITUDE]
    lon = config_entry.data[CONF_LONGITUDE]
    precip_coord = VCPrecipCoordinator(hass, api_key, lat, lon)
    await precip_coord.async_refresh()
    hass.data[DOMAIN][config_entry.entry_id + "_precip"] = precip_coord

    # 3) forward both platforms
    await hass.config_entries.async_forward_entry_setups(
        config_entry, PLATFORMS
    )
    return True


async def async_unload_entry(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> bool:
    """Unload a config entry (weather + precipitation)."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry, PLATFORMS
    )
    hass.data[DOMAIN].pop(config_entry.entry_id)
    hass.data[DOMAIN].pop(config_entry.entry_id + "_precip")
    return unload_ok


async def async_update_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    """Reload integration when options change."""
    await hass.config_entries.async_reload(config_entry.entry_id)


class CannotConnect(HomeAssistantError):
    """Unable to connect to the Visual Crossing API."""


class VCDataUpdateCoordinator(DataUpdateCoordinator["VCWeatherData"]):
    """Coordinator to fetch current weather and forecast."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        self.weather = VCWeatherData(
            hass, config_entry.data, config_entry.options
        )
        self.weather.initialize_data()

        # randomise interval to avoid spikes
        update_interval = datetime.timedelta(minutes=randrange(31, 32))
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN + "_weather",
            update_interval=update_interval,
        )

    async def _async_update_data(self) -> VCWeatherData:
        """Fetch current + forecast data."""
        try:
            return await self.weather.fetch_data()
        except VisualCrossingUnauthorized as err:
            _LOGGER.debug("Unauthorized: %s", err)
            raise ConfigEntryNotReady from err
        except (VisualCrossingBadRequest, VisualCrossingTooManyRequests) as err:
            _LOGGER.debug("API error: %s", err)
            raise UpdateFailed(err) from err
        except VisualCrossingInternalServerError as err:
            _LOGGER.debug("Server error: %s", err)
            raise ConfigEntryNotReady from err
        except Exception as err:
            raise UpdateFailed(err) from err


class VCWeatherData:
    """Hold data returned by pyVisualCrossing."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: MappingProxyType[str, Any],
        options: MappingProxyType[str, Any],
    ) -> None:
        self.hass = hass
        self._config = config
        self._options = options
        self._weather_data: VisualCrossing
        self.current_weather_data: ForecastData = {}
        self.daily_forecast: ForecastDailyData = []
        self.hourly_forecast: ForecastHourlyData = []

    def initialize_data(self) -> bool:
        """Instantiate the pyVisualCrossing client."""
        self._weather_data = VisualCrossing(
            self._config[CONF_API_KEY],
            self._config[CONF_LATITUDE],
            self._config[CONF_LONGITUDE],
            days=self._options.get(CONF_DAYS, 1),
            language=self._options.get(CONF_LANGUAGE),
            session=async_get_clientsession(self.hass),
        )
        return True

    async def fetch_data(self) -> Self:
        """Fetch data from the API."""
        _LOGGER.debug("Fetching Visual Crossing weather data")
        resp: ForecastData = await self._weather_data.async_fetch_data()
        if not resp:
            raise CannotConnect()
        self.current_weather_data = resp
        self.daily_forecast = resp.forecast_daily
        self.hourly_forecast = resp.forecast_hourly
        return self


class VCPrecipCoordinator(DataUpdateCoordinator[dict]):
    """Coordinator to fetch past 1 day and next 7 days of precipitation."""

    def __init__(self, hass: HomeAssistant, api_key: str, lat: float, lon: float):
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN + "_precip",
            update_interval=datetime.timedelta(hours=1),
        )
        self._api_key = api_key
        self._lat = lat
        self._lon = lon

    async def _async_update_data(self) -> dict:
        """Fetch the precipitation timeline from Visual Crossing."""
        session = async_get_clientsession(self.hass)
        today = datetime.date.today()
        start = (today - datetime.timedelta(days=1)).isoformat()
        end = (today + datetime.timedelta(days=7)).isoformat()
        url = (
            "https://weather.visualcrossing.com/VisualCrossingWebServices/"
            f"rest/services/timeline/{self._lat},{self._lon}/{start}/{end}"
        )
        params = {
            "unitGroup": "uk",
            "include": "hours,obs",
            "elements": "datetime,precip",
            "key": self._api_key,
        }
        resp = await session.get(url, params=params)
        resp.raise_for_status()
        return await resp.json()

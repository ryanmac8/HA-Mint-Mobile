"""
Custom integration to integrate Mint Mobile with Home Assistant.

"""
import asyncio
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MintMobile
from .const import (
    CONF_ATTRIBUTESENSORS,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_POLLING_INTERVAL,
    DEFAULT_POLLING_INTERVAL,
    DOMAIN,
    ISSUE_URL,
    PLATFORMS,
    STARTUP_MESSAGE,
    VERSION,
)

_LOGGER = logging.getLogger(__name__)


class MintMobileDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Mint Mobile data."""

    def __init__(self, hass: HomeAssistant, client: MintMobile, polling_interval: int):
        """Initialize."""
        self.client = client
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=polling_interval),
        )

    async def _async_update_data(self):
        """Update data via library."""
        try:
            return await self.client.async_get_all_data_remaining()
        except Exception as exception:
            raise UpdateFailed(f"Error communicating with Mint Mobile API: {exception}")


async def async_setup(hass: HomeAssistant, config: dict):
    """Disallow configuration via YAML"""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Load the saved entities."""
    _LOGGER.info(
        "Version %s is starting, if you have any issues please report them here: %s",
        VERSION,
        ISSUE_URL,
    )

    entry.async_on_unload(entry.add_update_listener(update_listener))

    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    token = entry.data.get("token")
    refresh_token = entry.data.get("refresh_token")
    expires_at = entry.data.get("expires_at")
    polling_interval = entry.data.get(CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL)

    session = async_get_clientsession(hass)

    def token_update_callback(new_token, new_refresh_token, new_expires_at):
        new_data = {
            **entry.data,
            "token": new_token,
            "refresh_token": new_refresh_token,
            "expires_at": new_expires_at,
        }
        hass.config_entries.async_update_entry(entry, data=new_data)

    client = MintMobile(
        session=session,
        username=username,
        password=password,
        token=token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        token_update_callback=token_update_callback,
    )

    coordinator = MintMobileDataUpdateCoordinator(hass, client, polling_interval)

    # Perform first refresh
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        raise ConfigEntryNotReady(f"Failed to perform initial fetch: {err}") from err

    # Store configuration state to detect user-initiated changes vs token updates
    coordinator.config_version = {
        CONF_USERNAME: username,
        CONF_PASSWORD: password,
        CONF_POLLING_INTERVAL: polling_interval,
        CONF_ATTRIBUTESENSORS: entry.data.get(CONF_ATTRIBUTESENSORS),
    }

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Handle removal of an entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        _LOGGER.info("Successfully removed sensor from the %s integration", DOMAIN)
    return unload_ok


async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Update listener."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not coordinator:
        return

    new_config = {
        CONF_USERNAME: entry.data.get(CONF_USERNAME),
        CONF_PASSWORD: entry.data.get(CONF_PASSWORD),
        CONF_POLLING_INTERVAL: entry.data.get(CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL),
        CONF_ATTRIBUTESENSORS: entry.data.get(CONF_ATTRIBUTESENSORS),
    }

    if getattr(coordinator, "config_version", None) != new_config:
        _LOGGER.info("User configuration changed. Reloading integration...")
        await hass.config_entries.async_reload(entry.entry_id)

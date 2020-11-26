"""Adds config flow for Mint Mobile."""
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from collections import OrderedDict
import voluptuous as vol
import logging

from .api import MintMobile
from .const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
    PLATFORMS,
)

_LOGGER = logging.getLogger(__name__)

class MintMobileFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Mint Mobile."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Initialize."""
        self._data = {}
        self._errors = {}

    async def async_step_user(self, user_input):
        """Handle a flow initialized by the user."""
        self._errors = {}


        if user_input is not None:
            #self._data.update(user_input)
            valid = await self._test_credentials(
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )
            if valid:
                return self.async_create_entry(
                    title=user_input[CONF_USERNAME], data=user_input
                )
            else:
                self._errors["base"] = "invalid_credentials"

            return await self._show_config_form(user_input)

        return await self._show_config_form(user_input)


    async def _show_config_form(self, user_input):  # pylint: disable=unused-argument
        """Show the configuration form to edit creds."""
        if not user_input:
            user_input = {}


        data_schema = OrderedDict()
        data_schema[vol.Required("username", default="")] = str
        data_schema[vol.Required("password", default="")] = str


        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(data_schema),
            errors=self._errors,
        )

    async def _test_credentials(self, username, password):
        """Return true if credentials is valid."""
        mm = MintMobile(username, password)
        return await self.hass.async_add_executor_job(mm.login)

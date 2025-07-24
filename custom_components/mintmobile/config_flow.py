"""Adds config flow for Mint Mobile."""
import logging
from collections import OrderedDict

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import MintMobile
from .const import (
    CONF_ATTRIBUTESENSORS,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_POLLING_INTERVAL,
    DEFAULT_POLLING_INTERVAL,
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
        """Handle the initial step for credentials."""
        self._errors = {}

        if user_input is not None:
            valid = await self._test_credentials(
                user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            if valid:
                self._data.update(
                    {
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_ATTRIBUTESENSORS: user_input.get(
                            CONF_ATTRIBUTESENSORS, False
                        ),
                    }
                )
                return await self.async_step_polling()
            self._errors["base"] = "invalid_credentials"

        return await self._show_config_form(user_input)

    async def async_step_polling(self, user_input=None):
        """Configure the polling interval after successful auth."""
        self._errors = {}

        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(
                title=self._data[CONF_USERNAME], data=self._data
            )

        return await self._show_polling_form(user_input)

    async def _show_config_form(self, user_input):  # pylint: disable=unused-argument
        """Show the configuration form to edit creds."""
        if not user_input:
            user_input = {}

        data_schema = OrderedDict()
        data_schema[vol.Required("username", default="")] = str
        data_schema[vol.Required("password", default="")] = str
        data_schema[vol.Optional("attributesensors", default=False)] = bool

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(data_schema),
            errors=self._errors,
        )

    async def _show_polling_form(self, user_input):  # pylint: disable=unused-argument
        """Show the polling interval form."""
        if not user_input:
            user_input = {}

        data_schema = OrderedDict()
        data_schema[
            vol.Optional(
                CONF_POLLING_INTERVAL, default=DEFAULT_POLLING_INTERVAL
            )
        ] = vol.All(int, vol.Range(min=1))

        return self.async_show_form(
            step_id="polling",
            data_schema=vol.Schema(data_schema),
            errors=self._errors,
        )

    async def _test_credentials(self, username, password):
        """Return true if credentials is valid."""
        mm = MintMobile(username, password)
        return await self.hass.async_add_executor_job(mm.login)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        """Initialize HACS options flow."""
        self.config_entry = config_entry
        self.options = dict(config_entry.options)
        self._errors = {}
        self._data = {}

    async def async_step_init(self, user_input=None):
        return await self.async_step_user()

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            self._data = user_input
            return await self._update_options()

        if self.config_entry.data.get(CONF_ATTRIBUTESENSORS):
            attributesensors = True
        else:
            attributesensors = False
        data_schema = OrderedDict()
        data_schema[
            vol.Required("username", default=self.config_entry.data.get(CONF_USERNAME))
        ] = str
        data_schema[vol.Required("password", default="")] = str
        data_schema[vol.Required("attributesensors", default=attributesensors)] = bool
        data_schema[
            vol.Optional(
                CONF_POLLING_INTERVAL,
                default=self.config_entry.data.get(
                    CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL
                ),
            )
        ] = vol.All(int, vol.Range(min=1))

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(data_schema),
            errors=self._errors,
        )

    async def _update_options(self):
        """Update config entry options."""
        valid = await self._test_credentials(
            self._data[CONF_USERNAME],
            self._data[CONF_PASSWORD],
        )
        if valid:
            return self.async_create_entry(
                title=self.config_entry.data.get(CONF_USERNAME), data=self._data
            )
        else:
            self._errors["base"] = "invalid_credentials"
            return await self.async_step_user()

    async def _test_credentials(self, username, password):
        """Return true if credentials is valid."""
        mm = MintMobile(username, password)
        return await self.hass.async_add_executor_job(mm.login)


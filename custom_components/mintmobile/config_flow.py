"""Adds config flow for Mint Mobile."""
import logging
from collections import OrderedDict

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MintMobile
from .const import (
    ATTRIBUTE_SENSOR_KEYS,
    CONF_ATTRIBUTESENSORS,
    CONF_LOGIN_MODE,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_POLLING_INTERVAL,
    CONF_SENSOR_DAYS_REMAINING_MONTH,
    CONF_SENSOR_DAYS_REMAINING_PLAN,
    CONF_SENSOR_PLAN_TERM,
    CONF_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_EXPIRES_AT,
    DEFAULT_LOGIN_MODE,
    DEFAULT_POLLING_INTERVAL,
    DOMAIN,
    LOGIN_MODE_INTERNET,
    LOGIN_MODE_PHONE,
    PLATFORMS,
)

_LOGGER = logging.getLogger(__name__)

LOGIN_MODE_LABELS = {
    LOGIN_MODE_PHONE: "Mint Mobile (phone line)",
    LOGIN_MODE_INTERNET: "Minternet",
}


def _attribute_sensor_defaults(data: dict) -> dict:
    """Per-attribute defaults, falling back to a pre-existing blanket toggle.

    Entries created before the per-attribute keys existed only stored
    CONF_ATTRIBUTESENSORS; treat that as every key's default so upgrading
    doesn't silently remove sensors someone already has.
    """
    legacy_default = bool(data.get(CONF_ATTRIBUTESENSORS, False))
    return {key: bool(data.get(key, legacy_default)) for key in ATTRIBUTE_SENSOR_KEYS}


class MintMobileFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Mint Mobile."""

    VERSION = 1

    def __init__(self):
        """Initialize."""
        self._data = {}
        self._errors = {}

    async def async_step_user(self, user_input=None):
        """Ask which kind of account is being added, before credentials."""
        self._errors = {}

        if user_input is not None:
            self._data[CONF_LOGIN_MODE] = user_input[CONF_LOGIN_MODE]
            return await self.async_step_credentials()

        return await self._show_login_mode_form()

    async def async_step_credentials(self, user_input=None):
        """Handle the credentials step, once login mode is known."""
        self._errors = {}

        if user_input is not None:
            valid = await self._test_credentials(
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                self._data.get(CONF_LOGIN_MODE, DEFAULT_LOGIN_MODE),
            )
            if valid:
                self._data.update(
                    {
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    }
                )
                return await self.async_step_attribute_sensors()
            self._errors["base"] = "invalid_credentials"

        return await self._show_config_form(user_input)

    async def async_step_attribute_sensors(self, user_input=None):
        """Pick which attributes also get their own separate sensor entity."""
        self._errors = {}

        if user_input is not None:
            self._data.update({key: user_input.get(key, False) for key in ATTRIBUTE_SENSOR_KEYS})
            return await self.async_step_polling()

        return await self._show_attribute_sensors_form()

    async def async_step_polling(self, user_input=None):
        """Configure the polling interval after successful auth."""
        self._errors = {}

        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(
                title=self._data[CONF_USERNAME], data=self._data
            )

        return await self._show_polling_form(user_input)

    async def _show_login_mode_form(self):
        """Show the login-mode picker, defaulting to a Mint Mobile phone line."""
        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_LOGIN_MODE, default=DEFAULT_LOGIN_MODE
                ): vol.In(LOGIN_MODE_LABELS)
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=self._errors,
        )

    async def _show_config_form(self, user_input):  # pylint: disable=unused-argument
        """Show the configuration form to edit creds."""
        data_schema = OrderedDict()
        data_schema[vol.Required("username", default="")] = str
        data_schema[vol.Required("password", default="")] = str

        login_mode = self._data.get(CONF_LOGIN_MODE, DEFAULT_LOGIN_MODE)
        credential_kind = (
            "Minternet username" if login_mode == LOGIN_MODE_INTERNET else "phone number"
        )

        return self.async_show_form(
            step_id="credentials",
            data_schema=vol.Schema(data_schema),
            errors=self._errors,
            description_placeholders={"credential_kind": credential_kind},
        )

    async def _show_attribute_sensors_form(self):
        """Show one checkbox per attribute that can become its own sensor."""
        data_schema = vol.Schema(
            {
                vol.Optional(CONF_SENSOR_PLAN_TERM, default=False): bool,
                vol.Optional(CONF_SENSOR_DAYS_REMAINING_MONTH, default=False): bool,
                vol.Optional(CONF_SENSOR_DAYS_REMAINING_PLAN, default=False): bool,
            }
        )

        return self.async_show_form(
            step_id="attribute_sensors",
            data_schema=data_schema,
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

    async def _test_credentials(self, username, password, login_mode=DEFAULT_LOGIN_MODE):
        """Return true if credentials is valid."""
        session = async_get_clientsession(self.hass)
        mm = MintMobile(session, username, password, login_mode=login_mode)
        try:
            return await mm.async_login()
        except Exception:
            return False

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self) -> None:
        """Initialize HACS options flow."""
        super().__init__()
        self._errors = {}
        self._data = {}

    async def async_step_init(self, user_input=None):
        return await self.async_step_user(user_input)

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            self._data = user_input
            return await self._update_options()

        attribute_defaults = _attribute_sensor_defaults(self.config_entry.data)
        data_schema = OrderedDict()
        data_schema[
            vol.Required("username", default=self.config_entry.data.get(CONF_USERNAME))
        ] = str
        data_schema[vol.Required("password", default="")] = str
        data_schema[
            vol.Required(
                CONF_LOGIN_MODE,
                default=self.config_entry.data.get(
                    CONF_LOGIN_MODE, DEFAULT_LOGIN_MODE
                ),
            )
        ] = vol.In(LOGIN_MODE_LABELS)
        data_schema[
            vol.Optional(
                CONF_SENSOR_PLAN_TERM, default=attribute_defaults[CONF_SENSOR_PLAN_TERM]
            )
        ] = bool
        data_schema[
            vol.Optional(
                CONF_SENSOR_DAYS_REMAINING_MONTH,
                default=attribute_defaults[CONF_SENSOR_DAYS_REMAINING_MONTH],
            )
        ] = bool
        data_schema[
            vol.Optional(
                CONF_SENSOR_DAYS_REMAINING_PLAN,
                default=attribute_defaults[CONF_SENSOR_DAYS_REMAINING_PLAN],
            )
        ] = bool
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
        mm = await self._test_credentials(
            self._data[CONF_USERNAME],
            self._data[CONF_PASSWORD],
            self._data.get(CONF_LOGIN_MODE, DEFAULT_LOGIN_MODE),
        )
        if mm is not None:
            new_data = {
                **self.config_entry.data,
                CONF_USERNAME: self._data[CONF_USERNAME],
                CONF_PASSWORD: self._data[CONF_PASSWORD],
                CONF_LOGIN_MODE: self._data.get(CONF_LOGIN_MODE, DEFAULT_LOGIN_MODE),
                CONF_POLLING_INTERVAL: self._data[CONF_POLLING_INTERVAL],
                CONF_TOKEN: mm.token,
                CONF_REFRESH_TOKEN: mm.refresh_token,
                CONF_EXPIRES_AT: mm.expires_at,
            }
            for key in ATTRIBUTE_SENSOR_KEYS:
                new_data[key] = self._data.get(key, False)
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=new_data
            )
            return self.async_create_entry(title="", data={})
        else:
            self._errors["base"] = "invalid_credentials"
            return await self.async_step_user()

    async def _test_credentials(self, username, password, login_mode=DEFAULT_LOGIN_MODE):
        """Return true if credentials is valid."""
        session = async_get_clientsession(self.hass)
        mm = MintMobile(session, username, password, login_mode=login_mode)
        try:
            if await mm.async_login():
                return mm
        except Exception:
            pass
        return None

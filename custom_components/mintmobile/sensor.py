"""Sensor platform for Mint Mobile."""
import datetime
import logging
import numbers
import uuid
from datetime import timedelta

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle

from .api import MintMobile
from .const import (
    CONF_ATTRIBUTESENSORS,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    ICON,
    SENSOR,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Setup sensor platform."""
    config = {
        CONF_USERNAME: entry.data[CONF_USERNAME],
        CONF_PASSWORD: entry.data[CONF_PASSWORD],
        CONF_ATTRIBUTESENSORS: entry.data[CONF_ATTRIBUTESENSORS],
    }

    sensors = []
    mm = MintMobile(config.get(CONF_USERNAME), config.get(CONF_PASSWORD))
    lines = await hass.async_add_executor_job(mm.lines)
    for line in lines:
        sensors.append(MintMobileSensor(hass, config, mm, line))
        sensors.append(DataUsed(hass, config, mm, line))
        if config.get(CONF_ATTRIBUTESENSORS):
            sensors.append(CurrentPlanSensor(hass, config, mm, line))
            sensors.append(DaysRemainingInMonthSensor(hass, config, mm, line))
            sensors.append(DaysRemainingInPlanSensor(hass, config, mm, line))

    async_add_entities(sensors, True)


class MintMobileSensor(Entity):
    def __init__(self, hass, config, mm, msin):
        """ Initialize the sensor """
        self._name = None
        self._icon = "mdi:cellphone"
        self._unit_of_measurement = "GB"
        self._state = None
        self._data = None
        self.msisdn = msin
        self.line_name = None
        self.mm = mm
        self.config = config
        self.last_updated = None
        self._scan_interval = timedelta(minutes=DEFAULT_SCAN_INTERVAL)
        self.hass = hass

        _LOGGER.debug("Config scan interval: %s", self._scan_interval)

        self.async_update = Throttle(self._scan_interval)(self.async_update)

    @property
    def unique_id(self):
        """
        Return a unique, Home Assistant friendly identifier for this entity.
        """
        return f"{DEFAULT_NAME}_{self.msisdn}"

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{self.line_name} Mobile Data Usage Remaining"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self._unit_of_measurement

    @property
    def icon(self):
        """Return the icon of the sensor."""
        return self._icon

    @property
    def device_state_attributes(self):
        """Return device specific state attributes."""
        attr = {}
        attr["phone_number"] = self.data["phone_number"]
        attr["line_name"] = self.data["line_name"]
        attr["last_updated"] = self.last_updated
        attr["days_remaining_in_month"] = self.data["endOfCycle"]
        attr["days_remaining_in_plan"] = self.data["exp"]
        attr["current_plan_term"] = f"{self.data['months']} Months"

        return attr

    async def async_update(self):
        """Fetch new state data for the sensor.
        This is the only method that should fetch new data for Home Assistant.
        """

        mm = MintMobile(self.config.get(CONF_USERNAME), self.config.get(CONF_PASSWORD))

        ## Login and make sure credentials are correct.
        login = await self.hass.async_add_executor_job(mm.login)
        if login:
            # If credentials are valid, pull additional information from APIs
            data = await self.hass.async_add_executor_job(mm.get_all_data_remaining)
            self.data = data.get(self.msisdn)
            # Using a dict to send the data back
            if isinstance(self.data["remaining4G"], numbers.Real):
                self._state = self.data["remaining4G"]
                self.line_name = self.data["line_name"]
                self.last_updated = self.update_time()
            else:
                _LOGGER.error("Unable to update line data useage")
        else:
            _LOGGER.error("Invalid Credentials")

    def update_time(self):
        """gets update time"""
        updated = datetime.datetime.now().strftime("%b-%d-%Y %I:%M %p")

        return updated

class DataUsed(Entity):
    def __init__(self, hass, config, mm, msin):
        """ Initialize the sensor """
        self._name = None
        self._icon = "mdi:cellphone"
        self._unit_of_measurement = "GB"
        self._state = None
        self._data = None
        self.msisdn = msin
        self.line_name = None
        self.mm = mm
        self.config = config
        self.last_updated = None
        self._scan_interval = timedelta(minutes=DEFAULT_SCAN_INTERVAL)
        self.hass = hass

        _LOGGER.debug("Config scan interval: %s", self._scan_interval)

        self.async_update = Throttle(self._scan_interval)(self.async_update)

    @property
    def unique_id(self):
        """
        Return a unique, Home Assistant friendly identifier for this entity.
        """
        return f"{DEFAULT_NAME}_{self.msisdn}_Data_Used"

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{self.line_name} Mobile Data Used"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self._unit_of_measurement

    @property
    def icon(self):
        """Return the icon of the sensor."""
        return self._icon

    @property
    def device_state_attributes(self):
        """Return device specific state attributes."""
        attr = {}
        attr["phone_number"] = self.data["phone_number"]
        attr["line_name"] = self.data["line_name"]
        attr["last_updated"] = self.last_updated
        attr["days_remaining_in_month"] = self.data["endOfCycle"]
        attr["days_remaining_in_plan"] = self.data["exp"]
        attr["current_plan_term"] = f"{self.data['months']} Months"

        return attr

    async def async_update(self):
        """Fetch new state data for the sensor.
        This is the only method that should fetch new data for Home Assistant.
        """

        mm = MintMobile(self.config.get(CONF_USERNAME), self.config.get(CONF_PASSWORD))

        ## Login and make sure credentials are correct.
        login = await self.hass.async_add_executor_job(mm.login)
        if login:
            # If credentials are valid, pull additional information from APIs
            data = await self.hass.async_add_executor_job(mm.get_all_data_remaining)
            self.data = data.get(self.msisdn)
            # Using a dict to send the data back
            if isinstance(self.data["used4G"], numbers.Real):
                self._state = self.data["used4G"]
                self.line_name = self.data["line_name"]
                self.last_updated = self.update_time()
            else:
                _LOGGER.error("Unable to update line data useage")
        else:
            _LOGGER.error("Invalid Credentials")

    def update_time(self):
        """gets update time"""
        updated = datetime.datetime.now().strftime("%b-%d-%Y %I:%M %p")

        return updated

class CurrentPlanSensor(Entity):
    def __init__(self, hass, config, mm, msin):
        """ Initialize the sensor """
        self._name = None
        self._icon = "mdi:calendar-text"
        self._unit_of_measurement = "Months"
        self._state = None
        self._data = None
        self.msisdn = msin
        self.line_name = None
        self.mm = mm
        self.config = config
        self.last_updated = None
        self._scan_interval = timedelta(minutes=DEFAULT_SCAN_INTERVAL)
        self.hass = hass

        _LOGGER.debug("Config scan interval: %s", self._scan_interval)

        self.async_update = Throttle(self._scan_interval)(self.async_update)

    @property
    def unique_id(self):
        """
        Return a unique, Home Assistant friendly identifier for this entity.
        """
        return f"{DEFAULT_NAME}_{self.msisdn}_CurrentPlan"

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{self.line_name} Mint Mobile Plan Term"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self._unit_of_measurement

    @property
    def icon(self):
        """Return the icon of the sensor."""
        return self._icon

    @property
    def device_state_attributes(self):
        """Return device specific state attributes."""
        attr = {}
        attr["phone_number"] = self.data["phone_number"]
        attr["line_name"] = self.data["line_name"]
        attr["last_updated"] = self.last_updated
        return attr

    async def async_update(self):
        """Fetch new state data for the sensor.
        This is the only method that should fetch new data for Home Assistant.
        """

        mm = MintMobile(self.config.get(CONF_USERNAME), self.config.get(CONF_PASSWORD))

        ## Login and make sure credentials are correct.
        login = await self.hass.async_add_executor_job(mm.login)
        if login:
            # If credentials are valid, pull additional information from APIs
            data = await self.hass.async_add_executor_job(mm.get_all_data_remaining)
            self.data = data.get(self.msisdn)
            # Using a dict to send the data back
            if isinstance(self.data["months"], numbers.Real):
                self._state = self.data["months"]
                self.line_name = self.data["line_name"]
                self.last_updated = self.update_time()
            else:
                _LOGGER.error("Unable to update current plan")
        else:
            _LOGGER.error("Invalid Credentials")

    def update_time(self):
        """gets update time"""
        updated = datetime.datetime.now().strftime("%b-%d-%Y %I:%M %p")

        return updated


class DaysRemainingInMonthSensor(Entity):
    def __init__(self, hass, config, mm, msin):
        """ Initialize the sensor """
        self._name = None
        self._icon = "mdi:counter"
        self._unit_of_measurement = "Days"
        self._state = None
        self._data = None
        self.msisdn = msin
        self.line_name = None
        self.mm = mm
        self.config = config
        self.last_updated = None
        self._scan_interval = timedelta(minutes=DEFAULT_SCAN_INTERVAL)
        self.hass = hass

        _LOGGER.debug("Config scan interval: %s", self._scan_interval)

        self.async_update = Throttle(self._scan_interval)(self.async_update)

    @property
    def unique_id(self):
        """
        Return a unique, Home Assistant friendly identifier for this entity.
        """
        return f"{DEFAULT_NAME}_{self.msisdn}_DaysRemainingInMonth"

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{self.line_name} Mint Mobile Days Remaining In Month"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self._unit_of_measurement

    @property
    def icon(self):
        """Return the icon of the sensor."""
        return self._icon

    @property
    def device_state_attributes(self):
        """Return device specific state attributes."""
        attr = {}
        attr["phone_number"] = self.data["phone_number"]
        attr["line_name"] = self.data["line_name"]
        attr["last_updated"] = self.last_updated
        return attr

    async def async_update(self):
        """Fetch new state data for the sensor.
        This is the only method that should fetch new data for Home Assistant.
        """

        mm = MintMobile(self.config.get(CONF_USERNAME), self.config.get(CONF_PASSWORD))

        ## Login and make sure credentials are correct.
        login = await self.hass.async_add_executor_job(mm.login)
        if login:
            # If credentials are valid, pull additional information from APIs
            data = await self.hass.async_add_executor_job(mm.get_all_data_remaining)
            self.data = data.get(self.msisdn)
            # Using a dict to send the data back
            if isinstance(self.data["endOfCycle"], numbers.Real):
                self._state = self.data["endOfCycle"]
                self.line_name = self.data["line_name"]
                self.last_updated = self.update_time()
            else:
                _LOGGER.error("Unable to update current plan")
        else:
            _LOGGER.error("Invalid Credentials")

    def update_time(self):
        """gets update time"""
        updated = datetime.datetime.now().strftime("%b-%d-%Y %I:%M %p")

        return updated


class DaysRemainingInPlanSensor(Entity):
    def __init__(self, hass, config, mm, msin):
        """ Initialize the sensor """
        self._name = None
        self._icon = "mdi:counter"
        self._unit_of_measurement = "Days"
        self._state = None
        self._data = None
        self.msisdn = msin
        self.line_name = None
        self.mm = mm
        self.config = config
        self.last_updated = None
        self._scan_interval = timedelta(minutes=DEFAULT_SCAN_INTERVAL)
        self.hass = hass

        _LOGGER.debug("Config scan interval: %s", self._scan_interval)

        self.async_update = Throttle(self._scan_interval)(self.async_update)

    @property
    def unique_id(self):
        """
        Return a unique, Home Assistant friendly identifier for this entity.
        """
        return f"{DEFAULT_NAME}_{self.msisdn}_DaysRemainingInPlan"

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{self.line_name} Mint Mobile Days Remaining In Plan"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self._unit_of_measurement

    @property
    def icon(self):
        """Return the icon of the sensor."""
        return self._icon

    @property
    def device_state_attributes(self):
        """Return device specific state attributes."""
        attr = {}
        attr["phone_number"] = self.data["phone_number"]
        attr["line_name"] = self.data["line_name"]
        attr["last_updated"] = self.last_updated
        return attr

    async def async_update(self):
        """Fetch new state data for the sensor.
        This is the only method that should fetch new data for Home Assistant.
        """

        mm = MintMobile(self.config.get(CONF_USERNAME), self.config.get(CONF_PASSWORD))

        ## Login and make sure credentials are correct.
        login = await self.hass.async_add_executor_job(mm.login)
        if login:
            # If credentials are valid, pull additional information from APIs
            data = await self.hass.async_add_executor_job(mm.get_all_data_remaining)
            self.data = data.get(self.msisdn)
            # Using a dict to send the data back
            if isinstance(self.data["exp"], numbers.Real):
                self._state = self.data["exp"]
                self.line_name = self.data["line_name"]
                self.last_updated = self.update_time()
            else:
                _LOGGER.error("Unable to update current plan")
        else:
            _LOGGER.error("Invalid Credentials")

    def update_time(self):
        """gets update time"""
        updated = datetime.datetime.now().strftime("%b-%d-%Y %I:%M %p")

        return updated

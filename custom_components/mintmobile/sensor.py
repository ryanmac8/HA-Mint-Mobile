"""Sensor platform for Mint Mobile."""
import datetime
import logging

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_ATTRIBUTESENSORS,
    DEFAULT_NAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Setup sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    lines = coordinator.data.keys()

    sensors = []
    for line in lines:
        sensors.append(MintMobileSensor(coordinator, line, entry))
        sensors.append(DataUsed(coordinator, line, entry))
        if entry.data.get(CONF_ATTRIBUTESENSORS):
            sensors.append(CurrentPlanSensor(coordinator, line, entry))
            sensors.append(DaysRemainingInMonthSensor(coordinator, line, entry))
            sensors.append(DaysRemainingInPlanSensor(coordinator, line, entry))

    async_add_entities(sensors, True)


class MintMobileSensor(CoordinatorEntity, Entity):
    """Sensor showing remaining high speed data."""

    def __init__(self, coordinator, msin, entry):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.msisdn = msin
        self.entry = entry
        self._icon = "mdi:cellphone"
        self._unit_of_measurement = "GB"

    @property
    def unique_id(self):
        """Return a unique identifier for this entity."""
        return f"{DEFAULT_NAME}_{self.msisdn}"

    @property
    def name(self):
        """Return the name of the sensor."""
        data = self.coordinator.data.get(self.msisdn)
        line_name = data["line_name"] if data else "Mint"
        return f"{line_name} Mobile Data Usage Remaining"

    @property
    def state(self):
        """Return the state of the sensor."""
        data = self.coordinator.data.get(self.msisdn)
        return data["remaining4G"] if data else None

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit_of_measurement

    @property
    def icon(self):
        """Return the icon."""
        return self._icon

    @property
    def extra_state_attributes(self):
        """Return device specific state attributes."""
        data = self.coordinator.data.get(self.msisdn)
        if not data:
            return {}
        last_updated = datetime.datetime.now().strftime("%b-%d-%Y %I:%M %p")
        return {
            "phone_number": data["phone_number"],
            "line_name": data["line_name"],
            "last_updated": last_updated,
            "days_remaining_in_month": data["endOfCycle"],
            "days_remaining_in_plan": data["exp"],
            "current_plan_term": f"{data['months']} Months",
        }


class DataUsed(CoordinatorEntity, Entity):
    """Sensor showing used high speed data."""

    def __init__(self, coordinator, msin, entry):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.msisdn = msin
        self.entry = entry
        self._icon = "mdi:cellphone"
        self._unit_of_measurement = "GB"

    @property
    def unique_id(self):
        """Return a unique identifier for this entity."""
        return f"{DEFAULT_NAME}_{self.msisdn}_Data_Used"

    @property
    def name(self):
        """Return the name of the sensor."""
        data = self.coordinator.data.get(self.msisdn)
        line_name = data["line_name"] if data else "Mint"
        return f"{line_name} Mobile Data Used"

    @property
    def state(self):
        """Return the state of the sensor."""
        data = self.coordinator.data.get(self.msisdn)
        return data["used4G"] if data else None

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit_of_measurement

    @property
    def icon(self):
        """Return the icon."""
        return self._icon

    @property
    def extra_state_attributes(self):
        """Return device specific state attributes."""
        data = self.coordinator.data.get(self.msisdn)
        if not data:
            return {}
        last_updated = datetime.datetime.now().strftime("%b-%d-%Y %I:%M %p")
        return {
            "phone_number": data["phone_number"],
            "line_name": data["line_name"],
            "last_updated": last_updated,
            "days_remaining_in_month": data["endOfCycle"],
            "days_remaining_in_plan": data["exp"],
            "current_plan_term": f"{data['months']} Months",
        }


class CurrentPlanSensor(CoordinatorEntity, Entity):
    """Sensor showing the plan term."""

    def __init__(self, coordinator, msin, entry):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.msisdn = msin
        self.entry = entry
        self._icon = "mdi:calendar-text"
        self._unit_of_measurement = "Months"

    @property
    def unique_id(self):
        """Return a unique identifier for this entity."""
        return f"{DEFAULT_NAME}_{self.msisdn}_CurrentPlan"

    @property
    def name(self):
        """Return the name of the sensor."""
        data = self.coordinator.data.get(self.msisdn)
        line_name = data["line_name"] if data else "Mint"
        return f"{line_name} Mint Mobile Plan Term"

    @property
    def state(self):
        """Return the state of the sensor."""
        data = self.coordinator.data.get(self.msisdn)
        return data["months"] if data else None

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit_of_measurement

    @property
    def icon(self):
        """Return the icon."""
        return self._icon

    @property
    def extra_state_attributes(self):
        """Return device specific state attributes."""
        data = self.coordinator.data.get(self.msisdn)
        if not data:
            return {}
        last_updated = datetime.datetime.now().strftime("%b-%d-%Y %I:%M %p")
        return {
            "phone_number": data["phone_number"],
            "line_name": data["line_name"],
            "last_updated": last_updated,
        }


class DaysRemainingInMonthSensor(CoordinatorEntity, Entity):
    """Sensor showing days remaining in month."""

    def __init__(self, coordinator, msin, entry):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.msisdn = msin
        self.entry = entry
        self._icon = "mdi:counter"
        self._unit_of_measurement = "Days"

    @property
    def unique_id(self):
        """Return a unique identifier for this entity."""
        return f"{DEFAULT_NAME}_{self.msisdn}_DaysRemainingInMonth"

    @property
    def name(self):
        """Return the name of the sensor."""
        data = self.coordinator.data.get(self.msisdn)
        line_name = data["line_name"] if data else "Mint"
        return f"{line_name} Mint Mobile Days Remaining In Month"

    @property
    def state(self):
        """Return the state of the sensor."""
        data = self.coordinator.data.get(self.msisdn)
        return data["endOfCycle"] if data else None

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit_of_measurement

    @property
    def icon(self):
        """Return the icon."""
        return self._icon

    @property
    def extra_state_attributes(self):
        """Return device specific state attributes."""
        data = self.coordinator.data.get(self.msisdn)
        if not data:
            return {}
        last_updated = datetime.datetime.now().strftime("%b-%d-%Y %I:%M %p")
        return {
            "phone_number": data["phone_number"],
            "line_name": data["line_name"],
            "last_updated": last_updated,
        }


class DaysRemainingInPlanSensor(CoordinatorEntity, Entity):
    """Sensor showing days remaining in plan."""

    def __init__(self, coordinator, msin, entry):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.msisdn = msin
        self.entry = entry
        self._icon = "mdi:counter"
        self._unit_of_measurement = "Days"

    @property
    def unique_id(self):
        """Return a unique identifier for this entity."""
        return f"{DEFAULT_NAME}_{self.msisdn}_DaysRemainingInPlan"

    @property
    def name(self):
        """Return the name of the sensor."""
        data = self.coordinator.data.get(self.msisdn)
        line_name = data["line_name"] if data else "Mint"
        return f"{line_name} Mint Mobile Days Remaining In Plan"

    @property
    def state(self):
        """Return the state of the sensor."""
        data = self.coordinator.data.get(self.msisdn)
        return data["exp"] if data else None

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit_of_measurement

    @property
    def icon(self):
        """Return the icon."""
        return self._icon

    @property
    def extra_state_attributes(self):
        """Return device specific state attributes."""
        data = self.coordinator.data.get(self.msisdn)
        if not data:
            return {}
        last_updated = datetime.datetime.now().strftime("%b-%d-%Y %I:%M %p")
        return {
            "phone_number": data["phone_number"],
            "line_name": data["line_name"],
            "last_updated": last_updated,
        }

"""Constants for Mint Mobile."""
# Base component constants
NAME = "Mint Mobile"
DOMAIN = "mintmobile"
DOMAIN_DATA = f"{DOMAIN}_data"
VERSION = "3.1.0"  # x-release-please-version
ATTRIBUTION = "Data provided by https://www.mintmobile.com"
ISSUE_URL = "https://github.com/ryanmac8/HA-Mint-Mobile/issues"

# Icons
ICON = "mdi:format-quote-close"

# Device classes

# Platforms
SENSOR = "sensor"
PLATFORMS = [SENSOR]


# Configuration and options
CONF_ENABLED = "enabled"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_ATTRIBUTESENSORS = "attributesensors"
CONF_SENSOR_PLAN_TERM = "sensor_plan_term"
CONF_SENSOR_DAYS_REMAINING_MONTH = "sensor_days_remaining_month"
CONF_SENSOR_DAYS_REMAINING_PLAN = "sensor_days_remaining_plan"
# Each attribute already appears on the main data-usage sensor; these three
# optionally split one out as its own sensor entity. Entries created before
# this existed only have the single blanket CONF_ATTRIBUTESENSORS -- readers
# of these keys should fall back to that value for such entries, not to
# False, so upgrading doesn't silently remove sensors someone already has.
ATTRIBUTE_SENSOR_KEYS = (
    CONF_SENSOR_PLAN_TERM,
    CONF_SENSOR_DAYS_REMAINING_MONTH,
    CONF_SENSOR_DAYS_REMAINING_PLAN,
)
CONF_POLLING_INTERVAL = "polling_interval"
CONF_TOKEN = "token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_EXPIRES_AT = "expires_at"
CONF_LOGIN_MODE = "login_mode"

# A Mint account, a Mint Mobile phone number, and a Minternet username are
# all valid credentials for the same login endpoint -- they just use a
# different request field (see api.py). The mode only picks that field; it
# does not limit which lines get created afterward.
LOGIN_MODE_PHONE = "phone"
LOGIN_MODE_INTERNET = "internet"

# Defaults
DEFAULT_NAME = "mint_mobile"
DEFAULT_SCAN_INTERVAL = 15
DEFAULT_POLLING_INTERVAL = 12
DEFAULT_LOGIN_MODE = LOGIN_MODE_PHONE


STARTUP_MESSAGE = f"""
-------------------------------------------------------------------
{NAME}
Version: {VERSION}
This is a custom integration!
If you have any issues with this you need to open an issue here:
{ISSUE_URL}
-------------------------------------------------------------------
"""

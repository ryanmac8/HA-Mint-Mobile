"""Constants for Mint Mobile."""
# Base component constants
NAME = "Mint Mobile"
DOMAIN = "mintmobile"
DOMAIN_DATA = f"{DOMAIN}_data"
VERSION = "0.0.1"
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

# Defaults
DEFAULT_NAME = "mint_mobile"
DEFAULT_SCAN_INTERVAL = 15


STARTUP_MESSAGE = f"""
-------------------------------------------------------------------
{NAME}
Version: {VERSION}
This is a custom integration!
If you have any issues with this you need to open an issue here:
{ISSUE_URL}
-------------------------------------------------------------------
"""

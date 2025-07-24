# Mint Mobile - Home Assistant Integration


This integration creates a sensor for each line and displays the remaining data usage for the month. If you have a Mint Mobile family, it will also pull in the data usage for each line. The sensor name includes additional attributes about the line.


### Attributes Included:

- Number of months purchased for plan
- Days remaining in month (The number of days left in the data plan month)
- Days remaining for plan (The number of days left that you have purchased)
- Phone number
- Line name
- Last updated

### Polling Interval

During setup you can specify how often the integration checks Mint Mobile for
new data. The value is in **hours** and defaults to **12**. Values less than 1
hour are not allowed.

### Attributes As Additional Sensors

If you want to have the following attributes as additional sensors, during the setup process or under the integration options menu check 'Display Attributes As Additional Sensors'.

- Number of months purchased for plan
- Days remaining in month (The number of days left in the data plan month)
- Days remaining for plan (The number of days left that you have purchased)


[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)

[![Validate with hassfest](https://github.com/ryanmac8/HA-Mint-Mobile/actions/workflows/combined.yaml/badge.svg)](https://github.com/ryanmac8/HA-Mint-Mobile/actions/workflows/combined.yaml)

![GitHub contributors](https://img.shields.io/github/contributors/ryanmac8/HA-Mint-Mobile)
![Maintenance](https://img.shields.io/maintenance/yes/2022)
![GitHub commit activity](https://img.shields.io/github/commit-activity/m/ryanmac8/HA-Mint-Mobile)
![GitHub last commit](https://img.shields.io/github/last-commit/ryanmac8/HA-Mint-Mobile)

---

Enjoying my integration? Help me out and buy me a :coffee: for $3!

[![coffee](https://www.buymeacoffee.com/assets/img/custom_images/black_img.png)](https://www.buymeacoffee.com/Ryanmac8)

---

## Installation
### [HACS](https://hacs.xyz) (Recommended)
1. Have [HACS](https://github.com/custom-components/hacs) installed, this will allow you to easily update
2. Add `https://github.com/ryanmac8/HA-Mint-Mobile` as a [custom repository](https://hacs.xyz/docs/faq/custom_repositories) and Type: Integration
3. Click install under "Mint Mobile", restart your instance.

### Manual Installation
1. Download this repository as a ZIP (green button, top right) and unzip the archive
2. Copy the `mintmobile` folder inside the `custom_components` folder to the Home Assistant `/<config path>/custom_components/` directory
   * You may need to create the `custom_components` in your Home Assistant installation folder if it does not exist
   * On Home Assistant (formerly Hass.io) and Home Assistant Container the final location should be `/config/custom_components/mintmobile`
   * On Home Assistant Supervised, Home Assistant Core, and Hassbian the final location should be `/home/homeassistant/.homeassistant/custom_components/mintmobile`
3. Restart your instance.

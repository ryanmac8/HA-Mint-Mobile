# Mint Mobile - Home Assistant Integration


This integration creates sensors for each line and displays the remaining and used data usage for the month. If you have a Mint Mobile family, it will also pull in the data usage for each line. The sensor name includes additional attributes about the line.

Data-only lines (tablet and mobile internet plans) are supported alongside phone lines; the correct subscriber type is detected automatically on the first refresh.

If your account also has a linked **Minternet** (home internet) product, it gets its own sensor pair automatically, whether you log in with your Mint Mobile phone number or your Minternet username -- either credential surfaces every product linked to the account. Each line's `line_type` attribute reads `phone`, `internet`, or `tablet` so you can tell them apart.

> **WARNING: Running Multiple Clients (Token Invalidation)**
>
> Mint Mobile's API rotates refresh tokens and only allows one active session per account. Running another automated client (like the TypeScript MQTT bridge) or logging into the official mobile app will invalidate the integration's token.
>
> When this happens, Home Assistant logs a `401 Unauthorized` warning and automatically recovers via a full login. To avoid warnings, do not run other automated API clients.


### Attributes Included:

- Number of months purchased for plan
- Days remaining in month (The number of days left in the data plan month)
- Days remaining for plan (The number of days left that you have purchased)
- Phone number
- Line name
- Line type (`phone`, `internet`, or `tablet`)
- Last updated

### Setup

Adding the integration walks through a few short screens:

1. **Account Type** -- choose Mint Mobile (phone) or Minternet. This only
   controls how your credential is sent; if your account has both linked,
   both still show up as separate sensors regardless of which you pick here.
2. **Credentials** -- your phone number or Minternet username, and password.
3. **Additional Sensors** -- each attribute above already appears on the
   main data-usage sensor. Turn on any of the three checkboxes here only if
   you also want that attribute as its own separate sensor entity.
4. **Polling Interval** -- see below.

All of these can be changed later from the integration's **Configure** menu.

### Polling Interval

During setup you can specify how often the integration checks Mint Mobile for
new data. The value is in **hours** and defaults to **12**. Values less than 1
hour are not allowed.


[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)

[![Validate with hassfest](https://github.com/ryanmac8/HA-Mint-Mobile/actions/workflows/combined.yaml/badge.svg)](https://github.com/ryanmac8/HA-Mint-Mobile/actions/workflows/combined.yaml)

[![E2E](https://github.com/ryanmac8/HA-Mint-Mobile/actions/workflows/e2e.yml/badge.svg)](https://github.com/ryanmac8/HA-Mint-Mobile/actions/workflows/e2e.yml)

![GitHub contributors](https://img.shields.io/github/contributors/ryanmac8/HA-Mint-Mobile)
![Maintenance](https://img.shields.io/maintenance/yes/2026)
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

---

## Development

### Running the end-to-end tests

The `tests/` suite boots a real Home Assistant instance, walks the config flow,
sets the integration up and asserts on the resulting sensor states. Only the
Mint Mobile gateway is stubbed — nothing else is mocked, and no network access
is required.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements_test.txt
pytest
```

`requirements_test.txt` pins `pytest-homeassistant-custom-component`; each of its
releases targets one Home Assistant version, so bumping that pin is how the
suite moves to a newer core.

The same suite runs in CI on every push to a pull request (the `e2e` check) and
must pass before a PR can be merged.

### Releases

Releases are automated with
[release-please](https://github.com/googleapis/release-please). Commits landing
on `master` should follow
[Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`,
`chore:`, …). release-please keeps an open "chore: release x.y.z" pull request
that updates `CHANGELOG.md`, `custom_components/mintmobile/manifest.json` and
`custom_components/mintmobile/const.py`; merging it tags `vX.Y.Z` and publishes
the matching GitHub Release that HACS picks up.

# Repository Guidance for Contributors

This repository contains a Home Assistant custom integration that is published through HACS. Any future automated or manual changes should follow these guidelines.

## HACS Requirements
- The repository must hold only one integration. All source code must live under `custom_components/mintmobile/`.
- Only files needed for the integration should exist inside that folder. Do not add files from other integrations.
- `manifest.json` inside the integration folder **must** define the following keys:
  - `domain`
  - `documentation`
  - `issue_tracker`
  - `codeowners`
  - `name`
  - `version`
- Ensure `hacs.json` exists at the repository root. This file defines the HACS metadata for this integration.
- If you publish GitHub releases they will be shown in HACS, otherwise the default branch is used.
- For visual assets you should submit them to the [`home-assistant/brands`](https://github.com/home-assistant/brands) repository.

These requirements are based on the [HACS integration publishing docs](https://www.hacs.xyz/docs/publish/integration/).

## General Development Tips
- Keep consistent Python style when modifying `custom_components/mintmobile`.
- Documentation updates should be reflected in `README.md` when applicable.


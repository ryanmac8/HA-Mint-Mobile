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

## Continuous Integration
- `.github/workflows/e2e.yml` runs the end-to-end suite in `tests/` on every push to a
  pull request. It is a required check on `master`; do not merge around it.
- The suite boots a real Home Assistant instance via
  `pytest-homeassistant-custom-component` and stubs only the Mint Mobile gateway.
  Run it locally with `pip install -r requirements_test.txt && pytest`.
- Behavioural changes to `custom_components/mintmobile/` should come with matching
  coverage in `tests/test_e2e.py`.
- The pinned harness version in `requirements_test.txt` selects the Home Assistant
  version under test. Bump it deliberately, in its own commit.

## Releases
- Releases are driven by [release-please](https://github.com/googleapis/release-please)
  (`.github/workflows/release-please.yml`, `release-please-config.json`,
  `.release-please-manifest.json`).
- Use [Conventional Commits](https://www.conventionalcommits.org/) on `master`
  (`feat:` -> minor, `fix:` -> patch, `feat!:`/`BREAKING CHANGE:` -> major).
- Do **not** hand-edit the `version` field in `manifest.json`, `VERSION` in
  `const.py`, or `.release-please-manifest.json`. release-please owns all three;
  the `const.py` line is kept in sync by its `# x-release-please-version` annotation.
- Merging the open "chore: release x.y.z" PR is what creates the `vX.Y.Z` tag and
  the published GitHub Release that HACS consumes.


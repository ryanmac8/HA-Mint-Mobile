"""End-to-end tests: drive a real Home Assistant instance through config flow,
integration setup and sensor state, with only the Mint Mobile gateway stubbed.
"""
import base64
import json
import time

import pytest
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.mintmobile.api import decode_jwt
from custom_components.mintmobile.const import (
    CONF_ATTRIBUTESENSORS,
    CONF_PASSWORD,
    CONF_POLLING_INTERVAL,
    CONF_USERNAME,
    DOMAIN,
)

from .conftest import ACCOUNT_ID, GATEWAY, MEMBER_ID, PASSWORD, PHONE, make_jwt

PRIMARY_REMAINING = "sensor.ryan_mobile_data_usage_remaining"
PRIMARY_USED = "sensor.ryan_mobile_data_used"
PRIMARY_PLAN_TERM = "sensor.ryan_mint_mobile_plan_term"
PRIMARY_DAYS_MONTH = "sensor.ryan_mint_mobile_days_remaining_in_month"
PRIMARY_DAYS_PLAN = "sensor.ryan_mint_mobile_days_remaining_in_plan"
MEMBER_REMAINING = "sensor.kiddo_mobile_data_usage_remaining"
MEMBER_USED = "sensor.kiddo_mobile_data_used"


async def run_config_flow(
    hass: HomeAssistant, *, attribute_sensors: bool = True, polling_interval: int = 12
):
    """Walk the two-step user config flow and return the final flow result."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_USERNAME: PHONE,
            CONF_PASSWORD: PASSWORD,
            CONF_ATTRIBUTESENSORS: attribute_sensors,
        },
    )
    if result["type"] is not FlowResultType.FORM or result["step_id"] != "polling":
        return result

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_POLLING_INTERVAL: polling_interval}
    )
    await hass.async_block_till_done()
    return result


async def test_full_setup_creates_sensors_for_every_line(
    hass: HomeAssistant, mint_api
) -> None:
    """Happy path: config flow -> setup -> sensors for primary and family lines."""
    mint_api.register_all()

    result = await run_config_flow(hass)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == PHONE
    assert result["data"][CONF_POLLING_INTERVAL] == 12

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.state is ConfigEntryState.LOADED

    # Primary line: 5120 MB remaining / 3072 MB used -> GB.
    assert hass.states.get(PRIMARY_REMAINING).state == "5.0"
    assert hass.states.get(PRIMARY_USED).state == "3.0"
    assert hass.states.get(PRIMARY_PLAN_TERM).state == "12"
    assert hass.states.get(PRIMARY_DAYS_MONTH).state == str(mint_api.days_in_cycle)
    assert hass.states.get(PRIMARY_DAYS_PLAN).state == str(mint_api.days_in_plan)

    # Family line discovered through the multi-line endpoint.
    assert hass.states.get(MEMBER_REMAINING).state == "2.0"
    assert hass.states.get(MEMBER_USED).state == "1.0"

    attributes = hass.states.get(PRIMARY_REMAINING).attributes
    assert attributes["phone_number"] == PHONE
    assert attributes["line_name"] == "Ryan"
    assert attributes["unit_of_measurement"] == "GB"
    assert attributes["current_plan_term"] == "12 Months"
    assert attributes["days_remaining_in_month"] == mint_api.days_in_cycle


async def test_attribute_sensors_disabled_creates_only_data_sensors(
    hass: HomeAssistant, mint_api
) -> None:
    """With the option off, only the two data sensors exist per line."""
    mint_api.register_all()

    result = await run_config_flow(hass, attribute_sensors=False)
    assert result["type"] is FlowResultType.CREATE_ENTRY

    assert hass.states.get(PRIMARY_REMAINING) is not None
    assert hass.states.get(PRIMARY_USED) is not None
    assert hass.states.get(PRIMARY_PLAN_TERM) is None
    assert hass.states.get(PRIMARY_DAYS_MONTH) is None
    assert hass.states.get(PRIMARY_DAYS_PLAN) is None


async def test_single_line_account_skips_multi_line(
    hass: HomeAssistant, mint_api
) -> None:
    """A 404 from the multi-line endpoint must not fail the whole update."""
    mint_api.register_all(multi_line=False)

    result = await run_config_flow(hass)
    assert result["type"] is FlowResultType.CREATE_ENTRY

    assert hass.states.get(PRIMARY_REMAINING).state == "5.0"
    assert hass.states.get(MEMBER_REMAINING) is None


async def test_invalid_credentials_reprompts(hass: HomeAssistant, mint_api) -> None:
    """A rejected login keeps the user on the credentials form."""
    mint_api.register_login(status=401)

    result = await run_config_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "invalid_credentials"}
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_setup_retries_when_gateway_is_down(
    hass: HomeAssistant, mint_api
) -> None:
    """Login succeeds but the account fetch fails -> entry goes to SETUP_RETRY."""
    mint_api.register_login()
    mint_api.register_account(status=500)

    result = await run_config_flow(hass)
    assert result["type"] is FlowResultType.CREATE_ENTRY

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert hass.states.get(PRIMARY_REMAINING) is None


async def test_unload_removes_entities(hass: HomeAssistant, mint_api) -> None:
    """Unloading the entry tears the sensors down cleanly."""
    mint_api.register_all()
    await run_config_flow(hass)

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    # Home Assistant keeps a restored placeholder state for unloaded entities.
    assert hass.states.get(PRIMARY_REMAINING).state == STATE_UNAVAILABLE
    assert hass.states.get(MEMBER_REMAINING).state == STATE_UNAVAILABLE
    assert entry.entry_id not in hass.data.get(DOMAIN, {})


async def test_cached_token_is_reused_across_updates(
    hass: HomeAssistant, mint_api
) -> None:
    """A still-valid token is persisted to the entry and reused, not re-fetched."""
    mint_api.register_all()
    await run_config_flow(hass)

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.data["token"] == mint_api.token
    assert entry.data["refresh_token"] == "refresh-token-abc"

    logins = [
        call for call in mint_api.mock.mock_calls if str(call[1]).endswith("/mint/login")
    ]
    coordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.last_update_success
    new_logins = [
        call for call in mint_api.mock.mock_calls if str(call[1]).endswith("/mint/login")
    ]
    assert len(new_logins) == len(logins)


async def test_entities_go_unavailable_when_a_refresh_fails(
    hass: HomeAssistant, mint_api
) -> None:
    """A later gateway outage marks the sensors unavailable rather than crashing."""
    mint_api.register_all()
    await run_config_flow(hass)
    assert hass.states.get(PRIMARY_REMAINING).state == "5.0"

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    coordinator = hass.data[DOMAIN][entry.entry_id]

    mint_api.mock.clear_requests()
    mint_api.register_login()
    mint_api.register_account(status=503)

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert not coordinator.last_update_success
    assert hass.states.get(PRIMARY_REMAINING).state == STATE_UNAVAILABLE


async def test_near_expiry_token_is_refreshed_not_relogged(
    hass: HomeAssistant, mint_api
) -> None:
    """A token inside the 60s expiry buffer is refreshed via the refresh
    endpoint; a full re-login must not happen while a refresh token exists.
    """
    mint_api.register_all()
    await run_config_flow(hass)

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    coordinator = hass.data[DOMAIN][entry.entry_id]

    # Force the cached token into the "must renew" window used by
    # async_ensure_valid_session (expires_at > now + 60).
    coordinator.client.expires_at = int(time.time()) + 30

    new_token = make_jwt(ACCOUNT_ID, int(time.time()) + 3600)
    mint_api.mock.clear_requests()
    mint_api.register_refresh(token=new_token, refresh_token="refresh-token-def")
    mint_api.register_account()
    mint_api.register_plans()
    mint_api.register_usage()
    mint_api.register_multi_line()

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.last_update_success
    login_calls = [
        c for c in mint_api.mock.mock_calls if str(c[1]).endswith("/mint/login")
    ]
    refresh_calls = [
        c for c in mint_api.mock.mock_calls if str(c[1]).endswith("/mint/refresh")
    ]
    assert len(login_calls) == 0
    assert len(refresh_calls) == 1

    # The refreshed token/refresh-token pair must be persisted to the entry.
    assert entry.data["token"] == new_token
    assert entry.data["refresh_token"] == "refresh-token-def"


async def test_refresh_failure_falls_back_to_full_login(
    hass: HomeAssistant, mint_api
) -> None:
    """If the refresh endpoint errors, the client must fall back to a full
    username/password login rather than leaving the update failed.
    """
    mint_api.register_all()
    await run_config_flow(hass)

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.client.expires_at = int(time.time()) + 30

    mint_api.mock.clear_requests()
    mint_api.register_refresh(status=500)
    mint_api.register_all()  # fallback login + full data fetch must succeed

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.last_update_success
    login_calls = [
        c for c in mint_api.mock.mock_calls if str(c[1]).endswith("/mint/login")
    ]
    refresh_calls = [
        c for c in mint_api.mock.mock_calls if str(c[1]).endswith("/mint/refresh")
    ]
    assert len(refresh_calls) == 1
    assert len(login_calls) == 1
    assert hass.states.get(PRIMARY_REMAINING).state == "5.0"


async def test_login_response_using_access_token_field(
    hass: HomeAssistant, mint_api
) -> None:
    """Some login responses carry the session token under `accessToken`
    instead of `token`; async_login must accept either key.
    """
    mint_api.mock.post(
        f"{GATEWAY}/v1/mint/login",
        json={
            "accessToken": mint_api.token,
            "refreshToken": "refresh-token-abc",
            "userId": ACCOUNT_ID,
        },
    )
    mint_api.register_account()
    mint_api.register_plans()
    mint_api.register_usage()
    mint_api.mock.get(f"{GATEWAY}/v1/mint/account/{ACCOUNT_ID}/multi-line", status=404)

    result = await run_config_flow(hass)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert hass.states.get(PRIMARY_REMAINING).state == "5.0"


async def test_login_response_missing_token_reprompts(
    hass: HomeAssistant, mint_api
) -> None:
    """A login response with neither `token` nor `accessToken` must be
    treated as a failed login, not crash the config flow.
    """
    mint_api.mock.post(
        f"{GATEWAY}/v1/mint/login",
        json={"refreshToken": "refresh-token-abc", "userId": ACCOUNT_ID},
    )

    result = await run_config_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "invalid_credentials"}
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_multi_line_member_usage_failure_is_skipped(
    hass: HomeAssistant, mint_api
) -> None:
    """A failing per-member usage call must not fail the whole update; that
    member is simply omitted while the primary line still updates.
    """
    mint_api.register_login()
    mint_api.register_account()
    mint_api.register_plans()
    mint_api.register_usage()
    mint_api.register_multi_line(usage_status=500)

    result = await run_config_flow(hass)
    assert result["type"] is FlowResultType.CREATE_ENTRY

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(PRIMARY_REMAINING).state == "5.0"
    assert hass.states.get(MEMBER_REMAINING) is None


async def test_multi_line_member_without_id_is_skipped(
    hass: HomeAssistant, mint_api
) -> None:
    """A multi-line member entry with no `id` field must be skipped rather
    than crash the update (there is no usage endpoint to call for it).
    """
    mint_api.register_login()
    mint_api.register_account()
    mint_api.register_plans()
    mint_api.register_usage()
    mint_api.register_multi_line(include_id=False)

    result = await run_config_flow(hass)
    assert result["type"] is FlowResultType.CREATE_ENTRY

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(PRIMARY_REMAINING).state == "5.0"
    assert hass.states.get(MEMBER_REMAINING) is None


async def test_account_payload_with_nested_phone_plan_shape(
    hass: HomeAssistant, mint_api
) -> None:
    """api.py falls back to the nested `phone.msisdn` / `phone.plan.*` shape
    when the top-level keys are absent; that shape must produce identical
    sensor values to the top-level shape covered by the happy-path test.
    """
    mint_api.register_login()
    mint_api.register_account(nested=True)
    mint_api.register_plans()
    mint_api.register_usage()
    mint_api.mock.get(f"{GATEWAY}/v1/mint/account/{ACCOUNT_ID}/multi-line", status=404)

    result = await run_config_flow(hass)
    assert result["type"] is FlowResultType.CREATE_ENTRY

    assert hass.states.get(PRIMARY_REMAINING).state == "5.0"
    attributes = hass.states.get(PRIMARY_REMAINING).attributes
    assert attributes["phone_number"] == PHONE
    assert attributes["line_name"] == "Ryan"
    assert attributes["days_remaining_in_month"] == mint_api.days_in_cycle
    assert hass.states.get(PRIMARY_DAYS_PLAN).state == str(mint_api.days_in_plan)


async def test_past_dated_cycle_and_plan_clamp_to_zero_days(
    hass: HomeAssistant, mint_api
) -> None:
    """An already-expired billing cycle/plan (e.g. a stale cache reload) must
    report 0 days remaining, not a negative number.
    """
    mint_api.register_login()
    mint_api.register_account(days_in_cycle=-10, days_in_plan=-3)
    mint_api.register_plans()
    mint_api.register_usage()
    mint_api.mock.get(f"{GATEWAY}/v1/mint/account/{ACCOUNT_ID}/multi-line", status=404)

    result = await run_config_flow(hass)
    assert result["type"] is FlowResultType.CREATE_ENTRY

    assert hass.states.get(PRIMARY_DAYS_MONTH).state == "0"
    assert hass.states.get(PRIMARY_DAYS_PLAN).state == "0"


async def test_options_flow_updates_credentials_and_reloads(
    hass: HomeAssistant, mint_api
) -> None:
    """Successfully re-authenticating through the options flow persists the
    new username/password/polling settings and reloads the entry with them.
    """
    mint_api.register_all()
    await run_config_flow(hass)
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_USERNAME: PHONE,
            CONF_PASSWORD: "new-password",
            CONF_ATTRIBUTESENSORS: False,
            CONF_POLLING_INTERVAL: 6,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert entry.data[CONF_PASSWORD] == "new-password"
    assert entry.data[CONF_POLLING_INTERVAL] == 6
    assert entry.data[CONF_ATTRIBUTESENSORS] is False
    # The reload applied the new (attributesensors=False) config: the plan-term
    # entity is no longer created, so HA leaves its old state as a restored
    # placeholder (see test_unload_removes_entities for the same behaviour).
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(PRIMARY_PLAN_TERM).state == STATE_UNAVAILABLE
    assert hass.states.get(PRIMARY_REMAINING).state == "5.0"


async def test_options_flow_invalid_credentials_reprompts(
    hass: HomeAssistant, mint_api
) -> None:
    """A rejected re-authentication in the options flow must not overwrite
    the entry's existing, still-working credentials.
    """
    mint_api.register_all()
    await run_config_flow(hass)
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    old_password = entry.data[CONF_PASSWORD]

    result = await hass.config_entries.options.async_init(entry.entry_id)

    mint_api.mock.clear_requests()
    mint_api.mock.post(f"{GATEWAY}/v1/mint/login", status=401, text="unauthorized")

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_USERNAME: PHONE,
            CONF_PASSWORD: "wrong-password",
            CONF_ATTRIBUTESENSORS: True,
            CONF_POLLING_INTERVAL: 12,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_credentials"}
    assert entry.data[CONF_PASSWORD] == old_password


def _b64url_segment(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


@pytest.mark.xfail(
    reason=(
        "Latent bug in custom_components/mintmobile/api.py: decode_jwt() uses "
        "base64.b64decode, but JWTs are base64url-encoded (RFC 7519 / RFC 4648 "
        "sec. 5). b64decode silently discards the out-of-alphabet '-' and '_', "
        "so such a segment either raises 'Incorrect padding' or decodes to the "
        "wrong bytes. The fix is one line: base64.urlsafe_b64decode. "
        "NOT currently reachable with Mint's tokens -- a base64url segment only "
        "contains '-'/'_' when the raw payload JSON has '>', '?', '~' or \\x7f at "
        "a byte offset of 2 mod 3, which alphanumeric claims (numeric ids, "
        "UUIDs, hex) never produce; the token shipped in api.py decodes fine. "
        "Hence the contrived payload below. This is a correctness guard against "
        "a future claim value, not a live outage."
    ),
    strict=True,
)
def test_decode_jwt_handles_base64url_specific_characters() -> None:
    """decode_jwt should tolerate the full base64url alphabet ('-' and '_'),
    since that is what real JWT payload segments are encoded with -- not the
    standard base64 alphabet ('+' and '/') that base64.b64decode expects.
    """
    header = _b64url_segment({"alg": "HS256", "typ": "JWT"})
    payload = {"sub": ">djA>Wt[GS=U8po!799NksnRH9~u&c", "exp": 1893456007}
    body = _b64url_segment(payload)
    assert "-" in body or "_" in body  # sanity check on the fixture itself
    token = f"{header}.{body}.signature"

    decoded = decode_jwt(token)

    assert decoded["sub"] == payload["sub"]
    assert decoded["exp"] == payload["exp"]

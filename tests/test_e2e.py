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

from custom_components.mintmobile.api import (
    STATIC_APP_TOKEN,
    SUBSCRIBER_TYPES,
    decode_jwt,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMockResponse,
)
from custom_components.mintmobile.const import (
    CONF_ATTRIBUTESENSORS,
    CONF_LOGIN_MODE,
    CONF_PASSWORD,
    CONF_POLLING_INTERVAL,
    CONF_SENSOR_DAYS_REMAINING_MONTH,
    CONF_SENSOR_DAYS_REMAINING_PLAN,
    CONF_SENSOR_PLAN_TERM,
    CONF_USERNAME,
    DEFAULT_LOGIN_MODE,
    DOMAIN,
    LOGIN_MODE_INTERNET,
    LOGIN_MODE_PHONE,
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
    hass: HomeAssistant,
    *,
    attribute_sensors: bool = True,
    polling_interval: int = 12,
    login_mode: str = DEFAULT_LOGIN_MODE,
    username: str = PHONE,
):
    """Walk the four-step config flow: login mode -> credentials ->
    attribute sensors -> polling.
    """
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LOGIN_MODE: login_mode}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "credentials"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USERNAME: username, CONF_PASSWORD: PASSWORD},
    )
    if result["type"] is not FlowResultType.FORM or result["step_id"] != "attribute_sensors":
        return result

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_SENSOR_PLAN_TERM: attribute_sensors,
            CONF_SENSOR_DAYS_REMAINING_MONTH: attribute_sensors,
            CONF_SENSOR_DAYS_REMAINING_PLAN: attribute_sensors,
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
    assert result["step_id"] == "credentials"
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
    assert result["step_id"] == "credentials"
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
            CONF_LOGIN_MODE: LOGIN_MODE_PHONE,
            CONF_SENSOR_PLAN_TERM: False,
            CONF_SENSOR_DAYS_REMAINING_MONTH: False,
            CONF_SENSOR_DAYS_REMAINING_PLAN: False,
            CONF_POLLING_INTERVAL: 6,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert entry.data[CONF_PASSWORD] == "new-password"
    assert entry.data[CONF_POLLING_INTERVAL] == 6
    assert entry.data[CONF_SENSOR_PLAN_TERM] is False
    # The reload applied the new (plan-term sensor off) config: that entity
    # is no longer created, so HA leaves its old state as a restored
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
            CONF_LOGIN_MODE: LOGIN_MODE_PHONE,
            CONF_SENSOR_PLAN_TERM: True,
            CONF_SENSOR_DAYS_REMAINING_MONTH: True,
            CONF_SENSOR_DAYS_REMAINING_PLAN: True,
            CONF_POLLING_INTERVAL: 12,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_credentials"}
    assert entry.data[CONF_PASSWORD] == old_password


def _b64url_segment(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def test_decode_jwt_handles_base64url_specific_characters() -> None:
    """decode_jwt must tolerate the full base64url alphabet ('-' and '_'),
    which is what real JWT payload segments are encoded with -- not the
    standard base64 alphabet ('+' and '/').
    """
    header = _b64url_segment({"alg": "HS256", "typ": "JWT"})
    payload = {"sub": ">djA>Wt[GS=U8po!799NksnRH9~u&c", "exp": 1893456007}
    body = _b64url_segment(payload)
    assert "-" in body or "_" in body  # sanity check on the fixture itself
    token = f"{header}.{body}.signature"

    decoded = decode_jwt(token)

    assert decoded["sub"] == payload["sub"]
    assert decoded["exp"] == payload["exp"]


def test_decode_jwt_still_accepts_standard_base64_segments() -> None:
    """The base64url fix must not regress segments encoded with the standard
    alphabet: '+' and '/' have to keep decoding as they did before.
    """
    payload = {"sub": ">djA>Wt[GS=U8po!799NksnRH9~u&c", "exp": 1893456007}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    body = base64.b64encode(raw).decode().rstrip("=")
    assert "+" in body or "/" in body  # sanity check on the fixture itself

    decoded = decode_jwt(f"header.{body}.signature")

    assert decoded["sub"] == payload["sub"]
    assert decoded["exp"] == payload["exp"]


def test_decode_jwt_rejects_a_corrupt_segment_instead_of_silently_decoding() -> None:
    """A segment containing characters in neither alphabet must raise, not be
    silently stripped down to a shorter, wrong payload.
    """
    body = _b64url_segment({"sub": "123456", "exp": 1893456007})
    corrupt = body[:4] + "*!" + body[4:]

    with pytest.raises(ValueError, match="Failed to decode JWT"):
        decode_jwt(f"header.{corrupt}.signature")


def test_decode_jwt_rejects_a_token_with_no_payload_segment() -> None:
    """A string that is not a JWT at all must raise a clear ValueError."""
    with pytest.raises(ValueError, match="Failed to decode JWT"):
        decode_jwt("not-a-jwt")


def test_decode_jwt_reads_the_token_shipped_in_api_py() -> None:
    """Regression guard: the static app token bundled in api.py must keep
    decoding to its known claims.
    """
    assert decode_jwt(STATIC_APP_TOKEN) == {
        "iat": 1507766824,
        "nbf": 1507766824,
        "exp": 1594080424,
        "aud": "MintApp",
        "iss": "ULTRA",
    }


async def test_setup_succeeds_with_a_base64url_encoded_session_token(
    hass: HomeAssistant, mint_api
) -> None:
    """End-to-end proof of the fix: a login token whose payload segment
    contains base64url characters must set the integration up normally, with
    the account id correctly recovered from the JWT.
    """
    body = _b64url_segment({"sub": ACCOUNT_ID, "exp": int(time.time()) + 3600, "jti": ">?~"})
    assert "-" in body or "_" in body  # the token must actually exercise the fix
    token = f"{_b64url_segment({'alg': 'HS256', 'typ': 'JWT'})}.{body}.signature"

    mint_api.mock.post(
        f"{GATEWAY}/v1/mint/login",
        json={"token": token, "refreshToken": "refresh-token-abc"},
    )
    mint_api.register_account()
    mint_api.register_plans()
    mint_api.register_usage()
    mint_api.register_multi_line()

    result = await run_config_flow(hass)
    assert result["type"] is FlowResultType.CREATE_ENTRY

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.state is ConfigEntryState.LOADED
    assert entry.data["token"] == token
    # The account id came from the JWT "sub" claim, so the per-account
    # endpoints were addressed correctly.
    assert hass.states.get(PRIMARY_REMAINING).state == "5.0"
    assert hass.states.get(MEMBER_REMAINING).state == "2.0"


async def test_data_only_line_falls_back_to_a_working_subscriber_type(
    hass: HomeAssistant, mint_api
) -> None:
    """A tablet / mobile-internet line 401s on subscriberType=PHONE. Setup must
    advance to the next candidate rather than failing the whole entry.
    """
    mint_api.register_login()
    mint_api.register_account()
    mint_api.register_plans()
    mint_api.register_usage_only_accepting("TABLET")
    mint_api.mock.get(f"{GATEWAY}/v1/mint/account/{ACCOUNT_ID}/multi-line", status=404)

    result = await run_config_flow(hass)
    assert result["type"] is FlowResultType.CREATE_ENTRY

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.state is ConfigEntryState.LOADED
    # The first refresh probes PHONE, gets a 401, and advances to TABLET.
    # (Setup refreshes more than once: async_add_entities(..., True) makes
    # CoordinatorEntity.async_update request another refresh.) Every attempt
    # after the initial probe must go straight to the discovered type.
    attempts = mint_api.usage_attempts()
    assert attempts[:2] == ["PHONE", "TABLET"]
    assert set(attempts[2:]) <= {"TABLET"}
    assert hass.states.get(PRIMARY_REMAINING).state == "5.0"
    assert hass.states.get(PRIMARY_USED).state == "3.0"


async def test_phone_line_still_makes_a_single_usage_request(
    hass: HomeAssistant, mint_api
) -> None:
    """Regression guard: phone accounts must not pay for the fallback loop.
    PHONE is tried first, succeeds, and no further candidates are attempted.
    """
    mint_api.register_login()
    mint_api.register_account()
    mint_api.register_plans()
    mint_api.register_usage_only_accepting("PHONE")
    mint_api.mock.get(f"{GATEWAY}/v1/mint/account/{ACCOUNT_ID}/multi-line", status=404)

    result = await run_config_flow(hass)
    assert result["type"] is FlowResultType.CREATE_ENTRY

    # PHONE is tried first and works, so no other candidate is ever sent.
    assert set(mint_api.usage_attempts()) == {"PHONE"}
    assert hass.states.get(PRIMARY_REMAINING).state == "5.0"


async def test_discovered_subscriber_type_is_reused_on_the_next_poll(
    hass: HomeAssistant, mint_api
) -> None:
    """Once a subscriber type is known it is tried first, so later polls cost
    one request instead of re-walking the 401 every refresh.
    """
    mint_api.register_login()
    mint_api.register_account()
    mint_api.register_plans()
    mint_api.register_usage_only_accepting("TABLET")
    mint_api.mock.get(f"{GATEWAY}/v1/mint/account/{ACCOUNT_ID}/multi-line", status=404)

    await run_config_flow(hass)
    during_setup = len(mint_api.usage_attempts())

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    coordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.last_update_success
    assert mint_api.usage_attempts()[during_setup:] == ["TABLET"]


async def test_a_non_401_usage_error_is_not_retried_across_subscriber_types(
    hass: HomeAssistant, mint_api
) -> None:
    """Only a 401 means "wrong subscriber type". A 5xx is a real outage and
    must surface immediately instead of being masked by the fallback loop.
    """
    mint_api.register_login()
    mint_api.register_account()
    mint_api.register_plans()
    mint_api.mock.post(
        f"{GATEWAY}/v2/mint/account/{ACCOUNT_ID}/usage", status=503, text="boom"
    )

    result = await run_config_flow(hass)
    assert result["type"] is FlowResultType.CREATE_ENTRY

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert mint_api.usage_attempts() == ["PHONE"]


async def test_setup_retries_when_no_subscriber_type_is_accepted(
    hass: HomeAssistant, mint_api
) -> None:
    """If every candidate 401s the error is still reported, after each one has
    genuinely been tried.
    """
    mint_api.register_login()
    mint_api.register_account()
    mint_api.register_plans()
    mint_api.register_usage_only_accepting("NOT_A_REAL_TYPE")

    result = await run_config_flow(hass)
    assert result["type"] is FlowResultType.CREATE_ENTRY

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert mint_api.usage_attempts() == list(SUBSCRIBER_TYPES)


async def test_login_mode_defaults_to_phone(hass: HomeAssistant, mint_api) -> None:
    """The account-type picker must default to Mint Mobile, not Minternet."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["step_id"] == "user"
    default = result["data_schema"]({})
    assert default[CONF_LOGIN_MODE] == LOGIN_MODE_PHONE == DEFAULT_LOGIN_MODE


async def test_phone_login_sends_msisdn_field(hass: HomeAssistant, mint_api) -> None:
    """Choosing Mint Mobile must send the credential as "msisdn"."""
    mint_api.register_all()

    result = await run_config_flow(hass, login_mode=LOGIN_MODE_PHONE, username=PHONE)
    assert result["type"] is FlowResultType.CREATE_ENTRY

    body = mint_api.login_request_body()
    assert body["msisdn"] == PHONE
    assert "username" not in body
    assert body["subscriberType"] == "PHONE"


async def test_internet_login_sends_username_field(hass: HomeAssistant, mint_api) -> None:
    """Choosing Minternet must send the credential as "username", not "msisdn" --
    confirmed against a real Minternet login capture (ha-mint-mobile#39).
    subscriberType still reads "PHONE" in the request even here; that's not a
    bug, see the comment in api.py.
    """
    mint_api.register_all()
    minternet_username = "jdoe-internet"

    result = await run_config_flow(
        hass, login_mode=LOGIN_MODE_INTERNET, username=minternet_username
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY

    body = mint_api.login_request_body()
    assert body["username"] == minternet_username
    assert "msisdn" not in body
    assert body["subscriberType"] == "PHONE"


async def test_attribute_sensors_screen_allows_picking_one_at_a_time(
    hass: HomeAssistant, mint_api
) -> None:
    """The three attributes must be independently selectable, not all-or-nothing."""
    mint_api.register_all()

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LOGIN_MODE: LOGIN_MODE_PHONE}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: PHONE, CONF_PASSWORD: PASSWORD}
    )
    assert result["step_id"] == "attribute_sensors"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_SENSOR_PLAN_TERM: True,
            CONF_SENSOR_DAYS_REMAINING_MONTH: False,
            CONF_SENSOR_DAYS_REMAINING_PLAN: False,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_POLLING_INTERVAL: 12}
    )
    await hass.async_block_till_done()

    assert hass.states.get(PRIMARY_PLAN_TERM) is not None
    assert hass.states.get(PRIMARY_DAYS_MONTH) is None
    assert hass.states.get(PRIMARY_DAYS_PLAN) is None


async def test_legacy_entry_with_only_blanket_flag_keeps_all_sensors(
    hass: HomeAssistant, mint_api
) -> None:
    """An entry saved before the per-attribute keys existed only has
    CONF_ATTRIBUTESENSORS=True; upgrading must not silently remove the
    sensors that flag used to create.
    """
    mint_api.register_all()
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_USERNAME: PHONE,
            CONF_PASSWORD: PASSWORD,
            CONF_ATTRIBUTESENSORS: True,
            # No CONF_LOGIN_MODE, no per-attribute keys -- exactly what a
            # pre-Minternet-support entry looks like.
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(PRIMARY_PLAN_TERM) is not None
    assert hass.states.get(PRIMARY_DAYS_MONTH) is not None
    assert hass.states.get(PRIMARY_DAYS_PLAN) is not None


async def test_linked_internet_line_appears_alongside_phone(
    hass: HomeAssistant, mint_api
) -> None:
    """A phone login on an account with a linked Minternet product must
    create a second line for it -- regardless of which credential logged in
    (ha-mint-mobile#39).
    """
    mint_api.register_login(primary_type="PHONE")
    mint_api.register_account(
        internet={
            "msisdn": "7778889999",
            "firstName": "Ryan",
            "plan": {
                "exp": mint_api._ts(180),
                "endOfCycle": mint_api._ts(20),
                "months": 12,
            },
        }
    )
    mint_api.register_plans()
    mint_api.register_usage(internet={"remainingHighSpeedData": 1024000, "usageHighSpeedData": 512000})
    mint_api.mock.get(f"{GATEWAY}/v1/mint/account/{ACCOUNT_ID}/multi-line", status=404)

    result = await run_config_flow(hass, login_mode=LOGIN_MODE_PHONE)
    assert result["type"] is FlowResultType.CREATE_ENTRY

    internet_remaining = "sensor.ryan_internet_data_usage_remaining"
    internet_used = "sensor.ryan_internet_data_used"
    assert hass.states.get(PRIMARY_REMAINING).state == "5.0"
    assert hass.states.get(PRIMARY_REMAINING).attributes["line_type"] == "phone"
    assert hass.states.get(internet_remaining).state == "1000.0"
    assert hass.states.get(internet_used).state == "500.0"
    assert hass.states.get(internet_remaining).attributes["line_type"] == "internet"
    assert hass.states.get(internet_remaining).attributes["phone_number"] == "7778889999"


async def test_internet_login_labels_the_primary_line_from_the_login_response(
    hass: HomeAssistant, mint_api
) -> None:
    """The primary line's label comes from the login response's
    subscriberType (ha-mint-mobile#39), not from an assumption that the
    top-level account data is always a phone line. Logging in with the
    Minternet credential must produce an "internet"-labeled primary line
    even though this fixture's top-level data is phone-shaped.
    """
    mint_api.register_login(primary_type="INTERNET")
    mint_api.register_account()  # top-level data is phone-shaped, as always
    mint_api.register_plans()
    mint_api.register_usage_only_accepting("PHONE")
    mint_api.mock.get(f"{GATEWAY}/v1/mint/account/{ACCOUNT_ID}/multi-line", status=404)

    result = await run_config_flow(hass, login_mode=LOGIN_MODE_INTERNET, username="jdoe-internet")
    assert result["type"] is FlowResultType.CREATE_ENTRY

    internet_remaining = "sensor.ryan_internet_data_usage_remaining"
    assert hass.states.get(internet_remaining).attributes["line_type"] == "internet"
    assert hass.states.get(internet_remaining).state == "5.0"
    # No separate "phone"-labeled line: this fixture's account response has
    # no nested "phone" key at all, so there's nothing else to surface.
    assert hass.states.get(PRIMARY_REMAINING) is None


async def test_internet_only_account_creates_a_single_correctly_labeled_line(
    hass: HomeAssistant, mint_api
) -> None:
    """A Minternet-only account (no linked phone at all) must produce exactly
    one line, labeled "internet", not a spuriously-labeled "phone" line.
    """
    mint_api.register_login(primary_type="INTERNET")
    mint_api.register_account()  # no internet=/tablet= kwargs -> nothing linked
    mint_api.register_plans()
    mint_api.register_usage_only_accepting("INTERNET")
    mint_api.mock.get(f"{GATEWAY}/v1/mint/account/{ACCOUNT_ID}/multi-line", status=404)

    result = await run_config_flow(hass, login_mode=LOGIN_MODE_INTERNET, username="jdoe-internet")
    assert result["type"] is FlowResultType.CREATE_ENTRY

    assert hass.states.get("sensor.ryan_internet_data_usage_remaining").attributes["line_type"] == "internet"
    # Exactly one line's worth of entities (5, since attribute sensors
    # default on in run_config_flow) -- proves nothing was double-counted.
    line_entities = [eid for eid in hass.states.async_entity_ids("sensor") if eid.startswith("sensor.ryan_")]
    assert len(line_entities) == 5


async def test_phone_only_account_is_unaffected_by_envelope_support(
    hass: HomeAssistant, mint_api
) -> None:
    """Regression guard: an account with no "internet"/"tablet" keys at all
    must behave exactly as before -- one line, labeled "phone".
    """
    mint_api.register_all()  # no internet=/tablet= kwargs

    result = await run_config_flow(hass)
    assert result["type"] is FlowResultType.CREATE_ENTRY

    assert hass.states.get(PRIMARY_REMAINING).state == "5.0"
    assert hass.states.get(PRIMARY_REMAINING).attributes["line_type"] == "phone"
    assert hass.states.get("sensor.ryan_internet_data_usage_remaining") is None


async def test_multi_line_family_members_are_labeled_phone(
    hass: HomeAssistant, mint_api
) -> None:
    """Family members found via /multi-line are always phone lines."""
    mint_api.register_all()

    result = await run_config_flow(hass)
    assert result["type"] is FlowResultType.CREATE_ENTRY

    assert hass.states.get(MEMBER_REMAINING).attributes["line_type"] == "phone"


async def test_adding_the_same_credential_twice_aborts(
    hass: HomeAssistant, mint_api
) -> None:
    """A second entry with the identical credential resolves to the same
    Mint account id (same JWT) and must abort instead of silently creating
    an entry whose sensors all collide on unique_id (ha-mint-mobile#39).
    """
    mint_api.register_all()

    first = await run_config_flow(hass)
    assert first["type"] is FlowResultType.CREATE_ENTRY

    second = await run_config_flow(hass)
    assert second["type"] is FlowResultType.ABORT
    assert second["reason"] == "already_configured"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_linked_credentials_with_different_account_ids_both_allowed(
    hass: HomeAssistant, mint_api
) -> None:
    """Phone and Minternet logins on a linked account resolve to *different*
    Mint account ids (confirmed in #39's captures) and must both be allowed
    as separate entries -- this is the supported way to use a linked
    account, distinct from the same-credential-twice case above.
    """
    other_id = "999999"

    # A single mock can't distinguish the two logins by URL, since both hit
    # the same endpoint -- match on which credential field was sent instead.
    async def _login_by_credential(method, url, data):
        credential = (data or {}).get("msisdn") or (data or {}).get("username")
        if credential == "jdoe-internet":
            return AiohttpClientMockResponse(
                method,
                url,
                status=200,
                json={
                    "token": make_jwt(other_id, int(time.time()) + 3600),
                    "refreshToken": "refresh-token-xyz",
                    "userId": other_id,
                    "subscriberType": "INTERNET",
                },
            )
        return AiohttpClientMockResponse(
            method,
            url,
            status=200,
            json={
                "token": mint_api.token,
                "refreshToken": "refresh-token-abc",
                "userId": ACCOUNT_ID,
                "subscriberType": "PHONE",
            },
        )

    mint_api.mock.post(f"{GATEWAY}/v1/mint/login", side_effect=_login_by_credential)
    mint_api.register_account()
    mint_api.register_plans()
    mint_api.register_usage()
    mint_api.register_multi_line()
    # The second account's own endpoints, so its entry loads successfully
    # too rather than just completing the flow.
    mint_api.mock.get(
        f"{GATEWAY}/v1/mint/account/{other_id}",
        json={"msisdn": "jdoe-internet", "firstName": "Jane", "plan": {"exp": 0, "endOfCycle": 0, "months": 12}},
    )
    mint_api.mock.get(f"{GATEWAY}/v1/mint/account/{other_id}/plans", json={"plans": []})
    mint_api.mock.post(
        f"{GATEWAY}/v2/mint/account/{other_id}/usage",
        json={"remainingHighSpeedData": 2048, "usageHighSpeedData": 1024},
    )
    mint_api.mock.get(f"{GATEWAY}/v1/mint/account/{other_id}/multi-line", status=404)

    first = await run_config_flow(hass, login_mode=LOGIN_MODE_PHONE)
    assert first["type"] is FlowResultType.CREATE_ENTRY

    second = await run_config_flow(
        hass, login_mode=LOGIN_MODE_INTERNET, username="jdoe-internet"
    )
    assert second["type"] is FlowResultType.CREATE_ENTRY

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 2
    assert all(e.state is ConfigEntryState.LOADED for e in entries)


async def test_legacy_entry_without_unique_id_is_backfilled_on_setup(
    hass: HomeAssistant, mint_api
) -> None:
    """Entries created before duplicate-entry detection existed have no
    unique_id. A successful setup must backfill one so a later attempt to
    re-add the same credential is actually caught, not silently allowed.
    """
    mint_api.register_all()
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: PHONE, CONF_PASSWORD: PASSWORD},
        unique_id=None,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.unique_id == ACCOUNT_ID

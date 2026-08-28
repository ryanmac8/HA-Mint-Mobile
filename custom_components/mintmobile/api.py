import logging
import time
import base64
import json
import aiohttp

_LOGGER = logging.getLogger(__name__)

# Mirrors const.LOGIN_MODE_INTERNET/const.LOGIN_MODE_PHONE. Kept as a literal
# here rather than imported so this module still runs standalone via test.py
# (`from api import MintMobile`, outside the custom_components package).
LOGIN_MODE_INTERNET = "internet"

STATIC_APP_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpYXQiOjE1MDc3NjY4MjQsIm5iZiI6MTUwNzc2NjgyNCwiZXhwIjoxNTk0MDgwNDI0LCJhdWQiOiJNaW50QXBwIiwiaXNzIjoiVUxUUkEifQ.r909IZmcavEhqvZO0td_-Ts_q27BBk4cCbFRXpDBQUM"

# JWT segments use the base64url alphabet, which swaps "+" and "/" for "-"
# and "_". Translating back lets one decode call accept either alphabet.
_B64URL_TO_STANDARD = str.maketrans("-_", "+/")


def decode_jwt(token: str) -> dict:
    """Decode the payload segment of a JWT.

    Segments are base64url encoded (RFC 7519, RFC 4648 section 5). Decoding
    them with the standard alphabet silently discards any "-" or "_", which
    either trips the padding check or, worse, yields a corrupted payload and a
    wrong account id. Translating first avoids that; validate=True then makes a
    genuinely malformed segment raise rather than decode to garbage.
    """
    try:
        parts = token.split(".")
        if len(parts) < 2:
            raise ValueError("Invalid JWT format")
        payload = parts[1].translate(_B64URL_TO_STANDARD)
        payload += "=" * ((4 - len(payload) % 4) % 4)
        decoded = base64.b64decode(payload, validate=True).decode("utf-8")
        return json.loads(decoded)
    except Exception as e:
        _LOGGER.error("Failed to decode JWT: %s", e)
        raise ValueError(f"Failed to decode JWT: {e}")

# Subscriber types accepted by the usage endpoint. Phone lines report as
# "PHONE"; data-only lines (tablet, mobile internet) reject that value with a
# 401 and must send their own type instead.
SUBSCRIBER_TYPES = ("PHONE", "TABLET", "INTERNET")

# account/{id} and its usage response both return every product linked to
# the account in one payload: values at the top level, plus the same shape
# again nested under "phone"/"internet"/"tablet" keys for whichever of those
# are also linked. LINE_TYPE maps a nested key to the label exposed on that
# line's "line_type" attribute; the top-level line uses whichever of these
# matches its own subscriber type (see _line_type_for below).
LINE_TYPES = ("phone", "internet", "tablet")


def _extract_product_fields(product: dict, fallback_name: str) -> dict:
    """Pull the common account fields out of one product's dict.

    Mint returns this exact shape (msisdn, firstName, plan.{exp,endOfCycle,
    months}) both at the top level of the account response and again nested
    under "internet"/"tablet" for any other product linked to the account,
    so this same extraction applies whichever dict it's handed.
    """
    plan = product.get("plan") or {}
    now_sec = int(time.time())
    plan_exp = plan.get("exp") or 0
    end_of_cycle = plan.get("endOfCycle") or 0
    return {
        "phone_number": product.get("msisdn") or "",
        "line_name": product.get("firstName") or fallback_name,
        "endOfCycle": max(0, int((end_of_cycle - now_sec) / 86400)),
        "months": plan.get("months") or 0,
        "exp": max(0, int((plan_exp - now_sec) / 86400)),
    }


def _extract_usage_fields(usage: dict) -> dict:
    """Pull remaining/used data out of one product's usage dict."""
    remaining_mb = usage.get("remainingHighSpeedData", 0)
    used_mb = usage.get("usageHighSpeedData", 0)
    return {
        "remaining4G": round(remaining_mb / 1024, 2),
        "used4G": round(used_mb / 1024, 2),
    }


class MintMobile:
    def __init__(self, session: aiohttp.ClientSession, username, password, login_mode="phone", token=None, refresh_token=None, expires_at=None, token_update_callback=None):
        self.session = session
        self.username = username
        self.password = password
        self.login_mode = login_mode
        self.token = token
        self.refresh_token = refresh_token
        self.expires_at = expires_at
        self.token_update_callback = token_update_callback
        self.id = ""
        self.info = {}
        self.subscriber_type = None
        # What the account's own top-level identity is, e.g. "INTERNET" for
        # a Minternet-only login. Learned from the login/refresh response
        # when present (see #39); otherwise inferred from subscriber_type
        # once usage succeeds, defaulting to PHONE as a last resort so every
        # account that predates this attribute keeps behaving exactly as
        # before.
        self.primary_type = None

    async def async_login(self):
        """Log in to Mint Mobile and obtain a new session token."""
        _LOGGER.debug("Logging into Mint Mobile with login_mode=%s", self.login_mode)
        login_url = "https://mint-gateway.mintmobile.com/v1/mint/login"
        # A Minternet-only credential authenticates on the same endpoint but
        # under a "username" field instead of "msisdn". subscriberType stays
        # "PHONE" in the request body either way -- confirmed against a real
        # Minternet login capture (ha-mint-mobile#39); the request value
        # doesn't reflect the account type, only the response does (read
        # below). Don't be tempted to set it to "INTERNET" here: that's
        # unverified and the "PHONE" constant is the only shape known to work.
        credential_field = "username" if self.login_mode == LOGIN_MODE_INTERNET else "msisdn"
        login_body = {
            credential_field: self.username,
            "password": self.password,
            "subscriberType": "PHONE",
        }

        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": f"Bearer {STATIC_APP_TOKEN}",
            "kaena-channel": "ktrz9qhy92a4nx6",
            "user-agent": "MintMobile | 2026.5.27 (9076) | arm64 | dce80f5e-5d5c-4c67-bd93-4e4e19f2db8f | Android",
        }

        async with self.session.post(login_url, json=login_body, headers=headers) as r:
            if r.status != 200:
                err_text = await r.text()
                _LOGGER.error("Login failed with status %s: %s", r.status, err_text)
                return False
            
            response = await r.json()
            self.token = response.get("token") or response.get("accessToken")
            self.refresh_token = response.get("refreshToken")
            
            if not self.token:
                _LOGGER.error("Token not found in login response")
                return False
            
            payload = decode_jwt(self.token)
            self.id = str(payload.get("sub") or payload.get("userId") or response.get("userId"))
            self.expires_at = payload.get("exp") or (int(time.time()) + 900)
            # Unlike the request, the login response's subscriberType does
            # reflect the account actually authenticated -- "INTERNET" for a
            # Minternet login, confirmed in #39. Used later to label the
            # primary line instead of assuming it's always a phone line.
            self.primary_type = response.get("subscriberType") or self.primary_type

            if self.token_update_callback:
                self.token_update_callback(self.token, self.refresh_token, self.expires_at)
            
            return True

    async def async_refresh_session(self):
        """Refresh token using the refresh token."""
        if not self.refresh_token or not self.id:
            _LOGGER.debug("Missing refresh token or userId, cannot refresh session.")
            return False

        _LOGGER.debug("Attempting to refresh session token...")
        refresh_url = "https://mint-gateway.mintmobile.com/v1/mint/refresh"
        refresh_body = {
            "id": self.id,
            "refreshToken": self.refresh_token,
        }
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": f"Bearer {STATIC_APP_TOKEN}",
            "kaena-channel": "ktrz9qhy92a4nx6",
            "user-agent": "MintMobile | 2026.5.27 (9076) | arm64 | dce80f5e-5d5c-4c67-bd93-4e4e19f2db8f | Android",
        }

        try:
            async with self.session.post(refresh_url, json=refresh_body, headers=headers) as r:
                if r.status != 200:
                    _LOGGER.warning("Token refresh failed with status %s. Falling back to full login.", r.status)
                    return False
                
                response = await r.json()
                new_token = response.get("token")
                new_refresh_token = response.get("refreshToken")
                
                if new_token and new_refresh_token:
                    self.token = new_token
                    self.refresh_token = new_refresh_token
                    payload = decode_jwt(self.token)
                    self.expires_at = payload.get("exp") or (int(time.time()) + 900)
                    self.primary_type = response.get("subscriberType") or self.primary_type

                    if self.token_update_callback:
                        self.token_update_callback(self.token, self.refresh_token, self.expires_at)
                    
                    _LOGGER.debug("Session token successfully refreshed.")
                    return True
        except Exception as e:
            _LOGGER.warning("Error during token refresh: %s", e)
        return False

    async def async_ensure_valid_session(self):
        """Ensure we have a valid session token, refreshing or logging in as needed."""
        now = int(time.time())
        if self.token and self.expires_at and self.expires_at > now + 60:
            # Token is still valid
            _LOGGER.debug("Reusing cached session token.")
            # Ensure id is populated from JWT if missing
            if not self.id:
                try:
                    payload = decode_jwt(self.token)
                    self.id = str(payload.get("sub") or payload.get("userId"))
                except Exception:
                    pass
            return True

        if self.refresh_token:
            # Ensure id is populated
            if not self.id and self.token:
                try:
                    payload = decode_jwt(self.token)
                    self.id = str(payload.get("sub") or payload.get("userId"))
                except Exception:
                    pass
            if self.id and await self.async_refresh_session():
                return True

        return await self.async_login()

    async def async_get_all_data_remaining(self):
        """Retrieve account details, plans, usage, and multiline data."""
        if not await self.async_ensure_valid_session():
            raise Exception("Authentication failed")

        headers = {
            "accept": "application/json",
            "authorization": f"Bearer {self.token}",
            "kaena-channel": "ktrz9qhy92a4nx6",
            "user-agent": "MintMobile | 2026.5.27 (9076) | arm64 | dce80f5e-5d5c-4c67-bd93-4e4e19f2db8f | Android",
        }

        # 1. Fetch Account Details
        account_url = f"https://mint-gateway.mintmobile.com/v1/mint/account/{self.id}?&subscriberType=PHONE"
        async with self.session.get(account_url, headers=headers) as r:
            if r.status != 200:
                raise Exception(f"Failed to fetch account info: {r.status}")
            account_data = await r.json()

        # 2. Fetch Plans
        plans_url = f"https://mint-gateway.mintmobile.com/v1/mint/account/{self.id}/plans"
        async with self.session.get(plans_url, headers=headers) as r:
            if r.status != 200:
                raise Exception(f"Failed to fetch plans: {r.status}")
            plans_data = await r.json()

        # 3. Fetch Data Usage
        usage_url = f"https://mint-gateway.mintmobile.com/v2/mint/account/{self.id}/usage"
        usage_headers = {**headers, "content-type": "application/json"}

        # Try the subscriber type we already know works for this account, then
        # fall back through the rest. Only a 401 means "wrong subscriber type";
        # any other status is a real error and is raised as before.
        candidates = list(SUBSCRIBER_TYPES)
        if self.subscriber_type in candidates:
            candidates.remove(self.subscriber_type)
            candidates.insert(0, self.subscriber_type)

        usage_data = None
        last_status = None
        for subscriber_type in candidates:
            # A live capture of a real Minternet session (#39) sent "roaming"
            # alongside "data" only for subscriberType=INTERNET; phone/tablet
            # usage is only confirmed with "data" alone, so that's kept as-is
            # rather than sent everywhere on an unverified guess.
            types = ["data", "roaming"] if subscriber_type == "INTERNET" else ["data"]
            usage_body = {
                "types": types,
                "subscriberType": subscriber_type,
            }
            async with self.session.post(usage_url, json=usage_body, headers=usage_headers) as r:
                last_status = r.status
                if r.status == 200:
                    usage_data = await r.json()
                    if self.subscriber_type != subscriber_type:
                        _LOGGER.debug(
                            "Using subscriberType=%s for usage on %s",
                            subscriber_type, self.username,
                        )
                        self.subscriber_type = subscriber_type
                    break
                if r.status != 401:
                    break

        if usage_data is None:
            raise Exception(f"Failed to fetch usage: {last_status}")

        # What the account's own top-level identity actually is. The login
        # response is the most direct signal (see async_login); if that
        # wasn't available -- e.g. resuming from a cached token -- fall back
        # to whichever subscriber type usage just proved works, and only
        # default to PHONE if neither is known. That default preserves exact
        # prior behavior for every account that predates this attribute.
        primary_type = (self.primary_type or self.subscriber_type or "PHONE").upper()
        primary_line_type = primary_type.lower() if primary_type.lower() in LINE_TYPES else "phone"

        # account/{id} and its usage response both carry every linked
        # product: values at the top level (whichever the primary identity
        # is), plus the same shape again nested under "phone"/"internet"/
        # "tablet" for any other product linked to the account (see #39).
        # The top-level line is built from the top level; every other
        # linked product becomes its own additional line below.
        primary_product = account_data
        if not primary_product.get("msisdn") and not primary_product.get("plan"):
            # Some account payloads put the primary line's own fields only
            # under this same product-type key rather than at the account's
            # top level; fall back to that instead of reporting empty data.
            primary_product = account_data.get(primary_line_type) or account_data
        fields = _extract_product_fields(primary_product, fallback_name="Mint Line")
        usage_fields = _extract_usage_fields(usage_data)
        self.info[self.id] = {**fields, **usage_fields, "line_type": primary_line_type}

        for line_type in LINE_TYPES:
            if line_type == primary_line_type:
                continue
            product = account_data.get(line_type)
            if not product:
                continue
            product_usage = usage_data.get(line_type) or {}
            fields = _extract_product_fields(product, fallback_name=f"Mint {line_type.title()}")
            usage_fields = _extract_usage_fields(product_usage)
            self.info[f"{self.id}:{line_type}"] = {
                **fields,
                **usage_fields,
                "line_type": line_type,
            }

        # Multi-line accounts lookup
        try:
            multi_line_url = f"https://mint-gateway.mintmobile.com/v1/mint/account/{self.id}/multi-line"
            async with self.session.get(multi_line_url, headers=headers) as r:
                if r.status == 200:
                    multi_line_data = await r.json()
                    active_members = multi_line_data.get("activeMembers", [])

                    for member in active_members:
                        member_id = member.get("id")
                        if not member_id:
                            continue
                        
                        try:
                            member_usage_url = f"https://mint-gateway.mintmobile.com/v1/mint/account/{self.id}/multi-line/{member_id}/usage"
                            async with self.session.get(member_usage_url, headers=headers) as mr:
                                if mr.status == 200:
                                    member_usage_json = await mr.json()
                                    m_data = member_usage_json.get("data", {})
                                    m_remaining_mb = m_data.get("remaining4G", 0)
                                    m_used_mb = m_data.get("usage4G", 0)
                                    
                                    m_remaining_gb = round(m_remaining_mb / 1024, 2)
                                    m_used_gb = round(m_used_mb / 1024, 2)

                                    m_end_of_cycle = member.get("currentPlan", {}).get("rechargeDate", 0)
                                    m_plan_exp = member.get("nextPlan", {}).get("renewalDate", 0)
                                    m_plan_months = member.get("currentPlan", {}).get("duration", 0)

                                    now_sec = int(time.time())
                                    m_days_remaining_month = max(0, int((m_end_of_cycle - now_sec) / 86400))
                                    m_days_remaining_plan = max(0, int((m_plan_exp - now_sec) / 86400))

                                    self.info[member_id] = {
                                        "phone_number": member.get("msisdn", ""),
                                        "line_name": member.get("nickName") or "Family Line",
                                        "endOfCycle": m_days_remaining_month,
                                        "months": m_plan_months,
                                        "exp": m_days_remaining_plan,
                                        "remaining4G": m_remaining_gb,
                                        "used4G": m_used_gb,
                                        "line_type": "phone",
                                    }
                        except Exception as member_err:
                            _LOGGER.warning("Error fetching multi-line member details for %s: %s", member_id, member_err)
        except Exception as multi_line_err:
            _LOGGER.debug("Multi-line lookup skipped or failed: %s", multi_line_err)

        return self.info

    async def async_lines(self):
        """Get the lines identifiers."""
        if not self.info:
            await self.async_get_all_data_remaining()
        return list(self.info.keys())

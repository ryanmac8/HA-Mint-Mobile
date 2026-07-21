import logging
import time
import base64
import json
import aiohttp

_LOGGER = logging.getLogger(__name__)

STATIC_APP_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpYXQiOjE1MDc3NjY4MjQsIm5iZiI6MTUwNzc2NjgyNCwiZXhwIjoxNTk0MDgwNDI0LCJhdWQiOiJNaW50QXBwIiwiaXNzIjoiVUxUUkEifQ.r909IZmcavEhqvZO0td_-Ts_q27BBk4cCbFRXpDBQUM"

def decode_jwt(token: str) -> dict:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            raise ValueError("Invalid JWT format")
        payload = parts[1]
        payload += "=" * ((4 - len(payload) % 4) % 4)
        decoded = base64.b64decode(payload).decode("utf-8")
        return json.loads(decoded)
    except Exception as e:
        _LOGGER.error("Failed to decode JWT: %s", e)
        raise ValueError(f"Failed to decode JWT: {e}")

class MintMobile:
    def __init__(self, session: aiohttp.ClientSession, username, password, token=None, refresh_token=None, expires_at=None, token_update_callback=None):
        self.session = session
        self.username = username
        self.password = password
        self.token = token
        self.refresh_token = refresh_token
        self.expires_at = expires_at
        self.token_update_callback = token_update_callback
        self.id = ""
        self.info = {}

    async def async_login(self):
        """Log in to Mint Mobile and obtain a new session token."""
        _LOGGER.debug("Logging into Mint Mobile with phone: %s", self.username)
        login_url = "https://mint-gateway.mintmobile.com/v1/mint/login"
        login_body = {
            "msisdn": self.username,
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
        usage_body = {
            "types": ["data"],
            "subscriberType": "PHONE",
        }
        usage_headers = {**headers, "content-type": "application/json"}
        async with self.session.post(usage_url, json=usage_body, headers=usage_headers) as r:
            if r.status != 200:
                raise Exception(f"Failed to fetch usage: {r.status}")
            usage_data = await r.json()

        # Extract primary line info
        phone = account_data.get("msisdn") or account_data.get("phone", {}).get("msisdn") or self.username
        
        plan_exp = account_data.get("plan", {}).get("exp") or account_data.get("phone", {}).get("plan", {}).get("exp") or 0
        end_of_cycle = account_data.get("plan", {}).get("endOfCycle") or account_data.get("phone", {}).get("plan", {}).get("endOfCycle") or 0
        plan_months = account_data.get("plan", {}).get("months") or account_data.get("phone", {}).get("plan", {}).get("months") or 0
        line_name = account_data.get("firstName") or account_data.get("phone", {}).get("firstName") or "Mint Line"

        # Calculate remaining days
        now_sec = int(time.time())
        days_remaining_month = max(0, int((end_of_cycle - now_sec) / 86400))
        days_remaining_plan = max(0, int((plan_exp - now_sec) / 86400))

        # Data calculations (MB to GB)
        remaining_mb = usage_data.get("remainingHighSpeedData", 0)
        used_mb = usage_data.get("usageHighSpeedData", 0)
        
        remaining_gb = round(remaining_mb / 1024, 2)
        used_gb = round(used_mb / 1024, 2)

        self.info[self.id] = {
            "phone_number": phone,
            "line_name": line_name,
            "endOfCycle": days_remaining_month,
            "months": plan_months,
            "exp": days_remaining_plan,
            "remaining4G": remaining_gb,
            "used4G": used_gb,
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

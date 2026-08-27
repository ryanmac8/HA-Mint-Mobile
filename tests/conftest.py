"""Shared fixtures for the Mint Mobile end-to-end tests."""
import base64
import json
import time

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

GATEWAY = "https://mint-gateway.mintmobile.com"

ACCOUNT_ID = "123456"
MEMBER_ID = "789012"
PHONE = "5551234567"
PASSWORD = "hunter2"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load custom_components/mintmobile in every test."""
    return


def make_jwt(sub: str, exp: int) -> str:
    """Build a JWT whose payload the integration can decode."""

    def segment(payload: dict) -> str:
        raw = json.dumps(payload, separators=(",", ":")).encode()
        return base64.b64encode(raw).decode().rstrip("=")

    header = segment({"alg": "HS256", "typ": "JWT"})
    body = segment({"sub": sub, "exp": exp})
    return f"{header}.{body}.signature"


class MintApiFixture:
    """Registers a full, self-consistent Mint Mobile gateway on the mocker.

    Timestamps are anchored to "now" plus half a day so that the integer day
    arithmetic in ``api.py`` produces the same answer no matter how long the
    test takes to run.
    """

    #: Whole days the integration should report for the primary line.
    days_in_cycle = 12
    days_in_plan = 300
    member_days_in_cycle = 4
    member_days_in_plan = 90

    def __init__(self, aioclient_mock):
        self.mock = aioclient_mock
        self.now = int(time.time())
        self.token = make_jwt(ACCOUNT_ID, self.now + 3600)

    def _ts(self, days: int) -> int:
        """Return an epoch timestamp ``days`` and a half into the future."""
        return self.now + days * 86400 + 43200

    def register_all(self, *, multi_line: bool = True) -> None:
        """Register every endpoint a successful update touches."""
        self.register_login()
        self.register_account()
        self.register_plans()
        self.register_usage()
        if multi_line:
            self.register_multi_line()
        else:
            self.mock.get(f"{GATEWAY}/v1/mint/account/{ACCOUNT_ID}/multi-line", status=404)

    def register_login(self, *, status: int = 200) -> None:
        if status != 200:
            self.mock.post(f"{GATEWAY}/v1/mint/login", status=status, text="unauthorized")
            return
        self.mock.post(
            f"{GATEWAY}/v1/mint/login",
            json={
                "token": self.token,
                "refreshToken": "refresh-token-abc",
                "userId": ACCOUNT_ID,
            },
        )

    def register_account(
        self,
        *,
        status: int = 200,
        nested: bool = False,
        days_in_cycle: int | None = None,
        days_in_plan: int | None = None,
    ) -> None:
        if status != 200:
            self.mock.get(
                f"{GATEWAY}/v1/mint/account/{ACCOUNT_ID}", status=status, text="boom"
            )
            return
        days_in_cycle = self.days_in_cycle if days_in_cycle is None else days_in_cycle
        days_in_plan = self.days_in_plan if days_in_plan is None else days_in_plan
        plan = {
            "exp": self._ts(days_in_plan),
            "endOfCycle": self._ts(days_in_cycle),
            "months": 12,
        }
        if nested:
            # Some account payloads nest everything under "phone" instead of
            # putting msisdn/firstName/plan at the top level.
            body = {"phone": {"msisdn": PHONE, "firstName": "Ryan", "plan": plan}}
        else:
            body = {"msisdn": PHONE, "firstName": "Ryan", "plan": plan}
        self.mock.get(f"{GATEWAY}/v1/mint/account/{ACCOUNT_ID}", json=body)

    def register_plans(self) -> None:
        self.mock.get(
            f"{GATEWAY}/v1/mint/account/{ACCOUNT_ID}/plans",
            json={"plans": [{"id": "plan-12mo", "months": 12}]},
        )

    def register_usage(self) -> None:
        self.mock.post(
            f"{GATEWAY}/v2/mint/account/{ACCOUNT_ID}/usage",
            json={
                "remainingHighSpeedData": 5120,  # MB -> 5.0 GB
                "usageHighSpeedData": 3072,  # MB -> 3.0 GB
            },
        )

    def register_multi_line(
        self, *, usage_status: int = 200, include_id: bool = True
    ) -> None:
        member = {
            "msisdn": "5559876543",
            "nickName": "Kiddo",
            "currentPlan": {
                "rechargeDate": self._ts(self.member_days_in_cycle),
                "duration": 3,
            },
            "nextPlan": {"renewalDate": self._ts(self.member_days_in_plan)},
        }
        if include_id:
            member["id"] = MEMBER_ID
        self.mock.get(
            f"{GATEWAY}/v1/mint/account/{ACCOUNT_ID}/multi-line",
            json={"activeMembers": [member]},
        )
        if not include_id:
            # Members without an "id" have no per-member usage endpoint to call;
            # the integration must skip them rather than crash.
            return
        if usage_status == 200:
            self.mock.get(
                f"{GATEWAY}/v1/mint/account/{ACCOUNT_ID}/multi-line/{MEMBER_ID}/usage",
                json={"data": {"remaining4G": 2048, "usage4G": 1024}},  # -> 2.0/1.0 GB
            )
        else:
            self.mock.get(
                f"{GATEWAY}/v1/mint/account/{ACCOUNT_ID}/multi-line/{MEMBER_ID}/usage",
                status=usage_status,
                text="boom",
            )

    def register_refresh(
        self, *, status: int = 200, token: str | None = None, refresh_token: str = "refresh-token-def"
    ) -> None:
        if status != 200:
            self.mock.post(f"{GATEWAY}/v1/mint/refresh", status=status, text="boom")
            return
        self.mock.post(
            f"{GATEWAY}/v1/mint/refresh",
            json={"token": token or self.token, "refreshToken": refresh_token},
        )


@pytest.fixture
def mint_api(aioclient_mock):
    """Return a helper for stubbing the Mint Mobile gateway."""
    return MintApiFixture(aioclient_mock)

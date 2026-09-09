from typing import Any

import httpx

from app.core.exceptions import IntegrationError


ULTRAMSG_API_BASE_URL = "https://api.ultramsg.com"
READY_STATUSES = {"authenticated", "standby"}


class UltraMsgClient:
    def __init__(self, instance_id: str, token: str) -> None:
        self.instance_id = instance_id
        self.token = token
        self.base_url = f"{ULTRAMSG_API_BASE_URL}/{instance_id}"

    @staticmethod
    def _account_status(payload: dict[str, Any]) -> str | None:
        status = payload.get("status")
        if isinstance(status, str):
            return status.lower()
        if isinstance(status, dict):
            value = (
                status.get("accountStatus")
                or status.get("account_status")
                or status.get("status")
            )
            return str(value).lower() if value else None
        value = payload.get("accountStatus") or payload.get("account_status")
        return str(value).lower() if value else None

    async def test_connection(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/instance/status",
                    params={"token": self.token},
                )
        except httpx.TimeoutException:
            return {"success": False, "error": "UltraMsg connection timed out"}
        except httpx.HTTPError as exc:
            return {"success": False, "error": f"UltraMsg connection failed: {exc}"}

        try:
            payload = response.json()
        except ValueError:
            payload = {"body": response.text[:500]}
        if response.status_code != 200:
            return {
                "success": False,
                "error": f"UltraMsg returned HTTP {response.status_code}",
                "details": payload,
            }
        status = self._account_status(payload)
        return {
            "success": status in READY_STATUSES,
            "status": status,
            "details": payload,
            **(
                {}
                if status in READY_STATUSES
                else {"error": f"UltraMsg instance is not ready (status: {status or 'unknown'})"}
            ),
        }

    async def send_text(self, to: str, body: str) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    f"{self.base_url}/messages/chat",
                    data={"token": self.token, "to": to, "body": body},
                )
        except httpx.TimeoutException as exc:
            raise IntegrationError("UltraMsg message request timed out") from exc
        except httpx.HTTPError as exc:
            raise IntegrationError("UltraMsg message request failed") from exc

        try:
            payload = response.json()
        except ValueError:
            payload = {"body": response.text[:500]}
        sent = payload.get("sent")
        rejected = sent is False or str(sent).lower() == "false" or payload.get("error")
        if response.status_code not in (200, 201) or rejected:
            raise IntegrationError(
                f"UltraMsg send failed: HTTP {response.status_code}",
                {"provider_response": payload},
            )
        return payload

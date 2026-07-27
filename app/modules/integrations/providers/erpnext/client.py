import logging
from typing import Optional, Any
import httpx
from app.core.exceptions import IntegrationError

logger = logging.getLogger(__name__)


class ERPNextClient:
    def __init__(self, base_url: str, api_key: str, api_secret: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self._headers = {
            "Authorization": f"token {api_key}:{api_secret}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def test_connection(self) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/api/method/frappe.auth.get_logged_user",
                    headers=self._headers,
                )
                if response.status_code == 200:
                    return {"success": True, "user": response.json().get("message")}
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}",
                    "body": response.text[:500],
                }
            except httpx.ConnectError as e:
                return {"success": False, "error": f"Connection failed: {str(e)}"}
            except httpx.TimeoutException:
                return {"success": False, "error": "Connection timed out"}

    async def get_document(self, doctype: str, name: str) -> Optional[dict]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self.base_url}/api/resource/{doctype}/{name}",
                headers=self._headers,
            )
            if response.status_code == 404:
                return None
            if response.status_code != 200:
                raise IntegrationError(f"ERPNext error: {response.status_code}", {"body": response.text[:500]})
            return response.json().get("data", {})

    async def find_customer(self, customer_doctype: str, mobile_no: str) -> Optional[dict]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self.base_url}/api/resource/{customer_doctype}",
                headers=self._headers,
                params={"filters": f'[["mobile_no","=","{mobile_no}"]]', "fields": '["name","customer_name","mobile_no"]'},
            )
            if response.status_code == 200:
                data = response.json().get("data", [])
                return data[0] if data else None
            return None

    async def create_document(self, doctype: str, data: dict[str, Any]) -> dict:
        payload = {"data": {**data, "doctype": doctype}}
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{self.base_url}/api/resource/{doctype}",
                headers=self._headers,
                json=payload,
            )
            if response.status_code not in (200, 201):
                raise IntegrationError(
                    f"ERPNext create failed: {response.status_code}",
                    {"body": response.text[:500]},
                )
            return response.json().get("data", {})

    async def update_document(self, doctype: str, name: str, data: dict[str, Any]) -> dict:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.put(
                f"{self.base_url}/api/resource/{doctype}/{name}",
                headers=self._headers,
                json={"data": data},
            )
            if response.status_code != 200:
                raise IntegrationError(
                    f"ERPNext update failed: {response.status_code}",
                    {"body": response.text[:500]},
                )
            return response.json().get("data", {})

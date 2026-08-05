import json
import logging
from dataclasses import dataclass

import httpx
from livekit import api

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LiveKitResources:
    trunk_id: str
    dispatch_rule_id: str


class LiveKitProvisioner:
    def _validate_settings(self) -> None:
        if not all(
            (
                settings.LIVEKIT_URL,
                settings.LIVEKIT_API_KEY,
                settings.LIVEKIT_API_SECRET,
                settings.LIVEKIT_SIP_ENDPOINT,
            )
        ):
            raise RuntimeError("LiveKit telephony settings are not configured")

    def _client(self) -> api.LiveKitAPI:
        self._validate_settings()
        return api.LiveKitAPI(
            settings.LIVEKIT_URL,
            settings.LIVEKIT_API_KEY,
            settings.LIVEKIT_API_SECRET,
        )

    async def provision(
        self,
        *,
        connection_id: str,
        company_id: str,
        name: str,
        phone_number: str,
        auth_username: str | None,
        auth_password: str | None,
        allowed_addresses: list[str],
    ) -> LiveKitResources:
        client = self._client()
        trunk_id: str | None = None
        try:
            await self._clear_conflicting_trunks(client, phone_number, connection_id)
            trunk = await client.sip.create_sip_inbound_trunk(
                api.CreateSIPInboundTrunkRequest(
                    trunk=api.SIPInboundTrunkInfo(
                        name=name,
                        metadata=json.dumps(
                            {"connection_id": connection_id, "company_id": company_id}
                        ),
                        numbers=[phone_number],
                        allowed_addresses=allowed_addresses,
                        auth_username=auth_username or "",
                        auth_password=auth_password or "",
                    )
                )
            )
            trunk_id = trunk.sip_trunk_id
            dispatch = await client.sip.create_sip_dispatch_rule(
                api.CreateSIPDispatchRuleRequest(
                    rule=api.SIPDispatchRule(
                        dispatch_rule_individual=api.SIPDispatchRuleIndividual(
                            room_prefix="call-"
                        )
                    ),
                    trunk_ids=[trunk_id],
                    name=f"{name} dispatch",
                    metadata=json.dumps(
                        {"connection_id": connection_id, "company_id": company_id}
                    ),
                    room_config=api.RoomConfiguration(
                        agents=[
                            api.RoomAgentDispatch(
                                agent_name=settings.LIVEKIT_AGENT_NAME,
                                metadata=json.dumps({"connection_id": connection_id}),
                            )
                        ]
                    ),
                )
            )
            return LiveKitResources(trunk_id, dispatch.sip_dispatch_rule_id)
        except Exception:
            if trunk_id:
                try:
                    await client.sip.delete_sip_trunk(
                        api.DeleteSIPTrunkRequest(sip_trunk_id=trunk_id)
                    )
                except Exception:
                    logger.warning("Could not roll back LiveKit SIP trunk", exc_info=True)
            raise
        finally:
            await client.aclose()

    @staticmethod
    async def _clear_conflicting_trunks(
        client: api.LiveKitAPI, phone_number: str, connection_id: str
    ) -> None:
        """LiveKit rejects two inbound trunks sharing a number; drop our leftovers."""
        result = await client.sip.list_sip_inbound_trunk(
            api.ListSIPInboundTrunkRequest()
        )
        for item in result.items:
            if phone_number not in item.numbers:
                continue
            try:
                owner = json.loads(item.metadata or "{}").get("connection_id")
            except ValueError:
                owner = None
            if owner != connection_id:
                raise RuntimeError(
                    f"LiveKit trunk {item.sip_trunk_id} already uses {phone_number}"
                )
            logger.info(
                "Removing stale LiveKit SIP trunk %s for %s",
                item.sip_trunk_id,
                phone_number,
            )
            await client.sip.delete_sip_trunk(
                api.DeleteSIPTrunkRequest(sip_trunk_id=item.sip_trunk_id)
            )

    async def exists(self, trunk_id: str) -> bool:
        client = self._client()
        try:
            result = await client.sip.list_sip_inbound_trunk(
                api.ListSIPInboundTrunkRequest(trunk_ids=[trunk_id])
            )
            return any(item.sip_trunk_id == trunk_id for item in result.items)
        finally:
            await client.aclose()

    async def delete(self, trunk_id: str | None, dispatch_rule_id: str | None) -> None:
        if not trunk_id and not dispatch_rule_id:
            return
        client = self._client()
        try:
            if dispatch_rule_id:
                try:
                    await client.sip.delete_sip_dispatch_rule(
                        api.DeleteSIPDispatchRuleRequest(
                            sip_dispatch_rule_id=dispatch_rule_id
                        )
                    )
                except Exception:
                    logger.warning("Could not delete LiveKit dispatch rule", exc_info=True)
            if trunk_id:
                try:
                    await client.sip.delete_sip_trunk(
                        api.DeleteSIPTrunkRequest(sip_trunk_id=trunk_id)
                    )
                except Exception:
                    logger.warning("Could not delete LiveKit SIP trunk", exc_info=True)
        finally:
            await client.aclose()


class TwilioElasticSipClient:
    base_url = "https://trunking.twilio.com/v1"

    def __init__(self, account_sid: str, auth_token: str) -> None:
        self.auth = httpx.BasicAuth(account_sid, auth_token)

    async def provision(
        self,
        *,
        connection_id: str,
        name: str,
        phone_number_sid: str,
    ) -> str:
        domain = f"mw-{connection_id.replace('-', '')[:20]}.pstn.twilio.com"
        async with httpx.AsyncClient(
            base_url=self.base_url, auth=self.auth, timeout=20
        ) as client:
            trunk_response = await client.post(
                "/Trunks", data={"FriendlyName": name, "DomainName": domain}
            )
            trunk_response.raise_for_status()
            trunk_sid = trunk_response.json()["sid"]
            try:
                origination = await client.post(
                    f"/Trunks/{trunk_sid}/OriginationUrls",
                    data={
                        "FriendlyName": "LiveKit SIP",
                        "SipUrl": f"sip:{settings.LIVEKIT_SIP_ENDPOINT};transport=tcp",
                        "Priority": 10,
                        "Weight": 10,
                        "Enabled": "true",
                    },
                )
                origination.raise_for_status()
                number = await client.post(
                    f"/Trunks/{trunk_sid}/PhoneNumbers",
                    data={"PhoneNumberSid": phone_number_sid},
                )
                number.raise_for_status()
                return trunk_sid
            except Exception:
                await client.delete(f"/Trunks/{trunk_sid}")
                raise

    async def delete(self, trunk_sid: str) -> None:
        async with httpx.AsyncClient(
            base_url=self.base_url, auth=self.auth, timeout=20
        ) as client:
            response = await client.delete(f"/Trunks/{trunk_sid}")
            if response.status_code not in (204, 404):
                response.raise_for_status()

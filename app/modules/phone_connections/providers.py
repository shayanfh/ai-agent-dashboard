import json
import logging
import secrets
import string
from dataclasses import dataclass

import httpx
from livekit import api

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LiveKitResources:
    trunk_id: str
    dispatch_rule_id: str


@dataclass(slots=True)
class AsteriskResource:
    resource_id: str
    state: str
    provider_setup: dict


@dataclass(slots=True)
class TwilioTrunkResource:
    trunk_sid: str
    domain: str
    credential_list_sid: str
    sip_username: str
    sip_password: str


class AsteriskProvisionerClient:
    def __init__(self) -> None:
        if not all(
            (
                settings.ASTERISK_PROVISIONER_URL,
                settings.ASTERISK_PROVISIONER_API_KEY,
                settings.ASTERISK_PUBLIC_SIP_URI,
            )
        ):
            raise RuntimeError("Asterisk provisioning settings are not configured")
        self.base_url = settings.ASTERISK_PROVISIONER_URL.rstrip("/")
        self.headers = {
            "X-Provisioner-API-Key": settings.ASTERISK_PROVISIONER_API_KEY
        }

    async def provision(
        self, connection_id: str, payload: dict
    ) -> AsteriskResource:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            timeout=settings.ASTERISK_REQUEST_TIMEOUT_SECONDS,
        ) as client:
            response = await client.put(f"/v1/connections/{connection_id}", json=payload)
            response.raise_for_status()
            body = response.json()
            return AsteriskResource(
                resource_id=body["resource_id"],
                state=body["state"],
                provider_setup=body.get("provider_setup") or {},
            )

    async def status(self, resource_id: str) -> AsteriskResource:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            timeout=settings.ASTERISK_REQUEST_TIMEOUT_SECONDS,
        ) as client:
            response = await client.get(f"/v1/connections/{resource_id}")
            response.raise_for_status()
            body = response.json()
            return AsteriskResource(
                resource_id=body["resource_id"],
                state=body["state"],
                provider_setup=body.get("provider_setup") or {},
            )

    async def delete(self, resource_id: str | None) -> None:
        if not resource_id:
            return
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            timeout=settings.ASTERISK_REQUEST_TIMEOUT_SECONDS,
        ) as client:
            response = await client.delete(f"/v1/connections/{resource_id}")
            if response.status_code not in (204, 404):
                response.raise_for_status()

    async def provision_extension(
        self, extension_id: str, payload: dict
    ) -> AsteriskResource:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            timeout=settings.ASTERISK_REQUEST_TIMEOUT_SECONDS,
        ) as client:
            response = await client.put(f"/v1/extensions/{extension_id}", json=payload)
            response.raise_for_status()
            body = response.json()
            return AsteriskResource(
                resource_id=body["resource_id"],
                state=body["state"],
                provider_setup={},
            )

    async def delete_extension(self, resource_id: str | None) -> None:
        if not resource_id:
            return
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            timeout=settings.ASTERISK_REQUEST_TIMEOUT_SECONDS,
        ) as client:
            response = await client.delete(f"/v1/extensions/{resource_id}")
            if response.status_code not in (204, 404):
                response.raise_for_status()

    async def upload_outbound_media(self, media_id: str, wav: bytes) -> dict:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            timeout=max(settings.ASTERISK_REQUEST_TIMEOUT_SECONDS, 60),
        ) as client:
            response = await client.put(
                f"/v1/outbound-media/{media_id}",
                files={"media": (f"{media_id}.wav", wav, "audio/wav")},
            )
            response.raise_for_status()
            return response.json()

    async def originate_outbound(self, payload: dict) -> dict:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            timeout=settings.ASTERISK_REQUEST_TIMEOUT_SECONDS,
        ) as client:
            response = await client.post("/v1/outbound-calls", json=payload)
            response.raise_for_status()
            return response.json()


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
        errors: list[Exception] = []
        try:
            if dispatch_rule_id:
                try:
                    await client.sip.delete_sip_dispatch_rule(
                        api.DeleteSIPDispatchRuleRequest(
                            sip_dispatch_rule_id=dispatch_rule_id
                        )
                    )
                except api.ServerError as exc:
                    if exc.code != api.TwirpErrorCode.NOT_FOUND:
                        errors.append(exc)
                except Exception as exc:  # noqa: BLE001 - surface SDK/network cleanup errors
                    errors.append(exc)
            if trunk_id:
                try:
                    await client.sip.delete_sip_trunk(
                        api.DeleteSIPTrunkRequest(sip_trunk_id=trunk_id)
                    )
                except api.ServerError as exc:
                    if exc.code != api.TwirpErrorCode.NOT_FOUND:
                        errors.append(exc)
                except Exception as exc:  # noqa: BLE001 - surface SDK/network cleanup errors
                    errors.append(exc)
        finally:
            await client.aclose()
        if errors:
            raise errors[0]


class TwilioElasticSipClient:
    base_url = "https://trunking.twilio.com/v1"

    def __init__(self, account_sid: str, auth_token: str) -> None:
        self.account_sid = account_sid
        self.auth = httpx.BasicAuth(account_sid, auth_token)

    async def provision(
        self,
        *,
        connection_id: str,
        name: str,
        phone_number_sid: str,
        target_sip_uri: str,
    ) -> TwilioTrunkResource:
        domain = f"mw-{connection_id.replace('-', '')[:20]}.pstn.twilio.com"
        sip_username = f"mw-{connection_id.replace('-', '')[:24]}"
        alphabet = string.ascii_letters + string.digits
        sip_password = "".join(secrets.choice(alphabet) for _ in range(40))
        credential_list_sid: str | None = None
        async with httpx.AsyncClient(
            base_url=self.base_url, auth=self.auth, timeout=20
        ) as client:
            trunk_response = await client.post(
                "/Trunks", data={"FriendlyName": name, "DomainName": domain}
            )
            trunk_response.raise_for_status()
            trunk_sid = trunk_response.json()["sid"]
            try:
                async with httpx.AsyncClient(
                    base_url="https://api.twilio.com/2010-04-01",
                    auth=self.auth,
                    timeout=20,
                ) as core_client:
                    credential_list = await core_client.post(
                        f"/Accounts/{self.account_sid}/SIP/CredentialLists.json",
                        data={"FriendlyName": f"Mozaic {connection_id}"},
                    )
                    credential_list.raise_for_status()
                    credential_list_sid = credential_list.json()["sid"]
                    credential = await core_client.post(
                        f"/Accounts/{self.account_sid}/SIP/CredentialLists/{credential_list_sid}/Credentials.json",
                        data={"Username": sip_username, "Password": sip_password},
                    )
                    credential.raise_for_status()
                association = await client.post(
                    f"/Trunks/{trunk_sid}/CredentialLists",
                    data={"CredentialListSid": credential_list_sid},
                )
                association.raise_for_status()
                origination = await client.post(
                    f"/Trunks/{trunk_sid}/OriginationUrls",
                    data={
                        "FriendlyName": "Mozaic Asterisk Gateway",
                        "SipUrl": target_sip_uri,
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
                return TwilioTrunkResource(
                    trunk_sid=trunk_sid,
                    domain=domain,
                    credential_list_sid=credential_list_sid,
                    sip_username=sip_username,
                    sip_password=sip_password,
                )
            except Exception:
                await client.delete(f"/Trunks/{trunk_sid}")
                if credential_list_sid:
                    await self._delete_credential_list(credential_list_sid)
                raise

    async def _delete_credential_list(self, credential_list_sid: str) -> None:
        async with httpx.AsyncClient(
            base_url="https://api.twilio.com/2010-04-01",
            auth=self.auth,
            timeout=20,
        ) as client:
            response = await client.delete(
                f"/Accounts/{self.account_sid}/SIP/CredentialLists/{credential_list_sid}.json"
            )
            if response.status_code not in (204, 404):
                response.raise_for_status()

    async def delete(self, trunk_sid: str, credential_list_sid: str | None = None) -> None:
        async with httpx.AsyncClient(
            base_url=self.base_url, auth=self.auth, timeout=20
        ) as client:
            response = await client.delete(f"/Trunks/{trunk_sid}")
            if response.status_code not in (204, 404):
                response.raise_for_status()
        if credential_list_sid:
            await self._delete_credential_list(credential_list_sid)

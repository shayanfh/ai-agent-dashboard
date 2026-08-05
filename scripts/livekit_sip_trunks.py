"""List or delete LiveKit inbound SIP trunks, for clearing conflicting numbers."""

import argparse
import asyncio
import json
import sys

from livekit import api

from app.core.config import settings


def _client() -> api.LiveKitAPI:
    return api.LiveKitAPI(
        settings.LIVEKIT_URL, settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET
    )


async def _list(number: str | None) -> int:
    client = _client()
    try:
        result = await client.sip.list_sip_inbound_trunk(
            api.ListSIPInboundTrunkRequest()
        )
        for item in result.items:
            if number and number not in item.numbers:
                continue
            try:
                metadata = json.loads(item.metadata or "{}")
            except ValueError:
                metadata = {}
            print(
                f"{item.sip_trunk_id}  numbers={list(item.numbers)}  "
                f"name={item.name!r}  connection_id={metadata.get('connection_id')}"
            )
    finally:
        await client.aclose()
    return 0


async def _rules(trunk_id: str | None) -> int:
    client = _client()
    try:
        result = await client.sip.list_sip_dispatch_rule(
            api.ListSIPDispatchRuleRequest()
        )
        for item in result.items:
            if trunk_id and trunk_id not in item.trunk_ids:
                continue
            print(
                f"{item.sip_dispatch_rule_id}  trunk_ids={list(item.trunk_ids)}  "
                f"name={item.name!r}"
            )
    finally:
        await client.aclose()
    return 0


async def _delete(trunk_id: str) -> int:
    client = _client()
    try:
        await client.sip.delete_sip_trunk(
            api.DeleteSIPTrunkRequest(sip_trunk_id=trunk_id)
        )
        print(f"Deleted {trunk_id}.")
    finally:
        await client.aclose()
    return 0


async def _delete_rule(rule_id: str) -> int:
    client = _client()
    try:
        await client.sip.delete_sip_dispatch_rule(
            api.DeleteSIPDispatchRuleRequest(sip_dispatch_rule_id=rule_id)
        )
        print(f"Deleted {rule_id}.")
    finally:
        await client.aclose()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    list_parser = subparsers.add_parser("list", help="Show inbound trunks")
    list_parser.add_argument("--number", help="Only trunks serving this E.164 number")
    rules_parser = subparsers.add_parser("rules", help="Show dispatch rules")
    rules_parser.add_argument("--trunk-id", help="Only rules bound to this trunk")
    delete_parser = subparsers.add_parser("delete", help="Delete one inbound trunk")
    delete_parser.add_argument("trunk_id", help="Trunk id, e.g. ST_rT2teHJyoaoa")
    delete_rule_parser = subparsers.add_parser(
        "delete-rule", help="Delete one dispatch rule"
    )
    delete_rule_parser.add_argument("rule_id", help="Dispatch rule id, e.g. SDR_...")
    args = parser.parse_args()

    if not all(
        (settings.LIVEKIT_URL, settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
    ):
        print("LiveKit settings are not configured.", file=sys.stderr)
        return 2

    if args.command == "list":
        return asyncio.run(_list(args.number))
    if args.command == "rules":
        return asyncio.run(_rules(args.trunk_id))
    if args.command == "delete-rule":
        return asyncio.run(_delete_rule(args.rule_id))
    return asyncio.run(_delete(args.trunk_id))


if __name__ == "__main__":
    raise SystemExit(main())

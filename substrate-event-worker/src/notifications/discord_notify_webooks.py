from upstash_redis import Redis
import aiohttp
import json
import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from .discord_call_decoder import MaterializedChainState, ProcessCallData

logger = logging.getLogger(__name__)
load_dotenv()


class WebhookNotifier:
    def __init__(self):
        self.redis = Redis(
            url=os.getenv('KV_REST_API_URL'),
            token=os.getenv('KV_REST_API_TOKEN')
        )

    async def discord_governance_alert(self, chain: str, event_data: Dict[str, Any], proposal_index: int, substrate=None) -> None:
        """
        Notify all webhooks registered for a specific chain about an event

        Args:
            chain: Name of the blockchain (e.g., 'polkadot', 'kusama')
            event_data: Event details including module_id, event_id, and attributes
            proposal_index: Block number where event was found
            substrate: Substrate instance
        """

        # Get all webhook IDs for this chain
        chain_key = f"chain:{chain}:webhooks"
        webhook_ids = self.redis.smembers(chain_key)

        if not webhook_ids:
            logger.debug(f"No webhooks found for chain: {chain}")
            return

        chainstate = MaterializedChainState(substrate) if substrate else MaterializedChainState()

        # Get and process call data
        data, preimagehash = chainstate.ref_caller(index=proposal_index, gov1=False, call_data=False)

        # Process call data if available
        embedded_call_data = None
        if data is not False:
            pdc = ProcessCallData(decimals=substrate.token_decimals)
            data = pdc.consolidate_call_args(data)
            embedded_call_data = pdc.find_and_collect_values(data, preimagehash)
            if embedded_call_data:
                embedded_call_data = embedded_call_data.to_dict()

        # Create message with event details
        message = {
            "content": "",
            "embeds": [
                {
                    "author":{
                        "name": f"🔔 {event_data['module_id']}.{event_data['event_id']}",
                    },
                    "color": 3447003,  # Blue color
                    "fields": [
                        {
                            "name": "Module",
                            "value": event_data['module_id'],
                            "inline": True
                        },
                        {
                            "name": "Event",
                            "value": event_data['event_id'],
                            "inline": True
                        }
                    ],
                    "footer": {
                        "text": "ParaG Notification System"
                    },
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            ],
            "components": [
                {
                    "type": 1,
                    "components": [
                        {
                            "type": 2,
                            "style": 5,
                            "label": "Polkassembly",
                            "url": f"https://polkadot.polkassembly.io/referenda/{proposal_index}"
                        },
                        {
                            "type": 2,
                            "style": 5,
                            "label": "Subscan",
                            "url": f"https://polkadot.subscan.io/referenda_v2/{proposal_index}"
                        },
                        {
                            "type": 2,
                            "style": 5,
                            "label": "Polkadot.JS",
                            "url": f"https://polkadot.js.org/apps/?rpc={substrate.url}#/referenda"
                        }
                    ]
                }
            ]
        }

        # Add attributes as fields
        for key, value in event_data['attributes'].items():
            message["embeds"][0]["fields"].append({
                "name": key,
                "value": str(value)[:1024],  # Discord field value limit
                "inline": False
            })

        # Add call data embed if available
        if embedded_call_data:
            message["embeds"].append(embedded_call_data)

        # Send to all registered webhooks
        async with aiohttp.ClientSession() as session:
            for webhook_id in webhook_ids:
                webhook_key = f"webhook:{webhook_id}"
                webhook_data = self.redis.get(webhook_key)

                if not webhook_data:
                    logger.warning(f"No data found for webhook: {webhook_id}")
                    continue

                try:
                    webhook_info = json.loads(webhook_data)
                    webhook_url = webhook_info['webhook_url']
                    notify_role = webhook_info['notify']
                    message['content'] = f"<@&{notify_role}>"

                    async with session.post(webhook_url, json=message) as response:
                        if response.status == 404:
                            logger.warning(f"Webhook deleted, removing: {webhook_id}")
                            # Clean up deleted webhook
                            self.redis.delete(webhook_key)
                            self.redis.srem(chain_key, webhook_id)
                        elif response.status != 204:
                            logger.error(f"Failed to send to webhook {webhook_id}: {response.status}")
                        else:
                            logger.debug(f"Successfully notified webhook {webhook_id} for {chain}")

                except Exception as e:
                    logger.error(f"Error processing webhook {webhook_id}: {e}")

    def cleanup_invalid_webhooks(self):
        """Remove any invalid webhook entries from Redis"""
        all_webhook_keys = self.redis.keys("webhook:*")

        for webhook_key in all_webhook_keys:
            webhook_data = self.redis.get(webhook_key)
            if not webhook_data:
                logger.info(f"Removing invalid webhook key: {webhook_key}")
                self.redis.delete(webhook_key)

                webhook_id = webhook_key.split(":")[-1]
                chain_keys = self.redis.keys("chain:*:webhooks")
                for chain_key in chain_keys:
                    self.redis.srem(chain_key, webhook_id)
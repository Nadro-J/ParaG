from substrateinterface import SubstrateInterface
from typing import Optional, Dict, List, Any
import logging

logger = logging.getLogger(__name__)


def connect_to_network(url: str, timeout: int = 15) -> Optional[SubstrateInterface]:
    """
    Establish connection to a substrate network

    Args:
        url (str): WebSocket URL for the network
        timeout (int): Connection timeout in seconds

    Returns:
        Optional[SubstrateInterface]: Connected substrate interface or None if connection fails
    """
    try:
        substrate = SubstrateInterface(
            url=url,
            ws_options={'timeout': timeout}
        )
        return substrate
    except Exception as e:
        logger.error(f"Failed to connect to {url}: {str(e)}")
        return None


def get_block_hash(substrate: SubstrateInterface, block_number: int) -> Optional[str]:
    """
    Get the block hash for a specific block number

    Args:
        substrate (SubstrateInterface): Connected substrate interface
        block_number (int): Block number to get hash for

    Returns:
        Optional[str]: Block hash or None if not found
    """
    try:
        return substrate.get_block_hash(block_number)
    except Exception as e:
        logger.error(f"Failed to get block hash for block {block_number}: {str(e)}")
        return None


def get_block_events(substrate: SubstrateInterface, block_hash: str) -> Optional[List[Dict[str, Any]]]:
    """
    Get all events for a specific block

    Args:
        substrate (SubstrateInterface): Connected substrate interface
        block_hash (str): Block hash to get events for

    Returns:
        Optional[List[Dict[str, Any]]]: List of decoded events or None if error occurs
    """
    try:
        events = substrate.query(
            module="System",
            storage_function="Events",
            block_hash=block_hash
        )
        return events.decode() if events else None
    except Exception as e:
        logger.error(f"Failed to get events for block {block_hash}: {str(e)}")
        return None


def decode_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Decode and clean up event data

    Args:
        events (List[Dict[str, Any]]): Raw events from substrate

    Returns:
        List[Dict[str, Any]]: Cleaned and formatted events
    """
    decoded_events = []
    for event in events:
        try:
            decoded_event = {
                'module_id': event.get('module_id', ''),
                'event_id': event.get('event_id', ''),
                'attributes': event.get('attributes', {}),
                'phase': event.get('phase', ''),
                'topics': event.get('topics', [])
            }
            decoded_events.append(decoded_event)
        except Exception as e:
            logger.error(f"Failed to decode event: {str(e)}")
            continue

    return decoded_events
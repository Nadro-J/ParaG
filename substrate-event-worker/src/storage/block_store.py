import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class BlockStore:
    def __init__(self, network_name: str):
        self.network_name = network_name
        self.storage_dir = self._ensure_storage_dir()
        self.block_file = self.storage_dir / f"{network_name}.lastblock"

    def _ensure_storage_dir(self) -> Path:
        """Ensure storage directory exists"""
        storage_dir = Path(__file__).parent / "data"
        storage_dir.mkdir(parents=True, exist_ok=True)
        return storage_dir

    def save_last_block(self, block_number: int) -> None:
        """Save the last processed block number"""
        try:
            with open(self.block_file, 'w') as f:
                f.write(str(block_number))
            logger.debug(f"Saved last block {block_number} for {self.network_name}")
        except Exception as e:
            logger.error(f"Failed to save last block: {e}")

    def get_last_block(self) -> int | None:
        """Get the last processed block number"""
        try:
            if self.block_file.exists():
                with open(self.block_file, 'r') as f:
                    return int(f.read().strip())
            return None
        except Exception as e:
            logger.error(f"Failed to read last block: {e}")
            return None

    def clear(self) -> None:
        """Clear stored block number"""
        try:
            if self.block_file.exists():
                self.block_file.unlink()
        except Exception as e:
            logger.error(f"Failed to clear block store: {e}")

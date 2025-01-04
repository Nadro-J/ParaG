#!/usr/bin/env python3
import asyncio
import argparse
import os
import logging
from src.monitoring import BlockRangeGovernanceMonitor
from src.config import load_config, get_network_names

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Monitor blockchain governance events',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument(
        '--watch',
        action='store_true',
        help='Enable interactive display mode'
    )

    parser.add_argument(
        '--network',
        type=str,
        default='polkadot',
        help='Network to monitor',
        choices=get_network_names()
    )

    parser.add_argument(
        '--start-block',
        type=int,
        help='Starting block number (default: latest)'
    )

    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug output'
    )

    parser.add_argument(
        '--config',
        type=str,
        help='Path to config file (default: auto-discover)'
    )

    return parser.parse_args()


async def main() -> None:
    """Main entry point for the blockchain monitor"""
    try:
        args = parse_arguments()

        if args.debug:
            logging.getLogger().setLevel(logging.DEBUG)

        config = load_config(args.config)

        if args.network not in config:
            logger.error(f"Network {args.network} not found in configuration")
            return

        if args.watch:
            os.system('cls' if os.name == 'nt' else 'clear')

        # Initialize monitor
        monitor = BlockRangeGovernanceMonitor(
            network_name=args.network,
            ws_url=config[args.network]['url'],
            display_mode=args.watch,
            debug=args.debug
        )

        # Start monitoring
        logger.info(f"Starting monitoring for {args.network}")
        await monitor.monitor_blocks(args.start_block)

    except KeyboardInterrupt:
        logger.info("\nShutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        if args.debug:
            logger.exception(e)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    
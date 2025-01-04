import asyncio
import json
import os
from .metrics import MetricsTracker
from ..display import DisplayManager
from ..storage import BlockStore
from ..config.settings import DEFAULT_CONFIG, get_monitored_events
from substrateinterface import SubstrateInterface


class BlockRangeGovernanceMonitor:
    def __init__(self, network_name, ws_url, display_mode=False, debug=False):
        self.network_name = network_name
        self.ws_url = ws_url
        self.current_block = None
        self.debug = debug
        self.display_mode = display_mode

        # Get configuration values from settings
        self.batch_size = DEFAULT_CONFIG['batch_size']
        self.connection_timeout = DEFAULT_CONFIG['connection_timeout']
        self.retry_delay = DEFAULT_CONFIG['retry_delay']

        # Initialize components
        self.metrics = MetricsTracker()
        self.display = DisplayManager(
            max_events=DEFAULT_CONFIG['max_events'],
            max_alerts=DEFAULT_CONFIG['max_alerts']
        ) if display_mode else None

        # Get monitored events from settings
        self.governance_modules = get_monitored_events(network_name)

        # Initialize block store
        self.block_store = BlockStore(network_name)

    def process_events(self, block_number, events):
        """Process events from a specific block"""
        event_count = 0
        for event in events:
            event_count += 1
            module_id = event['module_id']
            event_id = event['event_id']

            # Check if this event should be monitored
            should_monitor = False
            for monitored_module, monitored_event in self.governance_modules:
                if monitored_module.lower() == module_id.lower():
                    # If monitored_event is None, monitor all events from this module
                    # Otherwise, check if it matches the specific event
                    if monitored_event is None or monitored_event.lower() == event_id.lower():
                        should_monitor = True
                        break

            if should_monitor:
                if self.display_mode:
                    attributes = event.get('attributes', {})
                    alert_header = f"🔹 Block #{block_number}: {module_id}.{event_id}"
                    formatted_json = json.dumps(attributes, indent=4)
                    indented_json = '\n\t'.join(formatted_json.split('\n'))
                    alert = f"{alert_header}\n\t{indented_json}"
                    self.display.add_alert(alert)
                else:
                    print(f"Found monitored event in block #{block_number}: {module_id}.{event_id}")

        if event_count > 0 and self.display_mode:
            self.display.add_event(f"🔸 Processed {event_count} events in block #{block_number}")
        elif event_count > 0 and self.debug:
            print(f"Processed {event_count} events in block #{block_number}")

        # Update metrics
        metrics_update = self.metrics.update()
        if metrics_update and self.display_mode:
            self.display.set_speed(
                f"⚡ Speed: {metrics_update['current_speed']:.2f} blocks/s " +
                f"(avg: {metrics_update['average_speed']:.2f} blocks/s)"
            )

    async def monitor_blocks(self, start_block=None):
        """
        Monitor blocks starting from a specific block
        If no start_block is specified, starts from the current finalized block
        """
        base_delay = self.retry_delay  # Initial delay
        max_delay = 300                # Maximum delay of 5 minutes
        current_delay = base_delay
        connection_attempts = 0

        while True:
            try:
                with SubstrateInterface(
                        url=self.ws_url,
                        ws_options={'timeout': self.connection_timeout}
                ) as substrate:
                    if start_block is None:
                        last_block = self.block_store.get_last_block()
                        if last_block is not None:
                            start_block = last_block
                        else:
                            # If no stored block, get current finalized block
                            finalized_hash = substrate.get_chain_finalised_head()
                            start_block = substrate.get_block_number(finalized_hash)

                    self.current_block = start_block
                    self.metrics.start()

                    current_delay = base_delay
                    connection_attempts = 0

                    if self.display_mode:
                        print(f"Starting to process blocks from #{start_block}")
                        monitored_list = [
                            f"{module}.{event if event else '*'}"
                            for module, event in self.governance_modules
                        ]
                        print(f"Monitoring for events: {', '.join(monitored_list)}")

                        await asyncio.sleep(3)
                        os.system('cls' if os.name == 'nt' else 'clear')

                    while True:
                        try:
                            finalized_hash = substrate.get_chain_finalised_head()
                            finalized_block = substrate.get_block_number(finalized_hash)

                            if finalized_block >= self.current_block:
                                batch_end = min(self.current_block + self.batch_size, finalized_block + 1)

                                if self.display_mode:
                                    self.display.set_batch(
                                        f"🤖 Processing blocks #{self.current_block} to #{batch_end - 1}"
                                    )
                                elif self.debug:
                                    print(f"Processing blocks #{self.current_block} to #{batch_end - 1}")

                                for block_number in range(self.current_block, batch_end):
                                    try:
                                        block_hash = substrate.get_block_hash(block_number)
                                        events = substrate.query(
                                            module="System",
                                            storage_function="Events",
                                            block_hash=block_hash
                                        )

                                        if events:
                                            self.process_events(block_number, events.decode())

                                    except Exception as e:
                                        print(f"Error processing block {block_number}: {e}")
                                        continue

                                self.current_block = batch_end
                                # Store the last processed block
                                self.block_store.save_last_block(self.current_block - 1)

                        except Exception as e:
                            print(f"Error in block processing loop: {e}")
                            await asyncio.sleep(base_delay)
                            break

            except Exception as e:
                connection_attempts += 1
                print(f"Connection error (attempt {connection_attempts}): {e}")
                start_block = self.current_block  # Preserve current block for reconnection

                # Calculate exponential backoff with maximum limit
                current_delay = min(base_delay * (2 ** (connection_attempts - 1)), max_delay)
                print(f"Retrying connection in {current_delay} seconds...")

                await asyncio.sleep(current_delay)
                continue
            except KeyboardInterrupt:
                if self.display_mode:
                    self.display.cleanup()
                break

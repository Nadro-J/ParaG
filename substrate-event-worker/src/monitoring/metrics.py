import time


class MetricsTracker:
    def __init__(self):
        self.start_time = None
        self.blocks_processed = 0
        self.last_metrics_update = time.time()
        self.last_blocks_count = 0

    def start(self):
        """Start tracking metrics"""
        self.start_time = time.time()
        self.last_metrics_update = self.start_time

    def update(self, new_blocks=1):
        """Update block count and calculate metrics"""
        self.blocks_processed += new_blocks
        current_time = time.time()
        time_diff = current_time - self.last_metrics_update

        # Update metrics every 5 seconds
        if time_diff >= 5:
            blocks_since_last = self.blocks_processed - self.last_blocks_count
            blocks_per_second = blocks_since_last / time_diff
            total_blocks_per_second = self.blocks_processed / (current_time - self.start_time)

            # Reset counters
            self.last_metrics_update = current_time
            self.last_blocks_count = self.blocks_processed

            return {
                'current_speed': blocks_per_second,
                'average_speed': total_blocks_per_second,
                'total_blocks': self.blocks_processed
            }

        return None

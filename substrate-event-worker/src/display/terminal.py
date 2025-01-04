import shutil
import time
from collections import deque
from .formatters import TextFormatter


class DisplayManager:
    def __init__(self, max_events=10, max_alerts=10):
        # Initialize timing attributes
        self.last_update = time.time()
        self.update_interval = 0.5  # Increased to reduce updates

        # Initialize display properties
        self.max_events = max_events
        self.max_alerts = max_alerts
        self.events = deque(maxlen=max_events)
        self.alerts = deque(maxlen=max_alerts)
        self.batch_info = ""
        self.speed_info = ""
        self.display_height = max(max_events + 2, max_alerts + 1)
        self.term_width = shutil.get_terminal_size().columns
        self.left_width = min(80, self.term_width // 2)
        self.alert_width = self.term_width - self.left_width - 3

        # Initialize the formatter
        self.formatter = TextFormatter()

        # Buffer for alerts section
        self.alerts_buffer = []

        # Initialize display area
        print(self.formatter.alt_buffer + self.formatter.clear_screen, end='', flush=True)
        print('\n' * (self.display_height + 5))

    def _format_alerts_section(self):
        """Pre-format alerts section to buffer"""
        buffer = []
        # Header
        buffer.append("│ 🚨 Recent Alerts")

        # Format all alerts
        current_line = 1
        for alert in reversed(self.alerts):
            if current_line >= self.display_height:
                break

            formatted_lines = self.formatter.format_alert(alert, self.alert_width - 2)
            for line in formatted_lines:
                if current_line >= self.display_height:
                    break
                truncated_line = line[:self.alert_width - 2]
                buffer.append(f"│ {truncated_line}")
                current_line += 1

        # Fill remaining lines with empty borders
        while current_line < self.display_height:
            buffer.append(f"│{' ' * self.alert_width}")
            current_line += 1

        return buffer

    def _update_display(self):
        """Update the entire display"""
        self.check_terminal_size()
        self.move_to_top()

        # Update left side
        print(self.formatter.clear_line + self.formatter.cursor_start + self.batch_info[:self.left_width], flush=True)

        for i in range(self.max_events):
            event = self.events[i] if i < len(self.events) else ""
            print(self.formatter.clear_line + self.formatter.cursor_start + event[:self.left_width], flush=True)

        print(self.formatter.clear_line + self.formatter.cursor_start + self.speed_info[:self.left_width], flush=True)

        # Update right side from buffer
        self.move_to_top()
        for line_num, line in enumerate(self.alerts_buffer):
            print(f"{self.formatter.position_cursor(line_num + 1, self.left_width + 1)}{line}", end='', flush=True)

    def update(self):
        """Check timing and update if needed"""
        current_time = time.time()
        if (current_time - self.last_update) >= self.update_interval:
            self.last_update = current_time
            self.alerts_buffer = self._format_alerts_section()
            self._update_display()

    def check_terminal_size(self):
        """Update dimensions if terminal size changes"""
        new_width = shutil.get_terminal_size().columns
        if new_width != self.term_width:
            self.term_width = new_width
            self.left_width = min(80, self.term_width // 2)
            self.alert_width = self.term_width - self.left_width - 3
            self.alerts_buffer = self._format_alerts_section()
            self._update_display()

    def move_to_top(self):
        """Move cursor to top of display area"""
        print(self.formatter.cursor_up * (self.display_height + 5), end='', flush=True)

    def add_event(self, event):
        """Add new event and update display"""
        self.events.append(event)
        self.update()

    def add_alert(self, alert):
        """Add new alert and update display"""
        self.alerts.append(alert)
        self.alerts_buffer = self._format_alerts_section()
        self.update()

    def set_batch(self, batch):
        """Update batch information"""
        self.batch_info = batch
        self.update()

    def set_speed(self, speed):
        """Update speed information"""
        self.speed_info = speed
        self.update()

    def cleanup(self):
        """Restore terminal state"""
        print(self.formatter.show_cursor + self.formatter.main_buffer, end='', flush=True)
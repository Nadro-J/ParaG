class TextFormatter:
    def __init__(self):
        # ANSI escape codes
        self.cursor_up = '\033[A'
        self.cursor_down = '\033[B'
        self.clear_line = '\033[2K'
        self.cursor_start = '\r'
        self.hide_cursor = '\033[?25l'
        self.show_cursor = '\033[?25h'
        self.save_cursor = '\033[s'
        self.restore_cursor = '\033[u'
        self.clear_screen = '\033[2J'
        self.alt_buffer = '\033[?1049h'  # Switch to alternate buffer
        self.main_buffer = '\033[?1049l'  # Return to main buffer
        self.home = '\033[H'             # Move to home position

        # Color codes
        self.magenta = '\033[95m'  # Bright magenta for keys
        self.blue = '\033[94m'
        self.cyan = '\033[96m'
        self.reset = '\033[0m'

    def position_cursor(self, row, column):
        """Position cursor at specific row and column"""
        return f"\033[{row};{column}H"

    def wrap_text(self, text, width):
        """Wrap text to fit within specified width"""
        lines = []
        current_line = []
        current_length = 0

        for word in text.split():
            word_length = len(word)
            if current_length + word_length + 1 <= width:
                current_line.append(word)
                current_length += word_length + 1
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
                current_length = word_length

        if current_line:
            lines.append(' '.join(current_line))

        return lines

    def format_alert(self, alert, width):
        """Format alert to fit within alert section width"""
        lines = []
        parts = alert.split('\n', 1)

        # Add header
        header = parts[0]
        header_lines = self.wrap_text(header, width)
        lines.extend(header_lines)

        # Add content with indentation and color if it exists
        if len(parts) > 1:
            content_lines = parts[1].split('\n')
            # Color the lines, highlighting keys in quotes
            for line in content_lines:
                # Check if line is empty or just whitespace
                if not line.strip():
                    continue

                # Calculate available width considering indentation
                indent_level = len(line) - len(line.lstrip())
                available_width = width - indent_level

                # line contains key-value pair
                if '"' in line and ':' in line:
                    key_part, value_part = line.split(':', 1)
                    # Color the key (including quotes) in magenta, rest in cyan
                    if len(key_part) + len(value_part) > available_width:
                        # If line is too long, wrap the value part
                        wrapped_value = self.wrap_text(value_part, available_width - len(key_part))
                        colored_line = f"{' ' * indent_level}{self.magenta}{key_part}{self.reset}:{self.cyan}{wrapped_value[0]}{self.reset}"
                        lines.append(colored_line)
                        # Add wrapped value parts with proper indentation
                        for value_line in wrapped_value[1:]:
                            lines.append(f"{' ' * (indent_level + len(key_part) + 2)}{self.cyan}{value_line}{self.reset}")
                    else:
                        colored_line = f"{' ' * indent_level}{self.magenta}{key_part}{self.reset}:{self.cyan}{value_part}{self.reset}"
                        lines.append(colored_line)
                else:
                    # Lines without key:value pairs (brackets, braces, etc)
                    lines.append(f"{' ' * indent_level}{self.cyan}{line.strip()}{self.reset}")

        return lines

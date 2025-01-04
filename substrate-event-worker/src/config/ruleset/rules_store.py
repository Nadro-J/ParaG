import os
import yaml
import logging
from pathlib import Path
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)


class RulesStore:
    def __init__(self, network_name: str):
        self.network_name = network_name
        self.rules_dir = self._ensure_rules_dir()
        self.rules_file = self.rules_dir / f"{network_name}.rules"

    def _ensure_rules_dir(self) -> Path:
        """Ensure rules directory exists"""
        rules_dir = Path(__file__).parent / "data"
        rules_dir.mkdir(parents=True, exist_ok=True)
        return rules_dir

    def load_rules(self) -> List[Tuple[str, Optional[str]]]:
        """Load monitoring rules for the network"""
        try:
            if not self.rules_file.exists():
                logger.warning(f"No rules file found for {self.network_name}, using defaults")
                return [
                    ('democracy', None),
                    ('referenda', None)
                ]

            with open(self.rules_file, 'r') as f:
                rules_data = yaml.safe_load(f)

            if not rules_data or not isinstance(rules_data, list):
                logger.error("Invalid rules format")
                return []

            parsed_rules = []
            for rule in rules_data:
                if isinstance(rule, str):
                    # If rule is just a module name, monitor all events
                    parsed_rules.append((rule, None))
                elif isinstance(rule, dict) and len(rule) == 1:
                    # If rule is a dict with module and specific event
                    module = list(rule.keys())[0]
                    event = rule[module]
                    parsed_rules.append((module, event))
                else:
                    logger.warning(f"Skipping invalid rule format: {rule}")

            return parsed_rules

        except Exception as e:
            logger.error(f"Failed to load rules: {e}")
            return []

    def save_rules(self, rules: List[Tuple[str, Optional[str]]]) -> None:
        """Save monitoring rules for the network"""
        try:
            # Convert rules to YAML-friendly format
            rules_data = []
            for module, event in rules:
                if event is None:
                    rules_data.append(module)
                else:
                    rules_data.append({module: event})

            with open(self.rules_file, 'w') as f:
                yaml.safe_dump(rules_data, f, default_flow_style=False)

            logger.debug(f"Saved rules for {self.network_name}")
        except Exception as e:
            logger.error(f"Failed to save rules: {e}")

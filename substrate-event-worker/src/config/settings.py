import yaml
import os
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path
from .ruleset import RulesStore

# Default configuration values
DEFAULT_CONFIG = {
    'batch_size': 10,
    'connection_timeout': 15,
    'retry_delay': 5,
    'max_events': 50,
    'max_alerts': 100
}


class ConfigurationError(Exception):
    """Custom exception for configuration errors"""
    pass


def load_config(config_path: str = None) -> Dict[str, Any]:
    """
    Load configuration from YAML file

    Args:
        config_path (str, optional): Path to config file. Defaults to 'networks.yaml'

    Returns:
        Dict[str, Any]: Configuration dictionary

    Raises:
        ConfigurationError: If config file is invalid or missing
    """
    if config_path is None:
        config_path = find_config_file()

    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            validate_config(config)
            return config
    except yaml.YAMLError as e:
        raise ConfigurationError(f"Error parsing config file: {str(e)}")
    except FileNotFoundError:
        raise ConfigurationError(f"Config file not found: {config_path}")
    except Exception as e:
        raise ConfigurationError(f"Error loading config: {str(e)}")


def find_config_file() -> str:
    """
    Find the configuration file in standard locations

    Returns:
        str: Path to config file

    Raises:
        ConfigurationError: If no config file is found
    """
    # Get the ParaG directory (one level up from substrate-event-worker)
    current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    search_paths = [
        os.path.join(current_dir, 'networks.yaml'),  # ParaG/networks.yaml
        'networks.yaml',
        'config/networks.yaml',
        os.path.expanduser('~/.config/blockchain-monitor/networks.yaml'),
        '/etc/blockchain-monitor/networks.yaml'
    ]

    for path in search_paths:
        if os.path.isfile(path):
            return path

    raise ConfigurationError("No configuration file found")


def validate_config(config: Dict[str, Any]) -> None:
    """
    Validate configuration structure

    Args:
        config (Dict[str, Any]): Configuration to validate

    Raises:
        ConfigurationError: If configuration is invalid
    """
    if not isinstance(config, dict):
        raise ConfigurationError("Configuration must be a dictionary")

    for network, settings in config.items():
        if not isinstance(settings, dict):
            raise ConfigurationError(f"Network '{network}' settings must be a dictionary")

        if 'url' not in settings:
            raise ConfigurationError(f"Network '{network}' is missing 'url' setting")

        if not isinstance(settings['url'], str):
            raise ConfigurationError(f"Network '{network}' URL must be a string")


def get_monitored_events(network_name: str) -> List[Tuple[str, Optional[str]]]:
    """Get governance modules to monitor for a specific network"""
    rules_store = RulesStore(network_name)
    return rules_store.load_rules()


def get_network_urls() -> Dict[str, str]:
    """
    Get dictionary of network names and their WebSocket URLs

    Returns:
        Dict[str, str]: Dictionary of network names and URLs
    """
    config = load_config()
    return {name: settings['url'] for name, settings in config.items()}


def get_network_names() -> List[str]:
    """
    Get list of configured network names

    Returns:
        List[str]: List of network names
    """
    config = load_config()
    return list(config.keys())

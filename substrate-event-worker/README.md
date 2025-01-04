# Substrate Event Worker

A command-line tool for monitoring blockchain events across substrate-based networks. This tool provides real-time monitoring of specified blockchain events with an interactive terminal display.

## Features

- Real-time monitoring of blockchain events
- Interactive terminal display mode
- Persistent block tracking for resume capability
- Configurable event monitoring rules per network
- Support for multiple substrate-based networks
- Automatic reconnection with exponential backoff

## Installation

1. Install dependencies
```bash
pip3 install -r requirements.txt
```

## Using venv (Python's built-in virtual environment)
```bash
# Navigate to your project directory
cd substrate-event-worker

# Create a virtual environment
python -m venv venv

# Activate the virtual environment
# On Windows:
venv\Scripts\activate
# On Unix or MacOS:
source venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

## Using Conda
```bash
# Create a new conda environment
conda create -n substrate-worker python=3.10

# Activate the environment
conda activate substrate-worker

# Install requirements
pip install -r requirements.txt
```

## Usage
Basic usage:  
`python3 main.py --network polkadot --watch`  
`python3 main.py --network hydration --watch --start-block=6695830`

Available command-line options:
- `--network`: Network to monitor (default: polkadot)
- `--watch`: Enable interactive display mode
- `--start-block`: Start monitoring from a specific block number
- `--debug`: Enable debug output
- `--config`: Path to config file (default: auto-discover)

## Network Configuration
Networks are configured in networks.yaml. Example configuration:
```yaml
polkadot:
  url: "wss://rpc.polkadot.io"
kusama:
  url: "wss://kusama-rpc.polkadot.io"
```

## Event Rules
Each network can have its own rules for which events to monitor. Rules are stored in `src/config/ruleset/data/{network}.rules`.  
Example hydration.rules:
```yaml
# Monitor all events from these modules
- Referenda

# Monitor specific events from modules
- Referenda: Submitted
- Referenda: DecisionDepositPlaced
```

## Block Persistence
The tool maintains the last processed block number for each network in `src/storage/data/{network}.lastblock`. This allows the tool to resume monitoring from the last processed block after a restart, unless a specific start block is provided via command line.

## Interactive Display
When running with the `--watch` flag, the tool provides an interactive terminal display with two main sections:  
Left Panel:
- Current processing status
- Recent event logs
- Processing speed

Right Panel:
- Recent governance events with detailed information
- Color-coded event attributes
- Auto-updating display

Error Handling:
- Automatic reconnection on network issues
- Exponential backoff for connection retries
- Error logging and debug output
- Graceful shutdown on keyboard interrupt
# vrc-sleep

[English](README.md) | [日本語](README.ja.md)

A simple CLI tool to post a sleep announcement with a VRChat instance URL to Discord via Webhook, and automatically update the message to "Closed" upon waking up.

Runs using only the Python standard library with zero external dependencies.

## Requirements

- Python 3.10+

## Installation

Clone the repository and run the script directly, or install via pip:

```bash
git clone https://github.com/sorami-wanwan/vrc_position_nofy.git
cd vrc_position_nofy

# Optional: Install as a global CLI command
pip install .
```

## Setup

Configure your Discord Webhook URL and display username:

```bash
python3 vrc_sleep.py config --webhook "https://discord.com/api/webhooks/..." --username "SORAMI"
```

You can also configure via environment variables:
- `DISCORD_WEBHOOK_URL`
- `VRC_SLEEP_USERNAME`

View current configuration:
```bash
python3 vrc_sleep.py config
```

## Usage

### 1. Going to sleep
Run `start` with your VRChat instance URL:

```bash
python3 vrc_sleep.py start "https://vrchat.com/home/launch?worldId=..."
```

Shortened URLs (`https://vrch.at/...`) are also supported.

### 2. Waking up
Run `close` to update the previous Discord message to "Closed":

```bash
python3 vrc_sleep.py close
```

### 3. Check status
Check active session status and configuration:

```bash
python3 vrc_sleep.py status
```

## Commands

- `start <URL>`: Post sleep announcement (`-f` to force overwrite active session)
- `close`: Update posted message to closed status and end session
- `status`: Show current session and configuration
- `config`: View or update settings (`--webhook`, `--username`, `--show-secret`)

Use `--config /path/to/config.json` if you want to specify a custom configuration file location.

## License

MIT License

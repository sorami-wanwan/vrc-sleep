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
Run `start` with your VRChat instance URL. You can also specify a world name (`-w / --world`) and an image URL (`-i / --image`) to enrich the Discord Embed notification:

```bash
# Basic usage
python3 vrc_sleep.py start "https://vrchat.com/home/launch?worldId=..."

# With World name and Thumbnail image
python3 vrc_sleep.py start "https://vrchat.com/home/launch?worldId=..." \
  --world "Cozy Bedroom" \
  --image "https://example.com/sleep_thumbnail.png"
```

Shortened URLs (`https://vrch.at/...`) are also supported.

### 2. Waking up
Run `close` to update the previous Discord message to "Closed":

```bash
python3 vrc_sleep.py close

# Or manually specify the Message ID if local state was lost
python3 vrc_sleep.py close --message-id "123456789012345678"
```

### 3. Check status
Check active session status and configuration:

```bash
python3 vrc_sleep.py status
```

## Commands

- `start <URL>`: Post sleep announcement (`-w/--world` world name, `-i/--image` image URL, `-f` force overwrite active session)
- `close`: Update posted message to closed status and end session (`--message-id` for manual recovery)
- `status`: Show current session and configuration
- `config`: View or update settings (`--webhook`, `--username`, `--show-secret`)

Use `--config /path/to/config.json` if you want to specify a custom configuration file location.

## Development & Testing

Run unit tests using Python's built-in `unittest` module:

```bash
python3 -m unittest discover -s tests -v
```

## License

MIT License

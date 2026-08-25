# vrc-sleep

[English](README.md) | [日本語](README.ja.md)

A tool that notifies your instance URL to Discord when you sleep in VRChat, and updates the message to "Closed" when you wake up.
It provides both a CLI and a modern GUI (Desktop Application).

It runs solely on Python's standard libraries, requiring no external package installation.

## Requirements

- Python 3.10 or higher

## Installation

You can run it directly by cloning the repository, or install it via pip.

```bash
git clone https://github.com/sorami-wanwan/vrc_position_nofy.git
cd vrc_position_nofy

# To install via pip (makes the 'vrc-sleep' command available globally)
pip install .
```

## Usage

Initial setup is required for the Discord Webhook URL. If using the GUI version (`vrc_sleep_gui.py`), you can configure this by clicking the **Settings** button in the top right corner after launching.

For the CLI, run the `config` command as shown below, or use environment variables (`DISCORD_WEBHOOK_URL`, `VRC_SLEEP_USERNAME`).

```bash
python3 vrc_sleep.py config --webhook "https://discord.com/api/webhooks/..." --username "SORAMI"
```

### 1. Going to Sleep

**GUI:**
Launch `vrc_sleep_gui.py`, enter your "Instance URL", and click the **Start Sleep** button. You can optionally specify a World Name and Image URL.

**CLI:**
Run the `start` command with your instance URL. You can use (`-w`) for the world name and (`-i`) for an image URL to make the notification richer.
```bash
python3 vrc_sleep.py start "https://vrchat.com/home/launch?worldId=..." -w "Sleepy Bedroom" -i "https://example.com/sleep_thumbnail.png"
```
*Short URLs (`https://vrch.at/...`) are also supported.

### 2. Waking Up

**GUI:**
Click the **Close Session** button when you wake up to update the notification and end the session.

**CLI:**
Run `close` to automatically edit the previously posted Discord message to "Closed".
```bash
python3 vrc_sleep.py close

# If local state is lost, you can close it manually by specifying the message ID
python3 vrc_sleep.py close --message-id "123456789012345678"
```

### 3. Checking Status & Misc

- You can check if there's an active session using `python3 vrc_sleep.py status` (In the GUI, this is constantly displayed on the status bar).
- If you want to use a config file in a different location, specify the `--config /path/to/config.json` option.

## Development & Testing

Unit tests can be run using Python's standard `unittest` (no external packages required).

```bash
python3 -m unittest discover -s tests -v
```

## License

MIT License

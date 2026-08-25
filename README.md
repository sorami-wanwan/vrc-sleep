# vrc-sleep

[English](README.md) | [日本語](README.ja.md)

A tool that notifies your instance URL to Discord when you sleep in VRChat, and updates the message to "Closed" when you wake up.
It provides both a CLI and a modern GUI (Desktop Application).

<p align="center">
  <img src="assets/gui_screenshot.png" alt="VRC Sleep Notifier GUI" width="480">
</p>

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

## Important Notice for Windows Users (Installation & Execution)

When using the executable version of this tool on Windows, please strictly observe the following:

1. **Always "Extract All" before running the ZIP file**
   If you double-click the downloaded ZIP file and run the `.exe` directly from within it, the application will run in a temporary Windows folder (TEMP). This causes all your saved settings to be lost upon closing. Right-click the ZIP file and select **"Extract All..."** before running the executable.
2. **If you see a "Windows protected your PC" (SmartScreen) warning**
   Windows SmartScreen may display a warning prompt. In this case, click **"More info"**, and then click the **"Run anyway"** button that appears.
3. **Antivirus (e.g., Windows Defender) Interference**
   If settings cannot be saved or are reset, please add the folder containing this tool to the exclusion list of your antivirus software (e.g., Windows Defender).
4. **Secure Installation Location**
   For security reasons, do not extract or run this tool in shared folders or Temp directories. Please extract and run it in a trusted, secure directory such as My Documents.

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

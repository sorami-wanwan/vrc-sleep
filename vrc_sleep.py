#!/usr/bin/env python3
"""
VRChat Sleep Notification CLI for Discord Webhook.
Allows posting sleep announcements with VRChat instance URLs and updating them to 'Closed' when waking up.
"""

import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from datetime import datetime, timezone
from pathlib import Path

# Defaults
DEFAULT_USERNAME = "VRChat User"
MAX_USERNAME_LENGTH = 50
MAX_URL_LENGTH = 2048

DISCORD_WEBHOOK_PATTERN = re.compile(
    r"^https://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_-]+/?(?:\?.*)?$"
)
VRCHAT_URL_PATTERN = re.compile(
    r"^https://(?:(?:www\.)?vrchat\.com/home/(?:launch\?|world/|avatar/)|vrch\.at/).+$"
)

# ANSI Colors (disabled if NO_COLOR is set or stdout is not a tty)
def _supports_color() -> bool:
    if os.getenv("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    return True

_COLOR_ENABLED = _supports_color()
COLOR_RESET = "\033[0m" if _COLOR_ENABLED else ""
COLOR_BOLD = "\033[1m" if _COLOR_ENABLED else ""
COLOR_GREEN = "\033[32m" if _COLOR_ENABLED else ""
COLOR_YELLOW = "\033[33m" if _COLOR_ENABLED else ""
COLOR_BLUE = "\033[34m" if _COLOR_ENABLED else ""
COLOR_CYAN = "\033[36m" if _COLOR_ENABLED else ""
COLOR_RED = "\033[31m" if _COLOR_ENABLED else ""


def get_default_config_dir() -> Path:
    """Get the standard user configuration directory for vrc-sleep."""
    if sys.platform == "win32":
        app_data = os.getenv("APPDATA")
        if app_data:
            return Path(app_data) / "vrc_sleep"
    xdg_config = os.getenv("XDG_CONFIG_HOME")
    if xdg_config:
        return Path(xdg_config) / "vrc_sleep"
    return Path.home() / ".config" / "vrc_sleep"


def is_in_source_repo() -> bool:
    """Check if script is being run directly inside its git/source repository."""
    parent_dir = Path(__file__).resolve().parent
    return (parent_dir / ".git").exists() or (parent_dir / "config.example.json").exists()


def resolve_config_path(custom_path: str | None = None) -> Path:
    """
    Resolve configuration file path:
    1. Explicit custom path (--config)
    2. Local file in source repository root if running from source (config.json)
    3. User home config directory (~/.config/vrc_sleep/config.json or %APPDATA%/vrc_sleep/config.json)
    """
    if custom_path:
        return Path(custom_path).resolve()

    # 1. Check source repository directory (if developing/running from source)
    if is_in_source_repo():
        repo_config = Path(__file__).resolve().parent / "config.json"
        if repo_config.exists():
            return repo_config

    # 2. Check user config dir
    user_config = get_default_config_dir() / "config.json"
    if user_config.exists():
        return user_config

    # 3. Default target for new creation:
    # If running from source repository, prefer repo root; otherwise user config dir.
    if is_in_source_repo() and os.access(Path(__file__).resolve().parent, os.W_OK):
        return Path(__file__).resolve().parent / "config.json"
    return user_config


def resolve_state_path(custom_config_path: str | None = None) -> Path:
    """
    Resolve session state file path matching the configuration location.
    """
    config_path = resolve_config_path(custom_config_path)
    return config_path.parent / ".state.json"


def load_config(config_path: Path) -> dict:
    """Load configuration from config.json or environment variables."""
    config = {}
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    config = loaded
                else:
                    print(f"{COLOR_YELLOW}[!] Warning: Config file is not a JSON object ({config_path}). Using defaults.{COLOR_RESET}")
        except Exception as e:
            print(f"{COLOR_YELLOW}[!] Warning: Failed to parse config file ({config_path}): {e}{COLOR_RESET}")

    # Environment variables override config file
    env_webhook = os.getenv("DISCORD_WEBHOOK_URL")
    if env_webhook:
        config["webhook_url"] = env_webhook.strip()

    env_username = os.getenv("VRC_SLEEP_USERNAME")
    if env_username:
        config["username"] = env_username.strip()

    return config


def atomic_save_json(data: dict, file_path: Path, secure_mode: bool = False) -> None:
    """
    Atomically write JSON to file to prevent corruption on sudden termination.
    If secure_mode is True, sets 0o600 permissions (owner read/write only) on POSIX.
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = file_path.parent / f".{file_path.name}.{os.getpid()}.tmp"
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        if secure_mode and sys.platform != "win32":
            try:
                os.chmod(temp_file, 0o600)
            except OSError:
                pass
        temp_file.replace(file_path)
    except Exception:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except OSError:
                pass
        raise


def save_config(config: dict, config_path: Path) -> None:
    """Save configuration to config.json with secure file permissions."""
    atomic_save_json(config, config_path, secure_mode=True)


def load_state(state_path: Path) -> dict | None:
    """Load active session state from .state.json."""
    if state_path.exists():
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                return loaded if isinstance(loaded, dict) else None
        except Exception:
            return None
    return None


def save_state(state: dict, state_path: Path) -> None:
    """Save session state to .state.json atomically."""
    atomic_save_json(state, state_path, secure_mode=False)


def clear_state(state_path: Path) -> None:
    """Remove active session state file safely."""
    if state_path.exists():
        try:
            state_path.unlink()
        except OSError:
            pass


def append_query_param(url: str, key: str, value: str) -> str:
    """Safely add or update a query parameter in a URL."""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    qs[key] = [value]
    new_query = urlencode(qs, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))


def mask_url(url: str | None) -> str:
    """Mask sensitive token in Discord Webhook URL for safe console output."""
    if not url:
        return "Not configured"
    match = re.match(r"^(https://.+/api/webhooks/\d+/)(.+)$", url)
    if match:
        base, token = match.group(1), match.group(2)
        if len(token) > 8:
            masked_token = token[:4] + "..." + token[-4:]
        else:
            masked_token = "..."
        return f"{base}{masked_token}"
    return url[:30] + "..." if len(url) > 35 else url


def validate_webhook_url(url: str) -> bool:
    """Validate Discord Webhook URL format and domain strictly."""
    url = url.strip()
    if len(url) > MAX_URL_LENGTH:
        return False
    if not DISCORD_WEBHOOK_PATTERN.match(url):
        return False
    try:
        parsed = urlparse(url)
        if parsed.scheme != "https":
            return False
        hostname = (parsed.hostname or "").lower()
        if hostname not in ("discord.com", "discordapp.com", "canary.discord.com", "ptb.discord.com"):
            return False
        return True
    except Exception:
        return False


def validate_vrchat_url(url: str) -> bool:
    """
    Validate VRChat instance/world URL format strictly:
    - Length check
    - HTTPS scheme check
    - Whitelisted hostnames (vrchat.com, www.vrchat.com, vrch.at)
    - Forbidden characters check (newlines, spaces, quotes, brackets, control characters)
    """
    url = url.strip()
    if len(url) > MAX_URL_LENGTH:
        return False

    # Prevent Markdown injection, command injection, and header injection
    forbidden_chars = ("\n", "\r", "\t", "\0", "[", "]", "(", ")", " ", "`", "<", ">", '"', "'", "\\")
    if any(c in url for c in forbidden_chars):
        return False

    if not VRCHAT_URL_PATTERN.match(url):
        return False

    try:
        parsed = urlparse(url)
        if parsed.scheme != "https":
            return False
        hostname = (parsed.hostname or "").lower()
        if hostname in ("vrchat.com", "www.vrchat.com"):
            path = parsed.path
            return path.startswith("/home/launch") or path.startswith("/home/world") or path.startswith("/home/avatar")
        elif hostname == "vrch.at":
            return len(parsed.path) > 1
        return False
    except Exception:
        return False


def get_username(config: dict) -> str:
    """Get configured username or fallback to default."""
    return config.get("username", "").strip() or DEFAULT_USERNAME


def get_webhook_url(config: dict) -> str:
    """Retrieve webhook URL or prompt user to configure it."""
    webhook_url = config.get("webhook_url", "").strip()
    if not webhook_url:
        print(f"{COLOR_RED}[!] Error: Discord Webhook URL is not configured.{COLOR_RESET}")
        print(f"Please set your Webhook URL using:")
        print(f"  {COLOR_CYAN}python3 vrc_sleep.py config --webhook \"<YOUR_WEBHOOK_URL>\"{COLOR_RESET}")
        print(f"or set the {COLOR_YELLOW}DISCORD_WEBHOOK_URL{COLOR_RESET} environment variable.")
        sys.exit(1)
    return webhook_url


def send_http_request(url: str, method: str, payload: dict, timeout: float = 15.0) -> tuple[int, dict]:
    """
    Send an HTTP request with JSON payload.
    Returns (status_code, response_json).
    """
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "VRChat-Sleep-Notifier-CLI/1.0"
        },
        method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            resp_json = {}
            if body:
                try:
                    resp_json = json.loads(body)
                except Exception:
                    pass
            return resp.status, resp_json
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        err_json = {}
        try:
            err_json = json.loads(error_body)
        except Exception:
            pass
        return e.code, err_json
    except TimeoutError:
        print(f"{COLOR_RED}[!] Network Error: Request timed out after {timeout} seconds.{COLOR_RESET}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"{COLOR_RED}[!] Network Error: {e.reason}{COLOR_RESET}")
        sys.exit(1)


def build_sleep_embed(username: str, instance_url: str, timestamp_iso: str) -> dict:
    """Construct the Discord embed for sleep notification."""
    return {
        "title": f"🌙 {username} is sleeping now...",
        "description": "I have gone to sleep in VRChat. Feel free to join if you like!",
        "color": 0x3F51B5,  # Indigo / Night Blue
        "fields": [
            {
                "name": "Status",
                "value": "🟢 **Instance Open / Sleeping**",
                "inline": True
            },
            {
                "name": "VRChat Instance",
                "value": f"[🔗 Click here to Join Instance]({instance_url})",
                "inline": False
            }
        ],
        "footer": {
            "text": "VRChat Sleep Notification"
        },
        "timestamp": timestamp_iso
    }


def build_closed_embed(username: str, instance_url: str, closed_iso: str) -> dict:
    """Construct the Discord embed for instance closed notification."""
    instance_val = f"~~[Instance Link]({instance_url})~~ *(Closed)*" if instance_url else "*(Instance URL not recorded)*"
    return {
        "title": f"☀️ {username} has woken up / Instance Closed",
        "description": "The sleep instance is now closed. Thank you for visiting!",
        "color": 0x95A5A6,  # Slate Gray
        "fields": [
            {
                "name": "Status",
                "value": "🔴 **Instance Closed**",
                "inline": True
            },
            {
                "name": "VRChat Instance",
                "value": instance_val,
                "inline": False
            }
        ],
        "footer": {
            "text": "VRChat Sleep Notification • Instance Closed"
        },
        "timestamp": closed_iso
    }


def cmd_start(args):
    """Handle `start` command: Post sleep announcement to Discord."""
    config_path = resolve_config_path(args.config)
    state_path = resolve_state_path(args.config)
    config = load_config(config_path)

    webhook_url = get_webhook_url(config)
    username = get_username(config)
    instance_url = args.instance_url.strip()

    # Validate VRChat instance URL
    if not validate_vrchat_url(instance_url):
        print(f"{COLOR_RED}[!] Error: Invalid VRChat instance URL format.{COLOR_RESET}")
        print(f"    Expected format: https://vrchat.com/home/launch?worldId=...")
        print(f"    Received: {instance_url}")
        sys.exit(1)

    # Check for existing active session
    current_state = load_state(state_path)
    if current_state and not args.force:
        print(f"{COLOR_YELLOW}[!] An active sleep session is already recorded from: {current_state.get('started_at')}{COLOR_RESET}")
        print(f"    Message ID: {current_state.get('message_id')}")
        try:
            choice = input("Do you want to overwrite it and post a new message? (y/N): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            return
        if choice != "y":
            print("Aborted.")
            return

    now_iso = datetime.now(timezone.utc).isoformat()
    embed = build_sleep_embed(username, instance_url, now_iso)
    payload = {
        "username": f"{username} Sleep Notifier",
        "avatar_url": "https://assets.vrchat.com/www/brand/vrchat-logo-white.png",
        "embeds": [embed],
        "allowed_mentions": {"parse": []}
    }

    # Add wait=true safely using URL query manipulation
    post_url = append_query_param(webhook_url, "wait", "true")

    print(f"{COLOR_CYAN}[*] Sending sleep announcement for '{username}' to Discord...{COLOR_RESET}")
    status_code, resp = send_http_request(post_url, method="POST", payload=payload)

    if status_code == 429:
        retry_after = resp.get("retry_after", "a few")
        print(f"{COLOR_YELLOW}[!] Discord Rate Limit: Please wait {retry_after}s before trying again.{COLOR_RESET}")
        sys.exit(1)
    elif status_code not in (200, 201, 204):
        print(f"{COLOR_RED}[!] Discord API Error ({status_code}): {resp.get('message', 'Failed to post message')}{COLOR_RESET}")
        sys.exit(1)

    message_id = resp.get("id")
    if not message_id:
        print(f"{COLOR_RED}[!] Warning: Did not receive message ID from Discord.{COLOR_RESET}")
        return

    # Save state
    state = {
        "message_id": message_id,
        "instance_url": instance_url,
        "username": username,
        "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "started_at_iso": now_iso
    }
    save_state(state, state_path)

    print(f"{COLOR_GREEN}{COLOR_BOLD}[✓] Sleep notification posted successfully!{COLOR_RESET}")
    print(f"    • User   : {username}")
    print(f"    • Status : {COLOR_GREEN}Sleeping (Instance Open){COLOR_RESET}")
    print(f"    • Msg ID : {message_id}")
    print(f"    • URL    : {instance_url}")
    print(f"\n{COLOR_CYAN}When you wake up, run:{COLOR_RESET}")
    print(f"  {COLOR_BOLD}python3 vrc_sleep.py close{COLOR_RESET}")


def cmd_close(args):
    """Handle `close` command: Edit Discord message to indicate closed status."""
    config_path = resolve_config_path(args.config)
    state_path = resolve_state_path(args.config)
    config = load_config(config_path)

    webhook_url = get_webhook_url(config)
    state = load_state(state_path)

    if not state or "message_id" not in state:
        print(f"{COLOR_YELLOW}[!] No active sleep session found.{COLOR_RESET}")
        print("Nothing to close. If you want to start a session, run:")
        print(f"  {COLOR_CYAN}python3 vrc_sleep.py start <instance_url>{COLOR_RESET}")
        return

    message_id = state["message_id"]
    instance_url = state.get("instance_url", "")
    username = state.get("username") or get_username(config)
    now_iso = datetime.now(timezone.utc).isoformat()

    # Discord webhook edit endpoint: PATCH /webhooks/{webhook.id}/{webhook.token}/messages/{message.id}
    base_webhook = webhook_url.split("?")[0].rstrip("/")
    patch_url = f"{base_webhook}/messages/{message_id}"

    embed = build_closed_embed(username, instance_url, now_iso)
    payload = {
        "embeds": [embed],
        "allowed_mentions": {"parse": []}
    }

    print(f"{COLOR_CYAN}[*] Updating Discord message (ID: {message_id}) to 'Closed'...{COLOR_RESET}")
    status_code, resp = send_http_request(patch_url, method="PATCH", payload=payload)

    if status_code == 404:
        print(f"{COLOR_YELLOW}[!] Notice: The notification message on Discord was already deleted or not found.{COLOR_RESET}")
        clear_state(state_path)
        print(f"{COLOR_GREEN}[✓] Local active session state cleared successfully.{COLOR_RESET}")
        return
    elif status_code == 429:
        retry_after = resp.get("retry_after", "a few")
        print(f"{COLOR_YELLOW}[!] Discord Rate Limit: Please wait {retry_after}s before trying again.{COLOR_RESET}")
        sys.exit(1)
    elif status_code not in (200, 204):
        print(f"{COLOR_RED}[!] Discord API Error ({status_code}): {resp.get('message', 'Failed to update message')}{COLOR_RESET}")
        sys.exit(1)

    clear_state(state_path)

    print(f"{COLOR_GREEN}{COLOR_BOLD}[✓] Discord message updated to 'Instance Closed'!{COLOR_RESET}")
    print(f"    • Status: {COLOR_RED}Closed{COLOR_RESET}")
    print(f"    • Good morning, {username}! Session finished.")


def cmd_status(args):
    """Handle `status` command: Check current session and configuration status."""
    config_path = resolve_config_path(args.config)
    state_path = resolve_state_path(args.config)
    config = load_config(config_path)
    state = load_state(state_path)

    print(f"{COLOR_BOLD}=== VRChat Sleep Notifier Status ==={COLOR_RESET}")
    print(f"Config File   : {config_path}")
    print(f"State File    : {state_path}")
    print(f"User Display  : {COLOR_CYAN}{get_username(config)}{COLOR_RESET}")

    webhook = config.get("webhook_url")
    if webhook:
        print(f"Webhook URL   : {COLOR_GREEN}{mask_url(webhook)}{COLOR_RESET}")
    else:
        print(f"Webhook URL   : {COLOR_RED}Not configured{COLOR_RESET}")

    print("-" * 36)
    if state:
        print(f"Active Session: {COLOR_GREEN}ACTIVE{COLOR_RESET}")
        print(f"  • User         : {state.get('username', 'N/A')}")
        print(f"  • Message ID   : {state.get('message_id')}")
        print(f"  • Started At   : {state.get('started_at')}")
        print(f"  • Instance URL : {state.get('instance_url')}")
    else:
        print(f"Active Session: {COLOR_YELLOW}None (Idle){COLOR_RESET}")


def cmd_config(args):
    """Handle `config` command: Set Webhook URL / Username or view settings."""
    config_path = resolve_config_path(args.config)
    config = load_config(config_path)
    updated = False

    if args.webhook:
        webhook_clean = args.webhook.strip()
        if not validate_webhook_url(webhook_clean):
            print(f"{COLOR_RED}[!] Error: Invalid Discord Webhook URL format.{COLOR_RESET}")
            print("    Expected: https://discord.com/api/webhooks/<ID>/<TOKEN>")
            sys.exit(1)
        config["webhook_url"] = webhook_clean
        updated = True
        print(f"{COLOR_GREEN}[✓] Discord Webhook URL has been updated!{COLOR_RESET}")

    if args.username is not None:
        # Sanitize control characters and normalize spaces
        username_clean = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", args.username).strip()
        username_clean = " ".join(username_clean.split())
        if not username_clean:
            print(f"{COLOR_RED}[!] Error: Username cannot be empty or solely whitespace/control characters.{COLOR_RESET}")
            sys.exit(1)
        if len(username_clean) > MAX_USERNAME_LENGTH:
            print(f"{COLOR_RED}[!] Error: Username is too long (max {MAX_USERNAME_LENGTH} characters).{COLOR_RESET}")
            sys.exit(1)
        config["username"] = username_clean
        updated = True
        print(f"{COLOR_GREEN}[✓] Display username updated to: {COLOR_CYAN}{username_clean}{COLOR_RESET}")

    if updated:
        save_config(config, config_path)
        print(f"Saved to: {config_path}")
    else:
        # View configuration
        print(f"{COLOR_BOLD}Current Configuration ({config_path}):{COLOR_RESET}")
        display_config = dict(config)
        if "webhook_url" in display_config and not args.show_secret:
            display_config["webhook_url"] = mask_url(display_config["webhook_url"])
        print(json.dumps(display_config, indent=2, ensure_ascii=False))
        if not args.show_secret and "webhook_url" in config:
            print(f"\n{COLOR_YELLOW}(Tip: Use --show-secret to display full unmasked Webhook URL){COLOR_RESET}")


def main():
    parser = argparse.ArgumentParser(
        description="VRChat Sleep Notification CLI for Discord Webhook",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Set Discord Webhook URL & Username
  python3 vrc_sleep.py config --webhook "https://discord.com/api/webhooks/..." --username "SORAMI"

  # Start sleep session (post notification)
  python3 vrc_sleep.py start "https://vrchat.com/home/launch?worldId=wrld_xxx:12345"

  # Close instance upon waking up (edit message to closed)
  python3 vrc_sleep.py close

  # Check current session status
  python3 vrc_sleep.py status
        """
    )
    parser.add_argument("--config", help="Custom path to configuration file (config.json)")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # `start` command
    parser_start = subparsers.add_parser("start", help="Post sleep announcement with instance URL")
    parser_start.add_argument("instance_url", help="VRChat instance URL (e.g., https://vrchat.com/home/launch?worldId=...)")
    parser_start.add_argument("-f", "--force", action="store_true", help="Force new session even if one is active")
    parser_start.set_defaults(func=cmd_start)

    # `close` command
    parser_close = subparsers.add_parser("close", help="Edit Discord message to show instance is closed")
    parser_close.set_defaults(func=cmd_close)

    # `status` command
    parser_status = subparsers.add_parser("status", help="Check current sleep session status")
    parser_status.set_defaults(func=cmd_status)

    # `config` command
    parser_config = subparsers.add_parser("config", help="Configure Discord Webhook URL and Username")
    parser_config.add_argument("--webhook", help="Discord Webhook URL")
    parser_config.add_argument("--username", help="Display username to show in Discord notifications")
    parser_config.add_argument("--show-secret", action="store_true", help="Display unmasked Webhook URL")
    parser_config.set_defaults(func=cmd_config)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()

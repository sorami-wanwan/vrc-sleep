#!/usr/bin/env python3
"""
VRChat Sleep Notification CLI for Discord Webhook.
Allows posting sleep announcements with VRChat instance URLs, world names, and images,
and updating them to 'Closed' when waking up.
"""

import argparse
import json
import os
import re
import stat
import sys
import time
import unicodedata
import urllib.request
import urllib.error
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Defaults and limits
DEFAULT_USERNAME = "VRChat User"
MAX_USERNAME_LENGTH = 50
MAX_URL_LENGTH = 2048
MAX_EMBED_FIELD_VALUE_LENGTH = 1024
MAX_WORLD_NAME_LENGTH = 100
MAX_IMAGE_URL_LENGTH = 2048

ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
DISCORD_SNOWFLAKE_PATTERN = re.compile(r"^\d{17,20}$")

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


def load_config(config_path: Path) -> dict[str, Any]:
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


def atomic_save_json(data: dict[str, Any], file_path: Path, secure_mode: bool = False) -> None:
    """
    Atomically write JSON to file to prevent corruption on sudden termination.
    If secure_mode is True, sets 0o600 permissions (owner read/write only) on POSIX.
    Includes retry backoff for Windows file replacement contention.
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = file_path.parent / f".{file_path.name}.{os.getpid()}_{int(time.time()*1000)}.tmp"

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    mode = 0o600 if (secure_mode and sys.platform != "win32") else 0o644

    try:
        fd = os.open(temp_file, flags, mode)
        with open(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())

        max_retries = 5
        for attempt in range(max_retries):
            try:
                temp_file.replace(file_path)
                break
            except PermissionError:
                if attempt < max_retries - 1:
                    time.sleep(0.05 * (2 ** attempt))
                else:
                    raise
    except Exception:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except OSError:
                pass
        raise



def save_config(config: dict[str, Any], config_path: Path) -> None:
    """Save configuration to config.json with secure file permissions."""
    atomic_save_json(config, config_path, secure_mode=True)


def load_state(state_path: Path) -> dict[str, Any] | None:
    """Load active session state from .state.json with corruption quarantine and type validation."""
    if not state_path.exists():
        return None

    try:
        with open(state_path, "r", encoding="utf-8") as f:
            st = os.fstat(f.fileno())
            if not stat.S_ISREG(st.st_mode) or st.st_size > 1024 * 1024:
                return None
            loaded = json.load(f)
            if not isinstance(loaded, dict):
                print(f"{COLOR_YELLOW}[!] Warning: Session state file is invalid (not a dict).{COLOR_RESET}")
                return None

            message_id = loaded.get("message_id")
            if not isinstance(message_id, str) or not validate_message_id(message_id):
                return None

            instance_url = loaded.get("instance_url")
            if isinstance(instance_url, str) and not validate_vrchat_url(instance_url):
                instance_url = None

            raw_world = loaded.get("world_name")
            world_name = sanitize_world_name(raw_world) if isinstance(raw_world, str) else None

            raw_image = loaded.get("image_url")
            image_url = raw_image if (isinstance(raw_image, str) and validate_image_url(raw_image)) else None

            return {
                "message_id": message_id,
                "instance_url": instance_url,
                "username": str(loaded.get("username", "")),
                "world_name": world_name,
                "image_url": image_url,
                "started_at": str(loaded.get("started_at", "")),
                "started_at_iso": str(loaded.get("started_at_iso", ""))
            }
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"{COLOR_YELLOW}[!] Warning: Failed to parse session state file ({e}). Quarantining corrupted file...{COLOR_RESET}")
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            corrupt_dest = state_path.parent / f"{state_path.name}.corrupted.{timestamp}"
            state_path.replace(corrupt_dest)
            print(f"{COLOR_YELLOW}[!] Corrupted state saved to: {corrupt_dest}{COLOR_RESET}")
        except Exception:
            pass
        return None


def save_state(state: dict[str, Any], state_path: Path) -> None:
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
    if not url or not isinstance(url, str):
        return False
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
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    if len(url) > MAX_URL_LENGTH:
        return False

    # Check if all characters in the URL are within the printable ASCII range, excluding control characters and spaces
    if not all(0x21 <= ord(c) <= 0x7E for c in url):
        return False

    # Prevent Markdown injection, command injection, and header injection
    forbidden_chars = ("[", "]", "(", ")", "`", "<", ">", '"', "'", "\\")
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


def validate_message_id(message_id: str) -> bool:
    """Validate Discord Snowflake Message ID strictly (17-20 digits)."""
    if not message_id or not isinstance(message_id, str):
        return False
    return bool(DISCORD_SNOWFLAKE_PATTERN.match(message_id.strip()))


def validate_image_url(url: str) -> bool:
    """
    Strict validation for Discord Embed image URLs:
    - HTTPS only
    - Max 2048 chars
    - Disallow userinfo (user:pass@)
    - Disallow control chars, newlines, spaces, quotes, backslashes
    - Safe path extension check or query format check (case-insensitive)
    """
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    if len(url) > MAX_IMAGE_URL_LENGTH:
        return False

    # Check if all characters in the URL are within the printable ASCII range, excluding control characters and spaces
    if not all(0x21 <= ord(c) <= 0x7E for c in url):
        return False

    if any(c in url for c in ("<", ">", '"', "'", "`", "\\")):
        return False

    try:
        parsed = urlparse(url)
        if parsed.scheme.lower() != "https":
            return False
        if parsed.username or parsed.password:
            return False

        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return False

        path = parsed.path.lower()
        if any(path.endswith(ext) for ext in ALLOWED_IMAGE_EXTENSIONS):
            return True

        # Reject partial matches and perform strict query parsing
        qs = parse_qs(parsed.query, keep_blank_values=False)
        for key in ("format", "ext", "auto"):
            for val in qs.get(key, []):
                val_clean = f".{val.lower().strip()}"
                if val_clean in ALLOWED_IMAGE_EXTENSIONS:
                    return True

        return False
    except Exception:
        return False


def sanitize_world_name(name: str | None) -> str | None:
    """
    Sanitize world name:
    - Strip ANSI escape sequences
    - Neutralize Markdown & Discord Mentions (@, <, >, [, ], &, etc.)
    - Neutralize raw URL protocols (prevent autolink phishing)
    - Suppress Zalgo combining characters (Mn, Mc, Me)
    - Safe truncate handling combining characters
    - Return None if empty to prevent Discord 400 Bad Request
    """
    if not name or not isinstance(name, str):
        return None

    # Strip ANSI escape sequences first
    clean_ansi = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", name)
    normalized = unicodedata.normalize("NFC", clean_ansi)
    cleaned_chars = []
    combining_count = 0
    forbidden_symbols = set("[]()`*_~|>#@<:\\&")

    for char in normalized:
        cat = unicodedata.category(char)
        # Drop control (Cc), format (Cf), private use (Co)
        if cat in ("Cc", "Cf", "Co"):
            continue
        # Limit combining marks (Mn, Mc, Me)
        if cat in ("Mn", "Mc", "Me"):
            combining_count += 1
            if combining_count > 2:
                continue
        else:
            combining_count = 0

        if char in forbidden_symbols:
            cleaned_chars.append(" ")
        else:
            cleaned_chars.append(char)

    result = "".join(cleaned_chars)
    # Neutralize URL protocols if any left
    result = re.sub(r"https?://", " ", result, flags=re.IGNORECASE)
    result = " ".join(result.split()).strip()
    if not result:
        return None

    # Safe slicing up to MAX_WORLD_NAME_LENGTH
    trimmed = result[:MAX_WORLD_NAME_LENGTH]
    while trimmed and unicodedata.category(trimmed[-1]) in ("Mn", "Mc", "Me"):
        trimmed = trimmed[:-1]

    return trimmed.strip() or None


def get_username(config: dict[str, Any]) -> str:
    """Get configured username or fallback to default."""
    return config.get("username", "").strip() or DEFAULT_USERNAME


def get_webhook_url(config: dict[str, Any]) -> str:
    """Retrieve webhook URL or prompt user to configure it."""
    webhook_url = str(config.get("webhook_url", "")).strip()
    if not webhook_url:
        print(f"{COLOR_RED}[!] Error: Discord Webhook URL is not configured.{COLOR_RESET}")
        print(f"Please set your Webhook URL using:")
        print(f"  {COLOR_CYAN}python3 vrc_sleep.py config --webhook \"<YOUR_WEBHOOK_URL>\"{COLOR_RESET}")
        print(f"or set the {COLOR_YELLOW}DISCORD_WEBHOOK_URL{COLOR_RESET} environment variable.")
        sys.exit(1)
    return webhook_url


def send_http_request(url: str, method: str, payload: dict[str, Any], timeout: float = 15.0) -> tuple[int, dict[str, Any]]:
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


def build_sleep_embed(
    username: str,
    instance_url: str,
    timestamp_iso: str,
    world_name: str | None = None,
    image_url: str | None = None
) -> dict[str, Any]:
    """Construct the Discord embed for sleep notification safely within limits."""
    safe_username = (username[:MAX_USERNAME_LENGTH] if username else DEFAULT_USERNAME)

    # Guard 1024-char Discord field limit
    join_text = "[🔗 Click here to Join Instance]"
    max_url_len = MAX_EMBED_FIELD_VALUE_LENGTH - len(join_text) - 3  # for '(', ')', and safety margin
    safe_instance_url = instance_url if len(instance_url) <= max_url_len else instance_url[:max_url_len]
    instance_val = f"{join_text}({safe_instance_url})"

    fields = [
        {
            "name": "Status",
            "value": "🟢 **Instance Open / Sleeping**",
            "inline": True
        }
    ]
    if world_name:
        fields.append({
            "name": "World",
            "value": world_name[:MAX_EMBED_FIELD_VALUE_LENGTH],
            "inline": True
        })
    fields.append({
        "name": "VRChat Instance",
        "value": instance_val,
        "inline": False
    })

    embed = {
        "title": f"🌙 {safe_username} is sleeping now...",
        "description": "I have gone to sleep in VRChat. Feel free to join if you like!",
        "color": 0x3F51B5,  # Indigo / Night Blue
        "fields": fields,
        "footer": {
            "text": "VRChat Sleep Notification"
        },
        "timestamp": timestamp_iso
    }
    if image_url:
        embed["image"] = {"url": image_url}

    return embed


def build_closed_embed(
    username: str,
    instance_url: str | None,
    closed_iso: str,
    world_name: str | None = None,
    image_url: str | None = None
) -> dict[str, Any]:
    """Construct the Discord embed for instance closed notification safely within limits."""
    safe_username = (username[:MAX_USERNAME_LENGTH] if username else DEFAULT_USERNAME)

    if instance_url:
        prefix = "~~[Instance Link]("
        suffix = ")~~ *(Closed)*"
        max_url_len = MAX_EMBED_FIELD_VALUE_LENGTH - len(prefix) - len(suffix)
        safe_instance_url = instance_url if len(instance_url) <= max_url_len else instance_url[:max_url_len]
        instance_val = f"{prefix}{safe_instance_url}{suffix}"
    else:
        instance_val = "*(Instance URL not recorded)*"

    fields = [
        {
            "name": "Status",
            "value": "🔴 **Instance Closed**",
            "inline": True
        }
    ]
    if world_name:
        fields.append({
            "name": "World",
            "value": world_name[:MAX_EMBED_FIELD_VALUE_LENGTH],
            "inline": True
        })
    fields.append({
        "name": "VRChat Instance",
        "value": instance_val,
        "inline": False
    })

    embed = {
        "title": f"☀️ {safe_username} has woken up / Instance Closed",
        "description": "The sleep instance is now closed. Thank you for visiting!",
        "color": 0x95A5A6,  # Slate Gray
        "fields": fields,
        "footer": {
            "text": "VRChat Sleep Notification • Instance Closed"
        },
        "timestamp": closed_iso
    }
    if image_url:
        embed["image"] = {"url": image_url}

    return embed


def cmd_start(args: Any) -> None:
    """Handle `start` command: Post sleep announcement with optional world name and image to Discord."""
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

    # Sanitize World Name
    raw_world = getattr(args, "world", None)
    world_name = sanitize_world_name(raw_world) if isinstance(raw_world, str) else None

    # Validate Image URL
    image_url = None
    raw_image = getattr(args, "image", None)
    if isinstance(raw_image, str) and raw_image.strip():
        clean_img = raw_image.strip()
        if not validate_image_url(clean_img):
            print(f"{COLOR_RED}[!] Error: Invalid image URL format.{COLOR_RESET}")
            print(f"    Must be an HTTPS URL pointing to a valid image (.png, .jpg, .jpeg, .webp, .gif).")
            print(f"    Received: {clean_img}")
            sys.exit(1)
        image_url = clean_img

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
    embed = build_sleep_embed(username, instance_url, now_iso, world_name=world_name, image_url=image_url)
    safe_username = (username[:MAX_USERNAME_LENGTH] if username else DEFAULT_USERNAME)
    payload = {
        "username": f"{safe_username} Sleep Notifier",
        "avatar_url": "https://assets.vrchat.com/www/brand/vrchat-logo-white.png",
        "embeds": [embed],
        "allowed_mentions": {
            "parse": [],
            "users": [],
            "roles": [],
            "replied_user": False
        }
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
        "world_name": world_name,
        "image_url": image_url,
        "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "started_at_iso": now_iso
    }
    save_state(state, state_path)

    print(f"{COLOR_GREEN}{COLOR_BOLD}[+] Sleep notification posted successfully!{COLOR_RESET}")
    print(f"    - User   : {username}")
    if world_name:
        print(f"    - World  : {world_name}")
    if image_url:
        print(f"    - Image  : {image_url}")
    print(f"    - Status : {COLOR_GREEN}Sleeping (Instance Open){COLOR_RESET}")
    print(f"    - Msg ID : {message_id}")
    print(f"    - URL    : {instance_url}")
    print(f"\n{COLOR_CYAN}When you wake up, run:{COLOR_RESET}")
    print(f"  {COLOR_BOLD}python3 vrc_sleep.py close{COLOR_RESET}")


def cmd_close(args: Any) -> None:
    """Handle `close` command: Edit Discord message to indicate closed status."""
    config_path = resolve_config_path(args.config)
    state_path = resolve_state_path(args.config)
    config = load_config(config_path)

    webhook_url = get_webhook_url(config)
    state = load_state(state_path)

    # Determine message ID (from state or explicit CLI override)
    message_id = None
    raw_message_id = getattr(args, "message_id", None)
    if isinstance(raw_message_id, str) and raw_message_id.strip():
        if not validate_message_id(raw_message_id):
            print(f"{COLOR_RED}[!] Error: Invalid Discord message ID format (expected 17-20 digits).{COLOR_RESET}")
            sys.exit(1)
        message_id = raw_message_id.strip()
    elif state and "message_id" in state:
        message_id = state["message_id"]

    if not message_id:
        print(f"{COLOR_YELLOW}[!] No active sleep session found.{COLOR_RESET}")
        print("Nothing to close. If you want to start a session, run:")
        print(f"  {COLOR_CYAN}python3 vrc_sleep.py start <instance_url>{COLOR_RESET}")
        print("Or if you have a message ID to close manually:")
        print(f"  {COLOR_CYAN}python3 vrc_sleep.py close --message-id <MESSAGE_ID>{COLOR_RESET}")
        return

    instance_url = state.get("instance_url") if state else None
    world_name = state.get("world_name") if state else None
    image_url = state.get("image_url") if state else None
    username = (state.get("username") if state else None) or get_username(config)
    now_iso = datetime.now(timezone.utc).isoformat()

    # Discord webhook edit endpoint: PATCH /webhooks/{webhook.id}/{webhook.token}/messages/{message.id}
    base_webhook = webhook_url.split("?")[0].rstrip("/")
    patch_url = f"{base_webhook}/messages/{message_id}"

    embed = build_closed_embed(username, instance_url, now_iso, world_name=world_name, image_url=image_url)
    payload = {
        "embeds": [embed],
        "allowed_mentions": {
            "parse": [],
            "users": [],
            "roles": [],
            "replied_user": False
        }
    }

    print(f"{COLOR_CYAN}[*] Updating Discord message (ID: {message_id}) to 'Closed'...{COLOR_RESET}")
    status_code, resp = send_http_request(patch_url, method="PATCH", payload=payload)

    if status_code == 404:
        print(f"{COLOR_YELLOW}[!] Notice: The notification message on Discord was already deleted or not found.{COLOR_RESET}")
        clear_state(state_path)
        print(f"{COLOR_GREEN}[+] Local active session state cleared successfully.{COLOR_RESET}")
        return
    elif status_code == 429:
        retry_after = resp.get("retry_after", "a few")
        print(f"{COLOR_YELLOW}[!] Discord Rate Limit: Please wait {retry_after}s before trying again.{COLOR_RESET}")
        sys.exit(1)
    elif status_code not in (200, 204):
        print(f"{COLOR_RED}[!] Discord API Error ({status_code}): {resp.get('message', 'Failed to update message')}{COLOR_RESET}")
        sys.exit(1)

    clear_state(state_path)

    print(f"{COLOR_GREEN}{COLOR_BOLD}[+] Discord message updated to 'Instance Closed'!{COLOR_RESET}")
    print(f"    - Status: {COLOR_RED}Closed{COLOR_RESET}")
    print(f"    - Good morning, {username}! Session finished.")


def cmd_status(args: Any) -> None:
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
        print(f"  - User         : {state.get('username', 'N/A')}")
        if state.get("world_name"):
            print(f"  - World Name   : {state.get('world_name')}")
        if state.get("image_url"):
            print(f"  - Image URL    : {state.get('image_url')}")
        print(f"  - Message ID   : {state.get('message_id')}")
        print(f"  - Started At   : {state.get('started_at')}")
        print(f"  - Instance URL : {state.get('instance_url')}")
    else:
        print(f"Active Session: {COLOR_YELLOW}None (Idle){COLOR_RESET}")


def cmd_config(args: Any) -> None:
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
        print(f"{COLOR_GREEN}[+] Discord Webhook URL has been updated!{COLOR_RESET}")

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
        print(f"{COLOR_GREEN}[+] Display username updated to: {COLOR_CYAN}{username_clean}{COLOR_RESET}")

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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="VRChat Sleep Notification CLI for Discord Webhook",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Set Discord Webhook URL & Username
  python3 vrc_sleep.py config --webhook "https://discord.com/api/webhooks/..." --username "SORAMI"

  # Start sleep session (post notification with optional world name and image)
  python3 vrc_sleep.py start "https://vrchat.com/home/launch?worldId=wrld_xxx:12345"
  python3 vrc_sleep.py start "https://vrchat.com/home/launch?worldId=..." -w "Cozy Bedroom" -i "https://example.com/sleep.png"

  # Close instance upon waking up (edit message to closed)
  python3 vrc_sleep.py close

  # Close manually by message ID if state was lost
  python3 vrc_sleep.py close --message-id "123456789012345678"

  # Check current session status
  python3 vrc_sleep.py status
        """
    )
    parser.add_argument("--config", help="Custom path to configuration file (config.json)")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # `start` command
    parser_start = subparsers.add_parser("start", help="Post sleep announcement with instance URL")
    parser_start.add_argument("instance_url", help="VRChat instance URL (e.g., https://vrchat.com/home/launch?worldId=...)")
    parser_start.add_argument("-w", "--world", help="World name to display in Discord Embed (max 100 chars)")
    parser_start.add_argument("-i", "--image", help="Image URL to display in Discord Embed (.png, .jpg, .jpeg, .webp, .gif)")
    parser_start.add_argument("-f", "--force", action="store_true", help="Force new session even if one is active")
    parser_start.set_defaults(func=cmd_start)

    # `close` command
    parser_close = subparsers.add_parser("close", help="Edit Discord message to show instance is closed")
    parser_close.add_argument("-m", "--message-id", help="Manually specify Discord Message ID to close")
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

#!/usr/bin/env python3
"""
Unit tests for vrc-sleep CLI tool.
Uses only Python standard library (unittest).
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import urllib.error

# Add parent directory to path so vrc_sleep can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import vrc_sleep


class TestValidation(unittest.TestCase):
    """Test validation functions for Discord Webhook URLs, VRChat instance URLs, Message IDs, and Image URLs."""

    def test_validate_webhook_url_valid(self):
        valid_urls = [
            "https://discord.com/api/webhooks/123456789012345678/abcdefghijklmnopqrstuvwxyz0123456789_ABCDEFGHIJKLMNOPQRSTUVWXYZ",
            "https://discordapp.com/api/webhooks/1234567890/token_abc-123",
            "https://ptb.discord.com/api/webhooks/1234567890/token_abc-123",
            "https://canary.discord.com/api/webhooks/1234567890/token_abc-123",
            "https://discord.com/api/webhooks/1234567890/token_abc-123?wait=true",
        ]
        for url in valid_urls:
            with self.subTest(url=url):
                self.assertTrue(vrc_sleep.validate_webhook_url(url))

    def test_validate_webhook_url_invalid(self):
        invalid_urls = [
            "http://discord.com/api/webhooks/12345/token",  # Non-HTTPS
            "https://evil.com/api/webhooks/12345/token",
            "https://discord.com/api/webhooks/",  # Missing ID and token
            "https://discord.com/api/webhooks/notanid/token",
            "just a plain string",
            "",
            None,
        ]
        for url in invalid_urls:
            with self.subTest(url=url):
                self.assertFalse(vrc_sleep.validate_webhook_url(url))

    def test_validate_vrchat_url_valid(self):
        valid_urls = [
            "https://vrchat.com/home/launch?worldId=wrld_12345678-1234-1234-1234-123456789012&instanceId=12345~hidden",
            "https://www.vrchat.com/home/launch?worldId=wrld_12345678-1234-1234-1234-123456789012",
            "https://vrchat.com/home/world/wrld_12345678-1234-1234-1234-123456789012",
            "https://vrch.at/sample-instance-code",
        ]
        for url in valid_urls:
            with self.subTest(url=url):
                self.assertTrue(vrc_sleep.validate_vrchat_url(url))

    def test_validate_vrchat_url_invalid(self):
        invalid_urls = [
            "https://example.com/home/launch?worldId=wrld_12345",  # Wrong domain
            "https://vrchat.com/login",  # Not a launch/world/avatar/vrch.at url
            "https://vrchat.com/home/launch?worldId=123\nInject: header",  # Newline injection
            "https://vrchat.com/home/launch?worldId=123[Markdown](link)",  # Markdown injection
            "https://vrchat.com/home/launch?worldId=123(link)",  # Parentheses injection
            "https://vrchat.com/home/launch?worldId=123 with spaces",
            "https://vrchat.com/home/launch\u200b?worldId=123", # Zero width space
            "https://vrchat.com/home/launch\u3000?worldId=123", # Fullwidth space
            "https://vrchat.com/home/launch\x0b?worldId=123", # Vertical tab
            "",
            None,
        ]
        for url in invalid_urls:
            with self.subTest(url=url):
                self.assertFalse(vrc_sleep.validate_vrchat_url(url))

    def test_validate_message_id_valid(self):
        valid_ids = [
            "12345678901234567",     # 17 digits
            "123456789012345678",    # 18 digits
            "1234567890123456789",   # 19 digits
            "12345678901234567890",  # 20 digits
        ]
        for mid in valid_ids:
            with self.subTest(mid=mid):
                self.assertTrue(vrc_sleep.validate_message_id(mid))

    def test_validate_message_id_invalid(self):
        invalid_ids = [
            "123456",                   # Too short
            "123456789012345678901",    # Too long (21 digits)
            "123456789012345678?wait",  # Trailing query
            "../../other/endpoint",      # Path traversal
            "abc1234567890123456",      # Contains letters
            "",
            None,
        ]
        for mid in invalid_ids:
            with self.subTest(mid=mid):
                self.assertFalse(vrc_sleep.validate_message_id(mid))

    def test_validate_image_url_valid(self):
        valid_urls = [
            "https://example.com/image.png",
            "https://example.com/photos/avatar.jpg",
            "https://example.com/photo.JPEG",  # Case insensitive
            "https://cdn.example.com/anim.gif",
            "https://cdn.example.com/card.webp",
            "https://media.discordapp.net/attachments/123/456/test.png?format=webp&width=800",
            "https://images.unsplash.com/photo-12345?format=png",
            "https://images.unsplash.com/photo-12345?ext=jpg",
        ]
        for url in valid_urls:
            with self.subTest(url=url):
                self.assertTrue(vrc_sleep.validate_image_url(url))

    def test_validate_image_url_invalid(self):
        invalid_urls = [
            "https://ｅｘａｍｐｌｅ.ｃｏｍ/image.png\nInjection", # Fullwidth + Control character
            "http://example.com/image.png",               # Non-HTTPS
            "https://user:pass@example.com/image.png",     # User credentials
            "https://example.com/payload.exe?.png",        # Extension in query only without path/format
            "https://example.com/image.png\nInjection",   # Control character CRLF
            "https://example.com/image with space.png",   # Space
            "https://example.com/" + ("a" * 2050) + ".png", # Over 2048 chars
            "https://example.com/api?dummy=1&format=png_fake", # Query spoofing
            "https://example.com/image\u200b.png", # Zero width space
            "https://example.com/image\u3000.png", # Fullwidth space
            "https://example.com/image\x0b.png", # Vertical tab
            "",
            None,
        ]
        for url in invalid_urls:
            with self.subTest(url=url):
                self.assertFalse(vrc_sleep.validate_image_url(url))

    def test_append_query_param(self):
        url1 = "https://discord.com/api/webhooks/1/2"
        self.assertEqual(vrc_sleep.append_query_param(url1, "wait", "true"), "https://discord.com/api/webhooks/1/2?wait=true")

        url2 = "https://discord.com/api/webhooks/1/2?thread_id=123"
        result2 = vrc_sleep.append_query_param(url2, "wait", "true")
        self.assertIn("thread_id=123", result2)
        self.assertIn("wait=true", result2)

        # Overwrite existing
        url3 = "https://discord.com/api/webhooks/1/2?wait=false"
        self.assertEqual(vrc_sleep.append_query_param(url3, "wait", "true"), "https://discord.com/api/webhooks/1/2?wait=true")


class TestSanitization(unittest.TestCase):
    """Test world name sanitization against injection, mentions, and UI bombs."""

    def test_sanitize_world_name_normal(self):
        self.assertEqual(vrc_sleep.sanitize_world_name("Cozy Bedroom"), "Cozy Bedroom")
        self.assertEqual(vrc_sleep.sanitize_world_name("  おやすみ  ワールド  "), "おやすみ ワールド")

    def test_sanitize_world_name_mentions(self):
        # Disallow @everyone, <@123>, <@&role>
        sanitized = vrc_sleep.sanitize_world_name("@everyone <@&123456789012345678> Alert")
        self.assertNotIn("@", sanitized)
        self.assertNotIn("<", sanitized)
        self.assertNotIn(">", sanitized)
        self.assertEqual(sanitized, "everyone 123456789012345678 Alert")

    def test_sanitize_world_name_autolink_and_markdown(self):
        # Neutralize autolink protocols and markdown links
        raw = "My World [Click Here](https://evil-phishing.com) https://scam.org"
        sanitized = vrc_sleep.sanitize_world_name(raw)
        self.assertNotIn("http://", sanitized)
        self.assertNotIn("https://", sanitized)
        self.assertNotIn("[", sanitized)
        self.assertNotIn("]", sanitized)
        self.assertNotIn("(", sanitized)
        self.assertNotIn(")", sanitized)
        self.assertIn("evil-phishing.com", sanitized)
        self.assertIn("scam.org", sanitized)

    def test_sanitize_world_name_control_and_zalgo(self):
        # Neutralize ANSI escape, control chars, zero width chars
        raw = "\x1b[31mRed\x1b[0m \u200bZeroWidth\u200e \n\r\tNewlines"
        sanitized = vrc_sleep.sanitize_world_name(raw)
        self.assertNotIn("\x1b", sanitized)
        self.assertNotIn("\u200b", sanitized)
        self.assertNotIn("\n", sanitized)
        self.assertEqual(sanitized, "Red ZeroWidth Newlines")

        # Suppress excessive Zalgo combining characters
        zalgo = "e" + ("\u0301" * 20) + " test"
        sanitized_zalgo = vrc_sleep.sanitize_world_name(zalgo)
        # Should limit combining marks to max 2
        self.assertTrue(len(sanitized_zalgo) < 10)

    def test_sanitize_world_name_empty_or_whitespace(self):
        self.assertIsNone(vrc_sleep.sanitize_world_name(""))
        self.assertIsNone(vrc_sleep.sanitize_world_name("   "))
        self.assertIsNone(vrc_sleep.sanitize_world_name("\n\r\t"))
        self.assertIsNone(vrc_sleep.sanitize_world_name("\u200b\u200c\u200d"))
        self.assertIsNone(vrc_sleep.sanitize_world_name(None))

    def test_sanitize_world_name_length_limit(self):
        long_name = "A" * 150
        sanitized = vrc_sleep.sanitize_world_name(long_name)
        self.assertEqual(len(sanitized), 100)


class TestMasking(unittest.TestCase):
    """Test sensitive URL token masking."""

    def test_mask_url_none_or_empty(self):
        self.assertEqual(vrc_sleep.mask_url(None), "Not configured")
        self.assertEqual(vrc_sleep.mask_url(""), "Not configured")

    def test_mask_webhook_url_long_token(self):
        url = "https://discord.com/api/webhooks/1234567890/abcdefghijklmnopqrstuvwxyz"
        masked = vrc_sleep.mask_url(url)
        self.assertTrue(masked.startswith("https://discord.com/api/webhooks/1234567890/abcd...wxyz"))
        self.assertNotIn("efghijklmnopqrstuv", masked)

    def test_mask_webhook_url_short_token(self):
        url = "https://discord.com/api/webhooks/1234567890/token123"
        masked = vrc_sleep.mask_url(url)
        self.assertEqual(masked, "https://discord.com/api/webhooks/1234567890/...")


class TestEmbedBuilder(unittest.TestCase):
    """Test Discord embed generation."""

    def test_build_sleep_embed(self):
        username = "TestUser"
        url = "https://vrch.at/test1234"
        timestamp = "2026-08-21T05:00:00Z"

        embed = vrc_sleep.build_sleep_embed(username, url, timestamp)

        self.assertIn("TestUser", embed["title"])
        self.assertEqual(embed["timestamp"], timestamp)
        self.assertEqual(embed["color"], 0x3F51B5)
        self.assertTrue(any(f["name"] == "Status" and "Sleeping" in f["value"] for f in embed["fields"]))
        self.assertTrue(any("https://vrch.at/test1234" in f["value"] for f in embed["fields"]))
        self.assertFalse(any(f["name"] == "World" for f in embed["fields"]))
        self.assertNotIn("image", embed)

    def test_build_sleep_embed_with_world_and_image(self):
        username = "TestUser"
        url = "https://vrch.at/test1234"
        timestamp = "2026-08-21T05:00:00Z"
        world = "Cozy Bedroom"
        image = "https://example.com/bed.png"

        embed = vrc_sleep.build_sleep_embed(username, url, timestamp, world_name=world, image_url=image)

        self.assertTrue(any(f["name"] == "World" and f["value"] == "Cozy Bedroom" for f in embed["fields"]))
        self.assertEqual(embed["image"]["url"], "https://example.com/bed.png")

    def test_build_sleep_embed_field_length_limit(self):
        username = "TestUser"
        long_url = "https://vrchat.com/home/launch?worldId=wrld_123&" + ("x=" * 600)  # >1200 chars
        timestamp = "2026-08-21T05:00:00Z"

        embed = vrc_sleep.build_sleep_embed(username, long_url, timestamp)
        for field in embed["fields"]:
            self.assertLessEqual(len(field["value"]), 1024)

    def test_build_closed_embed(self):
        username = "TestUser"
        url = "https://vrch.at/test1234"
        timestamp = "2026-08-21T07:00:00Z"

        embed = vrc_sleep.build_closed_embed(username, url, timestamp)

        self.assertIn("TestUser", embed["title"])
        self.assertIn("Closed", embed["title"])
        self.assertEqual(embed["timestamp"], timestamp)
        self.assertEqual(embed["color"], 0x95A5A6)
        self.assertTrue(any(f["name"] == "Status" and "Closed" in f["value"] for f in embed["fields"]))
        self.assertFalse(any(f["name"] == "World" for f in embed["fields"]))
        self.assertNotIn("image", embed)

    def test_build_closed_embed_with_world_and_image(self):
        username = "TestUser"
        url = "https://vrch.at/test1234"
        timestamp = "2026-08-21T07:00:00Z"
        world = "Cozy Bedroom"
        image = "https://example.com/bed.png"

        embed = vrc_sleep.build_closed_embed(username, url, timestamp, world_name=world, image_url=image)

        self.assertTrue(any(f["name"] == "World" and f["value"] == "Cozy Bedroom" for f in embed["fields"]))
        self.assertEqual(embed["image"]["url"], "https://example.com/bed.png")

    def test_build_closed_embed_none_url(self):
        embed = vrc_sleep.build_closed_embed("User", None, "2026-08-21T07:00:00Z")
        self.assertTrue(any("*(Instance URL not recorded)*" in f["value"] for f in embed["fields"]))


class TestConfigAndState(unittest.TestCase):
    """Test config and session state storage and retrieval."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_and_load_config(self):
        config_path = self.temp_path / "config.json"
        config_data = {
            "webhook_url": "https://discord.com/api/webhooks/123/abc",
            "username": "SleepyCat"
        }

        vrc_sleep.save_config(config_data, config_path)
        self.assertTrue(config_path.exists())

        loaded = vrc_sleep.load_config(config_path)
        self.assertEqual(loaded["webhook_url"], "https://discord.com/api/webhooks/123/abc")
        self.assertEqual(loaded["username"], "SleepyCat")

    def test_env_override_config(self):
        config_path = self.temp_path / "config.json"
        config_data = {
            "webhook_url": "https://discord.com/api/webhooks/123/from_file",
            "username": "FileUser"
        }
        vrc_sleep.save_config(config_data, config_path)

        with patch.dict(os.environ, {
            "DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/999/from_env",
            "VRC_SLEEP_USERNAME": "EnvUser"
        }):
            loaded = vrc_sleep.load_config(config_path)
            self.assertEqual(loaded["webhook_url"], "https://discord.com/api/webhooks/999/from_env")
            self.assertEqual(loaded["username"], "EnvUser")

    def test_save_load_clear_state(self):
        state_path = self.temp_path / ".state.json"
        state_data = {
            "message_id": "123456789012345678",
            "instance_url": "https://vrch.at/abc",
            "username": "TestUser",
            "world_name": "My Room",
            "image_url": "https://example.com/pic.png",
            "started_at": "2026-08-21 05:00:00"
        }

        # Initially non-existent
        self.assertIsNone(vrc_sleep.load_state(state_path))

        # Save & Load
        vrc_sleep.save_state(state_data, state_path)
        self.assertTrue(state_path.exists())
        loaded = vrc_sleep.load_state(state_path)
        self.assertEqual(loaded["message_id"], "123456789012345678")
        self.assertEqual(loaded["world_name"], "My Room")
        self.assertEqual(loaded["image_url"], "https://example.com/pic.png")

        # Clear
        vrc_sleep.clear_state(state_path)
        self.assertFalse(state_path.exists())
        self.assertIsNone(vrc_sleep.load_state(state_path))

    def test_resolve_config_path_custom(self):
        custom_file = self.temp_path / "custom_config.json"
        resolved = vrc_sleep.resolve_config_path(str(custom_file))
        self.assertEqual(resolved, custom_file.resolve())

    def test_load_corrupted_config_and_state(self):
        corrupted_config = self.temp_path / "corrupted_config.json"
        corrupted_config.write_text("[1, 2, 3]")  # Non-dict valid JSON
        self.assertEqual(vrc_sleep.load_config(corrupted_config), {})

        corrupted_state = self.temp_path / "corrupted_state.json"
        corrupted_state.write_text("invalid json")
        self.assertIsNone(vrc_sleep.load_state(corrupted_state))

    def test_load_state_injection(self):
        state_path = self.temp_path / ".state.json"
        malicious_state = {
            "message_id": "123456789012345678",
            "instance_url": "https://vrchat.com/home/launch) [Evil](https://evil.com",
            "username": "Hacker",
            "started_at": "2026-08-21 05:00:00"
        }
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(malicious_state, f)
        
        loaded = vrc_sleep.load_state(state_path)
        self.assertIsNotNone(loaded)
        self.assertIsNone(loaded.get("instance_url"))

    def test_load_state_file_not_found_no_corrupt_file(self):
        state_path = self.temp_path / "does_not_exist.json"
        self.assertIsNone(vrc_sleep.load_state(state_path))
        corrupted_files = list(self.temp_path.glob("*.corrupted.*"))
        self.assertEqual(len(corrupted_files), 0)

    def test_load_state_size_limit(self):
        state_path = self.temp_path / ".state_large.json"
        with open(state_path, "wb") as f:
            f.write(b"0" * (1024 * 1024 + 100))
        self.assertIsNone(vrc_sleep.load_state(state_path))
        corrupted_files = list(self.temp_path.glob("*.corrupted.*"))
        self.assertEqual(len(corrupted_files), 0)

    @patch("os.fstat")
    def test_load_state_not_regular_file(self, mock_fstat):
        state_path = self.temp_path / ".state.json"
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump({"message_id": "123456789012345678"}, f)
        
        mock_stat = MagicMock()
        import stat
        mock_stat.st_mode = stat.S_IFCHR # Character device (not a regular file)
        mock_stat.st_size = 100
        mock_fstat.return_value = mock_stat

        self.assertIsNone(vrc_sleep.load_state(state_path))


class TestHttpRequests(unittest.TestCase):
    """Test send_http_request behavior with mocking."""

    @patch("urllib.request.urlopen")
    def test_send_http_request_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"id": "1122334455"}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        status, data = vrc_sleep.send_http_request("https://discord.com/api/webhooks/1/2", "POST", {"hello": "world"})
        self.assertEqual(status, 200)
        self.assertEqual(data.get("id"), "1122334455")

    @patch("urllib.request.urlopen")
    def test_send_http_request_http_error(self, mock_urlopen):
        error_content = json.dumps({"message": "Invalid Webhook Token", "code": 50027}).encode("utf-8")
        fp = MagicMock()
        fp.read.return_value = error_content
        err = urllib.error.HTTPError(
            url="https://discord.com/api/webhooks/1/2",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=fp
        )
        mock_urlopen.side_effect = err

        status, data = vrc_sleep.send_http_request("https://discord.com/api/webhooks/1/2", "POST", {})
        self.assertEqual(status, 401)
        self.assertEqual(data.get("code"), 50027)

    @patch("urllib.request.urlopen")
    def test_send_http_request_non_json_body(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 204
        mock_resp.read.return_value = b""
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        status, data = vrc_sleep.send_http_request("https://discord.com/api/webhooks/1/2", "POST", {})
        self.assertEqual(status, 204)
        self.assertEqual(data, {})

        # Test HTML / Cloudflare error page body
        mock_resp.status = 502
        mock_resp.read.return_value = b"<html><title>502 Bad Gateway</title></html>"
        status, data = vrc_sleep.send_http_request("https://discord.com/api/webhooks/1/2", "POST", {})
        self.assertEqual(status, 502)
        self.assertEqual(data, {})


class TestCommands(unittest.TestCase):
    """Test CLI command functions with isolated temp directories and mocks."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "config.json"
        self.state_path = Path(self.temp_dir.name) / ".state.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_cmd_config_set_and_view(self):
        # 1. Set webhook and username
        args = MagicMock()
        args.config = str(self.config_path)
        args.webhook = "https://discord.com/api/webhooks/12345/secrettoken"
        args.username = "Alice"
        args.show_secret = False

        vrc_sleep.cmd_config(args)

        loaded = vrc_sleep.load_config(self.config_path)
        self.assertEqual(loaded["username"], "Alice")
        self.assertEqual(loaded["webhook_url"], "https://discord.com/api/webhooks/12345/secrettoken")

        # 2. View without updating
        args.webhook = None
        args.username = None
        with patch("builtins.print") as mock_print:
            vrc_sleep.cmd_config(args)
            printed = " ".join(str(call) for call in mock_print.call_args_list)
            self.assertIn("Alice", printed)
            self.assertIn("12345", printed)
            self.assertNotIn("secrettoken", printed)  # Must be masked

    @patch("vrc_sleep.send_http_request")
    def test_cmd_start_and_close_flow(self, mock_http):
        mock_http.return_value = (200, {"id": "123456789012345678"})

        # Setup config
        vrc_sleep.save_config({
            "webhook_url": "https://discord.com/api/webhooks/123/token",
            "username": "Bob"
        }, self.config_path)

        # 1. Start session with world and image
        args_start = MagicMock()
        args_start.config = str(self.config_path)
        args_start.instance_url = "https://vrchat.com/home/launch?worldId=wrld_12345"
        args_start.world = "Cozy Bedroom"
        args_start.image = "https://example.com/bed.png"
        args_start.force = False

        vrc_sleep.cmd_start(args_start)

        state = vrc_sleep.load_state(self.state_path)
        self.assertIsNotNone(state)
        self.assertEqual(state["message_id"], "123456789012345678")
        self.assertEqual(state["username"], "Bob")
        self.assertEqual(state["world_name"], "Cozy Bedroom")
        self.assertEqual(state["image_url"], "https://example.com/bed.png")

        # Verify allowed_mentions in payload
        call_args = mock_http.call_args[1]
        payload = call_args["payload"]
        self.assertEqual(payload["allowed_mentions"]["parse"], [])
        self.assertEqual(payload["allowed_mentions"]["users"], [])
        self.assertEqual(payload["allowed_mentions"]["roles"], [])
        self.assertFalse(payload["allowed_mentions"]["replied_user"])

        # 2. Close session
        args_close = MagicMock()
        args_close.config = str(self.config_path)
        args_close.message_id = None

        vrc_sleep.cmd_close(args_close)

        state_after = vrc_sleep.load_state(self.state_path)
        self.assertIsNone(state_after)

    @patch("vrc_sleep.send_http_request")
    def test_cmd_close_with_manual_message_id(self, mock_http):
        mock_http.return_value = (200, {})

        vrc_sleep.save_config({"webhook_url": "https://discord.com/api/webhooks/1/2"}, self.config_path)

        args_close = MagicMock()
        args_close.config = str(self.config_path)
        args_close.message_id = "987654321098765432"

        vrc_sleep.cmd_close(args_close)

        # Verified that patch was sent to manual ID
        call_args = mock_http.call_args
        self.assertIn("987654321098765432", call_args[0][0])

    @patch("vrc_sleep.send_http_request")
    def test_cmd_close_backwards_compatibility(self, mock_http):
        mock_http.return_value = (200, {})

        vrc_sleep.save_config({"webhook_url": "https://discord.com/api/webhooks/1/2"}, self.config_path)
        # Old state format without world_name and image_url
        vrc_sleep.save_state({
            "message_id": "112233445566778899",
            "instance_url": "https://vrch.at/abc",
            "username": "OldUser",
            "started_at": "2026-08-20 00:00:00"
        }, self.state_path)

        args_close = MagicMock()
        args_close.config = str(self.config_path)
        args_close.message_id = None

        vrc_sleep.cmd_close(args_close)
        self.assertIsNone(vrc_sleep.load_state(self.state_path))

    @patch("vrc_sleep.send_http_request")
    def test_cmd_close_404_recovery(self, mock_http):
        mock_http.return_value = (404, {"message": "Unknown Message"})

        vrc_sleep.save_config({"webhook_url": "https://discord.com/api/webhooks/1/2"}, self.config_path)
        vrc_sleep.save_state({"message_id": "112233445566778899"}, self.state_path)

        args_close = MagicMock()
        args_close.config = str(self.config_path)
        args_close.message_id = None

        vrc_sleep.cmd_close(args_close)
        # Should clear local state gracefully even if message was deleted on Discord
        self.assertIsNone(vrc_sleep.load_state(self.state_path))


if __name__ == "__main__":
    unittest.main()

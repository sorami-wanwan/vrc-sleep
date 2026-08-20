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
    """Test validation functions for Discord Webhook URLs and VRChat instance URLs."""

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
            "",
        ]
        for url in invalid_urls:
            with self.subTest(url=url):
                self.assertFalse(vrc_sleep.validate_vrchat_url(url))

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
            "message_id": "123456789",
            "instance_url": "https://vrch.at/abc",
            "username": "TestUser",
            "started_at": "2026-08-21 05:00:00"
        }

        # Initially non-existent
        self.assertIsNone(vrc_sleep.load_state(state_path))

        # Save & Load
        vrc_sleep.save_state(state_data, state_path)
        self.assertTrue(state_path.exists())
        loaded = vrc_sleep.load_state(state_path)
        self.assertEqual(loaded["message_id"], "123456789")

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
        mock_http.return_value = (200, {"id": "msg_98765"})

        # Setup config
        vrc_sleep.save_config({
            "webhook_url": "https://discord.com/api/webhooks/123/token",
            "username": "Bob"
        }, self.config_path)

        # 1. Start session
        args_start = MagicMock()
        args_start.config = str(self.config_path)
        args_start.instance_url = "https://vrchat.com/home/launch?worldId=wrld_12345"
        args_start.force = False

        vrc_sleep.cmd_start(args_start)

        state = vrc_sleep.load_state(self.state_path)
        self.assertIsNotNone(state)
        self.assertEqual(state["message_id"], "msg_98765")
        self.assertEqual(state["username"], "Bob")

        # 2. Close session
        args_close = MagicMock()
        args_close.config = str(self.config_path)

        vrc_sleep.cmd_close(args_close)

        state_after = vrc_sleep.load_state(self.state_path)
        self.assertIsNone(state_after)

    @patch("vrc_sleep.send_http_request")
    def test_cmd_close_404_recovery(self, mock_http):
        mock_http.return_value = (404, {"message": "Unknown Message"})

        vrc_sleep.save_config({"webhook_url": "https://discord.com/api/webhooks/1/2"}, self.config_path)
        vrc_sleep.save_state({"message_id": "deleted_msg"}, self.state_path)

        args_close = MagicMock()
        args_close.config = str(self.config_path)

        vrc_sleep.cmd_close(args_close)
        # Should clear local state gracefully even if message was deleted on Discord
        self.assertIsNone(vrc_sleep.load_state(self.state_path))


if __name__ == "__main__":
    unittest.main()

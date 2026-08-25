import unittest
from unittest.mock import patch, MagicMock
import os
import tempfile

# Import modules to be tested
from vrc_sleep_gui import _is_running_in_temp, atomic_save_json, VRCCommandRunner


class TestVRCSleepGUI(unittest.TestCase):

    # --- Task 1.1: Test blocking execution from TEMP directory ---
    @patch('vrc_sleep_gui.tempfile.gettempdir')
    @patch('vrc_sleep_gui.os.path.realpath')
    @patch('vrc_sleep_gui.sys')
    def test_is_running_in_temp_true(self, mock_sys, mock_realpath, mock_gettempdir):
        """Return True if the execution path is under the TEMP directory"""
        mock_sys.frozen = False
        mock_gettempdir.return_value = '/tmp'

        # Mock the path returned by realpath
        def side_effect(path):
            if path == '/tmp':
                return '/tmp'
            return '/tmp/vrc_sleep_gui.py'  # Under the TEMP directory

        mock_realpath.side_effect = side_effect

        self.assertTrue(_is_running_in_temp())

    @patch('vrc_sleep_gui.tempfile.gettempdir')
    @patch('vrc_sleep_gui.os.path.realpath')
    @patch('vrc_sleep_gui.sys')
    def test_is_running_in_temp_false(self, mock_sys, mock_realpath, mock_gettempdir):
        """Return False if the execution path is not under the TEMP directory"""
        mock_sys.frozen = False
        mock_gettempdir.return_value = '/tmp'

        def side_effect(path):
            if path == '/tmp':
                return '/tmp'
            return '/opt/myapp/vrc_sleep_gui.py'  # Not under the TEMP directory

        mock_realpath.side_effect = side_effect

        self.assertFalse(_is_running_in_temp())

    @patch('vrc_sleep_gui.tempfile.gettempdir')
    @patch('vrc_sleep_gui.os.path.realpath')
    def test_is_running_in_temp_exception(self, mock_realpath, mock_gettempdir):
        """Return False on exception to fail safe"""
        mock_gettempdir.return_value = '/tmp'
        mock_realpath.side_effect = Exception("Test Exception")
        self.assertFalse(_is_running_in_temp())

    # --- Task 1.2: Test exponential backoff ---
    @patch('vrc_sleep_gui.os.replace')
    @patch('vrc_sleep_gui.os.remove')
    @patch('vrc_sleep_gui.os.path.exists')
    @patch('vrc_sleep_gui.os.fsync')
    @patch('vrc_sleep_gui.time.sleep')
    def test_atomic_save_json_success_with_retry(self, mock_sleep, mock_fsync, mock_exists, mock_remove, mock_replace):
        """Should retry on PermissionError and eventually succeed"""
        mock_exists.return_value = True  # Ensure path to delete temporary file in finally block is executed

        # Fail 3 times, succeed on the 4th
        mock_replace.side_effect = [PermissionError, PermissionError, PermissionError, None]

        # Mock builtins.open to prevent file creation
        with patch('builtins.open', unittest.mock.mock_open()):
            atomic_save_json({"key": "value"}, "dummy.json")

        self.assertEqual(mock_replace.call_count, 4)
        self.assertEqual(mock_sleep.call_count, 3)

    @patch('vrc_sleep_gui.os.replace')
    @patch('vrc_sleep_gui.os.remove')
    @patch('vrc_sleep_gui.os.path.exists')
    @patch('vrc_sleep_gui.os.fsync')
    @patch('vrc_sleep_gui.time.sleep')
    def test_atomic_save_json_failure_after_retries(
            self, mock_sleep, mock_fsync, mock_exists, mock_remove, mock_replace):
        """Should raise exception after exceeding max retries"""
        mock_exists.return_value = True
        mock_replace.side_effect = PermissionError  # Always fail

        with patch('builtins.open', unittest.mock.mock_open()):
            with self.assertRaises(PermissionError):
                atomic_save_json({"key": "value"}, "dummy.json")

        self.assertEqual(mock_replace.call_count, 5)  # Max 5 retries
        self.assertEqual(mock_sleep.call_count, 4)

    def test_atomic_save_json_integration(self):
        """Verify atomic_save_json on actual filesystem without mocks"""
        import json
        import time
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "test_config.json")
            data = {"test": "data"}

            # Create initial file
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump({"initial": "data"}, f)

            if os.name == 'nt':
                import msvcrt
                import threading

                def lock_file():
                    with open(file_path, 'r+', encoding='utf-8') as f:
                        fd = f.fileno()
                        # Lock the first byte
                        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                        time.sleep(0.5)
                        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

                t = threading.Thread(target=lock_file)
                t.start()

                # Wait a bit to ensure lock is acquired
                time.sleep(0.1)

                # Execute save in main thread (should retry)
                atomic_save_json(data, file_path)

                t.join()
            else:
                atomic_save_json(data, file_path)

            with open(file_path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            self.assertEqual(loaded, data)

    # --- Task 1.3: Test force process termination ---
    def test_terminate_process(self):
        """kill method of the held process should be called when terminate_process is called"""
        mock_process = MagicMock()
        VRCCommandRunner._current_process = mock_process

        VRCCommandRunner.terminate_process()

        mock_process.kill.assert_called_once()
        self.assertIsNone(VRCCommandRunner._current_process)

    def test_terminate_process_exception(self):
        """_current_process should be initialized even if kill raises an exception"""
        mock_process = MagicMock()
        mock_process.kill.side_effect = Exception("Kill failed")
        VRCCommandRunner._current_process = mock_process

        VRCCommandRunner.terminate_process()

        mock_process.kill.assert_called_once()
        self.assertIsNone(VRCCommandRunner._current_process)

    # --- New: Edge cases and vulnerability testing ---
    def test_argument_injection(self):
        """Argument injection prevention: ensure \'--\' is used"""
        import tkinter as tk
        from vrc_sleep_gui import VRCSleepGUI
        
        root = tk.Tk()
        root.withdraw()
        app = VRCSleepGUI(root)
        
        app.instance_var.set("--config")
        app.world_var.set("Normal World")
        app.image_var.set("")
        app.webhook_url = "http://test"

        with patch('vrc_sleep_gui.VRCCommandRunner.run_command') as mock_run:
            app._execute_start_command_thread(app.instance_var.get(), app.world_var.get(), app.image_var.get())
            
            args = mock_run.call_args[0][0]
            # Ensure '--' is before '--config'
            self.assertIn('--', args)
            self.assertLess(args.index('--'), args.index('--config'))
            
        root.destroy()

    def test_type_juggling(self):
        """Config type juggling: should not crash when invalid types are loaded"""
        import json
        import tkinter as tk
        from vrc_sleep_gui import VRCSleepGUI
        
        root = tk.Tk()
        root.withdraw()
        
        config_path = os.path.join(tempfile.gettempdir(), "test_config_juggling.json")
        state_path = os.path.join(tempfile.gettempdir(), "test_state_juggling.json")
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump({"webhook_url": ["not", "a", "string"], "username": 123}, f)
            
        with open(state_path, 'w', encoding='utf-8') as f:
            json.dump({"instance_url": {"invalid": "dict"}, "is_sleeping": "true"}, f)
            
        with patch('vrc_sleep_gui.CONFIG_FILE', config_path), \
             patch('vrc_sleep_gui.STATE_FILE', state_path):
            app = VRCSleepGUI(root)
            # Check that types are forcefully converted
            self.assertEqual(app.webhook_url, "['not', 'a', 'string']")
            self.assertEqual(app.username, "123")
            self.assertEqual(app.instance_var.get(), "{'invalid': 'dict'}")
            
        os.remove(config_path)
        os.remove(state_path)
        root.destroy()
        
    def test_tkinter_race_condition(self):
        """Tkinter destroy and thread race condition: callbacks after destroy should not leak exceptions"""
        import tkinter as tk
        from vrc_sleep_gui import VRCSleepGUI
        
        root = tk.Tk()
        root.withdraw()
        app = VRCSleepGUI(root)
        
        # Destroy window
        root.destroy()
        
        # Ensure no exception is raised even when _safe_after is called
        try:
            app._safe_after(0, app._on_start_success)
            success = True
        except Exception as e:
            success = False
            self.fail(f"_safe_after raised an exception: {e}")
            
        self.assertTrue(success)


if __name__ == '__main__':
    unittest.main()

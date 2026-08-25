import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Dict, Any, List

BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE: str = os.path.join(BASE_DIR, "config.json")
STATE_FILE: str = os.path.join(BASE_DIR, "gui_state.json")
VRC_SLEEP_SCRIPT: str = os.path.join(BASE_DIR, "vrc_sleep.py")


class VRCCommandRunner:
    """Handles execution of the vrc_sleep.py backend CLI script in a secure and cross-platform manner."""
    
    @staticmethod
    def _get_subprocess_kwargs() -> Dict[str, Any]:
        """Gets platform-specific kwargs for subprocess.run."""
        kwargs: Dict[str, Any] = {
            "cwd": BASE_DIR,
            "capture_output": True,
            "text": True,
            "encoding": "utf-8",
            "stdin": subprocess.DEVNULL,
            "env": os.environ.copy()
        }
        kwargs["env"]["PYTHONIOENCODING"] = "utf-8"
        
        # Windows-specific flags to prevent showing terminal windows.
        # getattr is used to prevent static analysis errors or execution errors on POSIX systems.
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            
        return kwargs

    @classmethod
    def run_command(cls, args: List[str], timeout: int = 30) -> subprocess.CompletedProcess:
        """Executes the CLI script with the given arguments securely."""
        executable = sys.executable or "python"
        cmd: List[str] = [executable, VRC_SLEEP_SCRIPT] + args
        kwargs = cls._get_subprocess_kwargs()
        
        return subprocess.run(cmd, check=False, timeout=timeout, **kwargs)


class VRCSleepGUI:
    """Main Application GUI for VRC Sleep Notifier."""

    def __init__(self, root: tk.Tk) -> None:
        self.root: tk.Tk = root
        self.root.title("VRC Sleep Notifier")
        self.root.geometry("550x400")
        self.root.resizable(False, False)
        
        self._is_processing: bool = False  # Strict lock to prevent rapid multi-clicks
        
        self._setup_style()
        self._init_variables()
        self._build_ui()
        
        self.load_data()
        self.update_ui_state()

    def _setup_style(self) -> None:
        self.style: ttk.Style = ttk.Style()
        if 'clam' in self.style.theme_names():
            self.style.theme_use('clam')
        
        self.style.configure('TLabel', font=('Segoe UI', 10))
        self.style.configure('TButton', font=('Segoe UI', 10, 'bold'), padding=5)

    def _init_variables(self) -> None:
        self.state_var: tk.StringVar = tk.StringVar()
        self.instance_var: tk.StringVar = tk.StringVar()
        self.world_var: tk.StringVar = tk.StringVar()
        self.image_var: tk.StringVar = tk.StringVar()
        
        self.webhook_url: str = ""
        self.username: str = ""
        self.is_sleeping: bool = False

    def _build_ui(self) -> None:
        self.main_frame: ttk.Frame = ttk.Frame(self.root, padding="25 25 25 25")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.top_frame: ttk.Frame = ttk.Frame(self.main_frame)
        self.top_frame.pack(fill=tk.X, pady=(0, 25))

        self.state_label: tk.Label = tk.Label(
            self.top_frame, 
            textvariable=self.state_var, 
            font=('Segoe UI', 14, 'bold'), 
            pady=15, 
            relief=tk.GROOVE, 
            borderwidth=2
        )
        self.state_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.settings_btn: ttk.Button = ttk.Button(
            self.top_frame,
            text="Settings",
            command=self.open_settings,
            width=10
        )
        self.settings_btn.pack(side=tk.RIGHT, padx=(15, 0), fill=tk.Y)

        self.inputs_frame: ttk.Frame = ttk.Frame(self.main_frame)
        self.inputs_frame.pack(fill=tk.X, pady=(0, 25))
        
        self._add_input_row("Instance URL (Required):", self.instance_var, row=0)
        self._add_input_row("World Name (Optional):", self.world_var, row=1)
        self._add_input_row("Image URL (Optional):", self.image_var, row=2)
        
        self.inputs_frame.columnconfigure(1, weight=1)

        self.buttons_frame: ttk.Frame = ttk.Frame(self.main_frame)
        self.buttons_frame.pack(fill=tk.X, pady=(10, 0))

        self.start_btn: ttk.Button = ttk.Button(
            self.buttons_frame, 
            text="Start Sleep", 
            command=self.on_start_click
        )
        self.start_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        self.close_btn: ttk.Button = ttk.Button(
            self.buttons_frame, 
            text="Close Session", 
            command=self.on_close_click
        )
        self.close_btn.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0))

    def _add_input_row(self, label_text: str, variable: tk.StringVar, row: int) -> None:
        ttk.Label(self.inputs_frame, text=label_text).grid(row=row, column=0, sticky=tk.E, pady=8)
        entry: ttk.Entry = ttk.Entry(self.inputs_frame, textvariable=variable, width=50)
        entry.grid(row=row, column=1, sticky=tk.EW, pady=8, padx=(10, 0))
        if row == 0:
            self.instance_entry = entry
        elif row == 1:
            self.world_entry = entry
        elif row == 2:
            self.image_entry = entry

    def load_data(self) -> None:
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config: Dict[str, Any] = json.load(f)
                    self.webhook_url = config.get("webhook_url", "")
                    self.username = config.get("username", "")
            except (OSError, json.JSONDecodeError) as e:
                print(f"Warning: Config load error: {e}")
        
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r', encoding='utf-8') as f:
                    state: Dict[str, Any] = json.load(f)
                    self.is_sleeping = bool(state.get("is_sleeping", False))
                    self.instance_var.set(state.get("instance_url", ""))
                    self.world_var.set(state.get("world_name", ""))
                    self.image_var.set(state.get("image_url", ""))
            except (OSError, json.JSONDecodeError) as e:
                print(f"Warning: State load error: {e}")

    def save_state(self) -> None:
        state: Dict[str, Any] = {
            "is_sleeping": self.is_sleeping,
            "instance_url": self.instance_var.get(),
            "world_name": self.world_var.get(),
            "image_url": self.image_var.get()
        }
        try:
            tmp_file = f"{STATE_FILE}.tmp"
            with open(tmp_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_file, STATE_FILE)
        except OSError as e:
            print(f"Error: State save error: {e}")

    def open_settings(self) -> None:
        self.settings_btn.state(['disabled'])
        
        settings_win: tk.Toplevel = tk.Toplevel(self.root)
        settings_win.title("Settings")
        settings_win.geometry("500x200")
        settings_win.resizable(False, False)
        
        settings_win.transient(self.root)
        settings_win.grab_set()

        def on_close() -> None:
            self.settings_btn.state(['!disabled'])
            settings_win.destroy()
            
        settings_win.protocol("WM_DELETE_WINDOW", on_close)

        frame: ttk.Frame = ttk.Frame(settings_win, padding="25 25 25 25")
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Webhook URL:").grid(row=0, column=0, sticky=tk.E, pady=8)
        webhook_var: tk.StringVar = tk.StringVar(value=self.webhook_url)
        webhook_entry: ttk.Entry = ttk.Entry(frame, textvariable=webhook_var, width=45)
        webhook_entry.grid(row=0, column=1, sticky=tk.EW, pady=8, padx=(10, 0))

        ttk.Label(frame, text="Username:").grid(row=1, column=0, sticky=tk.E, pady=8)
        username_var: tk.StringVar = tk.StringVar(value=self.username)
        username_entry: ttk.Entry = ttk.Entry(frame, textvariable=username_var, width=45)
        username_entry.grid(row=1, column=1, sticky=tk.EW, pady=8, padx=(10, 0))

        frame.columnconfigure(1, weight=1)

        btn_frame: ttk.Frame = ttk.Frame(frame)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=(15, 0))

        def save_settings() -> None:
            new_webhook: str = webhook_var.get().strip()
            new_username: str = username_var.get().strip()
            
            self.webhook_url = new_webhook
            self.username = new_username
            
            config: Dict[str, Any] = {}
            if os.path.exists(CONFIG_FILE):
                try:
                    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                except (OSError, json.JSONDecodeError):
                    pass
            
            config["webhook_url"] = new_webhook
            config["username"] = new_username
            
            try:
                tmp_file = f"{CONFIG_FILE}.tmp"
                with open(tmp_file, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_file, CONFIG_FILE)
            except OSError as e:
                messagebox.showerror("Save Error", f"Failed to save settings:\n{e}", parent=settings_win)
                return
                
            on_close()

        ttk.Button(btn_frame, text="Save", command=save_settings).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="Cancel", command=on_close).pack(side=tk.LEFT, padx=10)

    def update_ui_state(self) -> None:
        self._is_processing = False
        
        if self.is_sleeping:
            self.state_var.set("Sleeping...")
            self.state_label.config(bg="#d4edda", fg="#155724")
            self.start_btn.state(['disabled'])
            self.close_btn.state(['!disabled'])
            self.settings_btn.state(['disabled'])
            self.instance_entry.state(['disabled'])
            self.world_entry.state(['disabled'])
            self.image_entry.state(['disabled'])
        else:
            self.state_var.set("No Active Session")
            self.state_label.config(bg="#e2e3e5", fg="#383d41")
            self.start_btn.state(['!disabled'])
            self.close_btn.state(['disabled'])
            self.settings_btn.state(['!disabled'])
            self.instance_entry.state(['!disabled'])
            self.world_entry.state(['!disabled'])
            self.image_entry.state(['!disabled'])

    def set_loading_state(self) -> None:
        self.start_btn.state(['disabled'])
        self.close_btn.state(['disabled'])
        self.settings_btn.state(['disabled'])
        self.state_var.set("Processing...")
        self.state_label.config(bg="#fff3cd", fg="#856404")

    def _safe_after(self, delay: int, callback: Any, *args: Any) -> None:
        """Safely queues a callback on the main thread, suppressing TclError if the window is destroyed."""
        try:
            self.root.after(delay, callback, *args)
        except (RuntimeError, tk.TclError):
            pass

    def on_start_click(self) -> None:
        if self._is_processing:
            return
            
        instance: str = self.instance_var.get().strip()
        world: str = self.world_var.get().strip()
        image: str = self.image_var.get().strip()

        if not self.webhook_url:
            messagebox.showerror("Input Error", "Please configure Webhook URL in Settings.", parent=self.root)
            return
        if not instance:
            messagebox.showerror("Input Error", "Please enter an Instance URL.", parent=self.root)
            return

        if not os.path.exists(VRC_SLEEP_SCRIPT):
            messagebox.showerror("File Not Found", f"'{VRC_SLEEP_SCRIPT}' not found.", parent=self.root)
            return

        self._is_processing = True
        self.set_loading_state()
        self.save_state()

        threading.Thread(
            target=self._execute_start_command_thread, 
            args=(instance, world, image), 
            daemon=True
        ).start()

    def _execute_start_command_thread(self, instance: str, world: str, image: str) -> None:
        args: List[str] = ["start", instance, "-f"]
        if world:
            args.extend(["-w", world])
        if image:
            args.extend(["-i", image])
            
        try:
            result = VRCCommandRunner.run_command(args)
            if result.returncode == 0:
                self._safe_after(0, self._on_start_success)
            else:
                stderr: str = result.stderr or ""
                stdout: str = result.stdout or ""
                error_msg: str = stderr.strip() or stdout.strip() or f"Exit code: {result.returncode}"
                self._safe_after(0, self._on_command_fail, "Start Sleep", error_msg)
        except Exception as e:
            self._safe_after(0, self._on_command_fail, "Start Sleep", str(e))

    def _on_start_success(self) -> None:
        self.is_sleeping = True
        self.save_state()
        self.update_ui_state()

    def on_close_click(self) -> None:
        if self._is_processing:
            return
            
        if not os.path.exists(VRC_SLEEP_SCRIPT):
            messagebox.showerror("File Not Found", f"'{VRC_SLEEP_SCRIPT}' not found.", parent=self.root)
            return

        self._is_processing = True
        self.set_loading_state()
        
        threading.Thread(
            target=self._execute_close_command_thread, 
            daemon=True
        ).start()

    def _execute_close_command_thread(self) -> None:
        args: List[str] = ["close"]
        
        try:
            result = VRCCommandRunner.run_command(args)
            if result.returncode == 0:
                self._safe_after(0, self._on_close_success)
            else:
                stderr: str = result.stderr or ""
                stdout: str = result.stdout or ""
                error_msg: str = stderr.strip() or stdout.strip() or f"Exit code: {result.returncode}"
                self._safe_after(0, self._on_command_fail, "Close Session", error_msg)
        except Exception as e:
            self._safe_after(0, self._on_command_fail, "Close Session", str(e))

    def _on_close_success(self) -> None:
        self.is_sleeping = False
        self.save_state()
        self.update_ui_state()

    def _on_command_fail(self, action: str, error_msg: str) -> None:
        self.update_ui_state()
        messagebox.showerror(f"{action} Error", f"Command execution failed:\n\n{error_msg}", parent=self.root)


def main() -> None:
    root: tk.Tk = tk.Tk()
    app = VRCSleepGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()

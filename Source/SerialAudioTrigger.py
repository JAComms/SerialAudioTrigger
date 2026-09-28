import sys
import subprocess

# --- AUTOMATIC DEPENDENCY CHECKER ---
required_libraries = {"serial": "pyserial", "vlc": "python-vlc"}
for module_name, pip_name in required_libraries.items():
    try:
        __import__(module_name)
    except ImportError:
        print(f"Installing missing dependency: {pip_name}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name])

# --- MAIN PROGRAM ---
import os
import json
import time
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import serial
import serial.tools.list_ports
import vlc

CONFIG_FILE = "serial_config.json"

class SerialAudioApp:
    def __init__(self, root):
        self.root = root
        self.root.title("JAComms - Serial Port Audio Trigger")
        self.root.geometry("575x390")
        self.root.resizable(False, False)

        # State variables
        self.com_port = tk.StringVar()
        self.audio_1_path = tk.StringVar()
        self.audio_2_path = tk.StringVar()
        self.duration_1 = tk.StringVar(value="0") 
        self.duration_2 = tk.StringVar(value="0")
        self.volume_1 = tk.IntVar(value=100)
        self.volume_2 = tk.IntVar(value=100)
        self.loop_1 = tk.BooleanVar(value=False)
        self.loop_2 = tk.BooleanVar(value=False)
        self.auto_start = tk.BooleanVar(value=False)
        self.is_running = False
        self.monitor_thread = None

        # Timer references to handle stopping audio early
        self.timer_1 = None
        self.timer_2 = None

        # VLC Instances
        self.vlc_instance = vlc.Instance()
        self.player_1 = self.vlc_instance.media_player_new()
        self.player_2 = self.vlc_instance.media_player_new()

        # Load saved settings if they exist
        self.load_config()

        # Build UI Components
        self.create_widgets()

        # Start periodic UI checks for player status updates
        self.update_ui_indicators()

        # Trigger auto-start if configured and paths are valid
        if self.auto_start.get():
            self.root.after(500, self.check_and_auto_start)

    def create_widgets(self):
        # --- COM Port Selection ---
        port_frame = tk.LabelFrame(self.root, text=" 1. Select COM Port ", padx=10, pady=10)
        port_frame.pack(fill="x", padx=15, pady=10)

        available_ports = [p.device for p in serial.tools.list_ports.comports()]
        if not available_ports:
            available_ports = ["No COM Ports Found"]
        
        if self.com_port.get() not in available_ports and available_ports:
            self.com_port.set(available_ports)

        self.port_dropdown = ttk.Combobox(port_frame, textvariable=self.com_port, values=available_ports, state="readonly")
        self.port_dropdown.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        refresh_btn = ttk.Button(port_frame, text="Refresh", command=self.refresh_ports)
        refresh_btn.pack(side="right")

        # --- Audio File & Playback Customisations ---
        audio_frame = tk.LabelFrame(self.root, text=" 2. Assign Audio, Duration & Volume ", padx=10, pady=10)
        audio_frame.pack(fill="x", padx=15, pady=5)

        # --- PLAYER 1 (DSR) ---
        tk.Label(audio_frame, text="Trigger 1 (DTR -> DSR):", font=("Arial", 9, "bold")).grid(row=0, column=0, sticky="w", pady=2)
        ttk.Entry(audio_frame, textvariable=self.audio_1_path, width=32).grid(row=0, column=1, padx=5)
        ttk.Button(audio_frame, text="Browse...", command=lambda: self.browse_audio(1)).grid(row=0, column=2, padx=2)
        
        # Player 1 Live Visual Indicator Button (Clickable Override)
        self.ind_1 = tk.Button(audio_frame, text="■ IDLE", bg="#d9d9d9", fg="#666666", width=12, font=("Arial", 9, "bold"), relief="raised", command=self.handle_trigger_1)
        self.ind_1.grid(row=0, column=3, padx=5)

        tk.Label(audio_frame, text="Duration (sec, 0=Full):").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Entry(audio_frame, textvariable=self.duration_1, width=10).grid(row=1, column=1, sticky="w", padx=5)
        
        chk_loop_1 = ttk.Checkbutton(audio_frame, text="Loop Audio", variable=self.loop_1, command=self.save_config)
        chk_loop_1.grid(row=1, column=1, sticky="e", padx=(0, 40))

        tk.Label(audio_frame, text="Volume:").grid(row=2, column=0, sticky="w", pady=(0, 20))
        scale_1 = ttk.Scale(audio_frame, from_=0, to=100, variable=self.volume_1, orient="horizontal", command=lambda v: self.set_vlc_volume(1, v))
        scale_1.grid(row=2, column=1, sticky="ew", padx=5, pady=(0, 20))

        # --- PLAYER 2 (CTS) ---
        tk.Label(audio_frame, text="Trigger 2 (RTS -> CTS):", font=("Arial", 9, "bold")).grid(row=3, column=0, sticky="w", pady=2)
        ttk.Entry(audio_frame, textvariable=self.audio_2_path, width=32).grid(row=3, column=1, padx=5)
        ttk.Button(audio_frame, text="Browse...", command=lambda: self.browse_audio(2)).grid(row=3, column=2, padx=2)
        
        # Player 2 Live Visual Indicator Button (Clickable Override)
        self.ind_2 = tk.Button(audio_frame, text="■ IDLE", bg="#d9d9d9", fg="#666666", width=12, font=("Arial", 9, "bold"), relief="raised", command=self.handle_trigger_2)
        self.ind_2.grid(row=3, column=3, padx=5)

        tk.Label(audio_frame, text="Duration (sec, 0=Full):").grid(row=4, column=0, sticky="w", pady=2)
        ttk.Entry(audio_frame, textvariable=self.duration_2, width=10).grid(row=4, column=1, sticky="w", padx=5)
        
        chk_loop_2 = ttk.Checkbutton(audio_frame, text="Loop Audio", variable=self.loop_2, command=self.save_config)
        chk_loop_2.grid(row=4, column=1, sticky="e", padx=(0, 40))

        tk.Label(audio_frame, text="Volume:").grid(row=5, column=0, sticky="w")
        scale_2 = ttk.Scale(audio_frame, from_=0, to=100, variable=self.volume_2, orient="horizontal", command=lambda v: self.set_vlc_volume(2, v))
        scale_2.grid(row=5, column=1, sticky="ew", padx=5)

        # --- Automation Options ---
        options_frame = tk.Frame(self.root, pady=10)
        options_frame.pack(fill="x", padx=15)
        
        self.auto_chk = ttk.Checkbutton(
            options_frame, 
            text="COM Port Auto monitoring", 
            variable=self.auto_start,
            command=self.save_config
        )
        self.auto_chk.pack(side="left")

        # --- Control Section ---
        control_frame = tk.Frame(self.root, pady=5)
        control_frame.pack(fill="x", padx=15)

        self.status_label = tk.Label(control_frame, text="Status: Stopped", fg="red", font=("Arial", 10, "bold"))
        self.status_label.pack(side="left")

        self.start_btn = ttk.Button(control_frame, text="Start Monitoring", command=self.toggle_monitoring)
        self.start_btn.pack(side="right")

    def refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_dropdown['values'] = ports if ports else ["No COM Ports Found"]
        if ports and self.com_port.get() not in ports:
            self.com_port.set(ports)

    def browse_audio(self, trigger_num):
        file_path = filedialog.askopenfilename(filetypes=[("Audio Files", "*.mp3 *.wav *.ogg")])
        if file_path:
            if trigger_num == 1:
                self.audio_1_path.set(file_path)
            else:
                self.audio_2_path.set(file_path)
            self.save_config()

    def set_vlc_volume(self, player_num, val):
        volume_pct = int(float(val))
        if player_num == 1:
            self.player_1.audio_set_volume(volume_pct)
        else:
            self.player_2.audio_set_volume(volume_pct)
        self.save_config()

    # --- UI Live State Updates ---
    def update_ui_indicators(self):
        if self.player_1.is_playing():
            self.ind_1.config(text="▶ PLAYING", bg="#2ecc71", fg="white", activebackground="#27ae60", activeforeground="white")
        else:
            self.ind_1.config(text="■ IDLE", bg="#d9d9d9", fg="#666666", activebackground="#cccccc", activeforeground="#666666")

        if self.player_2.is_playing():
            self.ind_2.config(text="▶ PLAYING", bg="#2ecc71", fg="white", activebackground="#27ae60", activeforeground="white")
        else:
            self.ind_2.config(text="■ IDLE", bg="#d9d9d9", fg="#666666", activebackground="#cccccc", activeforeground="#666666")

        self.root.after(100, self.update_ui_indicators)

    # --- Persistent Config Management ---
    def save_config(self):
        config_data = {
            "com_port": self.com_port.get(),
            "audio_1": self.audio_1_path.get(),
            "audio_2": self.audio_2_path.get(),
            "duration_1": self.duration_1.get(),
            "duration_2": self.duration_2.get(),
            "volume_1": self.volume_1.get(),
            "volume_2": self.volume_2.get(),
            "loop_1": self.loop_1.get(),
            "loop_2": self.loop_2.get(),
            "auto_start": self.auto_start.get()
        }
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(config_data, f)
        except Exception:
            pass

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    config_data = json.load(f)
                    self.com_port.set(config_data.get("com_port", ""))
                    self.audio_1_path.set(config_data.get("audio_1", ""))
                    self.audio_2_path.set(config_data.get("audio_2", ""))
                    self.duration_1.set(config_data.get("duration_1", "0"))
                    self.duration_2.set(config_data.get("duration_2", "0"))
                    self.volume_1.set(config_data.get("volume_1", 100))
                    self.volume_2.set(config_data.get("volume_2", 100))
                    self.loop_1.set(config_data.get("loop_1", False))
                    self.loop_2.set(config_data.get("loop_2", False))
                    self.auto_start.set(config_data.get("auto_start", False))
            except Exception:
                pass

    def check_and_auto_start(self):
        if (os.path.exists(self.audio_1_path.get()) and 
            os.path.exists(self.audio_2_path.get()) and 
            self.com_port.get() and 
            self.com_port.get() != "No COM Ports Found"
        ):
            self.toggle_monitoring()

    # --- Controlled Playback Operations ---
    def handle_trigger_1(self):
        if self.player_1.is_playing():
            if self.timer_1:
                self.timer_1.cancel()
            self.player_1.stop()
            return

        if self.timer_1:
            self.timer_1.cancel()
        
        self.player_1.stop()
        
        if self.loop_1.get():
            media = self.vlc_instance.media_new(self.audio_1_path.get(), "input-repeat=65535")
        else:
            media = self.vlc_instance.media_new(self.audio_1_path.get())
            
        self.player_1.set_media(media)
        self.player_1.audio_set_volume(self.volume_1.get())
        self.player_1.play()
        
        try:
            secs = float(self.duration_1.get())
            if secs > 0:
                self.timer_1 = threading.Timer(secs, self.player_1.stop)
                self.timer_1.start()
        except ValueError:
            pass

    def handle_trigger_2(self):
        if self.player_2.is_playing():
            if self.timer_2:
                self.timer_2.cancel()
            self.player_2.stop()
            return

        if self.timer_2:
            self.timer_2.cancel()
        
        self.player_2.stop()
        
        if self.loop_2.get():
            media = self.vlc_instance.media_new(self.audio_2_path.get(), "input-repeat=65535")
        else:
            media = self.vlc_instance.media_new(self.audio_2_path.get())
            
        self.player_2.set_media(media)
        self.player_2.audio_set_volume(self.volume_2.get())
        self.player_2.play()
        
        try:
            secs = float(self.duration_2.get())
            if secs > 0:
                self.timer_2 = threading.Timer(secs, self.player_2.stop)
                self.timer_2.start()
        except ValueError:
            pass

    # --- Background Serial Monitoring Loop ---
    def toggle_monitoring(self):
        if self.is_running:
            self.is_running = False
            if self.timer_1: self.timer_1.cancel()
            if self.timer_2: self.timer_2.cancel()
            self.player_1.stop()
            self.player_2.stop()
            self.status_label.config(text="Status: Stopped", fg="red")
            self.start_btn.config(text="Start Monitoring")
            self.save_config()
        else:
            if not os.path.exists(self.audio_1_path.get()) or not os.path.exists(self.audio_2_path.get()):
                messagebox.showerror("Error", "Please select valid audio files for both triggers first.")
                return

            self.is_running = True
            self.status_label.config(text="Status: Monitoring...", fg="green")
            self.start_btn.config(text="Stop Monitoring")
            self.save_config()

            self.monitor_thread = threading.Thread(target=self.serial_loop, daemon=True)
            self.monitor_thread.start()

    def serial_loop(self):
        try:
            with serial.Serial(self.com_port.get(), 9600, timeout=1) as ser:
                ser.dtr = True
                ser.rts = True
                
                last_dsr = False
                last_cts = False

                while self.is_running:
                    current_dsr = ser.dsr
                    current_cts = ser.cts

                    if current_dsr and not last_dsr:
                        self.root.after(0, self.handle_trigger_1)
                        time.sleep(0.2) 

                    if current_cts and not last_cts:
                        self.root.after(0, self.handle_trigger_2)
                        time.sleep(0.2) 

                    last_dsr = current_dsr
                    last_cts = current_cts
                    time.sleep(0.03)

        except Exception as e:
            self.is_running = False
            self.root.after(0, lambda: messagebox.showerror("Serial Error", f"Failed to access serial port:\n{e}"))
            self.root.after(0, lambda: self.status_label.config(text="Status: Stopped", fg="red"))
            self.root.after(0, lambda: self.start_btn.config(text="Start Monitoring"))

if __name__ == "__main__":
    root = tk.Tk()
    app = SerialAudioApp(root)
    root.mainloop()


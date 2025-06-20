import os
import sys
import time
import ctypes

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QPushButton, QFileDialog, QLabel,
                            QSlider, QMessageBox, QSizePolicy, QGroupBox)
from PyQt5.QtCore import Qt, QTimer, QSettings
from PyQt5.QtGui import QKeyEvent
import vlc

# Workaround for PyInstaller
if getattr(sys, 'frozen', False):
    os.environ['PATH'] = sys._MEIPASS + os.pathsep + os.environ['PATH']

# Fix for PyQt5 DLL loading
os.environ['QT_PLUGIN_PATH'] = ''

class VideoCategorizer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("YourOrg", "VideoCategorizer")
        self.load_settings()
        
        # Set window title with version info
        self.setWindowTitle("Video Categorizer - V1.0, Developed by David Hofmann")
        
        # VLC setup
        self.vlc_instance = None
        self.player = None
        self.current_video = None
        self.video_files = []
        self.current_index = 0
        self.current_speed = 1.0
        self.brightness = 100
        self.current_stage = "primary"  # 'primary' or 'carnivorous'
        self.is_seeking = False
        self.was_playing = False
        self.seek_step = 5000  # 5 seconds
        
        # UI setup
        self.init_ui()
        
        # Playback position timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(30)
        
    def load_settings(self):
        """Load saved window geometry and settings"""
        self.restoreGeometry(self.settings.value("geometry", b""))
        self.restoreState(self.settings.value("windowState", b""))
        
    def closeEvent(self, event):
        """Save settings when window closes"""
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        super().closeEvent(event)
        
    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout()
        
        # Directory Selection
        dir_layout = QHBoxLayout()
        self.dir_label = QLabel("No directory selected")
        dir_button = QPushButton("Select Video Folder")
        dir_button.clicked.connect(self.select_directory)
        dir_layout.addWidget(self.dir_label)
        dir_layout.addWidget(dir_button)
        
        # Video Display
        self.video_widget = QWidget()
        self.video_widget.setStyleSheet("background-color: black;")
        self.video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Progress Bar with Time Display
        self.progress_bar = QSlider(Qt.Horizontal)
        self.progress_bar.setRange(0, 10000)
        self.progress_bar.sliderPressed.connect(self.start_seeking)
        self.progress_bar.sliderReleased.connect(self.end_seeking)
        self.progress_bar.sliderMoved.connect(self.set_position)
        self.time_label = QLabel("00:00 / 00:00")
        
        # Control buttons
        control_layout = QHBoxLayout()
        
        # Playback controls
        playback_group = QGroupBox("Playback Controls")
        playback_layout = QHBoxLayout()
        
        self.btn_play = QPushButton("Play (Space)")
        self.btn_play.clicked.connect(lambda: self.player.play() if self.player else None)
        playback_layout.addWidget(self.btn_play)
        
        self.btn_pause = QPushButton("Pause (Space)")
        self.btn_pause.clicked.connect(self.toggle_pause)
        playback_layout.addWidget(self.btn_pause)
        
        self.btn_stop = QPushButton("Stop (S)")
        self.btn_stop.clicked.connect(self.stop_video)
        playback_layout.addWidget(self.btn_stop)
        
        self.btn_prev = QPushButton("Previous (←)")
        self.btn_prev.clicked.connect(self.prev_video)
        playback_layout.addWidget(self.btn_prev)
        
        self.btn_next = QPushButton("Next (→)")
        self.btn_next.clicked.connect(self.next_video)
        playback_layout.addWidget(self.btn_next)
        
        # Add jump backward button
        btn_back = QPushButton("⏪ 5s (D)")
        btn_back.clicked.connect(self.jump_backward)
        playback_layout.addWidget(btn_back)

        # Add jump forward button
        btn_forward = QPushButton("5s ⏩ (K)")
        btn_forward.clicked.connect(self.jump_forward)
        playback_layout.addWidget(btn_forward)
        
        playback_group.setLayout(playback_layout)
        control_layout.addWidget(playback_group)
        
        # Speed controls
        speed_group = QGroupBox("Speed Controls")
        speed_layout = QHBoxLayout()
        
        self.btn_speed_down = QPushButton("Slower (F)")
        self.btn_speed_down.clicked.connect(self.decrease_speed)
        speed_layout.addWidget(self.btn_speed_down)
        
        self.btn_speed_up = QPushButton("Faster (J)")
        self.btn_speed_up.clicked.connect(self.increase_speed)
        speed_layout.addWidget(self.btn_speed_up)
        
        self.speed_label = QLabel(f"{self.current_speed:.1f}x")
        speed_layout.addWidget(self.speed_label)
        
        speed_group.setLayout(speed_layout)
        control_layout.addWidget(speed_group)
        
        # Brightness controls
        brightness_group = QGroupBox("Brightness Controls")
        brightness_layout = QHBoxLayout()
        
        self.btn_brightness_down = QPushButton("Darker (G)")
        self.btn_brightness_down.clicked.connect(self.decrease_brightness)
        brightness_layout.addWidget(self.btn_brightness_down)
        
        self.btn_brightness_up = QPushButton("Brighter (H)")
        self.btn_brightness_up.clicked.connect(self.increase_brightness)
        brightness_layout.addWidget(self.btn_brightness_up)
        
        self.brightness_label = QLabel(f"{self.brightness}%")
        brightness_layout.addWidget(self.brightness_label)
        
        brightness_group.setLayout(brightness_layout)
        control_layout.addWidget(brightness_group)
        
        # Primary Categories
        self.primary_group = QGroupBox("Primary Classification")
        primary_layout = QHBoxLayout()
        
        self.btn_carnivorous = QPushButton("Carnivorous (1)")
        self.btn_carnivorous.clicked.connect(self.enter_carnivorous_mode)
        primary_layout.addWidget(self.btn_carnivorous)
        
        self.btn_herbivorous = QPushButton("Herbivorous (2)")
        self.btn_herbivorous.clicked.connect(lambda: self.categorize_video("Herbivorous"))
        primary_layout.addWidget(self.btn_herbivorous)
        
        self.btn_not_animals = QPushButton("Not Animals (3)")
        self.btn_not_animals.clicked.connect(lambda: self.categorize_video("Not_Animals"))
        primary_layout.addWidget(self.btn_not_animals)
        
        self.btn_people = QPushButton("People (4)")
        self.btn_people.clicked.connect(lambda: self.categorize_video("People"))
        primary_layout.addWidget(self.btn_people)
        
        self.primary_group.setLayout(primary_layout)
        
        # Carnivorous Subcategories (initially hidden)
        self.carnivorous_group = QGroupBox("Carnivorous Species")
        carnivorous_layout = QVBoxLayout()
        
        # Row 1
        row1 = QHBoxLayout()
        self.btn_lion = QPushButton("Lion (1)")
        self.btn_lion.clicked.connect(lambda: self.categorize_carnivorous("Lion"))
        row1.addWidget(self.btn_lion)
        
        self.btn_leopard = QPushButton("Leopard (2)")
        self.btn_leopard.clicked.connect(lambda: self.categorize_carnivorous("Leopard"))
        row1.addWidget(self.btn_leopard)
        
        self.btn_wild_dog = QPushButton("Wild Dog (3)")
        self.btn_wild_dog.clicked.connect(lambda: self.categorize_carnivorous("Wild_Dog"))
        row1.addWidget(self.btn_wild_dog)
        
        self.btn_cheetah = QPushButton("Cheetah (4)")
        self.btn_cheetah.clicked.connect(lambda: self.categorize_carnivorous("Cheetah"))
        row1.addWidget(self.btn_cheetah)
        carnivorous_layout.addLayout(row1)
        
        # Row 2
        row2 = QHBoxLayout()
        self.btn_spotted_hyaena = QPushButton("Spotted Hyaena (5)")
        self.btn_spotted_hyaena.clicked.connect(lambda: self.categorize_carnivorous("Spotted_Hyaena"))
        row2.addWidget(self.btn_spotted_hyaena)
        
        self.btn_brown_hyaena = QPushButton("Brown Hyaena (6)")
        self.btn_brown_hyaena.clicked.connect(lambda: self.categorize_carnivorous("Brown_Hyaena"))
        row2.addWidget(self.btn_brown_hyaena)
        
        self.btn_fox = QPushButton("Fox (7)")
        self.btn_fox.clicked.connect(lambda: self.categorize_carnivorous("Fox"))
        row2.addWidget(self.btn_fox)
        
        self.btn_genet = QPushButton("Genet (8)")
        self.btn_genet.clicked.connect(lambda: self.categorize_carnivorous("Genet"))
        row2.addWidget(self.btn_genet)
        carnivorous_layout.addLayout(row2)
        
        # Row 3
        row3 = QHBoxLayout()
        self.btn_honeybadger = QPushButton("Honeybadger (9)")
        self.btn_honeybadger.clicked.connect(lambda: self.categorize_carnivorous("Honeybadger"))
        row3.addWidget(self.btn_honeybadger)
        
        self.btn_caracal = QPushButton("Caracal (C)")
        self.btn_caracal.clicked.connect(lambda: self.categorize_carnivorous("Caracal"))
        row3.addWidget(self.btn_caracal)
        
        self.btn_jackal = QPushButton("Jackal (J)")
        self.btn_jackal.clicked.connect(lambda: self.categorize_carnivorous("Jackal"))
        row3.addWidget(self.btn_jackal)
        
        self.btn_mongoose = QPushButton("Mongoose (M)")
        self.btn_mongoose.clicked.connect(lambda: self.categorize_carnivorous("Mongoose"))
        row3.addWidget(self.btn_mongoose)
        carnivorous_layout.addLayout(row3)
        
        # Row 4
        row4 = QHBoxLayout()
        self.btn_civet = QPushButton("Civet (V)")
        self.btn_civet.clicked.connect(lambda: self.categorize_carnivorous("Civet"))
        row4.addWidget(self.btn_civet)
        
        self.btn_small_cat = QPushButton("Small Cat (X)")
        self.btn_small_cat.clicked.connect(lambda: self.categorize_carnivorous("Small_Cat"))
        row4.addWidget(self.btn_small_cat)
        
        self.btn_back = QPushButton("Back to Primary (Esc)")
        self.btn_back.clicked.connect(self.exit_carnivorous_mode)
        row4.addWidget(self.btn_back)
        
        carnivorous_layout.addLayout(row4)
        self.carnivorous_group.setLayout(carnivorous_layout)
        self.carnivorous_group.setVisible(False)
        
        # Status label
        self.status_label = QLabel("No video loaded")
        self.status_label.setAlignment(Qt.AlignCenter)
        
        # Assemble Layout
        layout.addLayout(dir_layout)
        layout.addWidget(self.video_widget, stretch=1)
        
        progress_layout = QHBoxLayout()
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.time_label)
        layout.addLayout(progress_layout)
        layout.addLayout(control_layout)
        layout.addWidget(self.primary_group)
        layout.addWidget(self.carnivorous_group)
        layout.addWidget(self.status_label)
        central_widget.setLayout(layout)
        
        # Keyboard focus
        self.setFocusPolicy(Qt.StrongFocus)
        
        # Initialize keyboard shortcuts
        self.init_shortcuts()
        
        # Disable buttons until video is loaded
        self.set_buttons_enabled(False)
    
    def set_buttons_enabled(self, enabled):
        """Enable or disable all control buttons"""
        buttons = [
            self.btn_play, self.btn_pause, self.btn_stop,
            self.btn_prev, self.btn_next, self.btn_speed_down,
            self.btn_speed_up, self.btn_brightness_down,
            self.btn_brightness_up, self.btn_carnivorous,
            self.btn_herbivorous, self.btn_not_animals,
            self.btn_people
        ]
        for btn in buttons:
            btn.setEnabled(enabled)
    
    def init_shortcuts(self):
        """Initialize keyboard shortcut mappings"""
        # Primary stage shortcuts
        self.primary_shortcuts = {
            Qt.Key_1: ("Carnivorous", "primary"),
            Qt.Key_2: ("Herbivorous", "primary"),
            Qt.Key_3: ("Not Animals", "primary"),
            Qt.Key_4: ("People", "primary"),
            Qt.Key_S: "skip",
            Qt.Key_Q: "quit",
            Qt.Key_Space: "pause",
            Qt.Key_F: "speed_down",
            Qt.Key_J: "speed_up",
            Qt.Key_G: "brightness_down",
            Qt.Key_H: "brightness_up",
            Qt.Key_D: "seek_back",
            Qt.Key_K: "seek_forward"
        }
        
        # Carnivorous stage shortcuts
        self.carnivorous_shortcuts = {
            Qt.Key_1: "Lion",
            Qt.Key_2: "Leopard",
            Qt.Key_3: "Wild Dog",
            Qt.Key_4: "Cheetah",
            Qt.Key_5: "Spotted Hyaena",
            Qt.Key_6: "Brown Hyaena",
            Qt.Key_7: "Fox",
            Qt.Key_8: "Genet",
            Qt.Key_9: "Honeybadger",
            Qt.Key_C: "Caracal",
            Qt.Key_J: "Jackal",
            Qt.Key_M: "Mongoose",
            Qt.Key_V: "Civet",
            Qt.Key_X: "Small Cat",
            Qt.Key_Escape: "back",
            Qt.Key_S: "skip",
            Qt.Key_Q: "quit",
            Qt.Key_Space: "pause",
            Qt.Key_F: "speed_down",
            Qt.Key_J: "speed_up",
            Qt.Key_G: "brightness_down",
            Qt.Key_H: "brightness_up",
            Qt.Key_D: "seek_back",
            Qt.Key_K: "seek_forward"
        }
    
    def enter_carnivorous_mode(self):
        """Switch to carnivorous subcategory mode"""
        self.current_stage = "carnivorous"
        self.primary_group.setVisible(False)
        self.carnivorous_group.setVisible(True)
        self.status_label.setText("Select carnivorous species")
    
    def exit_carnivorous_mode(self):
        """Return to primary categorization mode"""
        self.current_stage = "primary"
        self.primary_group.setVisible(True)
        self.carnivorous_group.setVisible(False)
        self.status_label.setText("Select primary category")
    
    def find_vlc(self):
        """Locate system-installed VLC without bundling"""
        # Standard VLC installation paths
        paths = [
            r"C:\Program Files\VideoLAN\VLC",
            r"C:\Program Files (x86)\VideoLAN\VLC",
            os.path.expandvars(r"%PROGRAMFILES%\VideoLAN\VLC"),
            os.path.expandvars(r"%PROGRAMFILES(x86)%\VideoLAN\VLC")
        ]
    
        for path in paths:
            dll_path = os.path.join(path, "libvlc.dll")
            if os.path.exists(dll_path):
                return path
    
        return None

    def init_vlc(self):
        """Initialize using system VLC only"""
        vlc_path = self.find_vlc()
    
        if not vlc_path:
            QMessageBox.critical(
                self, "VLC Not Found",
                "VLC media player is required but not found.\n\n"
                "Please install VLC from https://www.videolan.org/\n"
                "and ensure it's installed in the default location."
            )
            return False

        try:
            # Add VLC to DLL search path
            os.environ['PATH'] = vlc_path + os.pathsep + os.environ['PATH']
        
            # Initialize VLC
            self.vlc_instance = vlc.Instance([f"--plugin-path={vlc_path}/plugins"])
            self.player = self.vlc_instance.media_player_new()
            return True
        
        except Exception as e:
            QMessageBox.critical(
                self, "VLC Error",
                f"VLC found but failed to initialize:\n\n{str(e)}\n\n"
                "Common solutions:\n"
                "1. Reinstall VLC (same architecture as this app)\n"
                "2. Restart after VLC installation\n"
                "3. Install Visual C++ Redistributable"
            )
            return False

    def find_vlc(self):
        """Enhanced VLC locator that handles all edge cases"""
        # Try these locations in order:
        search_paths = []
        
        # 1. Check PyInstaller bundle location
        if getattr(sys, 'frozen', False):
            search_paths.append(os.path.join(sys._MEIPASS, "vlc"))
            search_paths.append(os.path.dirname(sys.executable))
        
        # 2. Check standard VLC installation paths
        search_paths.extend([
            r"C:\Program Files\VideoLAN\VLC",
            r"C:\Program Files (x86)\VideoLAN\VLC",
            os.path.expandvars(r"%PROGRAMFILES%\VideoLAN\VLC"),
            os.path.expandvars(r"%PROGRAMFILES(x86)%\VideoLAN\VLC")
        ])
        
        # 3. Check environment variable
        if "VLC_PATH" in os.environ:
            search_paths.append(os.environ["VLC_PATH"])
        
        # Check each potential path
        for path in search_paths:
            try:
                if path and os.path.exists(os.path.join(path, "libvlc.dll")):
                    # Verify dependencies can load
                    ctypes.CDLL(os.path.join(path, "libvlc.dll"))
                    return path
            except Exception:
                continue
                
        return None

    def init_vlc(self):
        """Foolproof VLC initialization"""
        vlc_path = self.find_vlc()
    
        if not vlc_path:
            QMessageBox.critical(
                None, "VLC Not Found",
                "Could not locate VLC installation.\n\n"
                "Please install VLC from videolan.org or\n"
                "place these files next to the executable:\n"
                "- libvlc.dll\n- libvlccore.dll\n- plugins folder"
            )
            return False

        try:
            # Force add to PATH
            if sys.platform == "win32":
                os.environ['PATH'] = vlc_path + os.pathsep + os.environ['PATH']
                if hasattr(os, 'add_dll_directory'):  # Python 3.8+
                    os.add_dll_directory(vlc_path)
        
            # Initialize with explicit paths
            args = [
                f"--plugin-path={os.path.join(vlc_path, 'plugins')}",
                "--no-xlib"  # Important for Linux compatibility
            ]
            self.vlc_instance = vlc.Instance(args)
            self.player = self.vlc_instance.media_player_new()
            return True
        
        except Exception as e:
            QMessageBox.critical(
                None, "VLC Error",
                f"Failed to initialize VLC at {vlc_path}:\n\n{str(e)}\n\n"
                "This usually means:\n"
                "1. Missing Visual C++ Redistributable\n"
                "2. 32/64-bit architecture mismatch\n"
                "3. Corrupt VLC installation"
            )
            return False
    
    def init_vlc(self):
        """Initialize VLC player using the find_vlc() locator"""
        vlc_path = self.find_vlc()
    
        if not vlc_path:
            QMessageBox.critical(
                self, "VLC Not Found",
                "VLC media player is required but not found.\n\n"
                "Please install VLC from https://www.videolan.org/\n"
                "or place VLC files in application folder."
            )
            return False

        try:
            # Critical: Add VLC to DLL search path
            if sys.platform == "win32":
                os.environ['PATH'] = vlc_path + ';' + os.environ['PATH']
        
            # Initialize with plugin path
            args = [f"--plugin-path={os.path.join(vlc_path, 'plugins')}"]
            self.vlc_instance = vlc.Instance(args)
            self.player = self.vlc_instance.media_player_new()
            return True
        
        except Exception as e:
            QMessageBox.critical(
                self, "VLC Initialization Failed",
                f"Found VLC at {vlc_path} but failed to initialize:\n\n{str(e)}\n\n"
                "Possible solutions:\n"
                "1. Reinstall VLC (matching 32/64-bit version)\n"
                "2. Install Microsoft Visual C++ Redistributable\n"
                "3. Restart your computer after VLC installation"
            )
            return False
    
    def update_video_filters(self):
        """Update video brightness/contrast filters"""
        if self.player:
            self.player.video_set_adjust_int(vlc.VideoAdjustOption.Enable, 1)
            brightness_normalized = self.brightness / 100.0
            self.player.video_set_adjust_float(vlc.VideoAdjustOption.Brightness, brightness_normalized)
    
    def update_title(self):
        """Update window title with current status"""
        title = "Video Categorizer - V1.0, Developed by David Hofmann"
        if self.current_video:
            title += f" | {os.path.basename(self.current_video)}"
            title += f" | Speed: {self.current_speed:.1f}x"
            title += f" | Brightness: {self.brightness}%"
        self.setWindowTitle(title)
    
    def select_directory(self):
        """Select directory with video files"""
        folder = QFileDialog.getExistingDirectory(self, "Select Video Folder")
        if folder:
            self.video_folder = folder
            self.dir_label.setText(f"Folder: {folder}")
            self.video_files = [
                f for f in os.listdir(folder) 
                if f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))
            ]
            if self.video_files:
                self.current_index = 0
                self.play_video(0)
                self.video_widget.setFocus()
                self.set_buttons_enabled(True)
            else:
                self.set_buttons_enabled(False)
                self.status_label.setText("No video files found")
    
    def play_video(self, index):
        """Play video at specified index"""
        if index >= len(self.video_files):
            return
            
        self.current_index = index
        self.current_video = self.video_files[index]
        video_path = os.path.join(self.video_folder, self.current_video)
        
        if not self.init_vlc():
            return
            
        if sys.platform.startswith('linux'):
            self.player.set_xwindow(self.video_widget.winId())
        elif sys.platform == "win32":
            self.player.set_hwnd(self.video_widget.winId())
        
        media = self.vlc_instance.media_new(video_path)
        self.player.set_media(media)
        self.player.play()
        time.sleep(0.1)
        self.player.set_rate(self.current_speed)
        self.update_video_filters()
        self.update_title()
        self.current_stage = "primary"
        self.primary_group.setVisible(True)
        self.carnivorous_group.setVisible(False)
        self.status_label.setText(f"Playing: {os.path.basename(self.current_video)}")
    
    def toggle_pause(self):
        """Toggle pause/play state"""
        if self.player:
            if self.player.is_playing():
                self.player.pause()
                self.status_label.setText("Paused")
            else:
                self.player.play()
                self.status_label.setText("Playing")
    
    def stop_video(self):
        """Stop playback"""
        if self.player:
            self.player.stop()
            self.status_label.setText("Playback stopped")
    
    def increase_speed(self):
        """Increase playback speed"""
        self.current_speed = min(4.0, self.current_speed + 0.5)
        if self.player:
            self.player.set_rate(self.current_speed)
        self.speed_label.setText(f"{self.current_speed:.1f}x")
        self.update_title()
    
    def decrease_speed(self):
        """Decrease playback speed"""
        self.current_speed = max(0.5, self.current_speed - 0.5)
        if self.player:
            self.player.set_rate(self.current_speed)
        self.speed_label.setText(f"{self.current_speed:.1f}x")
        self.update_title()
    
    def increase_brightness(self):
        """Increase video brightness"""
        self.brightness = min(200, self.brightness + 10)
        self.update_video_filters()
        self.brightness_label.setText(f"{self.brightness}%")
        self.update_title()
    
    def decrease_brightness(self):
        """Decrease video brightness"""
        self.brightness = max(0, self.brightness - 10)
        self.update_video_filters()
        self.brightness_label.setText(f"{self.brightness}%")
        self.update_title()
    
    def start_seeking(self):
        """Pause playback while seeking starts"""
        self.is_seeking = True
        if self.player and self.player.is_playing():
            self.was_playing = True
            self.player.pause()
        else:
            self.was_playing = False
    
    def end_seeking(self):
        """Resume playback after seeking if needed"""
        self.is_seeking = False
        if self.was_playing and self.player:
            self.player.play()
    
    def set_position(self, position):
        """Set video position based on slider"""
        if self.is_seeking and self.player:
            length = self.player.get_length()
            if length > 0:
                new_time = int(position * length / 10000)
                self.player.set_time(new_time)
    
    def update_ui(self):
        """Update progress bar and time display"""
        if self.player and self.player.get_media():
            state = self.player.get_state()
            if state == vlc.State.Ended:
                self.player.stop()
                self.status_label.setText("Playback completed")
            
            if not self.is_seeking:
                length = self.player.get_length()
                time_pos = self.player.get_time()
                
                if length > 0 and time_pos >= 0:
                    # Update slider
                    self.progress_bar.blockSignals(True)
                    self.progress_bar.setValue(int(time_pos * 10000 / length))
                    self.progress_bar.blockSignals(False)
                    
                    # Update time label
                    current_sec = time_pos // 1000
                    total_sec = length // 1000
                    self.time_label.setText(
                        f"{current_sec//60:02d}:{current_sec%60:02d} / "
                        f"{total_sec//60:02d}:{total_sec%60:02d}"
                    )
    
    def categorize_video(self, category):
        """Move video to category subfolder"""
        if not self.current_video:
            return
            
        dest_folder = os.path.join(self.video_folder, category)
        os.makedirs(dest_folder, exist_ok=True)
        
        src = os.path.join(self.video_folder, self.current_video)
        dest = os.path.join(dest_folder, self.current_video)
        
        self.player.stop()
        time.sleep(0.3)
        
        try:
            os.rename(src, dest)
            self.status_label.setText(f"Moved to {category} folder")
            self.next_video()
        except Exception as e:
            self.status_label.setText(f"Error moving file: {str(e)}")
            QMessageBox.warning(self, "Move Failed", f"Could not move file:\n{str(e)}")
            if os.path.exists(src):
                self.play_video(self.current_index)
    
    def categorize_carnivorous(self, species):
        """Move video to carnivorous species subfolder"""
        if not self.current_video:
            return
            
        carnivorous_folder = os.path.join(self.video_folder, "Carnivorous")
        os.makedirs(carnivorous_folder, exist_ok=True)
        
        species_folder = os.path.join(carnivorous_folder, species)
        os.makedirs(species_folder, exist_ok=True)
        
        src = os.path.join(self.video_folder, self.current_video)
        dest = os.path.join(species_folder, self.current_video)
        
        self.player.stop()
        time.sleep(0.3)
        
        try:
            os.rename(src, dest)
            self.status_label.setText(f"Moved to Carnivorous/{species} folder")
            self.next_video()
        except Exception as e:
            self.status_label.setText(f"Error moving file: {str(e)}")
            QMessageBox.warning(self, "Move Failed", f"Could not move file:\n{str(e)}")
            if os.path.exists(src):
                self.play_video(self.current_index)
    
    def next_video(self):
        """Play next video in folder"""
        if self.video_files and self.current_video:
            next_index = self.current_index + 1
            if next_index < len(self.video_files):
                self.play_video(next_index)
            else:
                self.player.stop()
                self.current_video = None
                self.setWindowTitle("Video Categorizer - V1.0, Developed by David Hofmann")
                QMessageBox.information(self, "Done", "All videos have been processed!")
                self.set_buttons_enabled(False)
    
    def prev_video(self):
        """Play previous video in folder"""
        if self.video_files and self.current_video and self.current_index > 0:
            self.play_video(self.current_index - 1)
    
    def jump_forward(self):
        if self.player is not None:
            current_time = self.player.get_time()
            self.player.set_time(current_time + 5000)  # 5000 ms = 5 seconds

    def jump_backward(self):
        if self.player is not None:
            state = self.player.get_state()
            current_time = self.player.get_time()
            length = self.player.get_length()
            # If at the end, move just before the end
            if state == vlc.State.Ended or current_time >= length - 100:
                # Move to 5s before the end, or to 0 if video is shorter
                new_time = max(0, length - 5000)
                self.player.set_time(new_time)
                self.player.play()  # Resume playback if needed
            else:
                self.player.set_time(max(0, current_time - 5000))
    
    def keyPressEvent(self, event):
        """Handle all keyboard shortcuts"""
        if self.current_stage == "primary":
            action = self.primary_shortcuts.get(event.key())
        else:
            action = self.carnivorous_shortcuts.get(event.key())
        
        if action is None:
            return
            
        if isinstance(action, tuple):
            category, stage = action
            if category == "Carnivorous":
                self.enter_carnivorous_mode()
            else:
                self.categorize_video(category)
        elif action == "back":
            self.exit_carnivorous_mode()
        elif action in ["Lion", "Leopard", "Wild Dog", "Cheetah", "Spotted Hyaena", 
                       "Brown Hyaena", "Fox", "Genet", "Honeybadger", "Caracal", 
                       "Jackal", "Mongoose", "Civet", "Small Cat"]:
            self.categorize_carnivorous(action)
        elif action == "pause":
            self.toggle_pause()
        elif action == "speed_up":
            self.increase_speed()
        elif action == "speed_down":
            self.decrease_speed()
        elif action == "brightness_up":
            self.increase_brightness()
        elif action == "brightness_down":
            self.decrease_brightness()
        elif action == "seek_back":
            if self.player:
                new_time = max(0, self.player.get_time() - self.seek_step)
                self.player.set_time(new_time)
        elif action == "seek_forward":
            if self.player:
                new_time = min(
                    self.player.get_length(),
                    self.player.get_time() + self.seek_step
                )
                self.player.set_time(new_time)
        elif action == "skip":
            self.next_video()
        elif action == "quit":
            self.close()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VideoCategorizer()
    window.show()
    sys.exit(app.exec_())
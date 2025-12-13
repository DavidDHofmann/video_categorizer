import os
import sys
import time

import vlc
from PyQt5.QtCore import QSettings, Qt, QTimer
from PyQt5.QtGui import QKeyEvent
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

# Workaround for PyInstaller
if getattr(sys, "frozen", False):
    os.environ["PATH"] = sys._MEIPASS + os.pathsep + os.environ["PATH"]

# Fix for PyQt5 DLL loading
os.environ["QT_PLUGIN_PATH"] = ""


class VideoCategorizer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("YourOrg", "VideoCategorizer")
        self.load_settings()

        # Set window title with version info
        self.setWindowTitle("Video Categorizer - V1.3, Developed by David Hofmann")

        # VLC setup
        self.vlc_instance = None
        self.player = None
        self.current_video = None
        self.video_files = []
        self.current_index = 0
        self.current_speed = 1.0
        self.brightness = 100  # Normal brightness
        self.current_stage = "primary"
        self.is_seeking = False
        self.was_playing = False
        self.seek_step = 5000

        # Enhanced undo functionality
        self.undo_history = []  # List of moves for undo
        self.max_undo_levels = 10  # Configurable undo levels

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

        # Video Display Widget - SIMPLIFIED
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

        # Single Play/Pause button
        self.btn_play_pause = QPushButton("Play/Pause (P)")
        self.btn_play_pause.clicked.connect(self.toggle_pause)
        playback_layout.addWidget(self.btn_play_pause)

        self.btn_stop = QPushButton("Stop (S)")
        self.btn_stop.clicked.connect(self.stop_video)
        playback_layout.addWidget(self.btn_stop)

        # Enhanced undo button with counter
        self.btn_undo = QPushButton(f"Undo (U) [0]")
        self.btn_undo.clicked.connect(self.undo_last_move)
        self.btn_undo.setEnabled(False)
        playback_layout.addWidget(self.btn_undo)

        # Skip button
        self.btn_skip = QPushButton("Skip (0)")
        self.btn_skip.clicked.connect(self.skip_video)
        playback_layout.addWidget(self.btn_skip)

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

        # Primary Categories - REORDERED: Small Carnivores moved to end
        self.primary_group = QGroupBox("Primary Classification")
        primary_layout = QHBoxLayout()

        self.btn_carnivorous = QPushButton("Carnivorous (1)")
        self.btn_carnivorous.clicked.connect(self.enter_carnivorous_mode)
        primary_layout.addWidget(self.btn_carnivorous)

        self.btn_herbivorous = QPushButton("Herbivorous (2)")
        self.btn_herbivorous.clicked.connect(
            lambda: self.categorize_video("Herbivorous")
        )
        primary_layout.addWidget(self.btn_herbivorous)

        self.btn_not_animals = QPushButton("Not Animals (3)")
        self.btn_not_animals.clicked.connect(
            lambda: self.categorize_video("Not_Animals")
        )
        primary_layout.addWidget(self.btn_not_animals)

        self.btn_people = QPushButton("People (4)")
        self.btn_people.clicked.connect(lambda: self.categorize_video("People"))
        primary_layout.addWidget(self.btn_people)

        self.btn_small_carnivores = QPushButton("Small Carnivores (5)")
        self.btn_small_carnivores.clicked.connect(self.enter_small_carnivores_mode)
        primary_layout.addWidget(self.btn_small_carnivores)

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
        self.btn_wild_dog.clicked.connect(
            lambda: self.categorize_carnivorous("Wild_Dog")
        )
        row1.addWidget(self.btn_wild_dog)

        self.btn_cheetah = QPushButton("Cheetah (4)")
        self.btn_cheetah.clicked.connect(lambda: self.categorize_carnivorous("Cheetah"))
        row1.addWidget(self.btn_cheetah)
        carnivorous_layout.addLayout(row1)

        # Row 2
        row2 = QHBoxLayout()
        self.btn_spotted_hyaena = QPushButton("Spotted Hyaena (5)")
        self.btn_spotted_hyaena.clicked.connect(
            lambda: self.categorize_carnivorous("Spotted_Hyaena")
        )
        row2.addWidget(self.btn_spotted_hyaena)

        self.btn_brown_hyaena = QPushButton("Brown Hyaena (6)")
        self.btn_brown_hyaena.clicked.connect(
            lambda: self.categorize_carnivorous("Brown_Hyaena")
        )
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
        self.btn_honeybadger.clicked.connect(
            lambda: self.categorize_carnivorous("Honeybadger")
        )
        row3.addWidget(self.btn_honeybadger)

        self.btn_caracal = QPushButton("Caracal (C)")
        self.btn_caracal.clicked.connect(lambda: self.categorize_carnivorous("Caracal"))
        row3.addWidget(self.btn_caracal)

        self.btn_jackal = QPushButton("Jackal (L)")
        self.btn_jackal.clicked.connect(lambda: self.categorize_carnivorous("Jackal"))
        row3.addWidget(self.btn_jackal)

        self.btn_mongoose = QPushButton("Mongoose (M)")
        self.btn_mongoose.clicked.connect(
            lambda: self.categorize_carnivorous("Mongoose")
        )
        row3.addWidget(self.btn_mongoose)
        carnivorous_layout.addLayout(row3)

        # Row 4
        row4 = QHBoxLayout()
        self.btn_civet = QPushButton("Civet (V)")
        self.btn_civet.clicked.connect(lambda: self.categorize_carnivorous("Civet"))
        row4.addWidget(self.btn_civet)

        self.btn_small_cat = QPushButton("Small Cat (X)")
        self.btn_small_cat.clicked.connect(
            lambda: self.categorize_carnivorous("Small_Cat")
        )
        row4.addWidget(self.btn_small_cat)

        self.btn_back_carnivorous = QPushButton("Back to Primary (Esc)")
        self.btn_back_carnivorous.clicked.connect(self.exit_carnivorous_mode)
        row4.addWidget(self.btn_back_carnivorous)

        carnivorous_layout.addLayout(row4)
        self.carnivorous_group.setLayout(carnivorous_layout)
        self.carnivorous_group.setVisible(False)

        # Small Carnivores Subcategories (initially hidden) - NEW GROUP
        self.small_carnivores_group = QGroupBox("Small Carnivores Species")
        small_carnivores_layout = QVBoxLayout()

        # Row 1
        sc_row1 = QHBoxLayout()
        self.btn_mongoose_sc = QPushButton("Mongoose (1)")
        self.btn_mongoose_sc.clicked.connect(
            lambda: self.categorize_small_carnivore("Mongoose")
        )
        sc_row1.addWidget(self.btn_mongoose_sc)

        self.btn_serval = QPushButton("Serval (2)")
        self.btn_serval.clicked.connect(
            lambda: self.categorize_small_carnivore("Serval")
        )
        sc_row1.addWidget(self.btn_serval)

        self.btn_caracal_sc = QPushButton("Caracal (3)")
        self.btn_caracal_sc.clicked.connect(
            lambda: self.categorize_small_carnivore("Caracal")
        )
        sc_row1.addWidget(self.btn_caracal_sc)

        self.btn_wildcat = QPushButton("Wildcat (4)")
        self.btn_wildcat.clicked.connect(
            lambda: self.categorize_small_carnivore("Wildcat")
        )
        sc_row1.addWidget(self.btn_wildcat)
        small_carnivores_layout.addLayout(sc_row1)

        # Row 2
        sc_row2 = QHBoxLayout()
        self.btn_aardwolf = QPushButton("Aardwolf (5)")
        self.btn_aardwolf.clicked.connect(
            lambda: self.categorize_small_carnivore("Aardwolf")
        )
        sc_row2.addWidget(self.btn_aardwolf)

        self.btn_polecat = QPushButton("Polecat (6)")
        self.btn_polecat.clicked.connect(
            lambda: self.categorize_small_carnivore("Polecat")
        )
        sc_row2.addWidget(self.btn_polecat)

        self.btn_bat_eared_fox = QPushButton("Bat-eared Fox (7)")
        self.btn_bat_eared_fox.clicked.connect(
            lambda: self.categorize_small_carnivore("Bat_eared_Fox")
        )
        sc_row2.addWidget(self.btn_bat_eared_fox)

        self.btn_cape_fox = QPushButton("Cape Fox (8)")
        self.btn_cape_fox.clicked.connect(
            lambda: self.categorize_small_carnivore("Cape_Fox")
        )
        sc_row2.addWidget(self.btn_cape_fox)
        small_carnivores_layout.addLayout(sc_row2)

        # Row 3 - FIXED: Equal width buttons
        sc_row3 = QHBoxLayout()

        # Genet button
        self.btn_genet_sc = QPushButton("Genet (9)")
        self.btn_genet_sc.clicked.connect(
            lambda: self.categorize_small_carnivore("Genet")
        )

        # Unknown button
        self.btn_unknown_sc = QPushButton("Unknown (U)")
        self.btn_unknown_sc.clicked.connect(
            lambda: self.categorize_small_carnivore("Unknown")
        )

        # Back button
        self.btn_back_small_carnivores = QPushButton("Back to Primary (Esc)")
        self.btn_back_small_carnivores.clicked.connect(self.exit_small_carnivores_mode)

        # Add buttons with stretch factors for equal width
        sc_row3.addWidget(self.btn_genet_sc, 1)  # Stretch factor of 1
        sc_row3.addWidget(self.btn_unknown_sc, 1)  # Stretch factor of 1
        sc_row3.addWidget(self.btn_back_small_carnivores, 1)  # Stretch factor of 1

        small_carnivores_layout.addLayout(sc_row3)
        self.small_carnivores_group.setLayout(small_carnivores_layout)
        self.small_carnivores_group.setVisible(False)

        # Status label
        self.status_label = QLabel("No video loaded")
        self.status_label.setAlignment(Qt.AlignCenter)

        # Undo history display
        self.undo_status_label = QLabel("Undo history: 0 moves")
        self.undo_status_label.setAlignment(Qt.AlignCenter)
        self.undo_status_label.setStyleSheet("color: gray;")

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
        layout.addWidget(self.small_carnivores_group)
        layout.addWidget(self.status_label)
        layout.addWidget(self.undo_status_label)
        central_widget.setLayout(layout)

        # Prevent buttons from capturing spacebar
        for button in [
            self.btn_play_pause,
            self.btn_stop,
            self.btn_undo,
            self.btn_skip,
            self.btn_speed_down,
            self.btn_speed_up,
            self.btn_brightness_down,
            self.btn_brightness_up,
            self.btn_carnivorous,
            self.btn_small_carnivores,
            self.btn_herbivorous,
            self.btn_not_animals,
            self.btn_people,
            dir_button,
            btn_back,
            btn_forward,
        ]:
            button.setFocusPolicy(Qt.NoFocus)

        # Keyboard focus
        self.setFocusPolicy(Qt.StrongFocus)

        # Initialize keyboard shortcuts
        self.init_shortcuts()

        # Disable buttons until video is loaded
        self.set_buttons_enabled(False)

    def set_buttons_enabled(self, enabled):
        """Enable or disable all control buttons"""
        buttons = [
            self.btn_play_pause,
            self.btn_stop,
            self.btn_undo,
            self.btn_skip,
            self.btn_speed_down,
            self.btn_speed_up,
            self.btn_brightness_down,
            self.btn_brightness_up,
            self.btn_carnivorous,
            self.btn_small_carnivores,
            self.btn_herbivorous,
            self.btn_not_animals,
            self.btn_people,
        ]
        for btn in buttons:
            btn.setEnabled(enabled)

    def find_vlc(self):
        """Find system-installed VLC"""
        paths = [
            r"C:\Program Files\VideoLAN\VLC",
            r"C:\Program Files (x86)\VideoLAN\VLC",
            os.path.expandvars(r"%PROGRAMFILES%\VideoLAN\VLC"),
            os.path.expandvars(r"%PROGRAMFILES(x86)%\VideoLAN\VLC"),
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
                self,
                "VLC Not Found",
                "VLC media player is required but not found.\n\n"
                "Please install VLC from https://www.videolan.org/\n"
                "and ensure it's installed in the default location.",
            )
            return False

        try:
            # Add VLC to DLL search path
            os.environ["PATH"] = vlc_path + os.pathsep + os.environ["PATH"]

            # Initialize VLC with basic arguments
            args = [f"--plugin-path={vlc_path}/plugins"]
            self.vlc_instance = vlc.Instance(args)

            if not self.vlc_instance:
                raise Exception("Failed to create VLC instance")

            # Create media player
            self.player = self.vlc_instance.media_player_new()
            if not self.player:
                raise Exception("Failed to create media player")

            return True

        except Exception as e:
            error_msg = f"VLC initialization failed:\n\n{str(e)}\n\n"
            error_msg += "Common solutions:\n"
            error_msg += "1. Reinstall VLC (64-bit version from videolan.org)\n"
            error_msg += "2. Restart computer after VLC installation\n"
            error_msg += "3. Install Microsoft Visual C++ Redistributable"

            QMessageBox.critical(self, "VLC Error", error_msg)
            return False

    def init_shortcuts(self):
        """Initialize keyboard shortcut mappings"""
        # Primary stage shortcuts - REORDERED: 5 is now Small Carnivores
        self.primary_shortcuts = {
            Qt.Key_1: ("Carnivorous", "primary"),
            Qt.Key_2: ("Herbivorous", "primary"),
            Qt.Key_3: ("Not Animals", "primary"),
            Qt.Key_4: ("People", "primary"),
            Qt.Key_5: ("Small Carnivores", "primary"),
            Qt.Key_0: "skip",
            Qt.Key_U: "undo",
            Qt.Key_Q: "quit",
            Qt.Key_P: "pause",
            Qt.Key_F: "speed_down",
            Qt.Key_J: "speed_up",
            Qt.Key_G: "brightness_down",
            Qt.Key_H: "brightness_up",
            Qt.Key_D: "seek_back",
            Qt.Key_K: "seek_forward",
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
            Qt.Key_L: "Jackal",
            Qt.Key_M: "Mongoose",
            Qt.Key_V: "Civet",
            Qt.Key_X: "Small Cat",
            Qt.Key_Escape: "back",
            Qt.Key_0: "skip",
            Qt.Key_U: "undo",
            Qt.Key_Q: "quit",
            Qt.Key_P: "pause",
            Qt.Key_F: "speed_down",
            Qt.Key_J: "speed_up",
            Qt.Key_G: "brightness_down",
            Qt.Key_H: "brightness_up",
            Qt.Key_D: "seek_back",
            Qt.Key_K: "seek_forward",
        }

        # Small Carnivores stage shortcuts - NEW
        self.small_carnivores_shortcuts = {
            Qt.Key_1: "Mongoose",
            Qt.Key_2: "Serval",
            Qt.Key_3: "Caracal",
            Qt.Key_4: "Wildcat",
            Qt.Key_5: "Aardwolf",
            Qt.Key_6: "Polecat",
            Qt.Key_7: "Bat_eared_Fox",
            Qt.Key_8: "Cape_Fox",
            Qt.Key_9: "Genet",
            Qt.Key_U: "Unknown",
            Qt.Key_Escape: "back",
            Qt.Key_0: "skip",
            Qt.Key_U: "undo",
            Qt.Key_Q: "quit",
            Qt.Key_P: "pause",
            Qt.Key_F: "speed_down",
            Qt.Key_J: "speed_up",
            Qt.Key_G: "brightness_down",
            Qt.Key_H: "brightness_up",
            Qt.Key_D: "seek_back",
            Qt.Key_K: "seek_forward",
        }

    def enter_carnivorous_mode(self):
        """Switch to carnivorous subcategory mode"""
        self.current_stage = "carnivorous"
        self.primary_group.setVisible(False)
        self.carnivorous_group.setVisible(True)
        self.small_carnivores_group.setVisible(False)
        self.status_label.setText("Select carnivorous species")

    def enter_small_carnivores_mode(self):
        """Switch to small carnivores subcategory mode - NEW METHOD"""
        self.current_stage = "small_carnivores"
        self.primary_group.setVisible(False)
        self.carnivorous_group.setVisible(False)
        self.small_carnivores_group.setVisible(True)
        self.status_label.setText("Select small carnivore species")

    def exit_carnivorous_mode(self):
        """Return to primary categorization mode"""
        self.current_stage = "primary"
        self.primary_group.setVisible(True)
        self.carnivorous_group.setVisible(False)
        self.small_carnivores_group.setVisible(False)
        self.status_label.setText("Select primary category")

    def exit_small_carnivores_mode(self):
        """Return to primary categorization mode from small carnivores - NEW METHOD"""
        self.current_stage = "primary"
        self.primary_group.setVisible(True)
        self.carnivorous_group.setVisible(False)
        self.small_carnivores_group.setVisible(False)
        self.status_label.setText("Select primary category")

    def update_video_filters(self):
        """Update video brightness/contrast filters - SIMPLIFIED"""
        if self.player:
            try:
                # Enable video adjustment
                self.player.video_set_adjust_int(vlc.VideoAdjustOption.Enable, 1)
                # Set brightness (0.0-2.0 where 1.0 is normal)
                brightness_normalized = self.brightness / 100.0
                self.player.video_set_adjust_float(
                    vlc.VideoAdjustOption.Brightness, brightness_normalized
                )
                # Reset contrast to normal (1.0)
                self.player.video_set_adjust_float(vlc.VideoAdjustOption.Contrast, 1.0)
            except Exception as e:
                print(f"Video filter error (non-critical): {e}")

    def update_title(self):
        """Update window title with current status"""
        title = "Video Categorizer - V1.3, Developed by David Hofmann"
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
                f
                for f in os.listdir(folder)
                if f.lower().endswith((".mp4", ".mov", ".avi", ".mkv"))
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

        # Stop any existing playback
        if self.player:
            try:
                self.player.stop()
            except:
                pass
            time.sleep(0.1)

        self.current_index = index
        self.current_video = self.video_files[index]
        video_path = os.path.join(self.video_folder, self.current_video)

        if not self.init_vlc():
            return

        # Check if VLC instance and player were created
        if not self.vlc_instance or not self.player:
            QMessageBox.critical(
                self,
                "VLC Error",
                "VLC player not properly initialized.\n\n"
                "Please ensure VLC is installed correctly.",
            )
            return

        # Embed VLC in the widget
        if sys.platform == "win32":
            try:
                self.player.set_hwnd(int(self.video_widget.winId()))
            except Exception as e:
                print(f"Window handle error: {e}")

        # Load and play the media
        try:
            media = self.vlc_instance.media_new(video_path)
            self.player.set_media(media)

            # Apply settings
            self.player.set_rate(self.current_speed)
            self.update_video_filters()

            # Play
            self.player.play()

            # Wait briefly for playback to start
            time.sleep(0.2)

            # Update UI
            self.update_title()
            self.current_stage = "primary"
            self.primary_group.setVisible(True)
            self.carnivorous_group.setVisible(False)
            self.small_carnivores_group.setVisible(False)
            self.status_label.setText(
                f"Playing: {os.path.basename(self.current_video)}"
            )
            self.btn_play_pause.setText("Pause (P)")

        except Exception as e:
            QMessageBox.critical(
                self, "Playback Error", f"Failed to play video:\n\n{str(e)}"
            )
            self.status_label.setText(f"Failed to play: {self.current_video}")

    def toggle_pause(self):
        """Toggle pause/play state"""
        if not self.player:
            return

        state = self.player.get_state()

        # If video is ended, restart it
        if state == vlc.State.Ended:
            self.player.stop()
            self.player.play()
            self.status_label.setText("Playing (restarted)")
            self.btn_play_pause.setText("Pause (P)")
            return

        # Normal pause/play toggle
        if self.player.is_playing():
            self.player.pause()
            self.status_label.setText("Paused")
            self.btn_play_pause.setText("Play (P)")
        else:
            self.player.play()
            self.status_label.setText("Playing")
            self.btn_play_pause.setText("Pause (P)")

    def stop_video(self):
        """Stop playback"""
        if self.player:
            self.player.stop()
            self.status_label.setText("Playback stopped")
            self.btn_play_pause.setText("Play (P)")

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
        self.status_label.setText(f"Brightness: {self.brightness}%")

    def decrease_brightness(self):
        """Decrease video brightness"""
        self.brightness = max(0, self.brightness - 10)
        self.update_video_filters()
        self.brightness_label.setText(f"{self.brightness}%")
        self.update_title()
        self.status_label.setText(f"Brightness: {self.brightness}%")

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

    def add_to_undo_history(self, move_info):
        """Add a move to the undo history"""
        # Limit history size
        if len(self.undo_history) >= self.max_undo_levels:
            self.undo_history.pop(0)

        self.undo_history.append(move_info)
        self.update_undo_ui()

    def update_undo_ui(self):
        """Update undo-related UI elements"""
        count = len(self.undo_history)
        self.btn_undo.setText(f"Undo (U) [{count}]")
        self.btn_undo.setEnabled(count > 0)
        self.undo_status_label.setText(f"Undo history: {count} move(s) available")

        # Update tooltip with history preview
        if count > 0:
            preview = "Recent moves:\n"
            for i, move in enumerate(reversed(self.undo_history[-3:]), 1):
                filename = os.path.basename(move["src"])
                category = move.get("category", "Unknown")
                preview += f"{i}. {filename} → {category}\n"
            self.btn_undo.setToolTip(preview.strip())

    def undo_last_move(self):
        """Undo the most recent move"""
        if not self.undo_history:
            return

        move_info = self.undo_history[-1]
        src = move_info["dest"]
        dest = move_info["src"]
        category = move_info.get("category", "Unknown")

        try:
            # Stop player first
            if self.player:
                self.player.stop()
                time.sleep(0.3)

            # Move file back
            if os.path.exists(src):
                os.rename(src, dest)
                self.status_label.setText(
                    f"Undid move: {os.path.basename(dest)} → {category}"
                )
            else:
                QMessageBox.warning(
                    self, "Undo Failed", "Source file no longer exists."
                )
                # Remove from history if file doesn't exist
                self.undo_history.pop()
                self.update_undo_ui()
                return

            # Clean up empty folders
            self.cleanup_empty_folders(src)

            # Update file list
            filename = os.path.basename(dest)
            if filename not in self.video_files:
                self.video_files.append(filename)
                self.video_files.sort()

            # Remove from undo history
            self.undo_history.pop()
            self.update_undo_ui()

            # Find and play the restored file
            new_index = self.video_files.index(filename)
            self.play_video(new_index)

        except Exception as e:
            QMessageBox.warning(self, "Undo Failed", f"Could not undo:\n{str(e)}")

    def cleanup_empty_folders(self, moved_from_path):
        """Clean up empty folders after undo"""
        try:
            # Get the folder that contained the file
            folder = os.path.dirname(moved_from_path)

            # Check if folder is empty
            if os.path.exists(folder) and not os.listdir(folder):
                # Remove the empty folder
                os.rmdir(folder)

                # If this was a carnivorous species folder, check if Carnivorous folder is now empty
                carnivorous_folder = os.path.dirname(folder)
                if os.path.basename(carnivorous_folder) == "Carnivorous":
                    if os.path.exists(carnivorous_folder) and not os.listdir(
                        carnivorous_folder
                    ):
                        os.rmdir(carnivorous_folder)

        except Exception as e:
            print(f"Error cleaning up folders: {e}")

    def skip_video(self):
        """Skip current video without categorizing"""
        if self.current_video:
            self.status_label.setText(f"Skipped: {self.current_video}")
            # Move to next video
            next_index = self.current_index + 1
            if next_index < len(self.video_files):
                self.play_video(next_index)
            else:
                self.player.stop()
                self.current_video = None
                self.setWindowTitle(
                    "Video Categorizer - V1.3, Developed by David Hofmann"
                )
                QMessageBox.information(self, "Done", "All videos have been processed!")
                self.set_buttons_enabled(False)

    def categorize_video(self, category):
        """Move video to category subfolder"""
        if not self.current_video:
            return

        dest_folder = os.path.join(self.video_folder, category)
        os.makedirs(dest_folder, exist_ok=True)

        src = os.path.join(self.video_folder, self.current_video)
        dest = os.path.join(dest_folder, self.current_video)

        # Store move in history
        move_info = {
            "src": src,
            "dest": dest,
            "category": category,
            "timestamp": time.time(),
        }
        self.add_to_undo_history(move_info)

        self.player.stop()
        time.sleep(0.3)

        try:
            os.rename(src, dest)
            self.status_label.setText(f"Moved to {category} folder")
            self.skip_video()
        except Exception as e:
            self.status_label.setText(f"Error moving file: {str(e)}")
            QMessageBox.warning(self, "Move Failed", f"Could not move file:\n{str(e)}")
            # Remove failed move from history
            if self.undo_history and self.undo_history[-1] == move_info:
                self.undo_history.pop()
                self.update_undo_ui()
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

        # Store move in history
        move_info = {
            "src": src,
            "dest": dest,
            "category": f"Carnivorous/{species}",
            "timestamp": time.time(),
            "carnivorous_species": species,
        }
        self.add_to_undo_history(move_info)

        self.player.stop()
        time.sleep(0.3)

        try:
            os.rename(src, dest)
            self.status_label.setText(f"Moved to Carnivorous/{species} folder")
            self.skip_video()
        except Exception as e:
            self.status_label.setText(f"Error moving file: {str(e)}")
            QMessageBox.warning(self, "Move Failed", f"Could not move file:\n{str(e)}")
            # Remove failed move from history
            if self.undo_history and self.undo_history[-1] == move_info:
                self.undo_history.pop()
                self.update_undo_ui()
            if os.path.exists(src):
                self.play_video(self.current_index)

    def categorize_small_carnivore(self, species):
        """Move video to small carnivore species subfolder - NEW METHOD"""
        if not self.current_video:
            return

        small_carnivores_folder = os.path.join(self.video_folder, "Small_Carnivores")
        os.makedirs(small_carnivores_folder, exist_ok=True)

        species_folder = os.path.join(small_carnivores_folder, species)
        os.makedirs(species_folder, exist_ok=True)

        src = os.path.join(self.video_folder, self.current_video)
        dest = os.path.join(species_folder, self.current_video)

        # Store move in history
        move_info = {
            "src": src,
            "dest": dest,
            "category": f"Small_Carnivores/{species}",
            "timestamp": time.time(),
            "small_carnivore_species": species,
        }
        self.add_to_undo_history(move_info)

        self.player.stop()
        time.sleep(0.3)

        try:
            os.rename(src, dest)
            self.status_label.setText(f"Moved to Small_Carnivores/{species} folder")
            self.skip_video()
        except Exception as e:
            self.status_label.setText(f"Error moving file: {str(e)}")
            QMessageBox.warning(self, "Move Failed", f"Could not move file:\n{str(e)}")
            # Remove failed move from history
            if self.undo_history and self.undo_history[-1] == move_info:
                self.undo_history.pop()
                self.update_undo_ui()
            if os.path.exists(src):
                self.play_video(self.current_index)

    def update_ui(self):
        """Update progress bar and time display"""
        if self.player and self.player.get_media():
            state = self.player.get_state()
            if state == vlc.State.Ended:
                self.btn_play_pause.setText("Play (P)")

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
                        f"{current_sec // 60:02d}:{current_sec % 60:02d} / "
                        f"{total_sec // 60:02d}:{total_sec % 60:02d}"
                    )

    def jump_forward(self):
        if self.player is not None:
            current_time = self.player.get_time()
            self.player.set_time(current_time + 5000)

    def jump_backward(self):
        if self.player is not None:
            state = self.player.get_state()
            current_time = self.player.get_time()
            length = self.player.get_length()
            if state == vlc.State.Ended or current_time >= length - 100:
                new_time = max(0, length - 5000)
                self.player.set_time(new_time)
                self.player.play()
            else:
                self.player.set_time(max(0, current_time - 5000))

    def keyPressEvent(self, event):
        """Handle all keyboard shortcuts"""
        # Always process P key for pause/play regardless of focus
        if event.key() == Qt.Key_P:
            self.toggle_pause()
            return

        if self.current_stage == "primary":
            action = self.primary_shortcuts.get(event.key())
        elif self.current_stage == "carnivorous":
            action = self.carnivorous_shortcuts.get(event.key())
        elif self.current_stage == "small_carnivores":
            action = self.small_carnivores_shortcuts.get(event.key())
        else:
            action = None

        if action is None:
            return

        if isinstance(action, tuple):
            category, stage = action
            if category == "Carnivorous":
                self.enter_carnivorous_mode()
            elif category == "Small Carnivores":
                self.enter_small_carnivores_mode()
            else:
                self.categorize_video(category)
        elif action == "back":
            if self.current_stage == "carnivorous":
                self.exit_carnivorous_mode()
            elif self.current_stage == "small_carnivores":
                self.exit_small_carnivores_mode()
        elif action == "undo":
            self.undo_last_move()
        elif action == "skip":
            self.skip_video()
        elif action in [
            "Lion",
            "Leopard",
            "Wild Dog",
            "Cheetah",
            "Spotted Hyaena",
            "Brown Hyaena",
            "Fox",
            "Genet",
            "Honeybadger",
            "Caracal",
            "Jackal",
            "Mongoose",
            "Civet",
            "Small Cat",
        ]:
            self.categorize_carnivorous(action)
        elif action in [
            "Mongoose",
            "Serval",
            "Caracal",
            "Wildcat",
            "Aardwolf",
            "Polecat",
            "Bat_eared_Fox",
            "Cape_Fox",
            "Genet",
            "Unknown",
        ]:
            self.categorize_small_carnivore(action)
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
                    self.player.get_length(), self.player.get_time() + self.seek_step
                )
                self.player.set_time(new_time)
        elif action == "quit":
            self.close()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VideoCategorizer()
    window.show()
    sys.exit(app.exec_())

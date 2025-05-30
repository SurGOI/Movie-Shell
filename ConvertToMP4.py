import sys
import os
import shutil # Import shutil for shutil.which()

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton,
    QLabel, QListWidget, QProgressBar, QFileDialog, QMessageBox,
    QHBoxLayout, QScrollArea
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtGui import QFont, QColor, QPalette

import subprocess

# --- FFmpeg Conversion Worker Thread ---
class FFmpegWorker(QThread):
    # Signals for communication with the main GUI thread
    conversion_started = pyqtSignal(str)
    conversion_progress = pyqtSignal(str, int) # file_path, percentage (not fully implemented)
    conversion_finished = pyqtSignal(str, bool) # file_path, success
    conversion_error = pyqtSignal(str, str) # file_path, error_message

    def __init__(self, input_files, ffmpeg_path=None):
        super().__init__()
        self.input_files = input_files
        self.ffmpeg_path = ffmpeg_path # Store the path to ffmpeg
        self._is_running = True

    def run(self):
        if not self.ffmpeg_path:
            self.conversion_error.emit("", "FFmpeg executable path not provided.")
            return

        for input_file in self.input_files:
            if not self._is_running:
                # Emit a signal to indicate stopping for this file if it was running
                self.conversion_error.emit(input_file, "Conversion stopped by user.")
                break # Stop if requested

            output_file = os.path.splitext(input_file)[0] + ".mp4"
            self.conversion_started.emit(input_file)

            command = [
                self.ffmpeg_path, # Use the determined ffmpeg path
                '-i', input_file,
                '-c:v', 'libx264', # H.264 video codec
                '-preset', 'medium', # Encoding speed vs. compression ratio
                '-crf', '23', # Constant Rate Factor (quality, lower is better)
                '-c:a', 'aac', # AAC audio codec
                '-b:a', '128k', # Audio bitrate
                '-hide_banner', # Hide FFmpeg banner
                '-loglevel', 'error', # Only show errors
                output_file
            ]

            process = None
            try:
                # For Windows:
                if sys.platform == "win32":
                    process = subprocess.Popen(command,
                                               stdout=subprocess.PIPE,
                                               stderr=subprocess.PIPE,
                                               stdin=subprocess.PIPE,
                                               creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
                                               )
                else: # For Linux/macOS
                    process = subprocess.Popen(command,
                                               stdout=subprocess.PIPE,
                                               stderr=subprocess.PIPE,
                                               stdin=subprocess.PIPE
                                               )

                stdout, stderr = process.communicate() # Wait for process to complete

                if process.returncode == 0:
                    self.conversion_finished.emit(input_file, True)
                else:
                    error_message = stderr.decode('utf-8', errors='ignore')
                    self.conversion_error.emit(input_file, error_message)

            except FileNotFoundError:
                self.conversion_error.emit(input_file, f"FFmpeg not found at '{self.ffmpeg_path}'. Check installation.")
                self.conversion_finished.emit(input_file, False)
            except Exception as e:
                self.conversion_error.emit(input_file, f"An unexpected error occurred: {e}")
                self.conversion_finished.emit(input_file, False)
            finally:
                if process and process.poll() is None: # If process is still running, terminate it
                    process.terminate()
                    process.wait() # Ensure it's fully terminated

    def stop(self):
        self._is_running = False

# --- Main Application Window ---
class MovieConverterApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Retro Video Converter")
        self.setGeometry(100, 100, 800, 600)

        self.input_files = []
        self.conversion_workers = {} # To keep track of active conversions
        self.ffmpeg_path = self.find_ffmpeg() # Try to find ffmpeg on startup

        self.init_ui()
        self.apply_retro_style()

        if not self.ffmpeg_path:
            QMessageBox.warning(self, "FFmpeg Not Found",
                                "FFmpeg executable could not be found automatically.\n"
                                "Please ensure FFmpeg is installed and added to your system's PATH, "
                                "or specify its location manually if prompted by a future feature.")
            self.convert_button.setEnabled(False) # Disable convert button if ffmpeg isn't found
            self.status_bar_label.setText("Error: FFmpeg not found. Conversion disabled.")


    def find_ffmpeg(self):
        """
        Attempts to find the ffmpeg executable.
        1. Checks if 'ffmpeg' is in the system's PATH using shutil.which().
        2. (Optional: Add more specific common paths here if 1 fails, e.g., for Windows: 'C:\\ffmpeg\\bin\\ffmpeg.exe')
        """
        ffmpeg_exe = "ffmpeg"
        if sys.platform == "win32":
            ffmpeg_exe += ".exe"

        # Try to find it in PATH
        found_path = shutil.which(ffmpeg_exe)
        if found_path:
            print(f"Found FFmpeg at: {found_path}")
            return found_path
        else:
            print("FFmpeg not found in system PATH.")
            # You could add logic here to prompt the user or search specific directories
            # For example, on Windows, often it's in C:\ffmpeg\bin
            # if sys.platform == "win32" and os.path.exists("C:\\ffmpeg\\bin\\ffmpeg.exe"):
            #     print("Found FFmpeg at C:\\ffmpeg\\bin\\ffmpeg.exe")
            #     return "C:\\ffmpeg\\bin\\ffmpeg.exe"
            return None # Return None if not found

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Title
        title_label = QLabel("QUANTUM CONVERT-O-MATIC 5000")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setObjectName("titleLabel") # For QSS styling
        main_layout.addWidget(title_label)

        # File Selection Area
        file_selection_layout = QHBoxLayout()
        self.browse_button = QPushButton("Browse Files...")
        self.browse_button.clicked.connect(self.browse_files)
        file_selection_layout.addWidget(self.browse_button)

        self.clear_button = QPushButton("Clear List")
        self.clear_button.clicked.connect(self.clear_file_list)
        file_selection_layout.addWidget(self.clear_button)
        main_layout.addLayout(file_selection_layout)

        # File List
        file_list_label = QLabel("Files to Convert:")
        main_layout.addWidget(file_list_label)
        self.file_list_widget = QListWidget()
        main_layout.addWidget(self.file_list_widget)

        # Conversion Control
        convert_layout = QHBoxLayout()
        self.convert_button = QPushButton("Convert to MP4")
        self.convert_button.clicked.connect(self.start_conversion)
        self.convert_button.setEnabled(False) # Disable until files are added
        convert_layout.addWidget(self.convert_button)

        self.stop_all_button = QPushButton("Stop All Conversions")
        self.stop_all_button.clicked.connect(self.stop_all_conversions)
        self.stop_all_button.setEnabled(False) # Disable initially
        convert_layout.addWidget(self.stop_all_button)
        main_layout.addLayout(convert_layout)

        # Progress Area
        progress_label = QLabel("Conversion Status:")
        main_layout.addWidget(progress_label)

        self.progress_scroll_area = QScrollArea()
        self.progress_scroll_area.setWidgetResizable(True)
        self.progress_container_widget = QWidget()
        self.progress_layout = QVBoxLayout(self.progress_container_widget)
        self.progress_layout.setAlignment(Qt.AlignmentFlag.AlignTop) # Align items to the top
        self.progress_scroll_area.setWidget(self.progress_container_widget)
        main_layout.addWidget(self.progress_scroll_area)

        # Status Bar
        self.status_bar_label = QLabel("Ready for input...")
        main_layout.addWidget(self.status_bar_label)


    def apply_retro_style(self):
        # ... (same as before) ...
        dark_blue = "#0A1128"
        medium_blue = "#001F54"
        light_blue = "#034078"
        gold = "#F6C101"
        red = "#BF0603"
        white = "#E0E0E0"

        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {dark_blue};
                border: 3px outset {medium_blue};
            }}
            QWidget {{
                background-color: {dark_blue};
                color: {white};
                font-family: 'Courier New', monospace;
                font-size: 14px;
            }}
            #titleLabel {{
                color: {gold};
                font-size: 28px;
                font-weight: bold;
                margin-bottom: 15px;
                border: 2px solid {light_blue};
                padding: 10px;
                background-color: {medium_blue};
                border-radius: 5px;
            }}
            QPushButton {{
                background-color: {light_blue};
                color: {white};
                border: 2px outset {medium_blue};
                padding: 8px 15px;
                border-radius: 5px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {medium_blue};
            }}
            QPushButton:pressed {{
                background-color: {dark_blue};
                border-style: inset;
            }}
            QPushButton:disabled {{
                background-color: #555555;
                color: #AAAAAA;
                border-style: dotted;
            }}
            QLabel {{
                color: {gold};
                margin-top: 10px;
                margin-bottom: 5px;
            }}
            QListWidget {{
                background-color: {medium_blue};
                color: {white};
                border: 2px inset {dark_blue};
                padding: 5px;
                selection-background-color: {light_blue};
            }}
            QProgressBar {{
                border: 2px solid {light_blue};
                border-radius: 5px;
                text-align: center;
                color: {white};
                background-color: {medium_blue};
            }}
            QProgressBar::chunk {{
                background-color: {gold};
                border-radius: 3px;
            }}
            QScrollArea {{
                border: 2px inset {medium_blue};
                background-color: {dark_blue};
            }}
            /* Specific style for "Stop All Conversions" button */
            #stopAllButton {{
                background-color: {red};
                border-color: #AA0000;
            }}
            #stopAllButton:hover {{
                background-color: #DD0000;
            }}
        """)
        self.stop_all_button.setObjectName("stopAllButton")

        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(dark_blue))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(white))
        palette.setColor(QPalette.ColorRole.Base, QColor(medium_blue))
        palette.setColor(QPalette.ColorRole.Text, QColor(white))
        palette.setColor(QPalette.ColorRole.Button, QColor(light_blue))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(white))
        self.setPalette(palette)


    def browse_files(self):
        file_dialog = QFileDialog()
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        file_dialog.setNameFilter("Video Files (*.mp4 *.mkv *.avi *.mov *.flv *.webm);;All Files (*.*)")
        if file_dialog.exec():
            selected_files = file_dialog.selectedFiles()
            for file_path in selected_files:
                if file_path not in self.input_files:
                    self.input_files.append(file_path)
                    self.file_list_widget.addItem(os.path.basename(file_path))
            self.update_convert_button_state()

    def clear_file_list(self):
        self.input_files = []
        self.file_list_widget.clear()
        self.update_convert_button_state()
        self.status_bar_label.setText("File list cleared.")

    def update_convert_button_state(self):
        # Only enable convert button if files are added AND ffmpeg is found
        self.convert_button.setEnabled(bool(self.input_files) and self.ffmpeg_path is not None)

    def start_conversion(self):
        if not self.input_files:
            QMessageBox.warning(self, "No Files", "Please select files to convert first.")
            return
        if not self.ffmpeg_path:
            QMessageBox.critical(self, "FFmpeg Error", "FFmpeg executable not found. Cannot start conversion.")
            return

        self.convert_button.setEnabled(False)
        self.browse_button.setEnabled(False)
        self.clear_button.setEnabled(False)
        self.stop_all_button.setEnabled(True)
        self.status_bar_label.setText("Starting conversions...")

        for i in reversed(range(self.progress_layout.count())):
            widget_to_remove = self.progress_layout.itemAt(i).widget()
            if widget_to_remove:
                widget_to_remove.setParent(None)

        for file_path in self.input_files:
            worker = FFmpegWorker([file_path], ffmpeg_path=self.ffmpeg_path) # Pass ffmpeg_path
            self.conversion_workers[file_path] = worker

            worker.conversion_started.connect(self.on_conversion_started)
            worker.conversion_progress.connect(self.on_conversion_progress)
            worker.conversion_finished.connect(self.on_conversion_finished)
            worker.conversion_error.connect(self.on_conversion_error)
            worker.start()

    def stop_all_conversions(self):
        reply = QMessageBox.question(self, 'Stop Conversions',
                                     "Are you sure you want to stop all active conversions?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.status_bar_label.setText("Stopping all active conversions...")
            for file_path, worker in self.conversion_workers.items():
                if worker.isRunning():
                    worker.stop()
            # It's better to clear self.conversion_workers only after all workers have truly finished/stopped
            # This logic needs refinement for perfect state management.
            # For now, let's just let the on_conversion_finished/error handle cleanup
            QMessageBox.information(self, "Stopped", "All active conversions have been requested to stop. Please check output.")
            self.reset_ui_after_conversion() # Re-enable buttons immediately, users might want to try again.

    def on_conversion_started(self, file_path):
        base_name = os.path.basename(file_path)
        status_widget = QWidget()
        status_layout = QHBoxLayout(status_widget)
        status_layout.setContentsMargins(0,0,0,0)

        label = QLabel(f"Converting: {base_name}")
        status_layout.addWidget(label)

        indicator_label = QLabel("Working...")
        indicator_label.setStyleSheet("color: #F6C101; font-weight: bold;")
        status_layout.addWidget(indicator_label)

        self.progress_layout.addWidget(status_widget)
        self.status_bar_label.setText(f"Started conversion for {base_name}")

        if file_path in self.conversion_workers: # Ensure the worker still exists
            self.conversion_workers[file_path].status_label_ref = indicator_label


    def on_conversion_progress(self, file_path, percentage):
        pass # Not implemented in worker

    def on_conversion_finished(self, file_path, success):
        base_name = os.path.basename(file_path)
        if file_path in self.conversion_workers:
            worker = self.conversion_workers[file_path]
            if hasattr(worker, 'status_label_ref'):
                label = worker.status_label_ref
                if success:
                    label.setText("Done!")
                    label.setStyleSheet("color: #28a745; font-weight: bold;")
                    self.status_bar_label.setText(f"Finished converting {base_name}")
                else:
                    label.setText("Failed!")
                    label.setStyleSheet("color: #dc3545; font-weight: bold;")
                    self.status_bar_label.setText(f"Failed to convert {base_name}")

            worker.quit()
            worker.wait(5000) # Wait up to 5 seconds for the thread to finish cleanly
            if file_path in self.conversion_workers: # Ensure it's still there before deleting
                del self.conversion_workers[file_path] # Remove from active workers

        self.check_all_conversions_done()

    def on_conversion_error(self, file_path, error_message):
        base_name = os.path.basename(file_path) if file_path else "Unknown File"
        if file_path in self.conversion_workers:
            worker = self.conversion_workers[file_path]
            if hasattr(worker, 'status_label_ref'):
                label = worker.status_label_ref
                label.setText("Error!")
                label.setStyleSheet("color: #dc3545; font-weight: bold;")
            self.status_bar_label.setText(f"Error converting {base_name}: {error_message}")
            QMessageBox.critical(self, "Conversion Error", f"Error converting {base_name}:\n{error_message}")

            worker.quit()
            worker.wait(5000) # Wait up to 5 seconds for the thread to finish cleanly
            if file_path in self.conversion_workers:
                del self.conversion_workers[file_path]

        self.check_all_conversions_done()

    def check_all_conversions_done(self):
        if not self.conversion_workers: # If the dictionary of active workers is empty
            self.reset_ui_after_conversion()
            QMessageBox.information(self, "Conversion Complete", "All selected files have been processed.")


    def reset_ui_after_conversion(self):
        # Ensure conversion button is only enabled if files are present AND ffmpeg is found
        self.convert_button.setEnabled(bool(self.input_files) and self.ffmpeg_path is not None)
        self.browse_button.setEnabled(True)
        self.clear_button.setEnabled(True)
        self.stop_all_button.setEnabled(False)
        if not self.input_files and not self.conversion_workers:
            self.status_bar_label.setText("Ready for input...")
        elif self.input_files and not self.conversion_workers:
             self.status_bar_label.setText("Conversion finished. Ready for new conversions.")

    def closeEvent(self, event):
        if self.conversion_workers:
            reply = QMessageBox.question(self, 'Quit Application',
                                         "Conversions are still running. Do you want to stop them and quit?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                         QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                for worker in list(self.conversion_workers.values()): # Iterate over a copy
                    if worker.isRunning():
                        worker.stop()
                        worker.wait(5000)
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MovieConverterApp()
    window.show()
    sys.exit(app.exec())
import webview
import json
import os
import http.server
import socketserver
import threading
import mimetypes
from urllib.parse import quote, unquote  # Import unquote for decoding paths
import logging  # Import logging module
import re  # Import regex for parsing range headers
import sys  # Import sys to get executable path

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Define the port for the HTTP server
HTTP_SERVER_PORT = 8000

# Add mimetypes for video files and subtitle files
mimetypes.add_type("video/mp4", ".mp4")
mimetypes.add_type("video/x-m4v", ".m4v")
mimetypes.add_type("video/webm", ".webm")
mimetypes.add_type("video/ogg", ".ogg")
mimetypes.add_type("video/x-matroska", ".mkv")  # Official MIME type for MKV
mimetypes.add_type("text/vtt", ".vtt")  # WebVTT subtitles
mimetypes.add_type("application/x-subrip",
                   ".srt")  # SubRip subtitles (common, but text/vtt is preferred for HTML5 video)

# --- Dummy movies.json content for initial startup if no user file exists ---
# NOTE: subtitle_path is removed here as it will be derived from video_path
DUMMY_MOVIES_JSON_CONTENT = {
    "movies": {
        "Example Movie 1": {
            "title": "A Fantastic Journey",
            "type": "movie",
            "poster": "images/default.png",
            "video_path": "movies/dummy_movie_1.mp4",
            "trailer_path": None,
            "year": 2023,
            "description": "This is a placeholder for your first amazing movie. Replace this with your actual movie details! Ensure you place your 'images', 'movies', 'series', and 'trailers' folders next to the 'Movie Shell.exe' file. Subtitle files (.srt) should be in the same folder as their video files and have the same name."
        },
        "Example Movie 2": {
            "title": "Mystery of the Lost City",
            "type": "movie",
            "poster": "images/default.png",
            "video_path": "movies/dummy_movie_2.mp4",
            "trailer_path": None,
            "year": 2024,
            "description": "Another placeholder movie. Add your own content and enjoy! Remember to update 'movies.json' and place your media files in the corresponding 'images', 'movies', 'series', or 'trailers' subfolders. Subtitle files (.srt) should be in the same folder as their video files and have the same name."
        }
    },
    "series": {
        "Example Series 1": {
            "title": "The Grand Saga",
            "type": "series",
            "poster": "images/default.png",
            "trailer_path": None,
            "year": 2022,
            "description": "A placeholder series for you to explore. Seasons and episodes can be added here. Make sure your video paths are correct relative to the executable. Subtitle files (.srt) should be in the same folder as their video files and have the same name.",
            "seasons": {
                "1": {
                    "episodes": {
                        "Episode 1": {
                            "title": "The Beginning",
                            "video_path": "series/example_series_1/season 1/episode_1.mp4",
                            "duration": "45m"
                        },
                        "Episode 2": {
                            "title": "The Journey Continues",
                            "video_path": "series/example_series_1/season 1/episode_2.mp4",
                            "duration": "42m"
                        }
                    }
                }
            }
        },
        "Example Series 2": {
            "title": "Adventures Unfolding",
            "type": "series",
            "poster": "images/default.png",
            "trailer_path": None,
            "year": 2021,
            "description": "Another exciting placeholder series. Customize it with your favorite shows! Don't forget to put your 'default.png' in the 'images' folder. Subtitle files (.srt) should be in the same folder as their video files and have the same name.",
            "seasons": {
                "1": {
                    "episodes": {
                        "Part 1": {
                            "title": "First Steps",
                            "video_path": "series/example_series_2/season 1/part_1.mp4",
                            "duration": "30m"
                        }
                    }
                }
            }
        }
    }
}


class MovieShellHTTPHandler(http.server.SimpleHTTPRequestHandler):
    """
    A custom HTTP request handler that serves files from specific directories.
    It correctly maps requests for '/' to index.html and other bundled assets,
    and also serves user-supplied media from the executable's root.
    """

    def translate_path(self, path):
        # Decode the URL path to handle spaces and special characters
        decoded_path = unquote(path)

        # Determine base directories based on whether running as frozen executable or script
        if getattr(sys, 'frozen', False):
            # Running in a PyInstaller bundle:
            # Bundled files (html/, about_page.json) are in sys._MEIPASS
            bundled_base_dir = sys._MEIPASS
            # User-supplied files (movies.json, images/, movies/, series/, trailers/, subtitles/) are next to the .exe
            user_content_base_dir = os.path.dirname(sys.executable)
        else:
            # Running as a normal Python script (development mode):
            # Both bundled and user-supplied files are relative to the script's directory
            script_dir = os.path.dirname(os.path.abspath(__file__))
            bundled_base_dir = script_dir
            user_content_base_dir = script_dir

        # --- Handle Bundled HTML Assets ---
        # Handle the root path for index.html (always bundled inside 'html' folder)
        if decoded_path == '/' or decoded_path.startswith('/?'):
            return os.path.join(bundled_base_dir, 'html', 'index.html')
        # Handle requests for style.css and script.js (always bundled inside 'html' folder)
        elif decoded_path == '/style.css':
            return os.path.join(bundled_base_dir, 'html', 'style.css')
        elif decoded_path == '/script.js':
            return os.path.join(bundled_base_dir, 'html', 'script.js')
        # Handle requests for other files within the 'html' directory (if any, e.g., /html/some_image.png)
        elif decoded_path.startswith('/html/'):
            return os.path.join(bundled_base_dir,
                                decoded_path[1:])  # e.g., /html/some_image.png -> bundled_base_dir/html/some_image.png

        # --- Handle Bundled about_page.json ---
        # about_page.json is now expected directly in the bundled root
        elif decoded_path == '/about_page.json':
            return os.path.join(bundled_base_dir, 'about_page.json')

        # --- Handle User-Supplied Media Folders (images, movies, series, trailers, subtitles) ---
        # These URLs will be directly relative to the server's root (executable's directory)
        # e.g., /images/poster.png, /movies/my_movie.mp4, /series/mandalorian/season%201/episode%201.mp4, /subtitles/movie_en.srt
        # Now also includes direct access to any file in the user_content_base_dir if it's a media type
        elif decoded_path.startswith(('/images/', '/movies/', '/series/', '/trailers/')) or \
                decoded_path.endswith(
                    ('.mp4', '.m4v', '.webm', '.ogg', '.mkv', '.srt', '.vtt', '.jpg', '.jpeg', '.png', '.gif')):
            # Look for these in the user_content_base_dir (next to the .exe or script)
            full_local_path = os.path.join(user_content_base_dir,
                                           decoded_path[1:])  # decoded_path[1:] removes leading '/'
            return full_local_path

        # --- Handle favicon.ico and other browser-specific requests gracefully ---
        elif decoded_path == '/favicon.ico' or decoded_path.startswith('/.well-known/'):
            logging.debug(f"Unhandled browser request: {decoded_path}")
            return super().translate_path(path)  # Let default handler deal with it (likely 404)

        # --- Fallback for any other unexpected paths ---
        logging.warning(f"Unexpected path requested by webview: {decoded_path}")
        return super().translate_path(path)

    # To avoid logging each request, comment out the following method if verbose logging is not needed
    # def log_message(self, format, *args):
    #    pass # Uncomment this line to disable http.server's default verbose logging

    def do_GET(self):
        # This is where the path translation happens and files are served
        path = self.translate_path(self.path)

        logging.debug(f"Attempting to serve requested URL: {self.path}")  # Log the original URL
        logging.debug(f"Translated local file path: {path}")  # Log the translated local path

        if not os.path.exists(path) or not os.path.isfile(path):
            logging.debug(f"File not found: {path}")
            self.send_error(404, "File Not Found")
            return

        try:
            # Guess the MIME type
            ctype, _ = mimetypes.guess_type(path)
            if ctype is None:
                ctype = 'application/octet-stream'  # Default for unknown types

            logging.debug(f"Guessed MIME type for {self.path}: {ctype}")

            file_size = os.path.getsize(path)
            range_header = self.headers.get('Range')

            if range_header and ctype.startswith('video/'):
                # Handle Range requests for video files
                logging.debug(f"Received Range header: {range_header}")
                match = re.match(r'bytes=(\d*)-(\d*)', range_header)
                if match:
                    start_byte = int(match.group(1)) if match.group(1) else 0
                    end_byte = int(match.group(2)) if match.group(2) else file_size - 1

                    if start_byte >= file_size:
                        self.send_error(416, "Range Not Satisfiable")
                        return

                    length = end_byte - start_byte + 1

                    self.send_response(206)  # Partial Content
                    self.send_header("Content-type", ctype)
                    self.send_header("Content-Range", f"bytes {start_byte}-{end_byte}/{file_size}")
                    self.send_header("Content-Length", str(length))
                    self.send_header("Accept-Ranges", "bytes")
                    self.end_headers()

                    with open(path, 'rb') as f:
                        f.seek(start_byte)
                        self.wfile.write(f.read(length))
                    logging.debug(
                        f"Served partial content: bytes {start_byte}-{end_byte} of {file_size} for {self.path}")
                else:
                    logging.warning(f"Invalid Range header format: {range_header}")
                    self.send_error(400, "Bad Request")  # Malformed Range header
            else:
                # Serve full file
                self.send_response(200)
                self.send_header("Content-type", ctype)
                self.send_header("Content-Length", str(file_size))
                self.send_header("Accept-Ranges", "bytes")  # Indicate server supports ranges
                self.end_headers()

                with open(path, 'rb') as f:
                    self.copyfile(f, self.wfile)
                logging.debug(f"Served full file: {self.path}")

        except ConnectionAbortedError:
            logging.debug(f"Client aborted connection while serving {self.path}")
        except ConnectionResetError:
            logging.debug(f"Client reset connection while serving {self.path}")
        except Exception as e:
            logging.error(f"Error serving {self.path}: {e}", exc_info=True)  # exc_info=True to log full traceback
            self.send_error(500, "Internal Server Error")


class Api:
    def __init__(self, media_data, http_server_port, user_content_base_dir):  # Added user_content_base_dir
        self.media_data = media_data
        self.http_server_port = http_server_port
        self.user_content_base_dir = user_content_base_dir  # Store it
        logging.debug(
            f"API initialized with HTTP server port: {self.http_server_port}, user_content_base_dir: {self.user_content_base_dir}")

        # Determine the base directory for bundled resources (where about_page.json is)
        if getattr(sys, 'frozen', False):
            bundled_base_dir = sys._MEIPASS
        else:
            bundled_base_dir = os.path.dirname(os.path.abspath(__file__))

        self.about_json_path = os.path.join(bundled_base_dir,
                                            'about_page.json')  # about_page.json is now directly in bundled root
        logging.debug(f"About JSON path set to: {self.about_json_path}")

    def _get_full_http_url(self, relative_path):
        """
        Converts a relative file path to an HTTP URL.
        Assumes paths for media (images, movies, series, trailers, subtitles) are relative to the executable's directory,
        and about_page.json is bundled directly in the executable's root.
        """
        if not relative_path:
            return None
        if relative_path.startswith(('http://', 'https://')):
            return relative_path

        # If the path is for about_page.json, it's bundled directly in the executable's root
        if relative_path == 'about_page.json':  # Check for exact filename
            encoded_path = quote(relative_path)  # Just encode the filename
            return f"http://localhost:{self.http_server_port}/{encoded_path}"
        else:
            # For all other relative paths (images, movies, series, trailers, subtitles),
            # assume they are user-supplied and should be served directly from the root of the HTTP server
            # (which is the executable's directory or the script's directory during dev).
            # The relative_path from movies.json should be like "images/poster.png", "movies/my_movie.mp4", "subtitles/movie_en.srt"
            encoded_path = '/'.join(quote(part) for part in relative_path.split(os.sep))
            return f"http://localhost:{self.http_server_port}/{encoded_path}"

    def get_all_media(self):
        logging.debug("get_all_media called, returning items.")
        items_to_return = []
        for name_in_json, media_item in self.media_data.items():
            item_copy = media_item.copy()
            item_copy['poster'] = self._get_full_http_url(item_copy.get('poster'))
            # Ensure 'title' is always present, using name_in_json as fallback
            item_copy['title'] = item_copy.get('title', name_in_json)
            item_copy['has_video'] = self._is_video_file(item_copy.get('video_path'))
            item_copy['name_in_json'] = name_in_json
            items_to_return.append(item_copy)
        logging.debug(f"get_all_media returning {len(items_to_return)} items.")
        return json.dumps(items_to_return)

    def get_media_details(self, name_in_json):
        logging.debug(f"get_media_details called for: {name_in_json}")
        media_item = self.media_data.get(name_in_json)
        if media_item:
            details = media_item.copy()
            details['name_in_json'] = name_in_json
            # Ensure 'title' is always present, using name_in_json as fallback
            details['title'] = details.get('title', name_in_json)

            details['poster'] = self._get_full_http_url(details.get('poster'))
            details['video_path'] = self._get_full_http_url(details.get('video_path'))
            details['has_video'] = self._is_video_file(details.get('video_path'))
            details['trailer_path'] = self._get_full_http_url(details.get('trailer_path'))
            details['has_trailer'] = bool(details.get('trailer_path'))

            # NEW SUBTITLE DERIVATION LOGIC
            derived_subtitle_path_relative = None
            original_video_path_relative = media_item.get('video_path')

            if original_video_path_relative:
                # Construct the full local file path for the video to get its base name
                full_video_local_path = os.path.join(self.user_content_base_dir, original_video_path_relative)

                # Derive potential subtitle path by changing extension to .srt
                base_name_without_ext = os.path.splitext(full_video_local_path)[0]
                potential_subtitle_local_path = base_name_without_ext + '.srt'

                # Check if the .srt file actually exists on the filesystem
                if os.path.exists(potential_subtitle_local_path):
                    # If it exists, derive its relative path from user_content_base_dir
                    derived_subtitle_path_relative = os.path.relpath(potential_subtitle_local_path,
                                                                     self.user_content_base_dir)
                    logging.debug(f"Found existing subtitle: {derived_subtitle_path_relative}")
                else:
                    logging.debug(f"No subtitle found at: {potential_subtitle_local_path}")

            details['subtitle_path'] = self._get_full_http_url(derived_subtitle_path_relative)
            details['has_subtitles'] = bool(derived_subtitle_path_relative and os.path.exists(
                os.path.join(self.user_content_base_dir, derived_subtitle_path_relative)))

            if details.get('type') == 'series' and 'seasons' in details:
                for season_num, season_data in details['seasons'].items():
                    if 'episodes' in season_data:
                        for episode_name, episode_details in season_data['episodes'].items():
                            original_episode_video_path_relative = episode_details.get('video_path')
                            derived_episode_subtitle_path_relative = None
                            if original_episode_video_path_relative:
                                full_episode_video_local_path = os.path.join(self.user_content_base_dir,
                                                                             original_episode_video_path_relative)
                                base_name_without_ext = os.path.splitext(full_episode_video_local_path)[0]
                                potential_episode_subtitle_local_path = base_name_without_ext + '.srt'
                                if os.path.exists(potential_episode_subtitle_local_path):
                                    derived_episode_subtitle_path_relative = os.path.relpath(
                                        potential_episode_subtitle_local_path, self.user_content_base_dir)
                                    logging.debug(
                                        f"Found existing episode subtitle: {derived_episode_subtitle_path_relative}")
                                else:
                                    logging.debug(
                                        f"No episode subtitle found at: {potential_episode_subtitle_local_path}")

                            episode_details['video_path'] = self._get_full_http_url(
                                original_episode_video_path_relative)  # Keep original video path
                            episode_details['has_video'] = self._is_video_file(
                                original_episode_video_path_relative)  # Check original video path
                            episode_details['subtitle_path'] = self._get_full_http_url(
                                derived_episode_subtitle_path_relative)
                            episode_details['has_subtitles'] = bool(
                                derived_episode_subtitle_path_relative and os.path.exists(
                                    os.path.join(self.user_content_base_dir, derived_episode_subtitle_path_relative)))

            logging.debug(f"Details for {name_in_json} found and processed.")
            return json.dumps(details)
        logging.debug(f"Details for {name_in_json} not found.")
        return json.dumps(None)

    def get_about_info(self):
        """
        Reads and returns the content of the about.json file.
        """
        logging.debug(f"get_about_info called. Attempting to read from: {self.about_json_path}")
        try:
            with open(self.about_json_path, 'r', encoding='utf-8') as f:
                about_data = json.load(f)
            logging.debug("Successfully loaded about.json.")
            return json.dumps(about_data)
        except FileNotFoundError:
            logging.error(f"about.json not found at {self.about_json_path}")
            return json.dumps({"error": "About information file not found."})
        except json.JSONDecodeError:
            logging.error(f"Could not decode about.json at {self.about_json_path}")
            return json.dumps({"error": f"Error reading about information file."})
        except Exception as e:
            logging.error(f"An unexpected error occurred while reading about.json: {e}")
            return json.dumps({"error": f"An unexpected error occurred: {e}"})

    def _is_video_file(self, file_path):
        video_extensions = ['.mp4', '.webm', '.ogg', '.mkv']
        if file_path:
            # Check if it's a local file by its extension
            if any(file_path.lower().endswith(ext) for ext in video_extensions):
                return True
            # If it's an external URL, check if it's a YouTube URL (using the fixed googleusercontent.com URLs)
            # The URL provided by the user in the past was: https://www.youtube.com/embed/S2X3G-4sN20?autoplay=1
            # Let's make this more flexible to match common YouTube embed patterns if it's a trailer
            if "youtube.com/embed/" in file_path or "youtube.com/watch?v=" in file_path:
                return True
        return False

    def search_media(self, query):
        logging.debug(f"search_media called for query: '{query}'")
        query_lower = (query or "").lower()
        found_media = []
        for name_in_json, details in self.media_data.items():
            # Ensure 'title' is consistently available for search
            item_title = details.get('title', name_in_json)
            if query_lower in item_title.lower() or \
                    (details.get("description") and query_lower in details["description"].lower()):
                item_copy = details.copy()
                item_copy['poster'] = self._get_full_http_url(item_copy.get('poster'))
                item_copy['name_in_json'] = name_in_json
                # Ensure 'title' is added to the returned item
                item_copy['title'] = item_copy.get('title', name_in_json)
                found_media.append(item_copy)
        logging.debug(f"Search returned {len(found_media)} items for query: '{query}'")
        return json.dumps(found_media)

    def show_devtools(self):
        logging.debug("Python: show_devtools method CALLED from JavaScript.")
        if webview.windows:  # Check if there's an active window
            logging.debug("Python: Attempting to simulate F12 key press to open devtools.")
            # Simulate F12 key press to toggle dev tools
            # This is a common workaround when direct API calls like show_devtools() are not available
            webview.windows[0].evaluate_js("""
                window.dispatchEvent(new KeyboardEvent('keydown', {
                    key: 'F12',
                    code: 'F12',
                    keyCode: 123, // Deprecated, but good for compatibility
                    which: 123,   // Deprecated, but good for compatibility
                    bubbles: true,
                    cancelable: true
                }));
            """)
            logging.debug("Python: F12 key press simulated via evaluate_js.")
        else:
            logging.error("Python: No active webview window found to open devtools.")


class MovieShellApp:
    def __init__(self):
        # Determine the base directory for bundled resources (html/, about_page.json)
        if getattr(sys, 'frozen', False):
            self.bundled_base_dir = sys._MEIPASS
            # User-supplied content (movies.json, images/, movies/, series/, trailers/, subtitles/) are next to the .exe
            self.user_content_base_dir = os.path.dirname(sys.executable)
        else:
            # Running as a normal Python script (development mode)
            script_dir = os.path.dirname(os.path.abspath(__file__))
            self.bundled_base_dir = script_dir
            self.user_content_base_dir = script_dir

        self.movie_data = {}
        self.httpd = None
        self.server_thread = None
        self.port = HTTP_SERVER_PORT

        self._load_movie_data()

    def _load_movie_data(self):
        # Path for user-supplied movies.json (next to the .exe or main.py)
        user_supplied_json_path = os.path.join(self.user_content_base_dir, 'movies.json')

        json_path_to_load = user_supplied_json_path

        if not os.path.exists(user_supplied_json_path):
            logging.info(f"movies.json not found at {user_supplied_json_path}. Creating dummy file.")
            try:
                with open(user_supplied_json_path, 'w', encoding='utf-8') as f:
                    json.dump(DUMMY_MOVIES_JSON_CONTENT, f, indent=2)
                logging.debug("Dummy movies.json created successfully.")
            except Exception as e:
                logging.error(f"Failed to create dummy movies.json: {e}")
                self.movie_data = {}  # Ensure data is empty if dummy creation fails
                return

        try:
            with open(json_path_to_load, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
                if not isinstance(raw_data, dict) or 'movies' not in raw_data or 'series' not in raw_data:
                    logging.error("Invalid movies.json structure. Expected top-level 'movies' and 'series' keys.")
                    self.movie_data = {}
                    return

                # Flatten movies and series into a single dictionary for easier lookup
                self.movie_data = {}  # Initialize to ensure it's empty before populating
                for movie_title, item_details in raw_data.get('movies', {}).items():
                    item_details['type'] = 'movie'  # Explicitly set type
                    self.movie_data[movie_title] = item_details

                for series_title, item_details in raw_data.get('series', {}).items():
                    item_details['type'] = 'series'  # Explicitly set type
                    self.movie_data[series_title] = item_details

            logging.debug("Successfully loaded and processed data from %s", json_path_to_load)
        except FileNotFoundError:
            logging.error(
                f"movies.json not found at {json_path_to_load} after creation attempt. This should not happen.")
            self.movie_data = {}
        except json.JSONDecodeError as e:
            logging.error(f"Error decoding movies.json at {json_path_to_load}: {e}")
            self.movie_data = {}
        except Exception as e:
            logging.error(f"An unexpected error occurred loading movies.json from {json_path_to_load}: {e}")
            self.movie_data = {}

    def _start_http_server(self):
        logging.debug("Attempting to start HTTP server.")
        try:
            # The HTTP server's current working directory is the user_content_base_dir.
            # This allows it to serve user-supplied media directly from subfolders like images/, movies/, etc.
            os.chdir(self.user_content_base_dir)

            handler = MovieShellHTTPHandler  # Use the custom handler
            self.httpd = socketserver.TCPServer(("", self.port), handler)
            self.server_thread = threading.Thread(target=self.httpd.serve_forever)
            self.server_thread.daemon = True  # Daemon threads exit when the main program exits
            self.server_thread.start()
            logging.debug(f"Serving HTTP on http://localhost:{self.port}")
        except Exception as e:
            logging.error(f"Failed to start HTTP server: {e}")

    def _stop_http_server(self):
        if self.httpd:
            logging.debug("Shutting down HTTP server.")
            self.httpd.shutdown()
            self.httpd.server_close()
            logging.debug("HTTP server stopped.")

    def run(self):
        logging.debug("Starting Movie Shell application run method.")
        self._start_http_server()

        self.api = Api(self.movie_data, self.port, self.user_content_base_dir)  # Pass user_content_base_dir to API

        # Construct the URL for index.html, which the HTTP server will serve
        html_url = f"http://localhost:{self.port}/"  # Load the root URL, which maps to index.html

        logging.debug("Creating PyWebView window.")
        window = webview.create_window(
            'Movie Shell',
            url=html_url,
            js_api=self.api,
            width=1200,
            height=800,
            min_size=(800, 600),  # Minimum size for the window
            frameless=False,  # Keep window frame (title bar, minimize/maximize/close buttons)
            resizable=True,  # Make window not resizable by dragging
            # fullscreen=False, # Do not start in fullscreen, allow toggle (e.g., F11)
            # debug=False is now passed to webview.start()
        )

        # Register a callback to stop the HTTP server when the webview window is closed
        window.events.closed += self._stop_http_server

        logging.debug("PyWebView starting main loop.")
        # Start the webview application.
        # Set debug=False here to prevent dev tools from popping out automatically on startup.
        # The button will now attempt to toggle them via F12 simulation.
        webview.start(private_mode=False, debug=True)
        logging.debug("PyWebView main loop ended. Script exiting.")


if __name__ == "__main__":
    logging.debug("Script started. Entering __main__ block.")
    app = MovieShellApp()
    app.run()
    logging.debug("Script finished.")

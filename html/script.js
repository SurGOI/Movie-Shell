// Global state variables
let currentMediaDetails = null;

// Initialization flags
let isDomReady = false;
let isPywebviewReady = false;

// --- DOM Element References (Declared globally, will be assigned in DOMContentLoaded) ---
let posterGridView;
let detailView;
let playerView;

let posterGridContainer;
let searchInput;
let searchIcon;
let aboutIcon;

let backButtonDetail;
let detailPoster;
let noPosterPlaceholder;
let detailTitle;
let detailYear;
let playMovieButton;
let trailerButton;
let detailDescription;

let seriesInfo;
let seasonSelector;
let episodesList;

let backButtonPlayer;
let playerTitle;
let trailerIframeContainer;
let localVideoPlayer;
let ccButton; // NEW: Reference for the CC button

// About Modal Elements
let aboutModal;
let closeAboutModal;
let aboutAppName;
let aboutVersion;
let aboutDeveloper;
let aboutReleaseDate;
let aboutDescription;
let aboutContact;
let aboutWebsite;


// --- Utility Functions (These functions use the elements defined above) ---

/**
 * Hides all views and shows the specified one.
 * @param {HTMLElement} viewElement - The DOM element of the view to show (e.g., posterGridView, detailView, playerView).
 */
function showView(viewElement) {
    console.log(`DEBUG: showView called for: ${viewElement.id}`);
    // Hide all views by adding 'hidden' and removing 'active'
    document.querySelectorAll('.view').forEach(view => {
        view.classList.remove('active');
        view.classList.add('hidden');
    });

    // Show the requested view by removing 'hidden' and adding 'active'
    viewElement.classList.remove('hidden');
    // Force reflow to ensure transition plays (modern browsers often handle this, but good for consistency)
    void viewElement.offsetWidth;
    viewElement.classList.add('active');

    // Stop video playback when switching away from player view
    if (viewElement.id !== 'player-view') {
        stopVideoPlayback();
        // Reset CC button state if not in player view
        if (ccButton) {
            ccButton.classList.add('hidden'); // Hide the button
            ccButton.disabled = true; // Disable it
            ccButton.textContent = 'CC Off'; // Reset text
        }
    }
}

/**
 * Stops any active video playback (local video or YouTube iframe).
 */
function stopVideoPlayback() {
    console.log('DEBUG: Stopping video playback.');
    // Stop local video playback
    if (localVideoPlayer && !localVideoPlayer.paused) { // Check if localVideoPlayer exists
        localVideoPlayer.pause();
    }
    if (localVideoPlayer) { // Check if localVideoPlayer exists
        localVideoPlayer.src = ''; // Clear source
        localVideoPlayer.load(); // Important to clear source immediately
        localVideoPlayer.classList.add('hidden'); // Hide local video player
        // Remove any dynamically added subtitle tracks
        Array.from(localVideoPlayer.querySelectorAll('track')).forEach(track => track.remove());
    }

    // Remove YouTube iframe content and hide
    if (trailerIframeContainer) { // Check if trailerIframeContainer exists
        trailerIframeContainer.src = ''; // Clear iframe source
        trailerIframeContainer.classList.add('hidden'); // Hide iframe container
    }
}

/**
 * Creates a media card element for display in the grid.
 * @param {object} media - The media item data.
 * @returns {HTMLElement} The created div element for the media card.
 */
function createMediaCard(media) {
    const card = document.createElement('div');
    card.classList.add('media-card');
    card.dataset.nameInJson = media.name_in_json; // Store item ID for fetching details

    const img = document.createElement('img');
    img.src = media.poster;
    img.alt = media.title + " Poster"; // Use media.title for alt text

    // Handle image loading errors
    img.onerror = () => {
        console.warn(`WARNING: Failed to load image for ${media.title} from ${media.poster}. Using placeholder.`);
        img.classList.add('hidden'); // Hide broken image
        // Create and insert placeholder
        const placeholder = document.createElement('div');
        placeholder.classList.add('placeholder', 'poster-placeholder');
        placeholder.textContent = `No Poster\n(${media.title})`;
        card.insertBefore(placeholder, img.nextSibling); // Insert placeholder after img
    };

    const title = document.createElement('h3');
    title.classList.add('title'); // Add title class as per CSS
    title.textContent = media.title;

    card.appendChild(img);
    card.appendChild(title);

    // Attach click listener to the entire card
    card.addEventListener('click', () => showDetailView(media.name_in_json));
    return card;
}


// --- Data Loading Functions ---

/**
 * Loads and displays movie/series posters in the grid.
 * @param {string} [query=null] - Optional search query to filter posters.
 */
async function loadPosterGrid(query = null) {
    console.log(`DEBUG: loadPosterGrid called. Search query: ${query}`);
    // Show loading indicator before fetching data
    if (posterGridContainer) {
        posterGridContainer.innerHTML = '<div class="loading-indicator">Loading media...</div>';
    }


    let mediaItems;
    try {
        if (window.pywebview && window.pywebview.api) {
            mediaItems = await window.pywebview.api.get_all_media();
            // Ensure the result is parsed if it's a JSON string
            try {
                mediaItems = JSON.parse(mediaItems);
            } catch (e) {
                console.error("ERROR: Failed to parse media items JSON from Python API:", e);
                mediaItems = []; // Set to empty array to prevent further errors
            }

            if (query) {
                // Filter client-side if a query is present
                const queryLower = query.toLowerCase();
                mediaItems = mediaItems.filter(item =>
                    (item.title && item.title.toLowerCase().includes(queryLower)) ||
                    (item.description && item.description.toLowerCase().includes(queryLower))
                );
            }

        } else {
            console.error("Pywebview API not available within loadPosterGrid. This should not happen if initializeApp ran correctly.");
            if (posterGridContainer) {
                posterGridContainer.innerHTML = '<p class="error-message">Application API not available. Please ensure the Python backend is running correctly.</p>';
            }
            return;
        }
    } catch (error) {
        console.error("ERROR: Failed to load media items from Python API:", error);
        if (posterGridContainer) {
            posterGridContainer.innerHTML = '<p class="error-message">Failed to load media. Please check the Python server and `movies.json`.</p>';
        }
        return;
    }

    console.log("DEBUG: Received media items:", mediaItems);

    if (!mediaItems || mediaItems.length === 0) {
        if (posterGridContainer) {
            posterGridContainer.innerHTML = '<p class="no-results">No items found.</p>';
        }
        console.log("DEBUG: No media items found or received empty list.");
        return;
    }

    if (posterGridContainer) {
        posterGridContainer.innerHTML = ''; // Clear loading indicator/previous content
        mediaItems.forEach(item => {
            const card = createMediaCard(item);
            posterGridContainer.appendChild(card);
        });
    }
    console.log('DEBUG: All posters processed and appended to grid.');
}

/**
 * Displays the detail view for a selected media item.
 * @param {string} nameInJson - The name/key of the media item from movies.json.
 */
async function showDetailView(nameInJson) {
    console.log(`DEBUG: Showing detail view for: ${nameInJson}`);
    try {
        currentMediaDetails = await window.pywebview.api.get_media_details(nameInJson);
        // Ensure the result is parsed if it's a JSON string
        try {
            currentMediaDetails = JSON.parse(currentMediaDetails);
        } catch (e) {
            console.error("ERROR: Failed to parse media details JSON from Python API:", e);
            currentMediaDetails = null; // Set to null to prevent further errors
        }
    } catch (error) {
        console.error(`ERROR: Failed to fetch details for ${nameInJson}:`, error);
        console.log('Details for this item could not be loaded.');
        return;
    }

    if (!currentMediaDetails) {
        console.error(`ERROR: Details for ${nameInJson} not found.`);
        console.log('Details for this item could not be loaded.');
        return;
    }

    // Populate common fields
    if (detailTitle) detailTitle.textContent = currentMediaDetails.title;
    if (detailYear) detailYear.textContent = `Year: ${currentMediaDetails.year || 'N/A'}`;
    if (detailDescription) detailDescription.textContent = currentMediaDetails.description || 'No description available.';

    // Handle poster image or placeholder
    if (detailPoster && noPosterPlaceholder) {
        if (currentMediaDetails.poster) {
            detailPoster.src = currentMediaDetails.poster;
            detailPoster.classList.remove('hidden');
            noPosterPlaceholder.classList.add('hidden');
            detailPoster.onerror = () => {
                detailPoster.classList.add('hidden');
                noPosterPlaceholder.classList.remove('hidden');
                noPosterPlaceholder.textContent = currentMediaDetails.title + '\nNo Poster Available';
            };
        } else {
            detailPoster.classList.add('hidden');
            noPosterPlaceholder.classList.remove('hidden');
            noPosterPlaceholder.textContent = currentMediaDetails.title + '\nNo Poster Available';
        }
    }


    // Handle movie vs. series specific buttons/info
    if (currentMediaDetails.type === 'movie') {
        if (playMovieButton) {
            playMovieButton.classList.remove('hidden');
            playMovieButton.disabled = !currentMediaDetails.has_video;
            playMovieButton.textContent = '▶ Play Movie';
        }
        if (seriesInfo) seriesInfo.classList.add('hidden');
    } else if (currentMediaDetails.type === 'series') {
        if (playMovieButton) playMovieButton.classList.add('hidden'); // Hide movie play button for series
        if (seriesInfo) {
            seriesInfo.classList.remove('hidden');
            populateSeasonsAndEpisodes(currentMediaDetails);
        }
    } else {
        // Default for unknown type
        if (playMovieButton) playMovieButton.classList.add('hidden');
        if (seriesInfo) seriesInfo.classList.add('hidden');
    }

    if (trailerButton) {
        trailerButton.disabled = !currentMediaDetails.has_trailer;
        trailerButton.textContent = currentMediaDetails.has_trailer ? '▶ Watch Trailer' : 'No Trailer Available';
    }

    if (detailView) showView(detailView);
    console.log('DEBUG: Detail view displayed.');
}

/**
 * Populates the season selector and episode list for a series.
 * @param {object} seriesDetails - The full details of the series.
 */
function populateSeasonsAndEpisodes(seriesDetails) {
    if (seasonSelector) seasonSelector.innerHTML = ''; // Clear previous seasons
    if (episodesList) episodesList.innerHTML = ''; // Clear previous episodes

    const seasons = seriesDetails.seasons || {}; // Expect seasons to be an object
    const sortedSeasonNumbers = Object.keys(seasons).sort((a, b) => {
        // Extract season number from string keys like "season 1"
        const numA = parseInt(a.replace('season ', ''));
        const numB = parseInt(b.replace('season ', ''));
        return numA - numB;
    });

    if (sortedSeasonNumbers.length === 0) {
        if (seasonSelector) seasonSelector.innerHTML = '<option value="">No seasons found</option>';
        if (episodesList) episodesList.innerHTML = '<p class="placeholder">No episodes available.</p>';
        if (seasonSelector) seasonSelector.disabled = true;
        return;
    }

    if (seasonSelector) seasonSelector.disabled = false;
    sortedSeasonNumbers.forEach(seasonKey => {
        const option = document.createElement('option');
        option.value = seasonKey; // e.g., "season 1"
        option.textContent = seasonKey.charAt(0).toUpperCase() + seasonKey.slice(1); // "Season 1"
        if (seasonSelector) seasonSelector.appendChild(option);
    });

    // Automatically load episodes for the first season or selected season
    if (sortedSeasonNumbers.length > 0) {
        if (seasonSelector) seasonSelector.value = sortedSeasonNumbers[0];
        loadEpisodesForSelectedSeason();
    }
}

/**
 * Loads episodes for the currently selected season in the dropdown.
 */
function loadEpisodesForSelectedSeason() {
    if (episodesList) episodesList.innerHTML = ''; // Clear current episodes
    const selectedSeasonKey = seasonSelector ? seasonSelector.value : null;
    const seriesDetails = currentMediaDetails; // Use the globally stored details

    if (!selectedSeasonKey || !seriesDetails || !seriesDetails.seasons) {
        if (episodesList) episodesList.innerHTML = '<p class="placeholder">Please select a season.</p>';
        return;
    }

    const seasonData = seriesDetails.seasons[selectedSeasonKey];
    const episodes = seasonData ? seasonData.episodes : {};

    if (Object.keys(episodes).length === 0) {
        if (episodesList) episodesList.innerHTML = '<p class="placeholder">No episodes for this season.</p>';
        return;
    }

    Object.keys(episodes).sort((a, b) => {
        // Sort episodes by episode number if present, otherwise by key
        const epA = episodes[a].episode_number || 0;
        const epB = episodes[b].episode_number || 0;
        return epA - epB;
    }).forEach(episodeKey => {
        const episode = episodes[episodeKey];
        const episodeItem = document.createElement('button');
        episodeItem.classList.add('episode-item');
        episodeItem.innerHTML = `
            <span class="episode-title">${episode.title || episodeKey}</span>
            <span class="episode-duration">${episode.duration || ''}</span>
        `;
        episodeItem.disabled = !episode.has_video;
        episodeItem.addEventListener('click', () => {
            if (!episodeItem.disabled) {
                // Pass subtitle_path to playMedia for episodes
                playMedia(episode.video_path, `${seriesDetails.title} - ${selectedSeasonKey.charAt(0).toUpperCase() + selectedSeasonKey.slice(1)} - ${episode.title || episodeKey}`, episode.subtitle_path);
            }
        });
        if (episodesList) episodesList.appendChild(episodeItem);
    });
}


/**
 * Toggles the visibility of the subtitle track on the local video player.
 */
function toggleSubtitles() {
    console.log('DEBUG: Toggling subtitles.');
    if (!localVideoPlayer) {
        console.warn('No local video player found for subtitle toggle.');
        // Optionally provide user feedback
        // alert('Video player not ready.');
        return;
    }

    const tracks = localVideoPlayer.textTracks; // Get all text tracks associated with the video

    // Find the first subtitle or caption track
    let subtitleTrack = null;
    for (let i = 0; i < tracks.length; i++) {
        if (tracks[i].kind === 'subtitles' || tracks[i].kind === 'captions') {
            subtitleTrack = tracks[i];
            break; // We'll toggle the first one found for simplicity
        }
    }

    if (subtitleTrack) {
        if (subtitleTrack.mode === 'showing') {
            subtitleTrack.mode = 'hidden';
            if (ccButton) ccButton.textContent = 'CC Off'; // Update button text
            console.log('DEBUG: Subtitles hidden.');
        } else {
            subtitleTrack.mode = 'showing';
            if (ccButton) ccButton.textContent = 'CC On'; // Update button text
            console.log('DEBUG: Subtitles showing.');
        }
    } else {
        console.warn('No subtitle track found to toggle for the current video.');
        // Inform user if button is pressed but no subtitles are actually available for this video
        alert('No subtitles available for this video.');
        if (ccButton) {
            ccButton.textContent = 'No CC'; // Or some other indicator
            ccButton.disabled = true; // Disable button if no subtitles at all
        }
    }
}


/**
 * Plays a given media path (local video or YouTube URL) in the player view.
 * @param {string} mediaPath - The URL or local path of the media.
 * @param {string} title - The title to display in the player bar.
 * @param {string} [subtitlePath=null] - Optional path to the subtitle file (SRT or VTT).
 */
function playMedia(mediaPath, title, subtitlePath = null) {
    console.log(`DEBUG: Attempting to play media: ${mediaPath}`);
    stopVideoPlayback(); // Ensure any previous media is stopped

    if (playerTitle) playerTitle.textContent = title || 'Media Player'; // Fallback for title

    // Ensure CC button is hidden and disabled initially when starting playback
    if (ccButton) {
        ccButton.classList.add('hidden');
        ccButton.disabled = true;
        ccButton.textContent = 'CC Off'; // Reset text
    }

    if (mediaPath.startsWith('http://') || mediaPath.startsWith('https://')) {
        // It's a URL (assume YouTube embed or similar for now)
        if (trailerIframeContainer) {
            let finalTrailerPath = mediaPath;

            // Check if it's a YouTube URL and append autoplay parameter
            if (mediaPath.includes('youtube.com/embed/') || mediaPath.includes('youtube.com/watch?v=') || mediaPath.includes('youtu.be/')) { // Added last part to match previous regex
                let videoId = '';
                let urlObj;
                try {
                    urlObj = new URL(mediaPath);
                } catch (e) {
                    console.error("Invalid mediaPath URL for YouTube:", mediaPath, e);
                    finalTrailerPath = mediaPath; // Fallback
                }

                if (urlObj && urlObj.pathname.includes('/embed/')) {
                    videoId = urlObj.pathname.split('/embed/')[1];
                } else if (urlObj && urlObj.searchParams.has('v')) {
                    videoId = urlObj.searchParams.get('v');
                }

                if (videoId) {
                    // Always use the embed URL format for YouTube with autoplay and other desired parameters
                    finalTrailerPath = `https://www.youtube-nocookie.com/embed/${videoId}?autoplay=1&controls=0&modestbranding=1&rel=0&showinfo=0&loop=1&playlist=${videoId}`;
                } else {
                    console.warn("Could not extract YouTube video ID from:", mediaPath);
                }
            }

            trailerIframeContainer.src = finalTrailerPath;
            trailerIframeContainer.classList.remove('hidden');
            if (localVideoPlayer) localVideoPlayer.classList.add('hidden');
            console.log('DEBUG: Playing YouTube trailer in iframe.');
        }
    } else {
        // It's a local video file served by our Python HTTP server
        if (localVideoPlayer) {
            localVideoPlayer.src = mediaPath;
            localVideoPlayer.classList.remove('hidden');

            // --- Subtitle Integration ---
            // Remove any existing track elements to prevent duplicates
            Array.from(localVideoPlayer.querySelectorAll('track')).forEach(track => track.remove());

            if (subtitlePath) {
                console.log(`DEBUG: Adding subtitle track from: ${subtitlePath}`);
                const trackElement = document.createElement('track');
                trackElement.src = subtitlePath;
                trackElement.kind = 'subtitles';
                trackElement.srclang = 'en'; // Assuming English subtitles for now
                trackElement.label = 'English';
                trackElement.default = true; // Make it default if available
                trackElement.mode = 'showing'; // Attempt to make it showing initially

                // Add an event listener to the track to ensure button state is correct if track fails to load
                trackElement.onerror = (e) => {
                    console.error(`ERROR: Subtitle track failed to load from ${subtitlePath}:`, e);
                    if (ccButton) {
                        ccButton.classList.add('hidden');
                        ccButton.disabled = true;
                        ccButton.textContent = 'No CC';
                    }
                };

                localVideoPlayer.appendChild(trackElement);

                // Enable and update custom CC button after track is added
                if (ccButton) {
                    ccButton.classList.remove('hidden'); // Show the button
                    ccButton.disabled = false;
                    ccButton.textContent = 'CC On'; // Initial state: subtitles are ON
                }

            } else {
                // No subtitle path, ensure custom CC button is hidden and disabled
                if (ccButton) {
                    ccButton.classList.add('hidden'); // Hide the button
                    ccButton.disabled = true;
                    ccButton.textContent = 'CC Off'; // Reset text
                }
            }
            // --- End Subtitle Integration ---

            // Attempt to play immediately
            localVideoPlayer.play().catch(error => {
                console.error('Error playing local video (autoplay prevented or other issue):', error);
                // Inform user if autoplay failed due to browser policies or other reasons
                // Note: Modern browsers often require user interaction before video playback
                alert('Video playback might be blocked by your browser (autoplay). Please click the play button on the video player to start.');
            });
        }
        if (trailerIframeContainer) trailerIframeContainer.classList.add('hidden');
        console.log('DEBUG: Playing local video.');
    }
    if (playerView) showView(playerView);
}

// --- About Modal Functions ---
function openAboutModal() {
    if (aboutModal) {
        aboutModal.classList.remove('hidden'); // Ensure the modal container is visible
        aboutModal.classList.add('show');     // Trigger the opacity and slide-in transitions
    }
    loadAboutInfo(); // Load info when modal opens
}

function closeAboutModalFunc() {
    if (aboutModal) {
        aboutModal.classList.remove('show'); // Start the fade-out and slide-out transitions
        // Add a small delay before adding 'hidden' back, to allow transition to complete
        setTimeout(() => {
            aboutModal.classList.add('hidden');
        }, 300); // Match transition duration (0.3s) in CSS
    }
}

/**
 * Loads and displays information from the about_page.json file using the pywebview API.
 */
async function loadAboutInfo() {
    try {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.get_about_info) {
            console.log("DEBUG: Calling pywebview.api.get_about_info()");
            let aboutInfo = await window.pywebview.api.get_about_info();
            // Ensure the result is parsed if it's a JSON string
            try {
                aboutInfo = JSON.parse(aboutInfo);
            } catch (e) {
                console.error("ERROR: Failed to parse about info JSON from Python API:", e);
                aboutInfo = {}; // Set to empty object to prevent further errors
            }
            console.log("DEBUG: Loaded about info from Python API:", aboutInfo);

            // Populate the modal with data
            if (aboutAppName) aboutAppName.textContent = aboutInfo.appName || 'N/A';
            if (aboutVersion) aboutVersion.textContent = aboutInfo.version || 'N/A';
            if (aboutDeveloper) aboutDeveloper.textContent = aboutInfo.developer || 'N/A';
            if (aboutReleaseDate) aboutReleaseDate.textContent = aboutInfo.releaseDate || 'N/A';
            if (aboutDescription) aboutDescription.textContent = aboutInfo.description || 'No description available.';
            if (aboutContact) aboutContact.textContent = aboutInfo.contact || 'N/A';

            // Handle the website hyperlink
            if (aboutWebsite) {
                aboutWebsite.innerHTML = ''; // Clear existing text content
                if (aboutInfo.website) {
                    const linkElement = document.createElement('a');
                    linkElement.href = aboutInfo.website;
                    linkElement.textContent = aboutInfo.website;
                    linkElement.target = "_blank"; // Open in a new tab/window
                    linkElement.classList.add('text-blue-400', 'hover:underline'); // Tailwind classes for styling
                    aboutWebsite.appendChild(linkElement);
                } else {
                    aboutWebsite.textContent = 'N/A';
                }
            }
        } else {
            console.error("Pywebview API or get_about_info method not available. Cannot load about information.");
            // Fallback text if API is not available
            if (aboutAppName) aboutAppName.textContent = 'Error';
            if (aboutVersion) aboutVersion.textContent = 'Error';
            if (aboutDeveloper) aboutDeveloper.textContent = 'Error';
            if (aboutReleaseDate) aboutReleaseDate.textContent = 'Error';
            if (aboutDescription) aboutDescription.textContent = 'Application API not available. Please ensure the Python backend is running correctly.';
            if (aboutContact) aboutContact.textContent = 'N/A';
            if (aboutWebsite) aboutWebsite.textContent = 'N/A';
        }
    } catch (error) {
        console.error("ERROR: Failed to load about information from Python API:", error);
        // Fallback text if loading fails
        if (aboutAppName) aboutAppName.textContent = 'Error';
        if (aboutVersion) aboutVersion.textContent = 'Error';
        if (aboutDeveloper) aboutDeveloper.textContent = 'Error';
        if (aboutReleaseDate) aboutReleaseDate.textContent = 'Error';
        if (aboutDescription) aboutDescription.textContent = 'Could not load program information due to an error.';
        if (aboutContact) aboutContact.textContent = 'N/A';
        if (aboutWebsite) aboutWebsite.textContent = 'N/A';
    }
}


/**
 * Initializes the application by loading the poster grid and showing the main view.
 * This function is called only when both DOM is ready and Pywebview API is available.
 */
function initializeApp() {
    if (isDomReady && isPywebviewReady) {
        console.log("DEBUG: Both DOM and Pywebview API are ready. Initializing application.");
        loadPosterGrid(); // Load media only when both conditions are met
        if (posterGridView) showView(posterGridView); // Ensure poster grid view is shown
    } else {
        console.log("DEBUG: Waiting for both DOM and Pywebview API readiness.");
    }
}

// --- Event Listeners ---

// Pywebview ready event listener
// This event confirms that window.pywebview.api is available.
window.addEventListener('pywebviewready', () => {
    console.log("DEBUG: pywebviewready fired. PyWebView API is available.");
    try {
        isPywebviewReady = true;
        initializeApp(); // Attempt to initialize
    } catch (e) {
        console.error("ERROR: Script initialization failed on pywebviewready:", e);
        if (posterGridContainer) {
            posterGridContainer.innerHTML = '<p class="error-message">An error occurred during application startup. Please check the console for details.</p>';
        }
    }
});

// Initialize the app when the DOM is fully loaded and parsed.
document.addEventListener('DOMContentLoaded', () => {
    console.log("DEBUG JS: DOMContentLoaded fired. Assigning DOM element references and attaching event listeners.");

    try {
        // --- Assign DOM Element References (Inside DOMContentLoaded) ---
        posterGridView = document.getElementById('poster-grid-view');
        detailView = document.getElementById('detail-view');
        playerView = document.getElementById('player-view');

        posterGridContainer = document.getElementById('poster-grid-container');
        searchInput = document.getElementById('search-input');
        searchIcon = document.getElementById('search-icon');
        aboutIcon = document.getElementById('aboutIcon');

        backButtonDetail = document.getElementById('detail-back-button');
        detailPoster = document.getElementById('detail-poster');
        noPosterPlaceholder = document.getElementById('no-poster-placeholder');
        detailTitle = document.getElementById('detail-title');
        detailYear = document.getElementById('detail-year');
        playMovieButton = document.getElementById('play-button');
        trailerButton = document.getElementById('trailer-button');
        detailDescription = document.getElementById('detail-description');

        seriesInfo = document.getElementById('series-info');
        seasonSelector = document.getElementById('season-selector');
        episodesList = document.getElementById('episodes-list');

        backButtonPlayer = document.getElementById('player-back-button');
        playerTitle = document.getElementById('player-title');
        trailerIframeContainer = document.getElementById('trailer-iframe-container');
        localVideoPlayer = document.getElementById('local-video-player');
        ccButton = document.getElementById('cc-button'); // NEW: Assign CC button reference

        isDomReady = true;
        initializeApp(); // Attempt to initialize


        // --- Attach Event Listeners (Inside DOMContentLoaded) ---

        // Search functionality
        if (searchInput) {
            searchInput.addEventListener('keyup', (event) => {
                if (event.key === 'Enter') {
                    loadPosterGrid(searchInput.value);
                }
            });
        }
        if (searchIcon) {
            searchIcon.addEventListener('click', () => loadPosterGrid(searchInput.value));
        }

        // About Icon click to open modal
        if (aboutIcon) {
            aboutIcon.addEventListener('click', openAboutModal);
        }

        // Close About Modal button
        if (closeAboutModal) {
            closeAboutModal.addEventListener('click', closeAboutModalFunc);
        }

        // Close About modal when clicking outside content
        if (aboutModal) {
            aboutModal.addEventListener('click', (event) => {
                if (event.target === aboutModal) {
                    closeAboutModalFunc();
                }
            });
        }

        // Back buttons
        if (backButtonDetail) {
            backButtonDetail.addEventListener('click', () => showView(posterGridView));
        }
        if (backButtonPlayer) {
            backButtonPlayer.addEventListener('click', () => {
                if (currentMediaDetails) {
                    showDetailView(currentMediaDetails.name_in_json);
                } else {
                    showView(posterGridView);
                }
            });
        }

        // Detail view buttons
        if (playMovieButton) {
            playMovieButton.addEventListener('click', () => {
                if (currentMediaDetails && currentMediaDetails.has_video) {
                    playMedia(currentMediaDetails.video_path, currentMediaDetails.title, currentMediaDetails.subtitle_path);
                } else {
                    console.warn('No video path available for this item or item type is not a movie.');
                }
            });
        }

        if (trailerButton) {
            trailerButton.addEventListener('click', () => {
                if (currentMediaDetails && currentMediaDetails.has_trailer) {
                    const trailerTitle = currentMediaDetails.title ? `${currentMediaDetails.title} - Trailer` : 'Trailer';
                    playMedia(currentMediaDetails.trailer_path, trailerTitle, null);
                } else {
                    console.warn('No trailer path available for this item.');
                }
            });
        }

        // Season selector for series
        if (seasonSelector) {
            seasonSelector.addEventListener('change', loadEpisodesForSelectedSeason);
        }

        // NEW: CC button event listener
        if (ccButton) {
            ccButton.addEventListener('click', toggleSubtitles);
            // Initial state for CC button (hidden until a video with subtitles is played)
            ccButton.classList.add('hidden');
            ccButton.disabled = true;
            ccButton.textContent = 'CC Off';
        }

    } catch (e) {
        console.error("ERROR: Script initialization failed in DOMContentLoaded:", e);
        if (posterGridContainer) {
            posterGridContainer.innerHTML = '<p class="error-message">An error occurred during application startup. Please check the console for details.</p>';
        }
    }
});

"""
This is the main Flask application file for the Spotify to YouTube Playlist Converter.

It handles web routes, initializes Spotify and YouTube API clients,
and orchestrates the conversion process, streaming progress updates to the frontend.
"""

import os
import time
import webbrowser
from threading import Timer

from flask import Flask, render_template, request, Response, stream_with_context
from dotenv import load_dotenv
import googleapiclient.errors # Import specifically for HttpError handling

from src.spotify_client import SpotifyClient
from src.youtube_client import YouTubeClient, TOKEN_FILE as YT_TOKEN_FILE
from src.utils import sanitize_filename, extract_playlist_id_from_url
from src.logger_config import app_logger as logger

# Load environment variables from .env file
load_dotenv()

# Initialize Flask application
app = Flask(__name__)
app.secret_key = os.urandom(24) # Secret key for session management

# Global client handlers, initialized once per process
spotify_handler = None
youtube_handler = None

# Flag to ensure browser is opened only once per application run
_browser_opened_this_run = False

def initialize_clients():
    """
    Initializes or re-initializes Spotify and YouTube API clients.

    Ensures that both clients are ready for use. For YouTube, it also triggers
    the OAuth authentication flow if necessary (e.g., no token or expired token).

    Raises:
        FileNotFoundError: If YouTube client_secret.json is not found.
        ConnectionError: If YouTube authentication fails.
        Exception: For any other unexpected errors during initialization.
    """
    global spotify_handler, youtube_handler
    try:
        # Initialize Spotify client if not already initialized
        if not spotify_handler:
            spotify_handler = SpotifyClient()
            if not spotify_handler.sp:
                logger.error("Spotify client failed to initialize properly. Check .env and Spotify API status.")
                # Allow to continue; the generate_conversion_stream will handle this gracefully
        
        # Initialize/re-initialize YouTube client if not available or not authenticated
        if not youtube_handler or not youtube_handler.youtube:
            youtube_handler = YouTubeClient() # This might create a new instance and re-trigger auth
            
            # Validate YouTube client secrets file path
            if not youtube_handler.client_secrets_file or not os.path.exists(youtube_handler.client_secrets_file):
                logger.error("YouTube client_secret.json path not configured in .env or file missing. YouTube features will fail.")
                raise FileNotFoundError("YouTube client_secret.json path not configured or file missing. Check YOUTUBE_CLIENT_SECRETS_FILE in .env and the 'credentials' directory.")

            # Attempt to get an authenticated YouTube service (triggers OAuth if needed)
            if not youtube_handler._get_authenticated_service():
                logger.error("Failed to build and authenticate YouTube service. OAuth flow might not have completed or other issues occurred.")
                raise ConnectionError("Failed to initialize and authenticate YouTube service. Check terminal for OAuth prompts or error messages regarding 'client_secret.json' or API access.")

        logger.info("Spotify and YouTube clients initialized/re-initialized successfully.")
        return True
    except (ValueError, FileNotFoundError) as e:
        logger.error(f"Configuration error during client initialization: {e}")
        raise
    except ConnectionError as e:
        logger.error(f"Connection/Auth error during YouTube client initialization: {e}")
        raise
    except Exception as e:
        logger.exception(f"An unexpected error occurred during client initialization: {e}")
        raise

@app.route('/')
def index():
    """
    Renders the main index page.

    Checks if YouTube is authorized (i.e., if a token.json file exists)
    to display appropriate UI elements.
    """
    yt_authorized = os.path.exists(YT_TOKEN_FILE)
    return render_template('index.html', yt_authorized=yt_authorized)

def generate_conversion_stream(spotify_playlist_url: str, youtube_playlist_name: str, yt_privacy_status: str):
    """
    Generator function that performs the Spotify to YouTube playlist conversion
    and streams progress updates back to the client via Server-Sent Events (SSE).

    Args:
        spotify_playlist_url (str): The URL of the Spotify playlist to convert.
        youtube_playlist_name (str): The desired name for the new YouTube playlist.
        yt_privacy_status (str): The privacy status for the YouTube playlist ("public", "private", "unlisted").

    Yields:
        str: Formatted strings ("data: MESSAGE\n\n") representing conversion progress or errors.
             Ends with "data: END_OF_STREAM\n\n".
    """
    try:
        # Initialize API clients; if this fails, yield error and stop
        if not initialize_clients():
            yield "data: Error: Could not initialize API clients. Please check your .env configuration, 'credentials/client_secret.json', and ensure you have completed the YouTube OAuth flow if prompted. Check logs (logs/converter.log and terminal) for more details.\n\n"
            yield "data: END_OF_STREAM\n\n"
            return
    except Exception as e:
        logger.error(f"Fatal error during client initialization in generate_conversion_stream: {e}")
        yield f"data: FATAL Error during client initialization: {str(e)}. Please check server logs and configuration.\n\n"
        yield "data: END_OF_STREAM\n\n"
        return

    # Check if clients are available after initialization attempt
    if not spotify_handler or not spotify_handler.sp:
        yield "data: Error: Spotify client is not available. Check .env configuration and logs.\n\n"
        yield "data: END_OF_STREAM\n\n"
        return
    if not youtube_handler or not youtube_handler.youtube:
        yield "data: Error: YouTube client is not available or not authenticated. This usually means the YouTube authorization (OAuth) process was not completed successfully (e.g., token.json missing or invalid, or client_secret.json issue). Try again, ensure you allow permissions in the browser pop-up if prompted, and check server logs.\n\n"
        yield "data: END_OF_STREAM\n\n"
        return

    yield "data: Fetching tracks from Spotify playlist...\n\n"
    logger.info(f"Attempting to fetch tracks for URL: {spotify_playlist_url}")
    spotify_tracks = spotify_handler.get_playlist_tracks(spotify_playlist_url)

    if not spotify_tracks:
        yield f"data: No valid tracks (songs) found in Spotify playlist or an error occurred. URL: {spotify_playlist_url}. This could also mean the playlist is empty, private, or contains only podcasts/local files.\n\n"
        logger.warning(f"No tracks found for Spotify URL: {spotify_playlist_url}")
        yield "data: END_OF_STREAM\n\n"
        return
    
    yield f"data: Found {len(spotify_tracks)} tracks in the Spotify playlist.\n\n"

    # Determine the final YouTube playlist name
    final_youtube_playlist_name = youtube_playlist_name
    if not final_youtube_playlist_name:
        # If no name provided, try to derive from Spotify playlist details
        playlist_id_for_name = extract_playlist_id_from_url(spotify_playlist_url)
        suggested_name = "My Spotify Playlist on YouTube" # Default fallback name
        if playlist_id_for_name:
            playlist_details = spotify_handler.get_playlist_details(playlist_id_for_name)
            if playlist_details and playlist_details.get('name'):
                suggested_name = sanitize_filename(f"{playlist_details['name']} (on YouTube)")
            elif spotify_tracks: # Fallback to first track name if playlist details unavailable
                suggested_name = sanitize_filename(f"{spotify_tracks[0][0]} and others (on YouTube)")
        final_youtube_playlist_name = suggested_name
        yield f"data: Using default YouTube playlist name: '{final_youtube_playlist_name}'\n\n"

    youtube_playlist_desc = f"Playlist created from Spotify playlist: {spotify_playlist_url} by SpotifyToYouTubeConverter."
    
    yield f"data: Creating YouTube playlist: '{final_youtube_playlist_name}' (Privacy: {yt_privacy_status})...\n\n"
    youtube_playlist_id = youtube_handler.create_playlist(final_youtube_playlist_name, youtube_playlist_desc, yt_privacy_status)

    if not youtube_playlist_id:
        yield f"data: Error: Failed to create YouTube playlist '{final_youtube_playlist_name}'. Check logs for API errors (e.g., quota issues, invalid characters in name not caught by sanitization, or auth problems).\n\n"
        logger.error(f"Failed to create YouTube playlist: {final_youtube_playlist_name}")
        yield "data: END_OF_STREAM\n\n"
        return

    yield f"data: YouTube playlist created! ID: {youtube_playlist_id}\n\n"
    yield f"data: Link: https://www.youtube.com/playlist?list={youtube_playlist_id}\n\n"

    added_count = 0
    not_found_count = 0
    failed_to_add_count = 0
    # Keywords to use for YouTube search, ordered by preference
    search_keywords = ["official video", "official music video", "official audio", "lyrics", "audio", ""]

    # Iterate through each Spotify track and search/add to YouTube
    for i, (track_name, artist_name) in enumerate(spotify_tracks):
        base_query = f"{track_name} {artist_name}"
        yield f"data: [{i+1}/{len(spotify_tracks)}] Searching for: '{track_name} - {artist_name}'...\n\n"
        logger.info(f"Searching for '{base_query}' on YouTube.")
        
        video_ids = []
        try:
            # Defensive check for YouTube client availability
            if not youtube_handler or not youtube_handler.youtube:
                yield "data:   Critical Error: YouTube service became unavailable mid-process. Aborting.\n\n"
                logger.error("YouTube service object is None before search_video_with_keywords. Aborting current conversion.")
                break # Exit the loop if client is unavailable
            
            video_ids = youtube_handler.search_video_with_keywords(base_query, search_keywords, max_results=1)
        except googleapiclient.errors.HttpError as e:
            error_content = str(e.content.decode() if e.content else str(e))
            if e.resp.status == 403 and "quotaExceeded" in error_content.lower():
                yield "data: FATAL ERROR: YouTube API Quota Exceeded during song search. Cannot continue searching. Please try again after your quota resets (usually daily PST), or request a quota increase from Google Cloud Console.\n\n"
                logger.error("YouTube API Quota Exceeded during song search. Aborting current conversion.")
                break # Critical error, stop processing
            else:
                yield f"data:   API Error searching for '{base_query}'. Skipping. Error: {e.resp.status} - {error_content}\n\n"
                logger.warning(f"API Error searching for '{base_query}': {e.resp.status} - {error_content}")
                not_found_count +=1
                time.sleep(0.5) # Small delay before next search
                continue
        except Exception as e:
            yield f"data:   Unexpected error searching for '{base_query}'. Skipping. Error: {str(e)}\n\n"
            logger.exception(f"Unexpected error searching for '{base_query}': {e}")
            not_found_count +=1
            time.sleep(0.5) # Small delay before next search
            continue

        if video_ids:
            video_to_add_id = video_ids[0]
            yield f"data:   Found YouTube video ID: {video_to_add_id}. Adding to playlist...\n\n"
            logger.debug(f"Found video ID {video_to_add_id} for '{base_query}'. Attempting to add.")
            try:
                # Defensive check for YouTube client availability
                if not youtube_handler or not youtube_handler.youtube:
                    yield "data:   Critical Error: YouTube service became unavailable mid-process. Aborting.\n\n"
                    logger.error("YouTube service object is None before add_video_to_playlist. Aborting current conversion.")
                    break # Exit the loop if client is unavailable
                
                if youtube_handler.add_video_to_playlist(youtube_playlist_id, video_to_add_id):
                    yield f"data:   Successfully added '{track_name} - {artist_name}' to YouTube playlist.\n\n"
                    added_count += 1
                else:
                    yield f"data:   Failed to add '{track_name} - {artist_name}' (Video ID: {video_to_add_id}) to playlist. Video might be unavailable or other API issue noted in logs.\n\n"
                    failed_to_add_count += 1
            except googleapiclient.errors.HttpError as e:
                error_content = str(e.content.decode() if e.content else str(e))
                if e.resp.status == 403 and "quotaExceeded" in error_content.lower():
                    yield "data: FATAL ERROR: YouTube API Quota Exceeded while trying to add a video. Cannot continue. Please try again after your quota resets.\n\n"
                    logger.error("YouTube API Quota Exceeded during add_video_to_playlist. Aborting current conversion.")
                    break # Critical error, stop processing
                else:
                    yield f"data:   API Error adding video '{video_to_add_id}' to playlist. Skipping. Error: {e.resp.status} - {error_content}\n\n"
                    logger.warning(f"API Error adding video '{video_to_add_id}': {e.resp.status} - {error_content}")
                    failed_to_add_count += 1
            except Exception as e:
                yield f"data:   Unexpected error adding video '{video_to_add_id}'. Skipping. Error: {str(e)}\n\n"
                logger.exception(f"Unexpected error adding video '{video_to_add_id}': {e}")
                failed_to_add_count += 1
        else:
            yield f"data:   Could not find a suitable YouTube video for '{track_name} - {artist_name}'. Skipping.\n\n"
            not_found_count += 1
        
        time.sleep(0.5) # Small delay between adding videos to avoid hitting rate limits

    # Final summary messages
    yield "\n\ndata: --- Process Complete ---\n\n"
    yield f"data: Successfully added {added_count} songs to the YouTube playlist '{final_youtube_playlist_name}'.\n\n"
    if not_found_count > 0:
        yield f"data: {not_found_count} songs could not be found on YouTube.\n\n"
    if failed_to_add_count > 0:
        yield f"data: {failed_to_add_count} songs were found but failed to be added (e.g., video unavailable, quota issue during add, or other API error).\n\n"
    if youtube_playlist_id:
        yield f"data: Find your new playlist here: https://www.youtube.com/playlist?list={youtube_playlist_id}\n\n"
    yield "data: END_OF_STREAM\n\n" # Signal end of stream to frontend
    logger.info("Conversion process finished for this request.")

@app.route('/convert', methods=['POST'])
def convert_route():
    """
    Handles the POST request for playlist conversion.

    Retrieves Spotify URL, desired YouTube playlist name, and privacy status
    from the form data. Initiates the streaming conversion process.
    """
    spotify_playlist_url = request.form.get('spotify_url')
    youtube_playlist_name_input = request.form.get('yt_playlist_name', '').strip()
    yt_privacy_status_input = request.form.get('yt_privacy', 'private')

    if not spotify_playlist_url:
        logger.warning("Conversion attempt with no Spotify URL.")
        # Return an error stream if Spotify URL is missing
        def error_stream():
            yield "data: Error: Spotify Playlist URL is required.\n\n"
            yield "data: END_OF_STREAM\n\n"
        return Response(stream_with_context(error_stream()), mimetype='text/event-stream')

    logger.info(f"Received conversion request. Spotify URL: {spotify_playlist_url}, YT Playlist Name: '{youtube_playlist_name_input}', Privacy: {yt_privacy_status_input}")
    # Return a streaming response using the generator function
    return Response(stream_with_context(generate_conversion_stream(spotify_playlist_url, youtube_playlist_name_input, yt_privacy_status_input)),
                    mimetype='text/event-stream')

@app.route('/check_auth')
def check_auth_status():
    """
    API endpoint to check if YouTube is currently authorized.

    Returns:
        dict: A JSON object with {"yt_authorized": True/False}.
    """
    yt_authorized = os.path.exists(YT_TOKEN_FILE)
    return {"yt_authorized": yt_authorized}

def attempt_open_browser():
    """
    Attempts to open the web browser to the application URL.
    Ensures the browser is opened only once per application run.
    """
    global _browser_opened_this_run
    if not _browser_opened_this_run:
        url = "http://127.0.0.1:5000/"
        try:
            logger.info(f"Attempting to open web browser to {url}.")
            webbrowser.open_new(url)
            _browser_opened_this_run = True
        except Exception as e:
            logger.warning(f"Could not automatically open web browser: {e}")
            logger.warning(f"Please manually open your browser and navigate to {url}")

if __name__ == '__main__':
    # Determine desired debug mode. True for development.
    RUN_IN_DEBUG_MODE = True
    app.config['DEBUG'] = RUN_IN_DEBUG_MODE # Set DEBUG config for the app instance

    # Create necessary directories if they don't exist
    if not os.path.exists("logs"):
        try:
            os.makedirs("logs")
            logger.info("Created 'logs' directory.")
        except OSError as e:
            logger.error(f"Could not create 'logs' directory: {e}")
    
    if not os.path.exists("credentials"):
        try:
            os.makedirs("credentials")
            logger.info("Created 'credentials' directory. Place your 'client_secret.json' here.")
        except OSError as e:
            logger.error(f"Could not create 'credentials' directory: {e}")

    # Check if running in Flask's reloader worker process
    is_worker_process = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    
    # Open browser only from the worker process (when debug is True)
    # or from the single process (when debug is False).
    if is_worker_process or not app.debug:
        if not _browser_opened_this_run:
            # Delay opening the browser slightly to allow the server to start
            Timer(1.0, attempt_open_browser).start()

    # Conditional startup logging for cleaner console output in debug mode
    if not is_worker_process and app.debug: # This is the parent reloader process
        logger.info("Flask reloader is active. Main Flask application process will start shortly.")
    else: # This is the worker process, or debug is False (single process)
        logger.info("Starting Flask application process...")
        # Perform initial checks for client configurations
        try:
            temp_spotify_handler = SpotifyClient()
            if not temp_spotify_handler.sp:
                logger.warning("Spotify client failed to initialize properly on startup.")
            else:
                logger.info("Spotify client basic initialization check passed.")
        except Exception as e:
            logger.error(f"Failed during initial Spotify client check on startup: {e}")

        try:
            temp_yt_client = YouTubeClient()
            if not temp_yt_client.client_secrets_file:
                logger.error("YOUTUBE_CLIENT_SECRETS_FILE not set in .env.")
            elif not os.path.exists(temp_yt_client.client_secrets_file):
                logger.error(f"YouTube client_secret.json not found: {temp_yt_client.client_secrets_file}.")
            else:
                logger.info("YouTube client basic configuration check passed.")
        except Exception as e:
            logger.error(f"Problem with YouTube client configuration on startup: {e}")

    # Run the Flask application
    app.run(host='127.0.0.1', port=5000)

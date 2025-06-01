import os
import time
from flask import Flask, render_template, request, redirect, url_for, Response, stream_with_context
from dotenv import load_dotenv

from src.spotify_client import SpotifyClient
from src.youtube_client import YouTubeClient, TOKEN_FILE as YT_TOKEN_FILE
from src.utils import sanitize_filename, extract_playlist_id_from_url
from src.logger_config import app_logger as logger # Use the configured logger

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24) # For session management, if needed later

# Global handlers - initialize once if possible, or ensure re-initialization is safe
spotify_handler = None
youtube_handler = None

def initialize_clients():
    global spotify_handler, youtube_handler
    try:
        if not spotify_handler: # Initialize Spotify client if not already done
            spotify_handler = SpotifyClient()
        
        # Always re-initialize YouTube client or check token validity before major operations.
        # Re-initializing ensures that if token.json was deleted or became invalid,
        # the auth flow can be triggered again.
        youtube_handler = YouTubeClient() # This will trigger auth if token.json is missing/invalid
        
        if not youtube_handler.youtube: # Check if YouTube auth was successful
            logger.error("Failed to initialize YouTube client after attempt. YouTube object is None.")
            # It's possible auth flow started but didn't complete, or client_secret.json is bad.
            raise ConnectionError("Failed to initialize YouTube client. This might be due to an incomplete OAuth flow, an issue with 'client_secret.json', or network problems. Check terminal and logs.")

        logger.info("Spotify and YouTube clients initialized/re-initialized.")
        return True
    except (ValueError, FileNotFoundError) as e: # Specific config errors
        logger.error(f"Configuration error during client initialization: {e}")
        return False
    except ConnectionError as e: # Specific error from our check
        logger.error(f"Connection/Auth error during YouTube client initialization: {e}")
        return False
    except Exception as e: # Catch-all for other unexpected issues
        logger.exception(f"An unexpected error occurred during client initialization: {e}")
        return False

@app.route('/')
def index():
    # Check if YouTube token exists to give user an idea of auth status
    yt_authorized = os.path.exists(YT_TOKEN_FILE)
    return render_template('index.html', yt_authorized=yt_authorized)

def generate_conversion_stream(spotify_playlist_url, youtube_playlist_name, yt_privacy_status):
    """Generator function to stream conversion progress."""
    
    # Attempt to initialize clients at the beginning of each conversion request.
    # This allows for re-authorization if needed (e.g. token.json deleted).
    if not initialize_clients():
        yield "data: Error: Could not initialize API clients. Please check your .env configuration, 'credentials/client_secret.json', and ensure you have completed the YouTube OAuth flow if prompted. Check logs (logs/converter.log and terminal) for more details.\n\n"
        yield "data: END_OF_STREAM\n\n"
        return

    # Redundant checks after initialize_clients, but good for explicit error messaging if something unexpected happens
    if not spotify_handler or not spotify_handler.sp:
        yield "data: Error: Spotify client is not available. Check logs.\n\n"
        yield "data: END_OF_STREAM\n\n"
        return
    if not youtube_handler or not youtube_handler.youtube:
        yield "data: Error: YouTube client is not available. This usually means the YouTube authorization (OAuth) process was not completed successfully. Try again, and ensure you allow permissions in the browser pop-up. Check logs.\n\n"
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

    # Suggest a default YouTube playlist name if not provided by user
    final_youtube_playlist_name = youtube_playlist_name
    if not final_youtube_playlist_name:
        playlist_id_for_name = extract_playlist_id_from_url(spotify_playlist_url)
        suggested_name = "My Spotify Playlist on YouTube" # Generic fallback
        if playlist_id_for_name:
            playlist_details = spotify_handler.get_playlist_details(playlist_id_for_name)
            if playlist_details and playlist_details.get('name'):
                suggested_name = sanitize_filename(f"{playlist_details['name']} (on YouTube)")
            elif spotify_tracks: # Fallback if name fetch fails but we have tracks
                suggested_name = sanitize_filename(f"{spotify_tracks[0][0]} and others (on YouTube)")
        final_youtube_playlist_name = suggested_name
        yield f"data: Using default YouTube playlist name: '{final_youtube_playlist_name}'\n\n"


    youtube_playlist_desc = f"Playlist created from Spotify playlist: {spotify_playlist_url} by SpotifyToYouTubeConverter."
    
    yield f"data: Creating YouTube playlist: '{final_youtube_playlist_name}' (Privacy: {yt_privacy_status})...\n\n"
    youtube_playlist_id = youtube_handler.create_playlist(final_youtube_playlist_name, youtube_playlist_desc, yt_privacy_status)

    if not youtube_playlist_id:
        yield f"data: Error: Failed to create YouTube playlist '{final_youtube_playlist_name}'. Check logs for API errors (e.g., quota issues, invalid characters in name not caught by sanitization).\n\n"
        logger.error(f"Failed to create YouTube playlist: {final_youtube_playlist_name}")
        yield "data: END_OF_STREAM\n\n"
        return

    yield f"data: YouTube playlist created! ID: {youtube_playlist_id}\n\n"
    yield f"data: Link: https://www.youtube.com/playlist?list={youtube_playlist_id}\n\n"

    added_count = 0
    not_found_count = 0
    failed_to_add_count = 0
    # Order of preference for search keywords, "" for base query as last resort.
    search_keywords = ["official video", "official music video", "official audio", "lyrics", "audio", ""] 

    for i, (track_name, artist_name) in enumerate(spotify_tracks):
        base_query = f"{track_name} {artist_name}"
        yield f"data: [{i+1}/{len(spotify_tracks)}] Searching for: '{track_name} - {artist_name}'...\n\n"
        logger.info(f"Searching for '{base_query}' on YouTube.")
        
        video_ids = []
        try:
            video_ids = youtube_handler.search_video_with_keywords(base_query, search_keywords, max_results=1)
        except googleapiclient.errors.HttpError as e:
            if e.resp.status == 403 and "quotaExceeded" in str(e.content).lower():
                yield "data: FATAL ERROR: YouTube API Quota Exceeded. Cannot continue searching. Please try again after your quota resets (usually daily PST), or request a quota increase from Google Cloud Console.\n\n"
                logger.error("YouTube API Quota Exceeded during song search. Aborting current conversion.")
                break # Stop processing more songs for this conversion
            else:
                yield f"data:   API Error searching for '{base_query}'. Skipping. Error: {e.resp.status}\n\n"
                logger.warning(f"API Error searching for '{base_query}': {e.resp.status} - {e.content.decode()}")
                not_found_count +=1
                time.sleep(0.5) # Small delay after an error
                continue
        except Exception as e: # Catch other potential errors from search_video_with_keywords
            yield f"data:   Unexpected error searching for '{base_query}'. Skipping. Error: {str(e)}\n\n"
            logger.exception(f"Unexpected error searching for '{base_query}': {e}")
            not_found_count +=1
            time.sleep(0.5) # Small delay
            continue


        if video_ids:
            video_to_add_id = video_ids[0]
            yield f"data:   Found YouTube video ID: {video_to_add_id}. Adding to playlist...\n\n"
            logger.debug(f"Found video ID {video_to_add_id} for '{base_query}'. Attempting to add.")
            try:
                if youtube_handler.add_video_to_playlist(youtube_playlist_id, video_to_add_id):
                    yield f"data:   Successfully added '{track_name} - {artist_name}' to YouTube playlist.\n\n"
                    added_count += 1
                else:
                    yield f"data:   Failed to add '{track_name} - {artist_name}' (Video ID: {video_to_add_id}) to playlist. Video might be unavailable or other API issue.\n\n"
                    failed_to_add_count += 1
            except googleapiclient.errors.HttpError as e: # Specifically catch quota errors for adding video
                if e.resp.status == 403 and "quotaExceeded" in str(e.content).lower():
                    yield "data: FATAL ERROR: YouTube API Quota Exceeded while trying to add a video. Cannot continue. Please try again after your quota resets.\n\n"
                    logger.error("YouTube API Quota Exceeded during add_video_to_playlist. Aborting current conversion.")
                    break # Stop processing
                else:
                    yield f"data:   API Error adding video '{video_to_add_id}' to playlist. Skipping. Error: {e.resp.status}\n\n"
                    logger.warning(f"API Error adding video '{video_to_add_id}': {e.resp.status} - {e.content.decode()}")
                    failed_to_add_count += 1
            except Exception as e:
                yield f"data:   Unexpected error adding video '{video_to_add_id}'. Skipping. Error: {str(e)}\n\n"
                logger.exception(f"Unexpected error adding video '{video_to_add_id}': {e}")
                failed_to_add_count += 1

        else:
            yield f"data:   Could not find a suitable YouTube video for '{track_name} - {artist_name}'. Skipping.\n\n"
            not_found_count += 1
        
        time.sleep(0.5) # Small delay between song processing to be kind to APIs

    yield "\n\ndata: --- Process Complete ---\n\n"
    yield f"data: Successfully added {added_count} songs to the YouTube playlist '{final_youtube_playlist_name}'.\n\n"
    if not_found_count > 0:
        yield f"data: {not_found_count} songs could not be found on YouTube.\n\n"
    if failed_to_add_count > 0:
        yield f"data: {failed_to_add_count} songs were found but failed to be added (e.g., video unavailable, quota issue during add, or other API error).\n\n"
    if youtube_playlist_id: # Only show link if playlist was created
        yield f"data: Find your new playlist here: https://www.youtube.com/playlist?list={youtube_playlist_id}\n\n"
    yield "data: END_OF_STREAM\n\n" # Signal end for client-side
    logger.info("Conversion process finished for this request.")

@app.route('/convert', methods=['POST'])
def convert():
    spotify_playlist_url = request.form.get('spotify_url')
    youtube_playlist_name_input = request.form.get('yt_playlist_name', '').strip() # Optional
    yt_privacy_status_input = request.form.get('yt_privacy', 'private')

    if not spotify_playlist_url:
        # This should ideally be handled by client-side validation too, but server-side is crucial.
        logger.warning("Conversion attempt with no Spotify URL.")
        # For SSE, we can't just return a simple error string easily without breaking client expectation.
        # It's better to start the stream and send an error message through it.
        def error_stream():
            yield "data: Error: Spotify Playlist URL is required.\n\n"
            yield "data: END_OF_STREAM\n\n"
        return Response(stream_with_context(error_stream()), mimetype='text/event-stream')

    logger.info(f"Received conversion request. Spotify URL: {spotify_playlist_url}, YT Playlist Name: '{youtube_playlist_name_input}', Privacy: {yt_privacy_status_input}")
    # Stream the response
    return Response(stream_with_context(generate_conversion_stream(spotify_playlist_url, youtube_playlist_name_input, yt_privacy_status_input)),
                    mimetype='text/event-stream')

@app.route('/check_auth')
def check_auth_status():
    # This is a simplified check based on token file existence.
    # A more robust check would try a very small, low-quota API call to verify token validity.
    yt_authorized = os.path.exists(YT_TOKEN_FILE)
    return {"yt_authorized": yt_authorized}

if __name__ == '__main__':
    # Ensure necessary directories exist at startup
    if not os.path.exists("logs"):
        try:
            os.makedirs("logs")
            logger.info("Created 'logs' directory.")
        except OSError as e:
            logger.error(f"Could not create 'logs' directory: {e}")
            print(f"ERROR: Could not create 'logs' directory: {e}. Logging to file might fail.")
    
    if not os.path.exists("credentials"):
        try:
            os.makedirs("credentials")
            logger.info("Created 'credentials' directory. Place your 'client_secret.json' here.")
        except OSError as e:
            logger.error(f"Could not create 'credentials' directory: {e}")
            print(f"ERROR: Could not create 'credentials' directory: {e}. YouTube auth will likely fail without 'client_secret.json'.")


    logger.info("Starting Flask application...")
    # Initial client initialization attempt on startup can highlight immediate config issues.
    # However, for YouTube, the actual OAuth flow happens on first use if token.json is missing.
    # We won't block startup if YouTube auth isn't immediately ready, as the user needs the UI
    # to trigger the flow.
    try:
        # global spotify_handler # Ensure we're using the global
        spotify_handler = SpotifyClient() # Initialize Spotify client
        if not spotify_handler.sp:
            logger.warning("Spotify client failed to initialize properly on startup. Check .env and Spotify API status.")
    except Exception as e:
        logger.error(f"Failed to initialize Spotify client on startup: {e}")
        print(f"WARNING: Failed to initialize Spotify client on startup: {e}. Check .env.")

    # For YouTube, we just ensure the class can be instantiated. Actual auth is deferred.
    try:
        YouTubeClient() # Test if class can be instantiated (checks for YOUTUBE_CLIENT_SECRETS_FILE in .env)
    except (ValueError, FileNotFoundError) as e:
        logger.error(f"Problem with YouTube client configuration on startup (likely YOUTUBE_CLIENT_SECRETS_FILE in .env or missing client_secret.json): {e}")
        print(f"CRITICAL WARNING: Problem with YouTube client configuration: {e}. YouTube functionality will fail.")
    except Exception as e:
        logger.error(f"Unexpected error during initial YouTube client check: {e}")


    # For local development, debug=True is helpful. For any "production" local use, set to False.
    # host='0.0.0.0' makes it accessible on your local network, 127.0.0.1 only from your machine.
    app.run(debug=True, host='127.0.0.1', port=5000)
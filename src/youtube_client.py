import os
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
from google.oauth2.credentials import Credentials as OAuthCredentials
from google.auth.transport.requests import Request as GoogleAuthRequest # Alias to avoid confusion
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError, retry_if_exception_type
from typing import List, Optional

from src.logger_config import app_logger as logger

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"
TOKEN_FILE = "token.json" # Stores user's access and refresh tokens.

# Custom retry condition for specific HTTP errors (e.g., 500, 503 for server-side issues)
def is_retryable_youtube_error(exception):
    if isinstance(exception, googleapiclient.errors.HttpError):
        # Retry on server errors (5xx) or specific transient errors like 429 (Rate Limit Exceeded, though tenacity doesn't handle 'Retry-After' header by default)
        # For quotaExceeded (403), we typically don't want to retry immediately.
        return exception.resp.status in [500, 502, 503, 504] # , 429
    return False

class YouTubeClient:
    def __init__(self):
        self.client_secrets_file = os.getenv('YOUTUBE_CLIENT_SECRETS_FILE')
        self.youtube = None # Initialize to None

        if not self.client_secrets_file:
            logger.error("YouTube client secrets file path (YOUTUBE_CLIENT_SECRETS_FILE) not found in .env file.")
            # Not raising exception here, let app.py handle startup checks
            return
        if not os.path.exists(self.client_secrets_file):
            logger.error(f"YouTube client secrets file not found at specified path: {self.client_secrets_file}")
            return
            
        # Defer actual service building to _get_authenticated_service, which can be called on demand
        # self.youtube = self._get_authenticated_service() # Called by app.py or when needed

    def _get_authenticated_service(self):
        # If service already exists and credentials seem valid (simplified check), return it
        if self.youtube and self.youtube._http.credentials and self.youtube._http.credentials.valid:
             logger.debug("Returning existing valid YouTube service object.")
             return self.youtube

        credentials = None
        if os.path.exists(TOKEN_FILE):
            try:
                credentials = OAuthCredentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
                logger.info(f"Loaded YouTube credentials from {TOKEN_FILE}")
            except Exception as e: # Catch broad exceptions for token loading issues
                logger.warning(f"Error loading token file ({TOKEN_FILE}): {e}. Will attempt re-authentication.")
                if os.path.exists(TOKEN_FILE):
                    try: os.remove(TOKEN_FILE)
                    except OSError as oe: logger.error(f"Error removing corrupted token file '{TOKEN_FILE}': {oe}")

        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                try:
                    logger.info("Refreshing YouTube access token...")
                    credentials.refresh(GoogleAuthRequest())
                    logger.info("YouTube access token refreshed successfully.")
                except Exception as e: # Catch broad exceptions for refresh token issues
                    logger.warning(f"Error refreshing YouTube token: {e}. Re-authentication will be required.")
                    credentials = None # Force re-authentication
                    if os.path.exists(TOKEN_FILE): # Remove token if refresh fails
                        try: os.remove(TOKEN_FILE)
                        except OSError as oe: logger.error(f"Error removing token file after failed refresh '{TOKEN_FILE}': {oe}")
            
            if not credentials or not credentials.valid: # If still not valid, run full auth flow
                if not os.path.exists(self.client_secrets_file):
                    logger.error(f"Critical: YouTube client_secret.json not found at {self.client_secrets_file}. Cannot proceed with authentication.")
                    return None
                try:
                    logger.info("Starting YouTube OAuth flow. A browser window should open for authorization.")
                    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
                        self.client_secrets_file, SCOPES)
                    credentials = flow.run_local_server(port=0) # Opens browser, waits for auth
                    logger.info("YouTube OAuth flow completed by user.")
                except FileNotFoundError: # Specifically for client_secrets_file
                    logger.error(f"YouTube client_secret.json not found at {self.client_secrets_file} during OAuth flow initiation.")
                    return None
                except Exception as e: # Catch other OAuth flow errors
                    logger.exception(f"An error occurred during YouTube authentication flow: {e}")
                    return None
            
            try: # Save credentials after successful auth or refresh
                with open(TOKEN_FILE, 'w') as token:
                    token.write(credentials.to_json())
                logger.info(f"YouTube credentials saved to {TOKEN_FILE}")
            except Exception as e: # Catch errors during token saving
                logger.exception(f"Error saving YouTube token file '{TOKEN_FILE}': {e}")
                # Don't return None here if credentials object is valid, service might still build
                pass # Proceed to build service if credentials object is usable

        if not credentials: # If after all attempts, credentials are still None
            logger.error("Failed to obtain valid YouTube credentials.")
            return None

        try:
            # cache_discovery=False is important for dynamically loaded APIs or to avoid issues with stale cache files
            service = googleapiclient.discovery.build(API_SERVICE_NAME, API_VERSION, credentials=credentials, cache_discovery=False)
            logger.info("YouTube API service built successfully.")
            self.youtube = service # Store the service object
            return service
        except Exception as e: # Catch errors during service build
            logger.exception(f"An error occurred building YouTube service object: {e}")
            return None

    @retry(
        stop=stop_after_attempt(2), # Fewer retries for search as it's less critical per item
        wait=wait_exponential(multiplier=1, min=1, max=3),
        retry=retry_if_exception_type(googleapiclient.errors.HttpError) # Retry on HttpError (e.g. server error)
    )
    def search_video_with_keywords(self, base_query: str, keywords: List[str], max_results: int = 1) -> List[str]:
        if not self.youtube and not self._get_authenticated_service(): # Ensure service is available
            logger.error("YouTube client not initialized or authenticated for search_video_with_keywords.")
            return []

        # Try with " Official" appended to the base query first, as it's often very effective.
        prioritized_queries = [f"{base_query} Official"] 
        for kw in keywords:
            if kw: # Add non-empty keywords
                prioritized_queries.append(f"{base_query} {kw}")
        if "" in keywords or not keywords : # If empty string is a keyword or no keywords given, add base_query
            prioritized_queries.append(base_query)
        
        # Remove duplicates while preserving order (important for priority)
        unique_queries = list(dict.fromkeys(prioritized_queries))


        for query_attempt in unique_queries:
            logger.debug(f"Searching YouTube with query: '{query_attempt}'")
            try:
                request = self.youtube.search().list(
                    part="snippet",
                    q=query_attempt,
                    type="video",
                    maxResults=max_results,
                    videoCategoryId="10", # Music category ID
                    relevanceLanguage="en" # Optional: hint language for relevance
                )
                response = request.execute()
                video_ids = [item['id']['videoId'] for item in response.get('items', []) if item.get('id', {}).get('videoId')]
                if video_ids:
                    logger.info(f"Found video for query '{query_attempt}': {video_ids[0]}")
                    return video_ids # Return on first successful keyworded search
            except googleapiclient.errors.HttpError as e:
                if e.resp.status == 403 and "quotaExceeded" in str(e.content).lower():
                    logger.error(f"YouTube API quota exceeded during search for '{query_attempt}'.")
                    raise # Re-raise to stop retries for this specific query and inform caller
                elif e.resp.status == 400 and "invalidSearchFilter" in str(e.content).lower():
                    logger.warning(f"Invalid search filter for query '{query_attempt}'. This might be due to special characters. Error: {e.content.decode()}")
                    continue # Try next query if this one has bad chars
                logger.warning(f"API error during YouTube search for '{query_attempt}': {e.resp.status} - {e.content.decode()}")
                # Let Tenacity handle retries for other HttpErrors if configured
            except RetryError: # Comes from Tenacity if all retries for this query fail
                logger.warning(f"All retry attempts failed for YouTube search query: '{query_attempt}'")
                continue # Try next query in the list
            except Exception as e:
                logger.exception(f"Unexpected error during YouTube search for '{query_attempt}': {e}")
                continue # Try next query if unexpected error occurs
        
        logger.warning(f"No video found for base query '{base_query}' with any keyword variations.")
        return []


    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(is_retryable_youtube_error))
    def create_playlist(self, title: str, description: str = "", privacy_status: str = "private") -> Optional[str]:
        if not self.youtube and not self._get_authenticated_service():
            logger.error("YouTube client not initialized or authenticated for create_playlist.")
            return None
            
        valid_privacy_statuses = ["public", "private", "unlisted"]
        if privacy_status not in valid_privacy_statuses:
            logger.warning(f"Invalid privacy status '{privacy_status}'. Defaulting to 'private'.")
            privacy_status = "private"
        try:
            logger.info(f"Creating YouTube playlist: '{title}' (Privacy: {privacy_status})")
            request = self.youtube.playlists().insert(
                part="snippet,status",
                body={
                    "snippet": {"title": title, "description": description},
                    "status": {"privacyStatus": privacy_status}
                }
            )
            response = request.execute()
            playlist_id = response["id"]
            logger.info(f"YouTube playlist created successfully. ID: {playlist_id}, Title: '{title}'")
            return playlist_id
        except googleapiclient.errors.HttpError as e:
            if e.resp.status == 403 and "quotaExceeded" in str(e.content).lower():
                logger.error(f"YouTube API quota exceeded while creating playlist '{title}'.")
            elif e.resp.status == 400 and "playlistTitleInvalid" in str(e.content).lower():
                logger.error(f"Invalid title for YouTube playlist: '{title}'. Error: {e.content.decode()}")
            else:
                logger.error(f"API error creating playlist '{title}': Status {e.resp.status} - {e.content.decode()}")
            return None # Do not retry on quota exceeded or invalid title
        except RetryError as e: # Comes from Tenacity
            logger.error(f"Failed to create playlist '{title}' after multiple retries: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error creating playlist '{title}': {e}")
            return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(is_retryable_youtube_error))
    def add_video_to_playlist(self, playlist_id: str, video_id: str) -> bool:
        if not self.youtube and not self._get_authenticated_service():
            logger.error("YouTube client not initialized or authenticated for add_video_to_playlist.")
            return False
        try:
            logger.debug(f"Adding video {video_id} to playlist {playlist_id}")
            request = self.youtube.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {"kind": "youtube#video", "videoId": video_id}
                    }
                }
            )
            request.execute()
            logger.info(f"Successfully added video {video_id} to playlist {playlist_id}.")
            return True
        except googleapiclient.errors.HttpError as e:
            error_content_str = e.content.decode().lower() # For easier string searching
            if e.resp.status == 403 and "quotaExceeded" in error_content_str:
                logger.error(f"YouTube API quota exceeded while adding video {video_id} to playlist {playlist_id}.")
                raise # Re-raise to inform the caller and stop retries for this specific action
            elif e.resp.status == 404 and ("videoNotFound" in error_content_str or "playlistNotFound" in error_content_str):
                logger.warning(f"Video {video_id} or Playlist {playlist_id} not found. Cannot add.")
            elif e.resp.status == 403 and "forbidden" in error_content_str: # General forbidden, not quota
                 logger.warning(f"Forbidden to add video {video_id} to playlist {playlist_id}. Check ownership/permissions or if video allows embedding/adding.")
            elif e.resp.status == 400 and "videoAlreadyInPlaylist" in error_content_str:
                 logger.info(f"Video {video_id} is already in playlist {playlist_id}.")
                 return True # Treat as success as the goal is achieved
            else: # Other HTTP errors
                logger.error(f"API error adding video {video_id} to playlist {playlist_id}: Status {e.resp.status} - {e.content.decode()}")
            return False # For errors we don't want to retry or that indicate failure
        except RetryError as e: # Comes from Tenacity
            logger.error(f"Failed to add video {video_id} to playlist {playlist_id} after retries: {e}")
            return False
        except Exception as e:
            logger.exception(f"Unexpected error adding video {video_id} to playlist {playlist_id}: {e}")
            return False

if __name__ == '__main__':
    try:
        yt_client = YouTubeClient()
        # Manually trigger service build if needed for testing non-Flask scenarios
        if not yt_client.youtube:
            yt_client._get_authenticated_service()

        if yt_client.youtube:
            logger.info("YouTube client initialized successfully for testing.")
            
            # Test search
            test_song_name = "Bohemian Rhapsody"
            test_artist_name = "Queen"
            base_q = f"{test_song_name} {test_artist_name}"
            search_kws = ["official video", "official audio", "live", ""]
            
            logger.info(f"Searching for: '{base_q}' with keywords...")
            video_ids_found = yt_client.search_video_with_keywords(base_q, search_kws, max_results=1)
            
            if video_ids_found:
                test_vid_id = video_ids_found[0]
                logger.info(f"Found video ID for '{base_q}': {test_vid_id}")

                # Test create playlist
                pl_title_test = "Test API Playlist - Py"
                pl_id_test = yt_client.create_playlist(pl_title_test, "A test playlist via API.", "private")
                if pl_id_test:
                    logger.info(f"Playlist '{pl_title_test}' created with ID: {pl_id_test}")
                    logger.info(f"Link: https://www.youtube.com/playlist?list={pl_id_test}")

                    # Test add video
                    logger.info(f"Adding video {test_vid_id} to playlist {pl_id_test}")
                    add_success = yt_client.add_video_to_playlist(pl_id_test, test_vid_id)
                    if add_success:
                        logger.info(f"Video {test_vid_id} added successfully to {pl_id_test}!")
                    else:
                        logger.warning(f"Failed to add video {test_vid_id} to {pl_id_test}.")
                    
                    # Test adding it again (should be handled gracefully)
                    logger.info(f"Attempting to add video {test_vid_id} to playlist {pl_id_test} again...")
                    add_success_again = yt_client.add_video_to_playlist(pl_id_test, test_vid_id)
                    if add_success_again:
                        logger.info(f"Video {test_vid_id} 'added' again successfully (or was already there).")

                else:
                    logger.warning(f"Failed to create playlist '{pl_title_test}'.")
            else:
                logger.warning(f"No video found for test query '{base_q}'.")
        else:
            logger.error("YouTube client could not be initialized in __main__ test block.")
            
    except Exception as e:
        logger.exception(f"Error in YouTube client __main__ test block: {e}")
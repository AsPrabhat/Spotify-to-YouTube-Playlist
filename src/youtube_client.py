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

def is_retryable_youtube_error(exception):
    """
    Determines if a Google API HttpError is retryable based on its HTTP status code.
    Retryable status codes typically indicate transient server errors.
    """
    if isinstance(exception, googleapiclient.errors.HttpError):
        return exception.resp.status in [500, 502, 503, 504]
    return False

class YouTubeClient:
    """
    Handles authentication and interactions with the YouTube Data API v3.

    Provides methods for searching videos, creating playlists, and adding videos to playlists.
    Manages OAuth 2.0 authentication flow and token persistence.
    """
    def __init__(self):
        """
        Initializes the YouTubeClient by loading the path to the client secrets file.
        The actual authentication and service building are deferred to _get_authenticated_service.
        """
        self.client_secrets_file = os.getenv('YOUTUBE_CLIENT_SECRETS_FILE')
        self.youtube = None # Stores the authenticated YouTube API service object

        if not self.client_secrets_file:
            logger.error("YouTube client secrets file path (YOUTUBE_CLIENT_SECRETS_FILE) not found in .env file.")
            return
        if not os.path.exists(self.client_secrets_file):
            logger.error(f"YouTube client secrets file not found at specified path: {self.client_secrets_file}")
            return

    def _get_authenticated_service(self):
        """
        Authenticates with the YouTube API and returns a service object.

        This method handles:
        1. Loading existing credentials from TOKEN_FILE.
        2. Refreshing expired credentials using a refresh token.
        3. Initiating a new OAuth 2.0 flow if no valid credentials exist.
        4. Saving new/refreshed credentials to TOKEN_FILE.

        Returns:
            googleapiclient.discovery.Resource: An authenticated YouTube API service object,
                                                or None if authentication fails.
        """
        # Return existing valid service object if available
        if self.youtube and self.youtube._http.credentials and self.youtube._http.credentials.valid:
             logger.debug("Returning existing valid YouTube service object.")
             return self.youtube

        credentials = None
        # Attempt to load credentials from a saved token file
        if os.path.exists(TOKEN_FILE):
            try:
                credentials = OAuthCredentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
                logger.info(f"Loaded YouTube credentials from {TOKEN_FILE}")
            except Exception as e:
                logger.warning(f"Error loading token file ({TOKEN_FILE}): {e}. Will attempt re-authentication.")
                # Remove corrupted token file to force re-authentication
                if os.path.exists(TOKEN_FILE):
                    try: os.remove(TOKEN_FILE)
                    except OSError as oe: logger.error(f"Error removing corrupted token file '{TOKEN_FILE}': {oe}")

        # If credentials are not valid (e.g., expired or not found)
        if not credentials or not credentials.valid:
            # Attempt to refresh expired credentials if a refresh token is available
            if credentials and credentials.expired and credentials.refresh_token:
                try:
                    logger.info("Refreshing YouTube access token...")
                    credentials.refresh(GoogleAuthRequest())
                    logger.info("YouTube access token refreshed successfully.")
                except Exception as e:
                    logger.warning(f"Error refreshing YouTube token: {e}. Re-authentication will be required.")
                    credentials = None # Invalidate credentials to force new OAuth flow
                    # Remove token file if refresh failed to prevent using stale token
                    if os.path.exists(TOKEN_FILE):
                        try: os.remove(TOKEN_FILE)
                        except OSError as oe: logger.error(f"Error removing token file after failed refresh '{TOKEN_FILE}': {oe}")

            # If still no valid credentials, initiate a new OAuth flow
            if not credentials or not credentials.valid:
                if not os.path.exists(self.client_secrets_file):
                    logger.error(f"Critical: YouTube client_secret.json not found at {self.client_secrets_file}. Cannot proceed with authentication.")
                    return None
                try:
                    logger.info("Starting YouTube OAuth flow. A browser window should open for authorization.")
                    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
                        self.client_secrets_file, SCOPES)
                    # run_local_server opens a browser for user authorization
                    credentials = flow.run_local_server(port=0)
                    logger.info("YouTube OAuth flow completed by user.")
                except FileNotFoundError:
                    logger.error(f"YouTube client_secret.json not found at {self.client_secrets_file} during OAuth flow initiation.")
                    return None
                except Exception as e:
                    logger.exception(f"An error occurred during YouTube authentication flow: {e}")
                    return None

            # Save the newly obtained or refreshed credentials to TOKEN_FILE
            try:
                with open(TOKEN_FILE, 'w') as token:
                    token.write(credentials.to_json())
                logger.info(f"YouTube credentials saved to {TOKEN_FILE}")
            except Exception as e:
                logger.exception(f"Error saving YouTube token file '{TOKEN_FILE}': {e}")
                pass # Continue even if saving fails, as credentials are in memory

        if not credentials:
            logger.error("Failed to obtain valid YouTube credentials.")
            return None

        # Build the YouTube API service object
        try:
            service = googleapiclient.discovery.build(API_SERVICE_NAME, API_VERSION, credentials=credentials, cache_discovery=False)
            logger.info("YouTube API service built successfully.")
            self.youtube = service # Store the service object for future use
            return service
        except Exception as e:
            logger.exception(f"An error occurred building YouTube service object: {e}")
            return None

    @retry(
        stop=stop_after_attempt(2), # Stop after 2 attempts
        wait=wait_exponential(multiplier=1, min=1, max=3), # Exponential backoff
        retry=retry_if_exception_type(googleapiclient.errors.HttpError) # Retry on HttpError
    )
    def search_video_with_keywords(self, base_query: str, keywords: List[str], max_results: int = 1) -> List[str]:
        """
        Searches for a YouTube video using a base query and a list of keywords.
        Prioritizes queries with "Official" and then other keywords.

        Args:
            base_query (str): The primary search query (e.g., "Song Name Artist").
            keywords (List[str]): A list of additional keywords to try with the base query.
                                  An empty string in the list will search with just the base_query.
            max_results (int): The maximum number of video IDs to return. Defaults to 1.

        Returns:
            List[str]: A list of YouTube video IDs found, or an empty list if no videos are found
                       or an error occurs.
        """
        # Ensure client is authenticated before proceeding
        if not self.youtube and not self._get_authenticated_service():
            logger.error("YouTube client not initialized or authenticated for search_video_with_keywords.")
            return []

        # Generate prioritized search queries
        prioritized_queries = [f"{base_query} Official"] # Prioritize official videos
        for kw in keywords:
            if kw:
                prioritized_queries.append(f"{base_query} {kw}")
        if "" in keywords or not keywords: # Add base query if empty keyword is present or no keywords provided
            prioritized_queries.append(base_query)

        # Remove duplicates while preserving order
        unique_queries = list(dict.fromkeys(prioritized_queries))

        for query_attempt in unique_queries:
            logger.debug(f"Searching YouTube with query: '{query_attempt}'")
            try:
                request = self.youtube.search().list(
                    part="snippet",
                    q=query_attempt,
                    type="video",
                    maxResults=max_results,
                    videoCategoryId="10", # Music category
                    relevanceLanguage="en" # English results preferred
                )
                response = request.execute()
                # Extract video IDs from the search results
                video_ids = [item['id']['videoId'] for item in response.get('items', []) if item.get('id', {}).get('videoId')]
                if video_ids:
                    logger.info(f"Found video for query '{query_attempt}': {video_ids[0]}")
                    return video_ids # Return first found video ID
            except googleapiclient.errors.HttpError as e:
                error_content_str = str(e.content.decode() if e.content else str(e)).lower()
                if e.resp.status == 403 and "quotaExceeded" in error_content_str:
                    logger.error(f"YouTube API quota exceeded during search for '{query_attempt}'.")
                    raise # Re-raise to be caught by tenacity or higher level
                elif e.resp.status == 400 and "invalidSearchFilter" in error_content_str:
                    logger.warning(f"Invalid search filter for query '{query_attempt}'. Error: {e.content.decode() if e.content else e}")
                    continue # Try next query attempt
                logger.warning(f"API error during YouTube search for '{query_attempt}': {e.resp.status} - {e.content.decode() if e.content else e}")
            except RetryError: # Caught if all tenacity retries fail for a specific query
                logger.warning(f"All retry attempts failed for YouTube search query: '{query_attempt}'")
                continue # Try next query attempt
            except Exception as e:
                logger.exception(f"Unexpected error during YouTube search for '{query_attempt}': {e}")
                continue # Try next query attempt

        logger.warning(f"No video found for base query '{base_query}' with any keyword variations.")
        return []


    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(is_retryable_youtube_error))
    def create_playlist(self, title: str, description: str = "", privacy_status: str = "private") -> Optional[str]:
        """
        Creates a new YouTube playlist.

        Args:
            title (str): The title of the new playlist.
            description (str): The description for the playlist. Defaults to an empty string.
            privacy_status (str): The privacy status of the playlist ("public", "private", or "unlisted").
                                  Defaults to "private".

        Returns:
            Optional[str]: The ID of the newly created playlist, or None if creation fails.
        """
        # Ensure client is authenticated before proceeding
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
            error_content_str = str(e.content.decode() if e.content else str(e)).lower()
            if e.resp.status == 403 and "quotaExceeded" in error_content_str:
                logger.error(f"YouTube API quota exceeded while creating playlist '{title}'.")
            elif e.resp.status == 400 and "playlistTitleInvalid" in error_content_str:
                logger.error(f"Invalid title for YouTube playlist: '{title}'. Error: {e.content.decode() if e.content else e}")
            else:
                logger.error(f"API error creating playlist '{title}': Status {e.resp.status} - {e.content.decode() if e.content else e}")
            return None
        except RetryError as e:
            logger.error(f"Failed to create playlist '{title}' after multiple retries: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error creating playlist '{title}': {e}")
            return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(is_retryable_youtube_error))
    def add_video_to_playlist(self, playlist_id: str, video_id: str) -> bool:
        """
        Adds a video to a specified YouTube playlist.

        Args:
            playlist_id (str): The ID of the target playlist.
            video_id (str): The ID of the video to add.

        Returns:
            bool: True if the video was successfully added or was already in the playlist,
                  False otherwise.
        """
        # Ensure client is authenticated before proceeding
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
            error_content_str = str(e.content.decode() if e.content else str(e)).lower()
            if e.resp.status == 403 and "quotaExceeded" in error_content_str:
                logger.error(f"YouTube API quota exceeded while adding video {video_id} to playlist {playlist_id}.")
                raise # Re-raise to be caught by tenacity or higher level
            elif e.resp.status == 404 and ("videoNotFound" in error_content_str or "playlistNotFound" in error_content_str):
                logger.warning(f"Video {video_id} or Playlist {playlist_id} not found. Cannot add.")
            elif e.resp.status == 403 and "forbidden" in error_content_str:
                 logger.warning(f"Forbidden to add video {video_id} to playlist {playlist_id}. Check ownership/permissions or if video allows embedding/adding.")
            elif e.resp.status == 400 and "videoAlreadyInPlaylist" in error_content_str:
                 logger.info(f"Video {video_id} is already in playlist {playlist_id}.")
                 return True # Consider it a success if video is already present
            else:
                logger.error(f"API error adding video {video_id} to playlist {playlist_id}: Status {e.resp.status} - {e.content.decode() if e.content else e}")
            return False
        except RetryError as e:
            logger.error(f"Failed to add video {video_id} to playlist {playlist_id} after retries: {e}")
            return False
        except Exception as e:
            logger.exception(f"Unexpected error adding video {video_id} to playlist {playlist_id}: {e}")
            return False

if __name__ == '__main__':
    # Example usage and testing when the script is run directly
    try:
        yt_client = YouTubeClient()
        # Ensure the client is authenticated for testing purposes
        if not yt_client.youtube:
            yt_client._get_authenticated_service()

        if yt_client.youtube:
            logger.info("YouTube client initialized successfully for testing.")

            # --- Test video search ---
            test_song_name = "Bohemian Rhapsody"
            test_artist_name = "Queen"
            base_q = f"{test_song_name} {test_artist_name}"
            search_kws = ["official video", "official audio", "live", ""] # Various keywords to try

            logger.info(f"Searching for: '{base_q}' with keywords...")
            video_ids_found = yt_client.search_video_with_keywords(base_q, search_kws, max_results=1)

            if video_ids_found:
                test_vid_id = video_ids_found[0]
                logger.info(f"Found video ID for '{base_q}': {test_vid_id}")

                # --- Test playlist creation ---
                pl_title_test = "Test API Playlist - Py"
                pl_id_test = yt_client.create_playlist(pl_title_test, "A test playlist via API.", "private")
                if pl_id_test:
                    logger.info(f"Playlist '{pl_title_test}' created with ID: {pl_id_test}")
                    logger.info(f"Link: https://www.youtube.com/playlist?list={pl_id_test}")

                    # --- Test adding video to playlist ---
                    logger.info(f"Adding video {test_vid_id} to playlist {pl_id_test}")
                    add_success = yt_client.add_video_to_playlist(pl_id_test, test_vid_id)
                    if add_success:
                        logger.info(f"Video {test_vid_id} added successfully to {pl_id_test}!")
                    else:
                        logger.warning(f"Failed to add video {test_vid_id} to {pl_id_test}.")

                    # Test adding the same video again (should be handled gracefully)
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

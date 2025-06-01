import os
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError, retry_if_exception_type
from typing import List, Tuple, Optional, Dict

from src.utils import extract_playlist_id_from_url
from src.logger_config import app_logger as logger

load_dotenv()

class SpotifyClient:
    def __init__(self):
        self.client_id = os.getenv('SPOTIPY_CLIENT_ID')
        self.client_secret = os.getenv('SPOTIPY_CLIENT_SECRET')
        self.sp = None # Initialize sp to None

        if not self.client_id or not self.client_secret:
            logger.error("Spotify API credentials (SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET) not found in .env file.")
            # Not raising an exception here, so app.py can handle it more gracefully at a higher level
            return

        try:
            auth_manager = SpotifyClientCredentials(client_id=self.client_id, client_secret=self.client_secret)
            self.sp = spotipy.Spotify(auth_manager=auth_manager)
            logger.info("Spotify client initialized successfully.")
        except Exception as e:
            logger.exception(f"Error initializing Spotify client: {e}")
            self.sp = None # Ensure sp is None on failure

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type(spotipy.SpotifyException) # Retry on specific Spotify exceptions
    )
    def _fetch_playlist_items_page(self, playlist_id: str, offset: int = 0, limit: int = 50):
        if not self.sp:
            logger.error("Spotify client not available for _fetch_playlist_items_page.")
            return None # Or raise an exception
        logger.debug(f"Fetching playlist items for {playlist_id} with offset {offset}, limit {limit}")
        return self.sp.playlist_items(playlist_id, offset=offset, limit=limit, fields="items(track(name,artists(name),type,id)),next,offset,limit,total")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type(spotipy.SpotifyException)
    )
    def get_playlist_details(self, playlist_id: str) -> Optional[Dict]:
        if not self.sp:
            logger.error("Spotify client not available for get_playlist_details.")
            return None
        try:
            logger.debug(f"Fetching details for Spotify playlist ID: {playlist_id}")
            return self.sp.playlist(playlist_id, fields="name,id,description")
        except spotipy.SpotifyException as e:
            logger.error(f"Spotify API error fetching playlist details for {playlist_id}: {e.http_status} - {e.msg}")
        except RetryError as e: # Comes from Tenacity
            logger.error(f"Failed to fetch playlist details for {playlist_id} after multiple retries: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error fetching playlist details for {playlist_id}: {e}")
        return None

    def get_playlist_tracks(self, playlist_url: str) -> List[Tuple[str, str]]:
        if not self.sp:
            logger.error("Spotify client not initialized. Cannot fetch playlist tracks.")
            return []

        playlist_id = extract_playlist_id_from_url(playlist_url)
        if not playlist_id:
            logger.warning(f"Invalid Spotify playlist URL or ID: '{playlist_url}'")
            return []

        tracks_info: List[Tuple[str, str]] = []
        offset = 0
        limit = 50 # Spotify API max limit per request for playlist_items is 50
        total_tracks_expected = None

        logger.info(f"Fetching tracks from Spotify playlist ID: {playlist_id}")
        try:
            while True:
                results = self._fetch_playlist_items_page(playlist_id, offset=offset, limit=limit)
                
                if not results:
                    logger.warning(f"No results returned from Spotify for playlist {playlist_id} at offset {offset}. Ending fetch.")
                    break
                
                if total_tracks_expected is None: # Get total on first successful call
                    total_tracks_expected = results.get('total', 0)
                    logger.info(f"Spotify reports {total_tracks_expected} total items in playlist {playlist_id}.")

                items = results.get('items', [])
                if not items and offset == 0 and total_tracks_expected == 0 : # Empty playlist
                    logger.info(f"Spotify playlist {playlist_id} is empty.")
                    break
                if not items and offset > 0: # No more items on subsequent pages
                    logger.debug(f"No more items found on page for playlist {playlist_id} at offset {offset}.")
                    break


                for item in items:
                    track = item.get('track')
                    
                    if not track: 
                        logger.info(f"Skipping non-track item in playlist (local file, removed, or unsupported type). Item data: {item.get('type', 'N/A')}")
                        continue

                    if track.get('type') != 'track': # Explicitly check type, podcasts are 'episode'
                        logger.info(f"Skipping non-song item of type '{track.get('type')}': '{track.get('name', 'Unknown Item')}'")
                        continue

                    if track.get('name') and track.get('artists'):
                        track_name = track['name']
                        artist_names = [artist['name'] for artist in track.get('artists', []) if artist.get('name')]
                        artist_name_str = ", ".join(artist_names)
                        if not artist_name_str: # Handle case where artists list is empty or names are missing
                            artist_name_str = "Unknown Artist"
                        tracks_info.append((track_name, artist_name_str))
                        logger.debug(f"Added track: {track_name} - {artist_name_str}")
                    else:
                        logger.warning(f"Skipping track due to missing name or artist data: ID {track.get('id', 'Unknown ID')}")
                
                if results.get('next'):
                    offset += limit 
                else: # No 'next' link means we're done
                    break
            
        except spotipy.SpotifyException as e:
            logger.error(f"Spotify API Error during track fetching for {playlist_id}: {e.http_status} - {e.msg}")
            if e.http_status == 404:
                logger.warning(f"Spotify playlist with ID: {playlist_id} not found.")
            return [] # Return empty on significant API error
        except RetryError as e: # Comes from Tenacity
            logger.error(f"Failed to fetch playlist tracks for {playlist_id} after multiple retries: {e}")
            return []
        except Exception as e:
            logger.exception(f"An unexpected error occurred while fetching Spotify playlist tracks for {playlist_id}: {e}")
            return []

        logger.info(f"Found {len(tracks_info)} valid song tracks in playlist {playlist_id}.")
        return tracks_info

if __name__ == '__main__':
    s_client = SpotifyClient()
    if s_client.sp:
        # Test with a playlist known to have various item types if possible
        # test_pl_url = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M" # Top 50 Global
        test_pl_url = "https://open.spotify.com/playlist/5xS3qcjoIuM26N8qXY1Tf5" # Example public playlist
        logger.info(f"Fetching tracks from: {test_pl_url}")
        
        playlist_id_for_details = extract_playlist_id_from_url(test_pl_url)
        if playlist_id_for_details:
            details = s_client.get_playlist_details(playlist_id_for_details)
            if details:
                logger.info(f"Playlist Name from details: {details.get('name')}")
            else:
                logger.warning("Could not get playlist details.")

        pl_tracks = s_client.get_playlist_tracks(test_pl_url)
        if pl_tracks:
            logger.info(f"Found {len(pl_tracks)} tracks:")
            for i, (name, artist) in enumerate(pl_tracks[:10]): # Print first 10
                logger.info(f"{i+1}. {name} - {artist}")
        else:
            logger.warning("No tracks found or error occurred.")
    else:
        logger.error("Spotify client failed to initialize in __main__ test block.")
import re
from typing import Optional

def extract_playlist_id_from_url(url: str) -> Optional[str]:
    """
    Extracts the Spotify playlist ID from a URL.
    Handles various Spotify playlist URL formats.
    Example URLs:
    - https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M
    - spotify:playlist:37i9dQZF1DXcBWIGoYBM5M
    - https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=somethingsomething
    """
    if not isinstance(url, str):
        return None
        
    # Regex to find the playlist ID in common Spotify URL formats
    # It looks for 'playlist/' followed by an ID, or 'playlist:' followed by an ID
    match = re.search(r"(?:playlist/|playlist:)([a-zA-Z0-9]{22})", url) # Spotify IDs are typically 22 chars
    if match:
        return match.group(1)
    
    # If it's just an ID (alphanumeric, 22 characters), assume it's valid
    if re.fullmatch(r"[a-zA-Z0-9]{22}", url):
        return url
        
    return None

def sanitize_filename(name: str) -> str:
    """Removes characters that are problematic for filenames and limits length."""
    if not isinstance(name, str):
        return "Invalid Playlist Name"
        
    # Remove most non-alphanumeric characters except spaces, hyphens, underscores, parentheses
    name = re.sub(r'[^\w\s\-\(\)]', '', name)
    # Replace multiple spaces with a single space
    name = re.sub(r'\s+', ' ', name).strip()
    # Limit length (YouTube playlist titles have a limit, e.g., 150 chars, be conservative)
    return name[:100]

if __name__ == '__main__':
    # Test cases for extract_playlist_id_from_url
    urls_to_test = [
        "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",
        "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M",
        "https://open.spotify.com/playlist/123abcXYZsomenewid12345?si=qwerty", # 22 char ID
        "37i9dQZF1DXcBWIGoYBM5M", # Just the ID
        "https://open.spotify.com/album/0sNOF9WDwhWunNAHPD3qjc", # Album URL (should fail)
        "invalid_url_string", # Invalid string (should fail)
        "https://open.spotify.com/user/spotify/playlist/37i9dQZF1DXcBWIGoYBM5M", # User specific URL
        None, # Test None input
        12345 # Test non-string input
    ]

    print("Testing extract_playlist_id_from_url:")
    for url in urls_to_test:
        playlist_id = extract_playlist_id_from_url(url)
        print(f"URL: '{url}' -> ID: '{playlist_id}'")

    print("\nTesting sanitize_filename:")
    filenames_to_test = [
        "My Awesome! Playlist*",
        "Song Title / Remix (feat. Artist) & More stuff here to test the length limit just in case it is very very very very very very very very very very very very very very very long",
        "  Extra   Spaces  ",
        "Test (Parentheses)",
        None,
        123
    ]
    for name in filenames_to_test:
        sanitized = sanitize_filename(name)
        print(f"Original: '{name}' -> Sanitized: '{sanitized}' (Length: {len(sanitized)})")
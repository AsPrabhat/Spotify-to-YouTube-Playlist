import re
from typing import Optional

def extract_playlist_id_from_url(url: str) -> Optional[str]:
    """
    Extracts the Spotify playlist ID from various URL formats or returns the ID if already provided.

    Args:
        url (str): The Spotify playlist URL or ID string.

    Returns:
        Optional[str]: The 22-character Spotify playlist ID, or None if not found or invalid.
    """
    if not isinstance(url, str):
        return None

    # Regex to find the 22-character ID after 'playlist/' or 'playlist:'
    match = re.search(r"(?:playlist/|playlist:)([a-zA-Z0-9]{22})", url)
    if match:
        return match.group(1)

    # If the input is just the 22-character ID
    if re.fullmatch(r"[a-zA-Z0-9]{22}", url):
        return url

    return None

def sanitize_filename(name: str) -> str:
    """
    Sanitizes a string to be used as a safe filename.

    Removes problematic characters, replaces multiple spaces with a single space,
    strips leading/trailing whitespace, and truncates the name to 100 characters.

    Args:
        name (str): The original string to sanitize.

    Returns:
        str: The sanitized filename string. Returns "Invalid Playlist Name" if input is not a string.
    """
    if not isinstance(name, str):
        return "Invalid Playlist Name"

    # Remove characters that are not alphanumeric, spaces, hyphens, or parentheses
    name = re.sub(r'[^\w\s\-\(\)]', '', name)
    # Replace multiple spaces with a single space and strip leading/trailing whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    # Truncate to 100 characters to avoid excessively long filenames
    return name[:100]

if __name__ == '__main__':
    # --- Test cases for extract_playlist_id_from_url ---
    urls_to_test = [
        "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",
        "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M",
        "https://open.spotify.com/playlist/123abcXYZsomenewid12345?si=qwerty",
        "37i9dQZF1DXcBWIGoYBM5M",
        "https://open.spotify.com/album/0sNOF9WDwhWunNAHPD3qjc", # Should not match playlist ID
        "invalid_url_string",
        "https://open.spotify.com/user/spotify/playlist/37i9dQZF1DXcBWIGoYBM5M",
        None, # Test with None input
        12345 # Test with non-string input
    ]

    print("Testing extract_playlist_id_from_url:")
    for url in urls_to_test:
        playlist_id = extract_playlist_id_from_url(url)
        print(f"URL: '{url}' -> ID: '{playlist_id}'")

    print("\nTesting sanitize_filename:")
    # --- Test cases for sanitize_filename ---
    filenames_to_test = [
        "My Awesome! Playlist*",
        "Song Title / Remix (feat. Artist) & More stuff here to test the length limit just in case it is very very very very very very very very very very very very very very very long",
        "  Extra   Spaces  ",
        "Test (Parentheses)",
        None, # Test with None input
        123 # Test with non-string input
    ]
    for name in filenames_to_test:
        sanitized = sanitize_filename(name)
        print(f"Original: '{name}' -> Sanitized: '{sanitized}' (Length: {len(sanitized)})")

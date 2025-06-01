# Spotify to YouTube Playlist Converter (Web App)

This program, now a local web application, takes a Spotify playlist URL as input, finds the corresponding songs on YouTube, and creates a new YouTube playlist with these songs.

## Directory Structure

```
spotify_to_youtube_playlist/
├── .env                   # Local environment variables (YOUR SECRETS - DO NOT COMMIT)
├── .env.example           # Example environment variables file
├── .gitignore             # Specifies intentionally untracked files that Git should ignore
├── app.py                 # Main Flask application file
├── requirements.txt       # Python package dependencies
├── credentials/           # Directory for API credential files
│   └── client_secret.json # Your YouTube OAuth 2.0 client secret (DO NOT COMMIT)
├── logs/                  # Directory for log files
│   └── converter.log      # Application log file (auto-generated)
├── src/                   # Source code directory
│   ├── __init__.py        # Makes 'src' a Python package
│   ├── logger_config.py   # Logging configuration
│   ├── spotify_client.py  # Spotify API interaction logic
│   ├── utils.py           # Utility functions
│   └── youtube_client.py  # YouTube API interaction logic
└── templates/             # HTML templates for Flask
    └── index.html         # Main web page template
```

## Features

-   Fetches all tracks from a public Spotify playlist.
    -   Gracefully skips local files and podcast episodes.
-   Searches for each track on YouTube using a prioritized keyword strategy (e.g., "official video", "official audio").
-   Creates a new YouTube playlist with user-selectable privacy (private, unlisted, public).
-   Adds found YouTube videos to the new playlist.
-   Handles Spotify API authentication (Client Credentials Flow).
-   Handles YouTube API authentication (OAuth 2.0 for Desktop Apps, via browser interaction).
-   Provides a web interface for input and progress viewing.
-   Includes basic logging to a file (`logs/converter.log`) and console.
-   Basic retry mechanism for transient API errors.

## Prerequisites

-   Python 3.8+ (ensure it's added to your system's PATH)
-   Pip (Python package installer, usually comes with Python)
-   A modern Web Browser (e.g., Chrome, Firefox, Edge)
-   A Spotify Developer Account (to get Client ID and Client Secret)
-   A Google Cloud Platform Project (to enable YouTube Data API v3 and get OAuth 2.0 credentials for a **Desktop app**)

## Setup Instructions

Follow these steps carefully to set up the project and its dependencies.

### 1. Clone the Repository

Open your terminal or command prompt.

```bash
git clone https://github.com/your_username/spotify_to_youtube_playlist.git
cd spotify_to_youtube_playlist
```
*(Replace `your_username` with your actual GitHub username if you fork/clone it there, or download the ZIP and extract it if you don't use Git).*

### 2. Create and Activate a Virtual Environment (Highly Recommended)

This isolates project dependencies and avoids conflicts with other Python projects.

```bash
python -m venv venv
```

**Activate the virtual environment:**
*   **On Windows (Command Prompt/PowerShell):**
    ```bash
    venv\Scripts\activate
    ```
*   **On macOS/Linux (bash/zsh):**
    ```bash
    source venv/bin/activate
    ```
After activation, you should see `(venv)` at the beginning of your command prompt.

### 3. Install Dependencies

With the virtual environment activated, install the required Python packages from `requirements.txt`:

```bash
pip install -r requirements.txt
```

### 4. Set Up Spotify API Credentials

You need a Client ID and Client Secret from Spotify.

1.  **Go to the Spotify Developer Dashboard:** [https://developer.spotify.com/dashboard/](https://developer.spotify.com/dashboard/)
2.  **Log in** with your Spotify account.
3.  Click **"Create app"** (or "Create an App").
    *   **App name:** `Spotify to YouTube Playlist Tool` (or any name you prefer).
    *   **App description:** `A tool to transfer Spotify playlists to YouTube.`
    *   **Website:** You can leave this blank or use your GitHub repository URL.
    *   **Redirect URI:** Enter `http://127.0.0.1:8888/callback`. (Spotify requires this for app registration, even though our script's current Spotify authentication method doesn't actively use it for this specific OAuth flow. Using `127.0.0.1` instead of `localhost` is often preferred or required by Spotify.)
    *   Agree to the terms.
4.  Once the app is created, you will see your **Client ID**. Click **"Show client secret"** to see your **Client Secret**.
    *   **Copy both the `Client ID` and `Client Secret`.** You'll need them for the `.env` file.

### 5. Set Up YouTube API Credentials (OAuth 2.0 for Desktop App)

This is the most involved step. You need to create a project in Google Cloud Console, enable the YouTube API, and get OAuth 2.0 credentials specifically for a "Desktop app".

1.  **Go to the Google Cloud Console:** [https://console.cloud.google.com/](https://console.cloud.google.com/)
2.  **Create a new project or select an existing one:**
    *   If you don't have a project, click the project dropdown at the top and then "NEW PROJECT".
    *   **Project name:** `SpotifyYouTubeTool` (or similar).
    *   Select an organization if applicable, otherwise leave as "No organization".
    *   Click **"CREATE"**.
3.  **Enable the YouTube Data API v3:**
    *   In the navigation menu (hamburger icon ☰) on the left, go to **"APIs & Services" > "Library"**.
    *   In the search bar, type `YouTube Data API v3` and select it from the results.
    *   Click the **"ENABLE"** button. Wait for it to enable.
4.  **Configure the OAuth Consent Screen:**
    *   In the navigation menu, go to **"APIs & Services" > "OAuth consent screen"**.
    *   **User Type:**
        *   Choose **"External"** unless you are part of a Google Workspace organization and only you/internal users will use this. Click **"CREATE"**.
    *   **App information:**
        *   **App name:** `Spotify to YouTube Playlist Tool` (or a name users will see when authorizing).
        *   **User support email:** Select your email address.
        *   **App logo:** Optional.
    *   **App domain:** Optional (can leave blank for local use).
    *   **Developer contact information:** Enter your email address. Click **"SAVE AND CONTINUE"**.
    *   **Scopes:**
        *   Click **"ADD OR REMOVE SCOPES"**.
        *   In the filter, search for `YouTube Data API v3`.
        *   Find and select the scope: `.../auth/youtube.force-ssl` (This scope allows full access to manage YouTube resources, including creating playlists and adding items, specifically over SSL).
        *   Click **"UPDATE"**. Then click **"SAVE AND CONTINUE"**.
    *   **Test users:**
        *   Click **"ADD USERS"**.
        *   Enter the Google account email address(es) that will be authorized to use this application while it's in "testing" mode. **Add your own Google account here.** This is crucial.
        *   Click **"ADD"**. Then click **"SAVE AND CONTINUE"**.
    *   Review the summary and click **"BACK TO DASHBOARD"**. (You might see a message about publishing the app; for personal use, keeping it in "testing" with yourself as a test user is fine and avoids Google's verification process for public apps).

5.  **Create OAuth 2.0 Client ID:**
    *   In the navigation menu, go to **"APIs & Services" > "Credentials"**.
    *   Click **"+ CREATE CREDENTIALS"** at the top.
    *   Select **"OAuth client ID"**.
    *   **Application type:** Select **"Desktop app"**. This is important for the authentication flow used by the script.
    *   **Name:** `Spotify YouTube Playlist Desktop Client` (or similar).
    *   Click **"CREATE"**.
6.  **Download Client Secret JSON:**
    *   A pop-up will appear showing your "Client ID" and "Client secret". You don't need to copy these directly from the pop-up.
    *   Instead, click **"DOWNLOAD JSON"** on the right of the newly created OAuth 2.0 Client ID entry in the credentials list (or from the pop-up if still visible).
    *   Save this file.
    *   **Rename the downloaded file to `client_secret.json`**.
    *   **Create a `credentials/` directory** inside your project folder (`spotify_to_youtube_playlist/`) if it doesn't already exist.
    *   **Place this `client_secret.json` file inside the `credentials/` directory.** The final path should be `spotify_to_youtube_playlist/credentials/client_secret.json`.

### 6. Create and Configure the Environment Variables File (`.env`)

This file will store your API keys securely.

1.  **Copy the example file:**
    In your project's root directory (`spotify_to_youtube_playlist/`), copy `.env.example` to a new file named `.env`.
    ```bash
    cp .env.example .env
    ```
    (On Windows, you might use `copy .env.example .env` in Command Prompt, or `Copy-Item .env.example .env` in PowerShell)

2.  **Edit the `.env` file** with your actual credentials using a text editor:
    ```
    SPOTIPY_CLIENT_ID='YOUR_SPOTIFY_CLIENT_ID_HERE'
    SPOTIPY_CLIENT_SECRET='YOUR_SPOTIFY_CLIENT_SECRET_HERE'
    YOUTUBE_CLIENT_SECRETS_FILE='credentials/client_secret.json'
    ```
    *   Replace `YOUR_SPOTIFY_CLIENT_ID_HERE` with the Client ID you copied from the Spotify Developer Dashboard.
    *   Replace `YOUR_SPOTIFY_CLIENT_SECRET_HERE` with the Client Secret you copied from the Spotify Developer Dashboard.
    *   The `YOUTUBE_CLIENT_SECRETS_FILE` path should already be correct (`credentials/client_secret.json`) if you placed the file as instructed.

**IMPORTANT SECURITY NOTE:**
*   The `.gitignore` file is already configured to ignore `.env` and the entire `credentials/` directory (including `client_secret.json`). **Never commit your `.env` file or your actual `client_secret.json` file to a public Git repository.**

### 7. Create Logs Directory

The application will write log files to a `logs/` directory. Create it if it doesn't exist:
```bash
mkdir logs
```
(On Windows, you can also use `md logs`)
The script will also attempt to create this directory if it's missing.

## Running the Web Application

1.  **Ensure your virtual environment is activated.**
    (e.g., `source venv/bin/activate` or `venv\Scripts\activate`)
2.  **Navigate to the project's root directory** in your terminal if you aren't already there.
3.  **Run the Flask application:**
    ```bash
    python app.py
    ```
    You should see output indicating the Flask development server is running, typically on `http://127.0.0.1:5000/`.
4.  **Open your web browser** and go to: **`http://127.0.0.1:5000`** (or `http://localhost:5000`)
5.  Use the web interface to:
    *   Enter the Spotify Playlist URL or ID.
    *   Optionally, provide a name for the new YouTube playlist.
    *   Select the privacy for the new YouTube playlist.
    *   Click "Convert Playlist".

### First-Time YouTube Authorization (via Web App)

When you run the web application and attempt your first conversion that interacts with YouTube (or if your previous authorization `token.json` is missing/expired):
1.  The Python script running the Flask application (in your terminal) will indicate it's starting the OAuth flow.
2.  A **new tab or window should automatically open in your default web browser**, prompting you to log in to your Google account (the one you added as a test user in the Google Cloud Console).
3.  After logging in, Google will ask you to grant permission for the application ("Spotify to YouTube Playlist Tool" or the name you configured in the OAuth Consent Screen) to access your YouTube account (specifically, the `youtube.force-ssl` scope).
4.  Review the permissions and click **"Allow"** (or similar).
5.  You might be shown an "Authentication successful" message in the browser, and you can usually close that browser tab. The local Flask application will have received the authorization code.
6.  The application will then create a `token.json` file in your project's root directory. This file stores your OAuth tokens so you don't have to re-authorize every time you restart the app (unless the token expires, is revoked, or the file is deleted). This `token.json` file is also in `.gitignore`.
7.  The conversion process in the web app's progress area should then continue.

If the browser does not open automatically, check the terminal running `python app.py` for a URL to manually copy and paste into your browser.

## Troubleshooting

-   **"Error initializing clients" / "client_secret.json not found":**
    *   Double-check the `YOUTUBE_CLIENT_SECRETS_FILE` path in your `.env` file.
    *   Ensure `client_secret.json` is correctly named and placed in the `spotify_to_youtube_playlist/credentials/` directory.
    *   Ensure the `client_secret.json` was downloaded for an OAuth client ID of type **"Desktop app"**.
-   **Authorization errors / "Error: restricted_client" / "Error: redirect_uri_mismatch" during YouTube auth:**
    *   This usually means the `client_secret.json` is not for a "Desktop app" type, or you're trying to use it in a way that doesn't match its configuration. The script uses a flow suitable for "Desktop app" credentials.
-   **Spotify errors:** Check `SPOTIPY_CLIENT_ID` and `SPOTIPY_CLIENT_SECRET` in `.env`.
-   **General issues:** Check the output in the terminal where `python app.py` is running, and look at the `logs/converter.log` file for more detailed error messages.
-   **Web page not loading:** Ensure `python app.py` is running without errors and accessible on `http://127.0.0.1:5000`.

## Disclaimer & API Quotas

-   Ensure you have the rights to the music you are transferring. This tool is for personal convenience and assumes you have legitimate access to the content.
-   This tool relies on public APIs (Spotify and YouTube Data API v3) and their terms of service. API behavior, terms, or quotas can change.
-   **YouTube API Quotas:** The YouTube Data API v3 has a default daily quota (typically 10,000 units).
    -   Searching for a video costs ~100 units.
    -   Adding a video to a playlist costs ~50 units.
    -   Creating a playlist costs ~50 units.
    -   A playlist with 50 songs could consume ~7550 units (50\*100 for searches + 50\*50 for adds + 50 for playlist creation).
    -   If you exceed the quota, the tool will stop processing YouTube actions and log an error. You'll need to wait until your quota resets (usually daily, Pacific Time) or apply for a quota increase from the Google Cloud Console for your project. This application does **not** manage quota increases.
-   YouTube search results may not always be perfect. The tool attempts to find the best match based on keywords.

## TODO / Future Enhancements (Beyond this version)

-   Allow user to select from top N YouTube search results per song via the UI.
-   Option to update an existing YouTube playlist (add missing songs, remove songs not in Spotify, etc.).
-   Batch processing for multiple Spotify playlists via the UI.
-   More sophisticated handling of API quota limits (e.g., estimating usage before starting, clearer warnings, potential for pause/resume if state can be saved).
-   Improved UI/UX with more dynamic updates and better error display.
-   User accounts and server-side token storage (if deploying to a shared environment, which would require hosting and a different OAuth flow than "Desktop app").
# Spotify to YouTube Playlist Converter (Web Application)

This web application facilitates the transfer of public Spotify playlists to YouTube. Users can input a Spotify playlist URL, and the application will attempt to find corresponding tracks on YouTube, subsequently creating a new YouTube playlist with these songs.

## Table of Contents

- [Spotify to YouTube Playlist Converter (Web Application)](#spotify-to-youtube-playlist-converter-web-application)
  - [Table of Contents](#table-of-contents)
  - [Overview](#overview)
  - [Features](#features)
  - [Directory Structure](#directory-structure)
  - [Prerequisites](#prerequisites)
  - [Setup Instructions](#setup-instructions)
    - [1. Clone the Repository](#1-clone-the-repository)
    - [2. Create and Activate a Virtual Environment](#2-create-and-activate-a-virtual-environment)
    - [3. Install Dependencies](#3-install-dependencies)
    - [4. Set Up Spotify API Credentials](#4-set-up-spotify-api-credentials)
    - [5. Set Up YouTube API Credentials (OAuth 2.0 for Desktop App)](#5-set-up-youtube-api-credentials-oauth-20-for-desktop-app)
    - [6. Create and Configure the Environment Variables File (`.env`)](#6-create-and-configure-the-environment-variables-file-env)
    - [7. Create Logs and Credentials Directories](#7-create-logs-and-credentials-directories)
  - [Running the Web Application](#running-the-web-application)
    - [First-Time YouTube Authorization](#first-time-youtube-authorization)
  - [Troubleshooting](#troubleshooting)
  - [API Quotas and Disclaimer](#api-quotas-and-disclaimer)

## Overview

The application provides a user-friendly web interface for converting Spotify playlists. It leverages the Spotify API to retrieve playlist data and the YouTube Data API v3 to search for tracks and manage YouTube playlists. The backend is built with Python and Flask, while the frontend uses HTML, CSS (with Bootstrap 5), and JavaScript for a responsive and interactive experience.

## Features

*   Modern, responsive, and aesthetically pleasing web interface.
*   Fetches all tracks from a public Spotify playlist.
    *   Gracefully skips local files and non-track items (e.g., podcast episodes).
*   Searches for each track on YouTube using a prioritized keyword strategy (e.g., "official video", "official audio").
*   Creates a new YouTube playlist with user-selectable privacy (private, unlisted, public).
*   Adds found YouTube videos to the new playlist.
*   Button to directly navigate to the newly created YouTube playlist.
*   Handles Spotify API authentication (Client Credentials Flow).
*   Handles YouTube API authentication (OAuth 2.0 for Desktop Apps, via browser interaction).
*   Real-time conversion progress streamed to the web interface.
*   Comprehensive logging to a file (`logs/converter.log`) and console for diagnostics.
*   Retry mechanisms for transient API errors.

## Directory Structure

```
Spotify-to-YouTube-Playlist/
├── .env                   # Local environment variables (YOUR SECRETS)
├── .env.example           # Example environment variables file
├── .gitignore             # Specifies intentionally untracked files
├── app.py                 # Main Flask application file
├── requirements.txt       # Python package dependencies
├── README.md              # This file
├── credentials/           # Directory for API credential files
│   └── client_secret.json # Your YouTube OAuth 2.0 client secret
├── logs/                  # Directory for log files
│   └── converter.log      # Application log file (auto-generated)
├── src/                   # Source code directory
│   ├── __init__.py        # Makes 'src' a Python package
│   ├── logger_config.py   # Logging configuration
│   ├── spotify_client.py  # Spotify API interaction logic
│   ├── utils.py           # Utility functions
│   └── youtube_client.py  # YouTube API interaction logic
├── static/                # Static files (CSS, JS, images)
│   └── css/
│       └── style.css      # Custom stylesheets
└── templates/             # HTML templates for Flask
    └── index.html         # Main web page template
```

## Prerequisites

*   Python 3.8 or higher (ensure it's added to your system's PATH).
*   Pip (Python package installer, typically included with Python).
*   A modern Web Browser (e.g., Chrome, Firefox, Edge, Safari).
*   A Spotify Developer Account (for Client ID and Client Secret).
*   A Google Cloud Platform Project (to enable YouTube Data API v3 and obtain OAuth 2.0 credentials for a **Desktop app**).

## Setup Instructions

Please follow these steps meticulously to configure the project and its dependencies.

### 1. Clone the Repository

Open your terminal or command prompt.

```bash
git clone https://github.com/AsPrabhat/Spotify-to-YouTube-Playlist
cd Spotify-to-YouTube-Playlist
```

### 2. Create and Activate a Virtual Environment

This practice isolates project dependencies, preventing conflicts with other Python projects.

```bash
python -m venv venv
```

**Activate the virtual environment:**
*   **Windows (Command Prompt/PowerShell):**
    ```bash
    venv\Scripts\activate
    ```
*   **macOS/Linux (bash/zsh):**
    ```bash
    source venv/bin/activate
    ```
Upon successful activation, your command prompt should be prefixed with `(venv)`.

### 3. Install Dependencies

With the virtual environment active, install the required Python packages:

```bash
pip install -r requirements.txt
```

### 4. Set Up Spotify API Credentials

A Client ID and Client Secret are required from Spotify.

1.  Navigate to the **Spotify Developer Dashboard**: [https://developer.spotify.com/dashboard/](https://developer.spotify.com/dashboard/)
2.  **Log in** using your Spotify account.
3.  Click **"Create app"** (or "Create an App").
    *   **App name:** e.g., `Playlist Transfer Tool`
    *   **App description:** e.g., `Application for converting Spotify playlists to YouTube.`
    *   **Website:** Optional (can be your GitHub repository URL).
    *   **Redirect URI:** Enter `http://127.0.0.1:5000/callback`. While not actively used by the Client Credentials Flow, Spotify requires this for app registration.
    *   Accept the terms and conditions.
4.  After app creation, your **Client ID** will be displayed. Click **"Show client secret"** to reveal the **Client Secret**.
    *   **Securely copy both the `Client ID` and `Client Secret`** for use in the `.env` file.

### 5. Set Up YouTube API Credentials (OAuth 2.0 for Desktop App)

This step involves configuring a Google Cloud Platform project.

1.  Access the **Google Cloud Console**: [https://console.cloud.google.com/](https://console.cloud.google.com/)
2.  **Create a new project or select an existing one.**
    *   If new: Click project dropdown > "NEW PROJECT".
    *   **Project name:** e.g., `YouTubePlaylistConverter`
    *   Click **"CREATE"**.
3.  **Enable the YouTube Data API v3:**
    *   Navigation menu (☰) > **"APIs & Services" > "Library"**.
    *   Search for `YouTube Data API v3` and select it.
    *   Click **"ENABLE"**.
4.  **Configure the OAuth Consent Screen:**
    *   Navigation menu > **"APIs & Services" > "OAuth consent screen"**.
    *   **User Type:** Select **"External"** (unless within a Google Workspace for internal use only). Click **"CREATE"**.
    *   **App information:**
        *   **App name:** e.g., `Playlist Transfer Tool` (this is shown to users during authorization).
        *   **User support email:** Your email address.
        *   **App logo:** Optional.
    *   **App domain:** Optional.
    *   **Developer contact information:** Your email address. Click **"SAVE AND CONTINUE"**.
    *   **Scopes:**
        *   Click **"ADD OR REMOVE SCOPES"**.
        *   Filter for `YouTube Data API v3`.
        *   Select scope: `https://www.googleapis.com/auth/youtube.force-ssl` (allows full management of YouTube resources over SSL).
        *   Click **"UPDATE"**, then **"SAVE AND CONTINUE"**.
    *   **Test users:**
        *   Click **"ADD USERS"**.
        *   Enter the Google account email address(es) authorized to use this application during its "testing" phase (typically your own Google account).
        *   Click **"ADD"**, then **"SAVE AND CONTINUE"**.
    *   Review the summary and click **"BACK TO DASHBOARD"**. For personal use, maintaining "testing" status with yourself as a test user is sufficient and bypasses Google's app verification for public apps.

5.  **Create OAuth 2.0 Client ID:**
    *   Navigation menu > **"APIs & Services" > "Credentials"**.
    *   Click **"+ CREATE CREDENTIALS"** > **"OAuth client ID"**.
    *   **Application type:** Select **"Desktop app"**. This is critical for the authentication flow used.
    *   **Name:** e.g., `Playlist Converter Desktop Client`
    *   Click **"CREATE"**.
6.  **Download Client Secret JSON:**
    *   A dialog will display your Client ID and Client Secret.
    *   Click **"DOWNLOAD JSON"** for the newly created OAuth 2.0 Client ID.
    *   Save the file.
    *   **Rename the downloaded file to `client_secret.json`**.
    *   Ensure a `credentials/` directory exists in your project root (`Spotify-to-YouTube-Playlist/`).
    *   **Place `client_secret.json` into the `credentials/` directory.** The path should be `Spotify-to-YouTube-Playlist/credentials/client_secret.json`.

### 6. Create and Configure the Environment Variables File (`.env`)

This file stores your API keys and sensitive configuration.

1.  **Copy the example file:**
    In the project's root directory, duplicate `.env.example` to create `.env`.
    ```bash
    cp .env.example .env
    ```
    (Windows: `copy .env.example .env` or PowerShell: `Copy-Item .env.example .env`)

2.  **Edit `.env`** with your credentials:
    ```
    SPOTIPY_CLIENT_ID='YOUR_SPOTIFY_CLIENT_ID_HERE'
    SPOTIPY_CLIENT_SECRET='YOUR_SPOTIFY_CLIENT_SECRET_HERE'
    YOUTUBE_CLIENT_SECRETS_FILE='credentials/client_secret.json'
    ```
    *   Replace placeholder values with your actual Spotify Client ID and Secret.
    *   Verify `YOUTUBE_CLIENT_SECRETS_FILE` points to the correct location.

**Security Imperative:**
The `.gitignore` file is configured to exclude `.env` and the `credentials/` directory.

### 7. Create Logs and Credentials Directories

If not already present, create these directories at the project root:

```bash
mkdir logs
mkdir credentials
```
(The application will also attempt to create `logs/` if missing. The `credentials/` directory is where you manually place `client_secret.json`.)

## Running the Web Application

1.  **Ensure the virtual environment is activated.**
2.  **Navigate to the project's root directory** in your terminal.
3.  **Execute the Flask application:**
    ```bash
    python app.py
    ```
    The terminal will indicate that the Flask development server is running, typically on `http://127.0.0.1:5000/`.
4.  **Open your web browser** and navigate to: **`http://127.0.0.1:5000`** (or `http://localhost:5000`).
5.  Utilize the web interface to:
    *   Input the Spotify Playlist URL or ID.
    *   Optionally, specify a name for the new YouTube playlist.
    *   Select the desired privacy setting for the YouTube playlist.
    *   Initiate the conversion process.

### First-Time YouTube Authorization

Upon the first conversion attempt (or if `token.json` is missing/expired):
1.  The terminal running `python app.py` will log the initiation of the OAuth flow.
2.  A **new browser tab/window should open automatically**, prompting for Google account login (use the account added as a test user).
3.  Google will request permission for the application to access your YouTube account.
4.  Review permissions and click **"Allow"**.
5.  An "Authentication successful" message may appear; this tab can typically be closed.
6.  The application creates/updates `token.json` in the project root, storing OAuth tokens for future sessions. This file is also gitignored.
7.  The conversion will then proceed, with progress displayed in the web interface.

If the browser does not open automatically, check the terminal for a URL to copy and paste manually.

## Troubleshooting

*   **"Error initializing clients" / "client_secret.json not found":**
    *   Verify `YOUTUBE_CLIENT_SECRETS_FILE` in `.env`.
    *   Ensure `client_secret.json` is correctly named and located in `Spotify-to-YouTube-Playlist/credentials/`.
    *   Confirm `client_secret.json` was generated for an OAuth client ID of type **"Desktop app"**.
*   **YouTube Authorization Errors (e.g., "restricted_client", "redirect_uri_mismatch"):**
    *   Typically indicates `client_secret.json` is not for a "Desktop app" type or a misconfiguration in the Google Cloud Console.
*   **Spotify API Errors:**
    *   Check `SPOTIPY_CLIENT_ID` and `SPOTIPY_CLIENT_SECRET` in `.env`.
*   **General Issues:**
    *   Consult terminal output from `python app.py`.
    *   Examine `logs/converter.log` for detailed error messages.
*   **Web Page Not Loading:**
    *   Ensure `python app.py` is running without errors and accessible at `http://127.0.0.1:5000`.
    *   Perform a hard refresh (Ctrl+F5 or Cmd+Shift+R) in your browser to clear cache.

## API Quotas and Disclaimer

*   This tool is intended for personal convenience. Users are responsible for ensuring they have the rights to the music being transferred.
*   The application relies on public APIs (Spotify and YouTube Data API v3) and their respective terms of service. API availability, behavior, or quotas are subject to change by the API providers.
*   **YouTube API Quotas:** The YouTube Data API v3 imposes default daily quotas (e.g., 10,000 units).
    *   Video search: ~100 units.
    *   Adding video to playlist: ~50 units.
    *   Playlist creation: ~50 units.
    *   Large playlists can consume significant quota. Exceeding the quota will result in API errors until the quota resets (typically daily, Pacific Time). The application does not manage quota increases; this must be handled via the Google Cloud Console.
*   **Search Accuracy:** While the tool attempts to find optimal matches, YouTube search result accuracy can vary.
# stl-book-club-v2

A Streamlit application for book club nominations and ranked-choice voting.

## Features

- **Book Nomination**: Search and nominate books using Google Books API
- **Ranked-Choice Voting**: Members can rank their book preferences
- **Results Visualization**: View voting results with interactive charts
- **Google Sheets Tracking**: Automatically track voting history across elections

## Setup

### Installation

```bash
poetry install
```

### Google Books API (Optional)

To enable book search functionality:

1. Get an API key from [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Add to `.streamlit/secrets.toml`:
   ```toml
   GOOGLE_BOOKS_API = "your-api-key-here"
   ```

### Google Sheets Voting Tracker

To track book voting history across elections:

1. **Create Google Cloud Service Account** (if not already done):
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project
   - Enable **Google Sheets API** and **Google Drive API**
   - Go to "APIs & Services" > "Credentials"
   - Create a service account and download the JSON key file

2. **Create a Google Sheet for tracking**:
   - Create a new Google Sheet (it can be empty)
   - Share it with your service account email (e.g., `robot-38@glassy-mystery-427419-e0.iam.gserviceaccount.com`) with **Editor** access
   - Copy the Sheet ID from the URL: `https://docs.google.com/spreadsheets/d/SHEET_ID_HERE/edit`

3. **Configure secrets** in `.streamlit/secrets.toml`:
   ```toml
   voting_tracker_sheet_id = "your-sheet-id-here"

   [gcp_service_account]
   type = "service_account"
   project_id = "your-project-id"
   private_key_id = "your-private-key-id"
   private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
   client_email = "your-service-account@your-project.iam.gserviceaccount.com"
   client_id = "your-client-id"
   auth_uri = "https://accounts.google.com/o/oauth2/auth"
   token_uri = "https://oauth2.googleapis.com/token"
   auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
   client_x509_cert_url = "your-cert-url"
   universe_domain = "googleapis.com"
   ```

   The service account fields come from your downloaded JSON key file.


## Running the App

```bash
poetry run streamlit run src/stl_book_club_v2/app.py
```

## Usage

1. **Nominate Books**: Use the "Nominate Books" tab to search and add books
2. **Vote**: Go to "Vote" tab, enter your name, and rank the books
3. **View Results**: Navigate to "Results" tab and click "Calculate Results"
4. **Track Results**: Click "📊 Record to Tracking Sheet" to save voting history to your Google Sheet
   - Tracks: book title, author, genre, pages, times voted on, last vote date, and if it won
   - Updates existing books or adds new ones automatically
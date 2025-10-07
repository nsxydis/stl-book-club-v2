# stl-book-club-v2

A Streamlit application for book club nominations and ranked-choice voting.

## Features

- **Book Nomination**: Search and nominate books using Google Books API
- **Ranked-Choice Voting**: Members can rank their book preferences
- **Results Visualization**: View voting results with interactive charts
- **Google Sheets Export**: Export election results to Google Sheets

## Setup

### Installation

```bash
poetry install
```

### Google Books API (Optional)

To enable book search functionality:

1. Get an API key from [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create `src/stl_book_club_v2/key.py`:
   ```python
   GOOGLE_BOOKS_API_KEY = 'your-api-key-here'
   ```
3. Or add to `.streamlit/secrets.toml` for Streamlit Cloud

### Google Sheets Export Setup

To enable exporting results to Google Sheets:

1. **Create a Google Cloud Project**:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select an existing one

2. **Enable Google Sheets API**:
   - Navigate to "APIs & Services" > "Library"
   - Search for "Google Sheets API" and enable it
   - Search for "Google Drive API" and enable it

3. **Create Service Account**:
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "Service Account"
   - Give it a name (e.g., "book-club-sheets")
   - Click "Create and Continue"
   - Skip optional steps and click "Done"

4. **Create Service Account Key**:
   - Click on the service account you just created
   - Go to "Keys" tab
   - Click "Add Key" > "Create new key"
   - Select "JSON" format
   - Download the JSON file

5. **Configure Credentials**:

   **For Local Development:**
   Create `.streamlit/secrets.toml`:
   ```toml
   [gcp_service_account]
   type = "service_account"
   project_id = "your-project-id"
   private_key_id = "your-private-key-id"
   private_key = "-----BEGIN PRIVATE KEY-----\nYour-Private-Key\n-----END PRIVATE KEY-----\n"
   client_email = "your-service-account@your-project.iam.gserviceaccount.com"
   client_id = "your-client-id"
   auth_uri = "https://accounts.google.com/o/oauth2/auth"
   token_uri = "https://oauth2.googleapis.com/token"
   auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
   client_x509_cert_url = "your-cert-url"
   ```

   **For Streamlit Cloud:**
   - Go to your app settings
   - Add the entire JSON content from the service account key file to secrets
   - Use the same format as above

## Running the App

```bash
poetry run streamlit run src/stl_book_club_v2/app.py
```

## Usage

1. **Nominate Books**: Use the "Nominate Books" tab to search and add books
2. **Vote**: Go to "Vote" tab, enter your name, and rank the books
3. **View Results**: Navigate to "Results" tab and click "Calculate Results"
4. **Export**: Click "Export to Google Sheets" to create a shareable spreadsheet with all election data
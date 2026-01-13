# Email Cleaner

A **100% local** Gmail aggregation tool that helps you analyze and clean up your inbox. All data stays on your machine - nothing is ever sent to external servers.

## Features

- Connect multiple Gmail accounts
- Aggregate emails by sender and domain
- View email counts, recent subjects, and snippets
- One-click unsubscribe (using email List-Unsubscribe headers)
- Mark emails as spam (bulk action per sender/domain)
- Move emails to trash (bulk action per sender/domain)
- Filter scans using Gmail search queries

## Security & Privacy

- **All processing happens locally** on your computer
- OAuth tokens stored only in `data/tokens/` directory
- No analytics, telemetry, or external API calls
- Open source - verify the code yourself

---

## Setup Instructions

### Step 1: Install Python Dependencies

Make sure you have Python 3.10+ installed, then:

```bash
cd "Email cleaner"
pip install -r requirements.txt
```

### Step 2: Create Google Cloud Project & OAuth Credentials

This tool uses the official Gmail API with OAuth 2.0. You need to create your own credentials (one-time setup):

#### 2.1 Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **Select a Project** (top bar) > **New Project**
3. Name it something like "Email Cleaner" and click **Create**
4. Wait for the project to be created, then select it

#### 2.2 Enable Gmail API

1. In the left sidebar, go to **APIs & Services** > **Library**
2. Search for "Gmail API"
3. Click **Gmail API** > **Enable**

#### 2.3 Configure OAuth Consent Screen

1. Go to **APIs & Services** > **OAuth consent screen**
2. Select **External** and click **Create**
3. Fill in the required fields:
   - **App name**: Email Cleaner (or any name)
   - **User support email**: Your email
   - **Developer contact email**: Your email
4. Click **Save and Continue**
5. On the **Scopes** page, click **Add or Remove Scopes**
6. Find and select:
   - `https://www.googleapis.com/auth/gmail.readonly`
   - `https://www.googleapis.com/auth/gmail.modify`
7. Click **Update** > **Save and Continue**
8. On **Test users**, click **Add Users** and add your Gmail address(es)
9. Click **Save and Continue** > **Back to Dashboard**

#### 2.4 Create OAuth 2.0 Credentials

1. Go to **APIs & Services** > **Credentials**
2. Click **Create Credentials** > **OAuth client ID**
3. Select **Desktop app** as the application type
4. Name it "Email Cleaner Desktop"
5. Click **Create**
6. Click **Download JSON** on the popup (or find it in the credentials list and download)
7. **Rename the downloaded file to `credentials.json`**
8. Move it to: `Email cleaner/config/credentials.json`

### Step 3: Run the Tool

```bash
python run.py
```

This will:
1. Start a local web server on `http://127.0.0.1:5000`
2. Open your browser (or navigate there manually)

### Step 4: Connect Your Gmail Account(s)

1. Click **"+ Add Gmail Account"**
2. A browser window will open for Google sign-in
3. Sign in and grant the requested permissions
4. The account will appear in the dashboard
5. Repeat for additional accounts

---

## Usage

### Scanning Emails

1. Set the maximum number of emails to scan per account (default: 500)
2. Optionally add a Gmail search filter (e.g., `category:promotions`, `is:unread`)
3. Click **"Scan All Accounts"**
4. Wait for the scan to complete

### Viewing Results

- **By Sender**: See all senders sorted by email count
- **By Domain**: See all domains sorted by total email count

Each result shows:
- Sender name and email
- Number of emails
- Recent subject lines
- Available actions

### Actions

- **View All**: See all emails from a sender
- **Unsubscribe**: Opens the unsubscribe link (if available in email headers)
- **Mark as Spam**: Moves all emails from sender/domain to spam folder
- **Trash All**: Moves all emails from sender/domain to trash

---

## Useful Gmail Search Filters

Use these in the "Filter" field when scanning:

| Filter | Description |
|--------|-------------|
| `category:promotions` | Marketing and promotional emails |
| `category:social` | Social media notifications |
| `category:updates` | Bills, receipts, confirmations |
| `is:unread` | Only unread emails |
| `older_than:1y` | Emails older than 1 year |
| `larger:5M` | Emails larger than 5MB |
| `has:attachment` | Emails with attachments |
| `from:newsletter` | Emails with "newsletter" in sender |

Combine filters with spaces: `category:promotions older_than:6m`

---

## Project Structure

```
Email cleaner/
├── config/
│   └── credentials.json    # Your OAuth credentials (not committed)
├── data/
│   └── tokens/             # OAuth tokens per account (local only)
├── src/
│   ├── __init__.py
│   ├── gmail_client.py     # Gmail API wrapper
│   ├── aggregator.py       # Email analysis logic
│   └── app.py              # Flask web application
├── templates/
│   └── index.html          # Web UI template
├── static/
│   ├── style.css           # Styles
│   └── app.js              # Frontend JavaScript
├── requirements.txt
├── run.py                  # Entry point
└── README.md
```

---

## Troubleshooting

### "OAuth credentials not found"
Make sure `credentials.json` is in the `config/` directory.

### "Access blocked: This app's request is invalid"
Your OAuth consent screen may not be configured correctly. Go back to Step 2.3 and ensure you've added the correct scopes and test users.

### "Error 403: access_denied"
You need to add your Gmail address as a test user in the OAuth consent screen (Step 2.3, point 8).

### Tokens expired
Delete the token file in `data/tokens/` for that account and re-authenticate.

---

## Command Line Options

```bash
python run.py --help

Options:
  -p, --port PORT   Port to run on (default: 5000)
  --debug           Enable debug mode
```

---

## License

MIT License - Use freely for personal purposes.

---

## Contributing

This is a local tool for personal use. Feel free to fork and modify for your needs.

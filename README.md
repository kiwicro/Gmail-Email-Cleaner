# Gmail Email Cleanmail

A **100% local** Gmail inbox analysis and cleanup tool. Helps you identify bulk senders, unsubscribe from newsletters, and clean up your inbox efficiently.

---

## Privacy First

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   YOUR DATA NEVER LEAVES YOUR COMPUTER                         │
│                                                                 │
│   • All processing happens locally on your machine             │
│   • No external servers, no cloud storage, no tracking         │
│   • OAuth tokens stored only in local files                    │
│   • No analytics, telemetry, or data collection                │
│   • Open source - verify the code yourself                     │
│                                                                 │
│   The only network requests are directly to Gmail's API        │
│   using YOUR credentials on YOUR machine.                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Features

- **Multi-account support** - Connect and analyze multiple Gmail accounts
- **Smart aggregation** - Group emails by sender and domain
- **Bulk actions** - Mark as spam or trash entire senders/domains at once
- **One-click unsubscribe** - Uses List-Unsubscribe headers when available
- **Gmail search filters** - Focus on promotions, old emails, large attachments, etc.
- **Privacy focused** - Everything runs locally, nothing is transmitted externally

---

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/kiwicro/Gmail-Email-Cleaner.git
cd Gmail-Email-Cleaner
```

### 2. Install Dependencies

Requires Python 3.10 or higher.

```bash
pip install -r requirements.txt
```

### 3. Set Up Google Cloud Credentials (One-Time Setup)

You need to create your own OAuth credentials. This takes about 5 minutes.

**[See detailed instructions below](#google-cloud-setup)**

### 4. Run the Tool

```bash
python run.py
```

Open your browser to `http://127.0.0.1:5000`

---

## Google Cloud Setup

Since this tool accesses your Gmail, you need to create your own Google Cloud credentials. This ensures YOU control access to YOUR data.

### Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Sign in with your Google account
3. Click **Select a Project** (top navigation bar) → **New Project**
4. Enter project name: `Gmail Cleanmail` (or any name you prefer)
5. Click **Create**
6. Wait for creation, then make sure the project is selected

### Step 2: Enable Gmail API

1. In the left sidebar, click **APIs & Services** → **Library**
2. Search for **"Gmail API"**
3. Click on **Gmail API** in the results
4. Click the blue **Enable** button

### Step 3: Configure OAuth Consent Screen

1. Go to **APIs & Services** → **OAuth consent screen**
2. Select **External** and click **Create**
3. Fill in the required fields:
   - **App name**: `Gmail Cleanmail`
   - **User support email**: Select your email
   - **Developer contact email**: Enter your email
4. Click **Save and Continue**
5. On the **Scopes** page:
   - Click **Add or Remove Scopes**
   - Find and check these two scopes:
     - `https://www.googleapis.com/auth/gmail.readonly`
     - `https://www.googleapis.com/auth/gmail.modify`
   - Click **Update**
6. Click **Save and Continue**
7. On **Test users** page:
   - Click **+ Add Users**
   - Enter your Gmail address (the one you want to clean)
   - Add any other Gmail addresses you want to use
   - Click **Add**
8. Click **Save and Continue** → **Back to Dashboard**

### Step 4: Create OAuth Credentials

1. Go to **APIs & Services** → **Credentials**
2. Click **+ Create Credentials** → **OAuth client ID**
3. Select **Desktop app** as Application type
4. Name it: `Gmail Cleanmail Desktop`
5. Click **Create**
6. In the popup, click **Download JSON**
7. **Rename** the downloaded file to exactly: `credentials.json`
8. **Move** the file to: `Gmail-Email-Cleaner/config/credentials.json`

### Step 5: First Run Authentication

1. Run `python run.py`
2. Click **"+ Add Gmail Account"** in the web interface
3. A browser window opens for Google sign-in
4. Sign in with a Gmail account you added as a test user
5. Click through the permissions (you may see "unverified app" warning - this is normal for personal projects, click "Advanced" → "Go to Gmail Cleanmail")
6. Grant the requested permissions
7. Done! The account appears in your dashboard

---

## Usage

### Scanning Your Inbox

1. After connecting your account(s), click **"Scan All Emails"**
2. Wait for the scan to complete (progress bar shows status)
3. View results by **Sender** or **Domain**

### Optional: Use Gmail Search Filters

Enter filters in the search box before scanning:

| Filter | What it does |
|--------|--------------|
| `category:promotions` | Marketing emails only |
| `category:social` | Social media notifications |
| `category:updates` | Receipts, confirmations |
| `is:unread` | Only unread emails |
| `older_than:1y` | Emails older than 1 year |
| `older_than:6m` | Emails older than 6 months |
| `larger:5M` | Large emails (5MB+) |
| `has:attachment` | Emails with attachments |

Combine filters: `category:promotions older_than:6m`

### Taking Action

For each sender or domain, you can:

- **View** - See all emails from that sender
- **Unsubscribe** - Open the unsubscribe link (if available)
- **Spam** - Move all emails to spam folder
- **Trash** - Move all emails to trash

Use checkboxes for bulk actions on multiple senders at once.

---

## Project Structure

```
Gmail-Email-Cleaner/
├── config/
│   └── credentials.json    ← Your OAuth credentials (you create this)
├── data/
│   └── tokens/             ← OAuth tokens (created automatically)
├── src/
│   ├── gmail_client.py     # Gmail API wrapper
│   ├── aggregator.py       # Email analysis logic
│   └── app.py              # Flask web server
├── templates/
│   └── index.html          # Web UI
├── static/
│   ├── style.css
│   └── app.js
├── requirements.txt
├── run.py                  ← Entry point
└── README.md
```

---

## Security Notes

### What This Tool Can Access

With the permissions granted, this tool can:
- ✅ Read your email metadata (sender, subject, date)
- ✅ Read email snippets
- ✅ Move emails to spam or trash
- ✅ Read List-Unsubscribe headers

It **cannot**:
- ❌ Read full email body content
- ❌ Send emails on your behalf
- ❌ Delete emails permanently (only trash)
- ❌ Access your contacts or calendar

### Where Your Data Lives

| Data | Location | Shared? |
|------|----------|---------|
| OAuth credentials | `config/credentials.json` | Never - local only |
| OAuth tokens | `data/tokens/` | Never - local only |
| Email data | Memory only | Never - not even saved to disk |
| Scan results | Memory only | Never - cleared on restart |

### Revoking Access

To disconnect this tool from your Gmail:
1. Go to [Google Account Security](https://myaccount.google.com/permissions)
2. Find "Gmail Cleanmail" (or your app name)
3. Click **Remove Access**

Or simply delete the token files in `data/tokens/`

---

## Troubleshooting

### "credentials.json not found"

Make sure you:
1. Downloaded the OAuth credentials from Google Cloud Console
2. Renamed the file to exactly `credentials.json`
3. Placed it in the `config/` folder

### "Access blocked: This app's request is invalid"

Your OAuth consent screen needs configuration:
1. Go to Google Cloud Console → OAuth consent screen
2. Make sure you added the Gmail API scopes
3. Make sure you added yourself as a test user

### "Error 403: access_denied"

You need to add your Gmail address as a test user:
1. Google Cloud Console → OAuth consent screen
2. Go to "Test users" section
3. Add your Gmail address

### "Token expired" or authentication errors

Delete the token file and re-authenticate:
1. Delete files in `data/tokens/`
2. Restart the app
3. Click "Add Gmail Account" again

### App shows "unverified" warning

This is normal for personal OAuth apps. Click:
1. **Advanced**
2. **Go to Gmail Cleanmail (unsafe)**

This warning appears because the app isn't verified by Google (which requires a review process meant for public apps). Since this runs locally and you created the credentials yourself, it's safe.

---

## Command Line Options

```bash
python run.py --help

Options:
  -p, --port PORT   Port to run on (default: 5000)
  --debug           Enable debug mode (for development)
```

---

## Contributing

Issues and pull requests welcome! This is a personal tool shared for anyone who finds it useful.

---

## License

MIT License - Free to use, modify, and distribute.

---

## Disclaimer

This tool is provided as-is. Always review what you're deleting before taking bulk actions. Trashed emails can be recovered within 30 days from Gmail's Trash folder.

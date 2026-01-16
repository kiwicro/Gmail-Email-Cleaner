"""
Gmail API client with OAuth 2.0 support for multiple accounts.
All data stays local - no external transmission.
Desktop app version.
"""

import os
import stat
import json
import base64
import re
import time
from pathlib import Path
from typing import Optional
from email.utils import parseaddr
from urllib.parse import urlparse

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Gmail API scopes - only request what we need
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',      # Read emails
    'https://www.googleapis.com/auth/gmail.modify',        # Mark as spam/trash
    'https://www.googleapis.com/auth/gmail.settings.basic', # Create filters
]

# Paths - for desktop app, use the app directory
BASE_DIR = Path(__file__).parent.parent
CONFIG_DIR = BASE_DIR / 'config'
TOKENS_DIR = BASE_DIR / 'data' / 'tokens'

# Ensure directories exist
TOKENS_DIR.mkdir(parents=True, exist_ok=True)


def sanitize_account_id(account_id: str) -> str:
    """
    Sanitize account_id to prevent path traversal attacks.
    Only allows alphanumeric characters, underscores, and hyphens.
    """
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '', account_id)
    if not sanitized:
        sanitized = 'default_account'
    return sanitized[:64]


def validate_url(url: str) -> Optional[str]:
    """
    Validate URL to prevent malicious links.
    Returns the URL if safe, None otherwise.
    """
    if not url:
        return None

    try:
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https', 'mailto'):
            return None
        if parsed.scheme in ('http', 'https'):
            if not parsed.netloc:
                return None
        return url
    except Exception:
        return None


class GmailClient:
    """Handles Gmail API authentication and operations for a single account."""

    def __init__(self, account_id: str):
        self.account_id = sanitize_account_id(account_id)
        self.credentials: Optional[Credentials] = None
        self.service = None
        self.email_address: Optional[str] = None

    @property
    def token_path(self) -> Path:
        return TOKENS_DIR / f'{self.account_id}_token.json'

    @property
    def credentials_path(self) -> Path:
        return CONFIG_DIR / 'credentials.json'

    def is_authenticated(self) -> bool:
        return self.credentials is not None and self.credentials.valid

    def authenticate(self) -> bool:
        """Authenticate with Gmail API using OAuth 2.0."""
        if self.token_path.exists():
            try:
                self.credentials = Credentials.from_authorized_user_file(
                    str(self.token_path), SCOPES
                )
            except Exception:
                self.credentials = None

        if self.credentials and self.credentials.expired and self.credentials.refresh_token:
            try:
                self.credentials.refresh(Request())
            except Exception:
                self.credentials = None

        if not self.credentials or not self.credentials.valid:
            if not self.credentials_path.exists():
                raise FileNotFoundError(
                    f"OAuth credentials not found at {self.credentials_path}. "
                    "Please place your credentials.json file in the config folder."
                )

            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.credentials_path), SCOPES
            )
            self.credentials = flow.run_local_server(port=0)

        # Save credentials with secure permissions
        with open(self.token_path, 'w') as token_file:
            token_file.write(self.credentials.to_json())

        try:
            if os.name != 'nt':
                os.chmod(self.token_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

        self.service = build('gmail', 'v1', credentials=self.credentials)
        profile = self.service.users().getProfile(userId='me').execute()
        self.email_address = profile.get('emailAddress')

        return True

    def disconnect(self) -> None:
        if self.token_path.exists():
            self.token_path.unlink()
        self.credentials = None
        self.service = None
        self.email_address = None

    def get_messages(self, max_results: int = None, query: str = '') -> list[dict]:
        """Fetch messages from Gmail."""
        if not self.service:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        messages = []
        page_token = None

        while True:
            try:
                if max_results is None:
                    request_size = 500
                else:
                    remaining = max_results - len(messages)
                    if remaining <= 0:
                        break
                    request_size = min(500, remaining)

                results = self.service.users().messages().list(
                    userId='me',
                    maxResults=request_size,
                    pageToken=page_token,
                    q=query if query else None
                ).execute()

                batch = results.get('messages', [])
                messages.extend(batch)

                page_token = results.get('nextPageToken')
                if not page_token:
                    break

            except HttpError:
                break

        return messages

    def get_messages_batch(self, message_ids: list[str], batch_size: int = 40) -> list[dict]:
        """Get details for multiple messages using batch API."""
        if not self.service:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        all_results = []

        for i in range(0, len(message_ids), batch_size):
            batch_ids = message_ids[i:i + batch_size]
            batch_results = {}

            def make_callback(results_dict):
                def callback(request_id, response, exception):
                    if exception:
                        results_dict[request_id] = {}
                    else:
                        results_dict[request_id] = response
                return callback

            batch = self.service.new_batch_http_request(callback=make_callback(batch_results))

            for msg_id in batch_ids:
                batch.add(
                    self.service.users().messages().get(
                        userId='me',
                        id=msg_id,
                        format='metadata',
                        metadataHeaders=['From', 'Subject', 'Date', 'List-Unsubscribe']
                    ),
                    request_id=msg_id
                )

            max_retries = 3
            for attempt in range(max_retries):
                try:
                    batch.execute()
                    break
                except HttpError as e:
                    if e.resp.status == 429 and attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                    else:
                        break
                except Exception:
                    break

            for msg_id in batch_ids:
                all_results.append(batch_results.get(msg_id, {}))

            if i + batch_size < len(message_ids):
                time.sleep(0.5)

        return all_results

    def mark_as_spam(self, message_ids: list[str]) -> bool:
        """Mark messages as spam."""
        if not self.service:
            raise RuntimeError("Not authenticated.")

        try:
            self.service.users().messages().batchModify(
                userId='me',
                body={
                    'ids': message_ids,
                    'addLabelIds': ['SPAM'],
                    'removeLabelIds': ['INBOX']
                }
            ).execute()
            return True
        except HttpError:
            return False

    def trash_messages(self, message_ids: list[str]) -> bool:
        """Move messages to trash."""
        if not self.service:
            raise RuntimeError("Not authenticated.")

        try:
            self.service.users().messages().batchModify(
                userId='me',
                body={
                    'ids': message_ids,
                    'addLabelIds': ['TRASH'],
                    'removeLabelIds': ['INBOX']
                }
            ).execute()
            return True
        except HttpError:
            return False

    def create_filter(self, sender_email: str = None, domain: str = None,
                      action: str = 'trash') -> dict:
        """Create a Gmail filter for a sender or domain."""
        if not self.service:
            raise RuntimeError("Not authenticated.")

        if sender_email:
            criteria = {'from': sender_email}
        elif domain:
            criteria = {'from': f'@{domain}'}
        else:
            return {'success': False, 'error': 'sender_email or domain required'}

        action_config = {}
        if action == 'trash':
            action_config = {'addLabelIds': ['TRASH'], 'removeLabelIds': ['INBOX']}
        elif action == 'spam':
            action_config = {'addLabelIds': ['SPAM'], 'removeLabelIds': ['INBOX']}
        elif action == 'archive':
            action_config = {'removeLabelIds': ['INBOX']}
        elif action == 'read':
            action_config = {'removeLabelIds': ['UNREAD']}

        try:
            result = self.service.users().settings().filters().create(
                userId='me',
                body={'criteria': criteria, 'action': action_config}
            ).execute()
            return {'success': True, 'filter_id': result.get('id')}
        except HttpError as e:
            return {'success': False, 'error': str(e)}


class GmailAccountManager:
    """Manages multiple Gmail accounts."""

    def __init__(self):
        self.accounts: dict[str, GmailClient] = {}
        self._load_existing_accounts()

    def _load_existing_accounts(self) -> None:
        if not TOKENS_DIR.exists():
            return

        for token_file in TOKENS_DIR.glob('*_token.json'):
            account_id = token_file.stem.replace('_token', '')
            client = GmailClient(account_id)
            try:
                client.authenticate()
                self.accounts[account_id] = client
            except Exception:
                pass

    def add_account(self, account_id: str) -> GmailClient:
        if account_id in self.accounts:
            return self.accounts[account_id]

        client = GmailClient(account_id)
        client.authenticate()
        self.accounts[account_id] = client
        return client

    def remove_account(self, account_id: str) -> None:
        if account_id in self.accounts:
            self.accounts[account_id].disconnect()
            del self.accounts[account_id]

    def get_account(self, account_id: str) -> Optional[GmailClient]:
        return self.accounts.get(account_id)

    def list_accounts(self) -> list[dict]:
        return [
            {
                'id': account_id,
                'email': client.email_address,
                'authenticated': client.is_authenticated()
            }
            for account_id, client in self.accounts.items()
        ]

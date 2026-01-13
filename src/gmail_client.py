"""
Gmail API client with OAuth 2.0 support for multiple accounts.
All data stays local - no external transmission.
"""

import os
import json
import base64
import re
import time
from pathlib import Path
from typing import Optional
from email.utils import parseaddr

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Gmail API scopes - only request what we need
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',      # Read emails
    'https://www.googleapis.com/auth/gmail.modify',        # Mark as spam/read
]

# Paths
BASE_DIR = Path(__file__).parent.parent
CONFIG_DIR = BASE_DIR / 'config'
TOKENS_DIR = BASE_DIR / 'data' / 'tokens'

# Ensure directories exist
TOKENS_DIR.mkdir(parents=True, exist_ok=True)


class GmailClient:
    """Handles Gmail API authentication and operations for a single account."""

    def __init__(self, account_id: str):
        """
        Initialize Gmail client for a specific account.

        Args:
            account_id: Unique identifier for this account (used for token storage)
        """
        self.account_id = account_id
        self.credentials: Optional[Credentials] = None
        self.service = None
        self.email_address: Optional[str] = None

    @property
    def token_path(self) -> Path:
        """Path to store OAuth token for this account."""
        return TOKENS_DIR / f'{self.account_id}_token.json'

    @property
    def credentials_path(self) -> Path:
        """Path to OAuth credentials file."""
        return CONFIG_DIR / 'credentials.json'

    def is_authenticated(self) -> bool:
        """Check if we have valid credentials."""
        return self.credentials is not None and self.credentials.valid

    def authenticate(self) -> bool:
        """
        Authenticate with Gmail API using OAuth 2.0.
        Opens browser for user consent if needed.

        Returns:
            True if authentication successful, False otherwise
        """
        # Try to load existing token
        if self.token_path.exists():
            try:
                self.credentials = Credentials.from_authorized_user_file(
                    str(self.token_path), SCOPES
                )
            except Exception:
                self.credentials = None

        # Refresh or get new credentials
        if self.credentials and self.credentials.expired and self.credentials.refresh_token:
            try:
                self.credentials.refresh(Request())
            except Exception:
                self.credentials = None

        if not self.credentials or not self.credentials.valid:
            if not self.credentials_path.exists():
                raise FileNotFoundError(
                    f"OAuth credentials not found at {self.credentials_path}. "
                    "Please follow README instructions to set up Google Cloud credentials."
                )

            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.credentials_path), SCOPES
            )
            self.credentials = flow.run_local_server(port=0)

        # Save credentials for next run
        with open(self.token_path, 'w') as token_file:
            token_file.write(self.credentials.to_json())

        # Build service
        self.service = build('gmail', 'v1', credentials=self.credentials)

        # Get email address for this account
        profile = self.service.users().getProfile(userId='me').execute()
        self.email_address = profile.get('emailAddress')

        return True

    def disconnect(self) -> None:
        """Remove stored token for this account."""
        if self.token_path.exists():
            self.token_path.unlink()
        self.credentials = None
        self.service = None
        self.email_address = None

    def get_messages(self, max_results: int = 500, query: str = '') -> list[dict]:
        """
        Fetch messages from Gmail.

        Args:
            max_results: Maximum number of messages to fetch
            query: Gmail search query (e.g., 'is:unread', 'from:example.com')

        Returns:
            List of message metadata
        """
        if not self.service:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        messages = []
        page_token = None

        while len(messages) < max_results:
            try:
                results = self.service.users().messages().list(
                    userId='me',
                    maxResults=min(100, max_results - len(messages)),
                    pageToken=page_token,
                    q=query
                ).execute()

                batch = results.get('messages', [])
                messages.extend(batch)

                page_token = results.get('nextPageToken')
                if not page_token:
                    break

            except HttpError as e:
                print(f"Error fetching messages: {e}")
                break

        return messages

    def get_message_details(self, message_id: str) -> dict:
        """
        Get full details for a specific message.

        Args:
            message_id: Gmail message ID

        Returns:
            Message details including headers and snippet
        """
        if not self.service:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        try:
            message = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='metadata',
                metadataHeaders=['From', 'Subject', 'Date', 'List-Unsubscribe']
            ).execute()
            return message
        except HttpError as e:
            print(f"Error fetching message {message_id}: {e}")
            return {}

    def get_messages_batch(self, message_ids: list[str], batch_size: int = 40) -> list[dict]:
        """
        Get details for multiple messages using batch API.
        Much faster than individual calls - combines multiple requests per HTTP call.

        Gmail API rate limits:
        - 250 quota units per user per second
        - messages.get costs 5 quota units each
        - So max ~50 messages per second to stay safe

        Args:
            message_ids: List of Gmail message IDs
            batch_size: Number of requests per batch (default 40 to stay under rate limit)

        Returns:
            List of message details
        """
        if not self.service:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        all_results = []

        # Process in batches with rate limiting
        for i in range(0, len(message_ids), batch_size):
            batch_ids = message_ids[i:i + batch_size]
            batch_results = {}

            def make_callback(results_dict):
                def callback(request_id, response, exception):
                    if exception:
                        # Check for rate limit error
                        if hasattr(exception, 'resp') and exception.resp.status == 429:
                            print(f"Rate limited, will retry: {request_id}")
                        else:
                            print(f"Batch error for {request_id}: {exception}")
                        results_dict[request_id] = {}
                    else:
                        results_dict[request_id] = response
                return callback

            # Create batch request
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

            # Execute batch with retry on rate limit
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    batch.execute()
                    break
                except HttpError as e:
                    if e.resp.status == 429 and attempt < max_retries - 1:
                        # Rate limited - wait and retry
                        wait_time = 2 ** attempt  # Exponential backoff: 1, 2, 4 seconds
                        print(f"Rate limited, waiting {wait_time}s before retry...")
                        time.sleep(wait_time)
                    else:
                        print(f"Batch execution error: {e}")
                        break
                except Exception as e:
                    print(f"Batch execution error: {e}")
                    break

            # Collect results in order
            for msg_id in batch_ids:
                all_results.append(batch_results.get(msg_id, {}))

            # Small delay between batches to avoid rate limiting
            # 40 messages * 5 units = 200 units, under 250/second limit
            if i + batch_size < len(message_ids):
                time.sleep(0.5)  # 500ms between batches

        return all_results

    def mark_as_spam(self, message_ids: list[str]) -> bool:
        """
        Mark messages as spam.

        Args:
            message_ids: List of message IDs to mark as spam

        Returns:
            True if successful
        """
        if not self.service:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

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
        except HttpError as e:
            print(f"Error marking as spam: {e}")
            return False

    def trash_messages(self, message_ids: list[str]) -> bool:
        """
        Move messages to trash.

        Args:
            message_ids: List of message IDs to trash

        Returns:
            True if successful
        """
        if not self.service:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

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
        except HttpError as e:
            print(f"Error trashing messages: {e}")
            return False

    def get_unsubscribe_link(self, message_id: str) -> Optional[str]:
        """
        Extract unsubscribe link from message headers.

        Args:
            message_id: Gmail message ID

        Returns:
            Unsubscribe URL if found, None otherwise
        """
        if not self.service:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        try:
            message = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='metadata',
                metadataHeaders=['List-Unsubscribe']
            ).execute()

            headers = message.get('payload', {}).get('headers', [])
            for header in headers:
                if header['name'].lower() == 'list-unsubscribe':
                    value = header['value']
                    # Extract URL from header (can be <url> or <mailto:...>)
                    urls = re.findall(r'<(https?://[^>]+)>', value)
                    if urls:
                        return urls[0]
                    # Check for mailto as fallback
                    mailto = re.findall(r'<(mailto:[^>]+)>', value)
                    if mailto:
                        return mailto[0]
            return None
        except HttpError:
            return None


class GmailAccountManager:
    """Manages multiple Gmail accounts."""

    def __init__(self):
        self.accounts: dict[str, GmailClient] = {}
        self._load_existing_accounts()

    def _load_existing_accounts(self) -> None:
        """Load any existing authenticated accounts from tokens directory."""
        if not TOKENS_DIR.exists():
            return

        for token_file in TOKENS_DIR.glob('*_token.json'):
            account_id = token_file.stem.replace('_token', '')
            client = GmailClient(account_id)
            try:
                client.authenticate()
                self.accounts[account_id] = client
            except Exception as e:
                print(f"Failed to load account {account_id}: {e}")

    def add_account(self, account_id: str) -> GmailClient:
        """
        Add and authenticate a new Gmail account.

        Args:
            account_id: Unique identifier for this account

        Returns:
            Authenticated GmailClient
        """
        if account_id in self.accounts:
            return self.accounts[account_id]

        client = GmailClient(account_id)
        client.authenticate()
        self.accounts[account_id] = client
        return client

    def remove_account(self, account_id: str) -> None:
        """Remove an account and its stored credentials."""
        if account_id in self.accounts:
            self.accounts[account_id].disconnect()
            del self.accounts[account_id]

    def get_account(self, account_id: str) -> Optional[GmailClient]:
        """Get a specific account client."""
        return self.accounts.get(account_id)

    def list_accounts(self) -> list[dict]:
        """List all connected accounts."""
        return [
            {
                'id': account_id,
                'email': client.email_address,
                'authenticated': client.is_authenticated()
            }
            for account_id, client in self.accounts.items()
        ]

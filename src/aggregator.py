"""
Email aggregation logic - groups emails by sender and domain.
All processing happens locally.
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parseaddr, parsedate_to_datetime
from typing import Optional
from urllib.parse import urlparse

from .gmail_client import GmailClient, GmailAccountManager


def validate_unsubscribe_url(url: str) -> Optional[str]:
    """
    Validate unsubscribe URL to prevent malicious links.
    Returns the URL if safe, None otherwise.
    """
    if not url:
        return None

    try:
        parsed = urlparse(url)

        # Only allow http/https and mailto
        if parsed.scheme not in ('http', 'https', 'mailto'):
            return None

        # Block javascript: and data: schemes (defense in depth)
        if parsed.scheme.lower() in ('javascript', 'data', 'vbscript'):
            return None

        # For http/https, ensure there's a valid host
        if parsed.scheme in ('http', 'https'):
            if not parsed.netloc:
                return None
            # Block localhost/internal IPs to prevent SSRF-like issues
            host = parsed.netloc.lower().split(':')[0]
            if host in ('localhost', '127.0.0.1', '0.0.0.0', '::1'):
                return None

        return url
    except Exception:
        return None


# Age category constants
AGE_CATEGORIES = [
    ('today', 'Today', 1),
    ('week', 'This Week', 7),
    ('month', 'This Month', 30),
    ('3months', 'Last 3 Months', 90),
    ('6months', 'Last 6 Months', 180),
    ('year', 'Last Year', 365),
    ('older', 'Older', float('inf'))
]


def parse_email_date(date_str: str) -> Optional[datetime]:
    """
    Parse email date string to datetime object.

    Args:
        date_str: Raw date string from email header

    Returns:
        datetime object or None if parsing fails
    """
    if not date_str:
        return None

    try:
        # Try standard email date parsing
        return parsedate_to_datetime(date_str)
    except Exception:
        pass

    # Try common date formats as fallback
    formats = [
        '%a, %d %b %Y %H:%M:%S %z',
        '%d %b %Y %H:%M:%S %z',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%dT%H:%M:%S%z',
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    return None


def get_age_category(email_date: Optional[datetime]) -> str:
    """
    Determine the age category for an email based on its date.

    Args:
        email_date: datetime object or None

    Returns:
        Age category key (e.g., 'today', 'week', 'month', etc.)
    """
    if not email_date:
        return 'older'  # Unknown dates go to oldest category

    now = datetime.now(timezone.utc)

    # Make email_date timezone-aware if it isn't
    if email_date.tzinfo is None:
        email_date = email_date.replace(tzinfo=timezone.utc)

    days_old = (now - email_date).days

    for category_key, _, max_days in AGE_CATEGORIES:
        if days_old < max_days:
            return category_key

    return 'older'


@dataclass
class EmailInfo:
    """Information about a single email."""
    message_id: str
    subject: str
    date: str
    snippet: str
    size: int = 0  # Size in bytes
    unsubscribe_link: Optional[str] = None
    age_category: str = 'older'  # Age category key


def create_age_distribution() -> dict[str, int]:
    """Create an empty age distribution dict."""
    return {key: 0 for key, _, _ in AGE_CATEGORIES}


@dataclass
class SenderAggregation:
    """Aggregated data for a single sender."""
    email: str
    name: str
    domain: str
    count: int = 0
    total_size: int = 0  # Total size in bytes
    emails: list[EmailInfo] = field(default_factory=list)
    unsubscribe_link: Optional[str] = None
    age_distribution: dict[str, int] = field(default_factory=create_age_distribution)

    def add_email(self, email_info: EmailInfo) -> None:
        """Add an email to this aggregation."""
        self.count += 1
        self.total_size += email_info.size
        self.emails.append(email_info)
        # Track age distribution
        self.age_distribution[email_info.age_category] += 1
        # Keep the most recent unsubscribe link
        if email_info.unsubscribe_link:
            self.unsubscribe_link = email_info.unsubscribe_link


@dataclass
class DomainAggregation:
    """Aggregated data for a domain."""
    domain: str
    total_count: int = 0
    total_size: int = 0  # Total size in bytes
    senders: dict[str, SenderAggregation] = field(default_factory=dict)
    age_distribution: dict[str, int] = field(default_factory=create_age_distribution)

    def add_sender(self, sender: SenderAggregation) -> None:
        """Add a sender to this domain aggregation."""
        if sender.email not in self.senders:
            self.senders[sender.email] = sender
        else:
            # Merge emails
            existing = self.senders[sender.email]
            existing.count += sender.count
            existing.total_size += sender.total_size
            existing.emails.extend(sender.emails)
            # Merge age distribution
            for cat, count in sender.age_distribution.items():
                existing.age_distribution[cat] += count
            if sender.unsubscribe_link:
                existing.unsubscribe_link = sender.unsubscribe_link
        self.total_count += sender.count
        self.total_size += sender.total_size
        # Update domain's age distribution
        for cat, count in sender.age_distribution.items():
            self.age_distribution[cat] += count


@dataclass
class AccountAggregation:
    """Aggregated data for a single email account."""
    account_id: str
    email_address: str
    total_emails: int = 0
    total_size: int = 0  # Total size in bytes
    senders: dict[str, SenderAggregation] = field(default_factory=dict)
    domains: dict[str, DomainAggregation] = field(default_factory=dict)


def extract_sender_info(from_header: str) -> tuple[str, str, str]:
    """
    Extract name, email, and domain from From header.

    Args:
        from_header: Raw From header value

    Returns:
        Tuple of (name, email, domain)
    """
    name, email = parseaddr(from_header)
    email = email.lower()

    # Extract domain
    domain = ''
    if '@' in email:
        domain = email.split('@')[1]

    # Clean up name
    if not name:
        name = email.split('@')[0] if '@' in email else email

    return name, email, domain


def get_header_value(headers: list[dict], name: str) -> str:
    """Extract a header value by name."""
    for header in headers:
        if header.get('name', '').lower() == name.lower():
            return header.get('value', '')
    return ''


class EmailAggregator:
    """Aggregates email data from multiple accounts."""

    def __init__(self, account_manager: GmailAccountManager):
        self.account_manager = account_manager
        self.aggregations: dict[str, AccountAggregation] = {}

    def _process_message_details(self, message_id: str, details: dict) -> Optional[tuple[str, str, str, EmailInfo]]:
        """
        Process message details and extract sender info.

        Returns:
            Tuple of (name, email, domain, EmailInfo) or None if failed
        """
        if not details:
            return None

        headers = details.get('payload', {}).get('headers', [])
        from_header = get_header_value(headers, 'From')
        subject = get_header_value(headers, 'Subject')
        date = get_header_value(headers, 'Date')
        snippet = details.get('snippet', '')
        size = details.get('sizeEstimate', 0)

        # Get unsubscribe link with validation
        unsubscribe = get_header_value(headers, 'List-Unsubscribe')
        unsubscribe_link = None
        if unsubscribe:
            urls = re.findall(r'<(https?://[^>]+)>', unsubscribe)
            if urls:
                # Validate URL to prevent malicious links
                unsubscribe_link = validate_unsubscribe_url(urls[0])

        name, email, domain = extract_sender_info(from_header)

        # Parse date and calculate age category
        parsed_date = parse_email_date(date)
        age_category = get_age_category(parsed_date)

        email_info = EmailInfo(
            message_id=message_id,
            subject=subject,
            date=date,
            snippet=snippet,
            size=size,
            unsubscribe_link=unsubscribe_link,
            age_category=age_category
        )

        return name, email, domain, email_info

    def aggregate_account(
        self,
        account_id: str,
        max_emails: int = None,
        query: str = '',
        progress_callback=None
    ) -> AccountAggregation:
        """
        Aggregate emails for a single account.

        Args:
            account_id: Account identifier
            max_emails: Maximum emails to process
            query: Gmail search query to filter emails
            progress_callback: Optional callback(current, total) for progress updates

        Returns:
            AccountAggregation with all sender/domain data
        """
        client = self.account_manager.get_account(account_id)
        if not client:
            raise ValueError(f"Account {account_id} not found")

        aggregation = AccountAggregation(
            account_id=account_id,
            email_address=client.email_address or account_id
        )

        # Fetch message list
        messages = client.get_messages(max_results=max_emails, query=query)
        total = len(messages)
        message_ids = [msg['id'] for msg in messages]

        # Process messages in batches (much faster than individual calls)
        senders_data: dict[str, SenderAggregation] = {}
        batch_size = 100
        processed = 0

        for i in range(0, len(message_ids), batch_size):
            batch_ids = message_ids[i:i + batch_size]

            # Fetch batch of message details
            batch_details = client.get_messages_batch(batch_ids, batch_size=batch_size)

            # Process each message in the batch
            for msg_id, details in zip(batch_ids, batch_details):
                processed += 1
                if progress_callback:
                    progress_callback(processed, total)

                result = self._process_message_details(msg_id, details)
                if not result:
                    continue

                name, email, domain, email_info = result

                # Add to sender aggregation
                if email not in senders_data:
                    senders_data[email] = SenderAggregation(
                        email=email,
                        name=name,
                        domain=domain
                    )
                senders_data[email].add_email(email_info)

        # Build domain aggregations
        domains_data: dict[str, DomainAggregation] = {}

        for sender in senders_data.values():
            aggregation.senders[sender.email] = sender
            aggregation.total_emails += sender.count
            aggregation.total_size += sender.total_size

            if sender.domain not in domains_data:
                domains_data[sender.domain] = DomainAggregation(domain=sender.domain)
            domains_data[sender.domain].add_sender(sender)

        aggregation.domains = domains_data
        self.aggregations[account_id] = aggregation

        return aggregation

    def aggregate_all_accounts(
        self,
        max_emails_per_account: int = None,
        query: str = '',
        progress_callback=None
    ) -> dict[str, AccountAggregation]:
        """
        Aggregate emails for all connected accounts.

        Args:
            max_emails_per_account: Maximum emails per account
            query: Gmail search query
            progress_callback: Optional callback(account_id, current, total)

        Returns:
            Dict of account_id -> AccountAggregation
        """
        for account_id in self.account_manager.accounts:
            def account_progress(current, total):
                if progress_callback:
                    progress_callback(account_id, current, total)

            self.aggregate_account(
                account_id,
                max_emails=max_emails_per_account,
                query=query,
                progress_callback=account_progress
            )

        return self.aggregations

    def get_top_senders(
        self,
        account_id: Optional[str] = None,
        limit: int = 20
    ) -> list[tuple[str, SenderAggregation]]:
        """
        Get top senders by email count.

        Args:
            account_id: Specific account or None for all accounts
            limit: Maximum number of senders to return

        Returns:
            List of (account_id, SenderAggregation) sorted by count
        """
        results = []

        accounts = [account_id] if account_id else list(self.aggregations.keys())

        for acc_id in accounts:
            if acc_id not in self.aggregations:
                continue
            agg = self.aggregations[acc_id]
            for sender in agg.senders.values():
                results.append((acc_id, sender))

        # Sort by count descending
        results.sort(key=lambda x: x[1].count, reverse=True)
        return results[:limit]

    def get_top_domains(
        self,
        account_id: Optional[str] = None,
        limit: int = 20
    ) -> list[tuple[str, DomainAggregation]]:
        """
        Get top domains by email count.

        Args:
            account_id: Specific account or None for all accounts
            limit: Maximum number of domains to return

        Returns:
            List of (account_id, DomainAggregation) sorted by count
        """
        results = []

        accounts = [account_id] if account_id else list(self.aggregations.keys())

        for acc_id in accounts:
            if acc_id not in self.aggregations:
                continue
            agg = self.aggregations[acc_id]
            for domain in agg.domains.values():
                results.append((acc_id, domain))

        # Sort by count descending
        results.sort(key=lambda x: x[1].total_count, reverse=True)
        return results[:limit]

    def get_message_ids_for_sender(self, account_id: str, sender_email: str) -> list[str]:
        """Get all message IDs for a specific sender."""
        if account_id not in self.aggregations:
            return []
        agg = self.aggregations[account_id]
        if sender_email not in agg.senders:
            return []
        return [e.message_id for e in agg.senders[sender_email].emails]

    def get_message_ids_for_domain(self, account_id: str, domain: str) -> list[str]:
        """Get all message IDs for a specific domain."""
        if account_id not in self.aggregations:
            return []
        agg = self.aggregations[account_id]
        if domain not in agg.domains:
            return []

        message_ids = []
        for sender in agg.domains[domain].senders.values():
            message_ids.extend(e.message_id for e in sender.emails)
        return message_ids

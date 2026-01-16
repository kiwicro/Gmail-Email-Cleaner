"""
Email aggregation logic - groups emails by sender and domain.
All processing happens locally.
Desktop app version.
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
    """Validate unsubscribe URL to prevent malicious links."""
    if not url:
        return None

    try:
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https', 'mailto'):
            return None
        if parsed.scheme.lower() in ('javascript', 'data', 'vbscript'):
            return None
        if parsed.scheme in ('http', 'https'):
            if not parsed.netloc:
                return None
            host = parsed.netloc.lower().split(':')[0]
            if host in ('localhost', '127.0.0.1', '0.0.0.0', '::1'):
                return None
        return url
    except Exception:
        return None


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
    """Parse email date string to datetime object."""
    if not date_str:
        return None

    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        pass

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
    """Determine the age category for an email based on its date."""
    if not email_date:
        return 'older'

    now = datetime.now(timezone.utc)

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
    size: int = 0
    unsubscribe_link: Optional[str] = None
    age_category: str = 'older'


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
    total_size: int = 0
    emails: list[EmailInfo] = field(default_factory=list)
    unsubscribe_link: Optional[str] = None
    age_distribution: dict[str, int] = field(default_factory=create_age_distribution)

    def add_email(self, email_info: EmailInfo) -> None:
        self.count += 1
        self.total_size += email_info.size
        self.emails.append(email_info)
        self.age_distribution[email_info.age_category] += 1
        if email_info.unsubscribe_link:
            self.unsubscribe_link = email_info.unsubscribe_link


@dataclass
class DomainAggregation:
    """Aggregated data for a domain."""
    domain: str
    total_count: int = 0
    total_size: int = 0
    senders: dict[str, SenderAggregation] = field(default_factory=dict)
    age_distribution: dict[str, int] = field(default_factory=create_age_distribution)

    def add_sender(self, sender: SenderAggregation) -> None:
        if sender.email not in self.senders:
            self.senders[sender.email] = sender
        else:
            existing = self.senders[sender.email]
            existing.count += sender.count
            existing.total_size += sender.total_size
            existing.emails.extend(sender.emails)
            for cat, count in sender.age_distribution.items():
                existing.age_distribution[cat] += count
            if sender.unsubscribe_link:
                existing.unsubscribe_link = sender.unsubscribe_link
        self.total_count += sender.count
        self.total_size += sender.total_size
        for cat, count in sender.age_distribution.items():
            self.age_distribution[cat] += count


@dataclass
class AccountAggregation:
    """Aggregated data for a single email account."""
    account_id: str
    email_address: str
    total_emails: int = 0
    total_size: int = 0
    senders: dict[str, SenderAggregation] = field(default_factory=dict)
    domains: dict[str, DomainAggregation] = field(default_factory=dict)


def extract_sender_info(from_header: str) -> tuple[str, str, str]:
    """Extract name, email, and domain from From header."""
    name, email = parseaddr(from_header)
    email = email.lower()

    domain = ''
    if '@' in email:
        domain = email.split('@')[1]

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
        if not details:
            return None

        headers = details.get('payload', {}).get('headers', [])
        from_header = get_header_value(headers, 'From')
        subject = get_header_value(headers, 'Subject')
        date = get_header_value(headers, 'Date')
        snippet = details.get('snippet', '')
        size = details.get('sizeEstimate', 0)

        unsubscribe = get_header_value(headers, 'List-Unsubscribe')
        unsubscribe_link = None
        if unsubscribe:
            urls = re.findall(r'<(https?://[^>]+)>', unsubscribe)
            if urls:
                unsubscribe_link = validate_unsubscribe_url(urls[0])

        name, email, domain = extract_sender_info(from_header)

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
        """Aggregate emails for a single account."""
        client = self.account_manager.get_account(account_id)
        if not client:
            raise ValueError(f"Account {account_id} not found")

        aggregation = AccountAggregation(
            account_id=account_id,
            email_address=client.email_address or account_id
        )

        messages = client.get_messages(max_results=max_emails, query=query)
        total = len(messages)
        message_ids = [msg['id'] for msg in messages]

        senders_data: dict[str, SenderAggregation] = {}
        batch_size = 100
        processed = 0

        for i in range(0, len(message_ids), batch_size):
            batch_ids = message_ids[i:i + batch_size]
            batch_details = client.get_messages_batch(batch_ids, batch_size=batch_size)

            for msg_id, details in zip(batch_ids, batch_details):
                processed += 1
                if progress_callback:
                    progress_callback(processed, total)

                result = self._process_message_details(msg_id, details)
                if not result:
                    continue

                name, email, domain, email_info = result

                if email not in senders_data:
                    senders_data[email] = SenderAggregation(
                        email=email,
                        name=name,
                        domain=domain
                    )
                senders_data[email].add_email(email_info)

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
        """Aggregate emails for all connected accounts."""
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
        """Get top senders by email count."""
        results = []
        accounts = [account_id] if account_id else list(self.aggregations.keys())

        for acc_id in accounts:
            if acc_id not in self.aggregations:
                continue
            agg = self.aggregations[acc_id]
            for sender in agg.senders.values():
                results.append((acc_id, sender))

        results.sort(key=lambda x: x[1].count, reverse=True)
        return results[:limit]

    def get_top_domains(
        self,
        account_id: Optional[str] = None,
        limit: int = 20
    ) -> list[tuple[str, DomainAggregation]]:
        """Get top domains by email count."""
        results = []
        accounts = [account_id] if account_id else list(self.aggregations.keys())

        for acc_id in accounts:
            if acc_id not in self.aggregations:
                continue
            agg = self.aggregations[acc_id]
            for domain in agg.domains.values():
                results.append((acc_id, domain))

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

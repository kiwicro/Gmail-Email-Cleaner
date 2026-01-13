"""
Flask web application for Email Cleaner.
All data stays local - served only on localhost.
"""

import os
import secrets
import threading
from flask import Flask, render_template, jsonify, request, redirect, url_for, session

from .gmail_client import GmailAccountManager
from .aggregator import EmailAggregator

# Initialize Flask app
app = Flask(
    __name__,
    template_folder='../templates',
    static_folder='../static'
)

# Generate a random secret key for sessions (changes each restart for security)
app.secret_key = secrets.token_hex(32)

# Global state (in-memory, never persisted externally)
account_manager = GmailAccountManager()
aggregator = EmailAggregator(account_manager)

# Store scan progress
scan_progress = {}


@app.route('/')
def index():
    """Main dashboard page."""
    accounts = account_manager.list_accounts()
    return render_template('index.html', accounts=accounts)


@app.route('/api/accounts', methods=['GET'])
def list_accounts():
    """List all connected accounts."""
    return jsonify(account_manager.list_accounts())


@app.route('/api/accounts/add', methods=['POST'])
def add_account():
    """Add a new Gmail account. Triggers OAuth flow."""
    data = request.json or {}
    account_id = data.get('account_id', f'account_{len(account_manager.accounts) + 1}')

    try:
        client = account_manager.add_account(account_id)
        return jsonify({
            'success': True,
            'account': {
                'id': account_id,
                'email': client.email_address
            }
        })
    except FileNotFoundError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Authentication failed: {str(e)}'
        }), 500


@app.route('/api/accounts/<account_id>/remove', methods=['POST'])
def remove_account(account_id):
    """Remove an account and its stored credentials."""
    account_manager.remove_account(account_id)
    # Also clear any cached aggregation
    if account_id in aggregator.aggregations:
        del aggregator.aggregations[account_id]
    return jsonify({'success': True})


def run_scan_background(scan_id, account_id, max_emails, query):
    """Run scan in background thread."""
    try:
        if account_id:
            def progress(current, total):
                scan_progress[scan_id]['current'] = current
                scan_progress[scan_id]['total'] = total

            aggregator.aggregate_account(
                account_id,
                max_emails=max_emails,
                query=query,
                progress_callback=progress
            )
        else:
            def progress(acc_id, current, total):
                scan_progress[scan_id]['current'] = current
                scan_progress[scan_id]['total'] = total
                scan_progress[scan_id]['account'] = acc_id

            aggregator.aggregate_all_accounts(
                max_emails_per_account=max_emails,
                query=query,
                progress_callback=progress
            )

        scan_progress[scan_id]['status'] = 'completed'

    except Exception as e:
        scan_progress[scan_id]['status'] = 'failed'
        scan_progress[scan_id]['error'] = str(e)


@app.route('/api/scan', methods=['POST'])
def start_scan():
    """Start scanning emails for aggregation."""
    data = request.json or {}
    account_id = data.get('account_id')  # None means all accounts
    max_emails = data.get('max_emails', 500)
    query = data.get('query', '')

    scan_id = secrets.token_hex(8)
    scan_progress[scan_id] = {
        'status': 'running',
        'current': 0,
        'total': 0,
        'account': account_id or 'all'
    }

    # Start scan in background thread
    thread = threading.Thread(
        target=run_scan_background,
        args=(scan_id, account_id, max_emails, query)
    )
    thread.daemon = True
    thread.start()

    return jsonify({
        'success': True,
        'scan_id': scan_id
    })


@app.route('/api/scan/<scan_id>/progress', methods=['GET'])
def get_scan_progress(scan_id):
    """Get progress of a scan."""
    if scan_id not in scan_progress:
        return jsonify({'error': 'Scan not found'}), 404
    return jsonify(scan_progress[scan_id])


@app.route('/api/results', methods=['GET'])
def get_results():
    """Get aggregation results."""
    account_id = request.args.get('account_id')
    view = request.args.get('view', 'senders')  # 'senders' or 'domains'
    limit = int(request.args.get('limit', 50))

    if view == 'domains':
        results = aggregator.get_top_domains(account_id, limit)
        return jsonify({
            'view': 'domains',
            'results': [
                {
                    'account_id': acc_id,
                    'domain': d.domain,
                    'total_count': d.total_count,
                    'sender_count': len(d.senders),
                    'senders': [
                        {
                            'email': s.email,
                            'name': s.name,
                            'count': s.count,
                            'has_unsubscribe': s.unsubscribe_link is not None
                        }
                        for s in sorted(d.senders.values(), key=lambda x: x.count, reverse=True)[:10]
                    ]
                }
                for acc_id, d in results
            ]
        })
    else:
        results = aggregator.get_top_senders(account_id, limit)
        return jsonify({
            'view': 'senders',
            'results': [
                {
                    'account_id': acc_id,
                    'email': s.email,
                    'name': s.name,
                    'domain': s.domain,
                    'count': s.count,
                    'has_unsubscribe': s.unsubscribe_link is not None,
                    'unsubscribe_link': s.unsubscribe_link,
                    'recent_subjects': [e.subject for e in s.emails[:5]],
                    'recent_snippets': [e.snippet for e in s.emails[:3]]
                }
                for acc_id, s in results
            ]
        })


@app.route('/api/sender/<account_id>/<path:sender_email>/details', methods=['GET'])
def get_sender_details(account_id, sender_email):
    """Get detailed info for a specific sender."""
    if account_id not in aggregator.aggregations:
        return jsonify({'error': 'Account not scanned'}), 404

    agg = aggregator.aggregations[account_id]
    if sender_email not in agg.senders:
        return jsonify({'error': 'Sender not found'}), 404

    sender = agg.senders[sender_email]
    return jsonify({
        'email': sender.email,
        'name': sender.name,
        'domain': sender.domain,
        'count': sender.count,
        'unsubscribe_link': sender.unsubscribe_link,
        'emails': [
            {
                'id': e.message_id,
                'subject': e.subject,
                'date': e.date,
                'snippet': e.snippet
            }
            for e in sender.emails
        ]
    })


@app.route('/api/action/spam', methods=['POST'])
def mark_as_spam():
    """Mark emails from a sender or domain as spam."""
    data = request.json or {}
    account_id = data.get('account_id')
    sender_email = data.get('sender_email')
    domain = data.get('domain')

    if not account_id:
        return jsonify({'error': 'account_id required'}), 400

    client = account_manager.get_account(account_id)
    if not client:
        return jsonify({'error': 'Account not found'}), 404

    # Get message IDs
    if sender_email:
        message_ids = aggregator.get_message_ids_for_sender(account_id, sender_email)
    elif domain:
        message_ids = aggregator.get_message_ids_for_domain(account_id, domain)
    else:
        return jsonify({'error': 'sender_email or domain required'}), 400

    if not message_ids:
        return jsonify({'error': 'No messages found'}), 404

    # Mark as spam in batches
    batch_size = 100
    success_count = 0
    for i in range(0, len(message_ids), batch_size):
        batch = message_ids[i:i + batch_size]
        if client.mark_as_spam(batch):
            success_count += len(batch)

    return jsonify({
        'success': True,
        'marked_count': success_count,
        'total_count': len(message_ids)
    })


@app.route('/api/action/trash', methods=['POST'])
def trash_emails():
    """Move emails from a sender or domain to trash."""
    data = request.json or {}
    account_id = data.get('account_id')
    sender_email = data.get('sender_email')
    domain = data.get('domain')

    if not account_id:
        return jsonify({'error': 'account_id required'}), 400

    client = account_manager.get_account(account_id)
    if not client:
        return jsonify({'error': 'Account not found'}), 404

    # Get message IDs
    if sender_email:
        message_ids = aggregator.get_message_ids_for_sender(account_id, sender_email)
    elif domain:
        message_ids = aggregator.get_message_ids_for_domain(account_id, domain)
    else:
        return jsonify({'error': 'sender_email or domain required'}), 400

    if not message_ids:
        return jsonify({'error': 'No messages found'}), 404

    # Trash in batches
    batch_size = 100
    success_count = 0
    for i in range(0, len(message_ids), batch_size):
        batch = message_ids[i:i + batch_size]
        if client.trash_messages(batch):
            success_count += len(batch)

    return jsonify({
        'success': True,
        'trashed_count': success_count,
        'total_count': len(message_ids)
    })


@app.route('/api/action/unsubscribe', methods=['POST'])
def get_unsubscribe():
    """Get unsubscribe link for a sender."""
    data = request.json or {}
    account_id = data.get('account_id')
    sender_email = data.get('sender_email')

    if not account_id or not sender_email:
        return jsonify({'error': 'account_id and sender_email required'}), 400

    if account_id not in aggregator.aggregations:
        return jsonify({'error': 'Account not scanned'}), 404

    agg = aggregator.aggregations[account_id]
    if sender_email not in agg.senders:
        return jsonify({'error': 'Sender not found'}), 404

    sender = agg.senders[sender_email]
    if sender.unsubscribe_link:
        return jsonify({
            'success': True,
            'unsubscribe_link': sender.unsubscribe_link
        })
    else:
        return jsonify({
            'success': False,
            'error': 'No unsubscribe link found for this sender'
        })


def run_app(host='127.0.0.1', port=5000, debug=False):
    """Run the Flask application."""
    print(f"\n{'='*60}")
    print("  Email Cleaner - Local Gmail Aggregation Tool")
    print(f"{'='*60}")
    print(f"\n  Open your browser to: http://{host}:{port}")
    print(f"\n  All data stays on your local machine.")
    print(f"  Press Ctrl+C to stop the server.\n")
    print(f"{'='*60}\n")

    app.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
    run_app(debug=True)

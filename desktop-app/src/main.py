"""
Gmail Email Cleanmail - Desktop Application
Native Windows app built with PySide6 (Qt)
"""

import sys
import webbrowser
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QMessageBox, QComboBox, QTabWidget,
    QGroupBox, QSplitter, QFrame, QStatusBar, QToolBar, QMenu,
    QDialog, QDialogButtonBox, QTextEdit, QCheckBox, QSpinBox
)
from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QAction, QPalette, QColor, QFont, QIcon

from .gmail_client import GmailAccountManager, GmailClient
from .aggregator import EmailAggregator, SenderAggregation, DomainAggregation, AGE_CATEGORIES


def format_size(bytes_size: int) -> str:
    """Format bytes to human readable size."""
    if bytes_size == 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.1f} TB"


class ScanWorker(QThread):
    """Background worker for scanning emails."""
    progress = Signal(int, int)  # current, total
    finished = Signal(bool, str)  # success, message

    def __init__(self, aggregator: EmailAggregator, query: str = ''):
        super().__init__()
        self.aggregator = aggregator
        self.query = query

    def run(self):
        try:
            def progress_callback(current, total):
                self.progress.emit(current, total)

            for account_id in self.aggregator.account_manager.accounts:
                self.aggregator.aggregate_account(
                    account_id,
                    query=self.query,
                    progress_callback=progress_callback
                )

            self.finished.emit(True, "Scan completed successfully!")
        except Exception as e:
            self.finished.emit(False, str(e))


class ActionWorker(QThread):
    """Background worker for email actions."""
    finished = Signal(bool, str, int)  # success, message, count

    def __init__(self, client: GmailClient, message_ids: list[str], action: str):
        super().__init__()
        self.client = client
        self.message_ids = message_ids
        self.action = action

    def run(self):
        try:
            count = len(self.message_ids)
            if self.action == 'trash':
                success = self.client.trash_messages(self.message_ids)
            elif self.action == 'spam':
                success = self.client.mark_as_spam(self.message_ids)
            else:
                success = False

            if success:
                self.finished.emit(True, f"{self.action.title()}ed {count} emails", count)
            else:
                self.finished.emit(False, f"Failed to {self.action} emails", 0)
        except Exception as e:
            self.finished.emit(False, str(e), 0)


class EmailDetailsDialog(QDialog):
    """Dialog showing email details for a sender."""

    def __init__(self, sender: SenderAggregation, parent=None):
        super().__init__(parent)
        self.sender = sender
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle(f"Emails from {self.sender.name}")
        self.setMinimumSize(600, 400)

        layout = QVBoxLayout(self)

        # Header info
        info_label = QLabel(f"<b>{self.sender.name}</b><br>"
                           f"Email: {self.sender.email}<br>"
                           f"Total: {self.sender.count} emails ({format_size(self.sender.total_size)})")
        layout.addWidget(info_label)

        # Email list
        self.email_list = QTableWidget()
        self.email_list.setColumnCount(3)
        self.email_list.setHorizontalHeaderLabels(["Subject", "Date", "Size"])
        self.email_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.email_list.setRowCount(len(self.sender.emails))

        for i, email in enumerate(self.sender.emails):
            self.email_list.setItem(i, 0, QTableWidgetItem(email.subject or "(No subject)"))
            self.email_list.setItem(i, 1, QTableWidgetItem(email.date))
            self.email_list.setItem(i, 2, QTableWidgetItem(format_size(email.size)))

        layout.addWidget(self.email_list)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.account_manager = GmailAccountManager()
        self.aggregator = EmailAggregator(self.account_manager)
        self.dark_mode = False
        self.current_view = 'senders'
        self.search_text = ''
        self.age_filter = 'all'

        self.setup_ui()
        self.refresh_accounts()

    def setup_ui(self):
        self.setWindowTitle("Gmail Email Cleanmail")
        self.setMinimumSize(1000, 700)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Header
        header = QLabel("<h1>Gmail Email Cleanmail</h1>"
                       "<p style='color: gray;'>Your data never leaves your machine</p>")
        header.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(header)

        # Create toolbar
        self.create_toolbar()

        # Main content splitter
        splitter = QSplitter(Qt.Vertical)
        main_layout.addWidget(splitter, 1)

        # Top section - Accounts and Scan
        top_widget = QWidget()
        top_layout = QHBoxLayout(top_widget)

        # Accounts section
        accounts_group = QGroupBox("Connected Accounts")
        accounts_layout = QVBoxLayout(accounts_group)

        self.accounts_list = QTableWidget()
        self.accounts_list.setColumnCount(3)
        self.accounts_list.setHorizontalHeaderLabels(["Email", "Status", "Actions"])
        self.accounts_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.accounts_list.setMaximumHeight(150)
        accounts_layout.addWidget(self.accounts_list)

        add_account_btn = QPushButton("+ Add Gmail Account")
        add_account_btn.clicked.connect(self.add_account)
        accounts_layout.addWidget(add_account_btn)

        top_layout.addWidget(accounts_group)

        # Scan section
        scan_group = QGroupBox("Scan Emails")
        scan_layout = QVBoxLayout(scan_group)

        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filter:"))
        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("e.g., category:promotions, is:unread, older_than:1y")
        filter_layout.addWidget(self.query_input)
        scan_layout.addLayout(filter_layout)

        self.scan_btn = QPushButton("Scan All Emails")
        self.scan_btn.clicked.connect(self.start_scan)
        scan_layout.addWidget(self.scan_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        scan_layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        scan_layout.addWidget(self.progress_label)

        top_layout.addWidget(scan_group)

        splitter.addWidget(top_widget)

        # Results section
        results_widget = QWidget()
        results_layout = QVBoxLayout(results_widget)

        # Toolbar for results
        results_toolbar = QHBoxLayout()

        # View toggle
        self.sender_btn = QPushButton("By Sender")
        self.sender_btn.setCheckable(True)
        self.sender_btn.setChecked(True)
        self.sender_btn.clicked.connect(lambda: self.switch_view('senders'))
        results_toolbar.addWidget(self.sender_btn)

        self.domain_btn = QPushButton("By Domain")
        self.domain_btn.setCheckable(True)
        self.domain_btn.clicked.connect(lambda: self.switch_view('domains'))
        results_toolbar.addWidget(self.domain_btn)

        results_toolbar.addSpacing(20)

        # Search
        results_toolbar.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter results...")
        self.search_input.textChanged.connect(self.on_search_changed)
        self.search_input.setMaximumWidth(200)
        results_toolbar.addWidget(self.search_input)

        # Age filter
        results_toolbar.addWidget(QLabel("Age:"))
        self.age_combo = QComboBox()
        self.age_combo.addItem("All Ages", "all")
        for key, label, _ in AGE_CATEGORIES:
            self.age_combo.addItem(label, key)
        self.age_combo.currentIndexChanged.connect(self.on_age_filter_changed)
        results_toolbar.addWidget(self.age_combo)

        results_toolbar.addStretch()

        # Export button
        export_btn = QPushButton("Export CSV")
        export_btn.clicked.connect(self.export_csv)
        results_toolbar.addWidget(export_btn)

        results_layout.addLayout(results_toolbar)

        # Summary stats
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("font-size: 14px; padding: 10px; background: #f0f0f0; border-radius: 5px;")
        results_layout.addWidget(self.stats_label)

        # Results table
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(5)
        self.results_table.setHorizontalHeaderLabels(["Name", "Email/Domain", "Count", "Size", "Actions"])
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.results_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.results_table.setAlternatingRowColors(True)
        results_layout.addWidget(self.results_table)

        splitter.addWidget(results_widget)
        splitter.setSizes([200, 500])

        # Status bar
        self.statusBar().showMessage("Ready. Add a Gmail account to get started.")

    def create_toolbar(self):
        toolbar = QToolBar()
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # Dark mode toggle
        self.dark_mode_action = QAction("Dark Mode", self)
        self.dark_mode_action.setCheckable(True)
        self.dark_mode_action.triggered.connect(self.toggle_dark_mode)
        toolbar.addAction(self.dark_mode_action)

        toolbar.addSeparator()

        # Help
        help_action = QAction("Help", self)
        help_action.triggered.connect(self.show_help)
        toolbar.addAction(help_action)

        # About
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        toolbar.addAction(about_action)

    def toggle_dark_mode(self, checked):
        self.dark_mode = checked
        app = QApplication.instance()

        if checked:
            # Dark palette
            palette = QPalette()
            palette.setColor(QPalette.Window, QColor(32, 33, 36))
            palette.setColor(QPalette.WindowText, QColor(232, 234, 237))
            palette.setColor(QPalette.Base, QColor(41, 42, 45))
            palette.setColor(QPalette.AlternateBase, QColor(53, 54, 58))
            palette.setColor(QPalette.ToolTipBase, QColor(232, 234, 237))
            palette.setColor(QPalette.ToolTipText, QColor(232, 234, 237))
            palette.setColor(QPalette.Text, QColor(232, 234, 237))
            palette.setColor(QPalette.Button, QColor(53, 54, 58))
            palette.setColor(QPalette.ButtonText, QColor(232, 234, 237))
            palette.setColor(QPalette.Link, QColor(138, 180, 248))
            palette.setColor(QPalette.Highlight, QColor(66, 133, 244))
            palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
            app.setPalette(palette)
            self.stats_label.setStyleSheet("font-size: 14px; padding: 10px; background: #35363a; border-radius: 5px;")
        else:
            # Light palette (default)
            app.setPalette(app.style().standardPalette())
            self.stats_label.setStyleSheet("font-size: 14px; padding: 10px; background: #f0f0f0; border-radius: 5px;")

    def refresh_accounts(self):
        """Refresh the accounts list."""
        accounts = self.account_manager.list_accounts()
        self.accounts_list.setRowCount(len(accounts))

        for i, account in enumerate(accounts):
            self.accounts_list.setItem(i, 0, QTableWidgetItem(account['email'] or account['id']))

            status = "Connected" if account['authenticated'] else "Disconnected"
            status_item = QTableWidgetItem(status)
            status_item.setForeground(QColor("green") if account['authenticated'] else QColor("red"))
            self.accounts_list.setItem(i, 1, status_item)

            remove_btn = QPushButton("Remove")
            remove_btn.clicked.connect(lambda checked, aid=account['id']: self.remove_account(aid))
            self.accounts_list.setCellWidget(i, 2, remove_btn)

        if not accounts:
            self.statusBar().showMessage("No accounts connected. Click 'Add Gmail Account' to get started.")
        else:
            self.statusBar().showMessage(f"{len(accounts)} account(s) connected.")

    def add_account(self):
        """Add a new Gmail account."""
        try:
            account_id = f"account_{len(self.account_manager.accounts) + 1}"
            self.statusBar().showMessage("Opening Google sign-in...")
            QApplication.processEvents()

            client = self.account_manager.add_account(account_id)
            self.refresh_accounts()
            self.statusBar().showMessage(f"Account {client.email_address} added successfully!")

        except FileNotFoundError as e:
            QMessageBox.critical(self, "Error",
                "credentials.json not found!\n\n"
                "Please place your Google OAuth credentials file in:\n"
                f"{Path(__file__).parent.parent / 'config' / 'credentials.json'}\n\n"
                "See README for setup instructions.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add account:\n{str(e)}")

    def remove_account(self, account_id: str):
        """Remove a Gmail account."""
        reply = QMessageBox.question(self, "Confirm Removal",
            "Remove this account? This will delete stored credentials.",
            QMessageBox.Yes | QMessageBox.No)

        if reply == QMessageBox.Yes:
            self.account_manager.remove_account(account_id)
            self.refresh_accounts()
            self.statusBar().showMessage("Account removed.")

    def start_scan(self):
        """Start scanning emails."""
        if not self.account_manager.accounts:
            QMessageBox.warning(self, "No Accounts", "Please add a Gmail account first.")
            return

        self.scan_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_label.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_label.setText("Starting scan...")

        query = self.query_input.text()

        self.scan_worker = ScanWorker(self.aggregator, query)
        self.scan_worker.progress.connect(self.on_scan_progress)
        self.scan_worker.finished.connect(self.on_scan_finished)
        self.scan_worker.start()

    def on_scan_progress(self, current, total):
        """Update scan progress."""
        if total > 0:
            percent = int((current / total) * 100)
            self.progress_bar.setValue(percent)
            self.progress_label.setText(f"Scanning: {current} / {total} emails ({percent}%)")

    def on_scan_finished(self, success, message):
        """Handle scan completion."""
        self.scan_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)

        if success:
            self.statusBar().showMessage(message)
            self.update_results()
        else:
            QMessageBox.critical(self, "Scan Error", message)

    def switch_view(self, view):
        """Switch between sender and domain views."""
        self.current_view = view
        self.sender_btn.setChecked(view == 'senders')
        self.domain_btn.setChecked(view == 'domains')
        self.update_results()

    def on_search_changed(self, text):
        """Handle search text change."""
        self.search_text = text.lower()
        self.update_results()

    def on_age_filter_changed(self, index):
        """Handle age filter change."""
        self.age_filter = self.age_combo.currentData()
        self.update_results()

    def update_results(self):
        """Update the results table."""
        self.results_table.setRowCount(0)

        if self.current_view == 'senders':
            self.update_senders_view()
        else:
            self.update_domains_view()

    def filter_by_search_and_age(self, name: str, email_or_domain: str, age_dist: dict) -> bool:
        """Check if item passes search and age filters."""
        # Search filter
        if self.search_text:
            if self.search_text not in name.lower() and self.search_text not in email_or_domain.lower():
                return False

        # Age filter
        if self.age_filter != 'all':
            if age_dist.get(self.age_filter, 0) == 0:
                return False

        return True

    def update_senders_view(self):
        """Update results with sender view."""
        results = self.aggregator.get_top_senders(limit=10000)

        # Filter results
        filtered = [(acc_id, s) for acc_id, s in results
                   if self.filter_by_search_and_age(s.name, s.email, s.age_distribution)]

        # Update stats
        total_emails = sum(s.count for _, s in filtered)
        total_size = sum(s.total_size for _, s in filtered)
        self.stats_label.setText(
            f"<b>{total_emails:,}</b> emails from <b>{len(filtered)}</b> senders "
            f"(<b>{format_size(total_size)}</b> total)"
        )

        self.results_table.setRowCount(len(filtered))
        self.results_table.setHorizontalHeaderLabels(["Name", "Email", "Count", "Size", "Actions"])

        for i, (account_id, sender) in enumerate(filtered):
            self.results_table.setItem(i, 0, QTableWidgetItem(sender.name))
            self.results_table.setItem(i, 1, QTableWidgetItem(sender.email))

            count_item = QTableWidgetItem(str(sender.count))
            count_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.results_table.setItem(i, 2, count_item)

            size_item = QTableWidgetItem(format_size(sender.total_size))
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.results_table.setItem(i, 3, size_item)

            # Actions widget
            actions = QWidget()
            actions_layout = QHBoxLayout(actions)
            actions_layout.setContentsMargins(2, 2, 2, 2)
            actions_layout.setSpacing(2)

            view_btn = QPushButton("View")
            view_btn.setMaximumWidth(50)
            view_btn.clicked.connect(lambda checked, s=sender: self.show_sender_details(s))
            actions_layout.addWidget(view_btn)

            if sender.unsubscribe_link:
                unsub_btn = QPushButton("Unsub")
                unsub_btn.setMaximumWidth(50)
                unsub_btn.setStyleSheet("background-color: #34a853; color: white;")
                unsub_btn.clicked.connect(lambda checked, link=sender.unsubscribe_link: webbrowser.open(link))
                actions_layout.addWidget(unsub_btn)

            trash_btn = QPushButton("Trash")
            trash_btn.setMaximumWidth(50)
            trash_btn.setStyleSheet("background-color: #5f6368; color: white;")
            trash_btn.clicked.connect(lambda checked, aid=account_id, s=sender: self.trash_sender(aid, s))
            actions_layout.addWidget(trash_btn)

            spam_btn = QPushButton("Spam")
            spam_btn.setMaximumWidth(50)
            spam_btn.setStyleSheet("background-color: #ea4335; color: white;")
            spam_btn.clicked.connect(lambda checked, aid=account_id, s=sender: self.spam_sender(aid, s))
            actions_layout.addWidget(spam_btn)

            self.results_table.setCellWidget(i, 4, actions)

    def update_domains_view(self):
        """Update results with domain view."""
        results = self.aggregator.get_top_domains(limit=10000)

        # Filter results
        filtered = [(acc_id, d) for acc_id, d in results
                   if self.filter_by_search_and_age(d.domain, d.domain, d.age_distribution)]

        # Update stats
        total_emails = sum(d.total_count for _, d in filtered)
        total_size = sum(d.total_size for _, d in filtered)
        total_senders = sum(len(d.senders) for _, d in filtered)
        self.stats_label.setText(
            f"<b>{total_emails:,}</b> emails from <b>{len(filtered)}</b> domains "
            f"(<b>{total_senders}</b> senders, <b>{format_size(total_size)}</b> total)"
        )

        self.results_table.setRowCount(len(filtered))
        self.results_table.setHorizontalHeaderLabels(["Domain", "Senders", "Count", "Size", "Actions"])

        for i, (account_id, domain) in enumerate(filtered):
            self.results_table.setItem(i, 0, QTableWidgetItem(domain.domain))
            self.results_table.setItem(i, 1, QTableWidgetItem(f"{len(domain.senders)} senders"))

            count_item = QTableWidgetItem(str(domain.total_count))
            count_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.results_table.setItem(i, 2, count_item)

            size_item = QTableWidgetItem(format_size(domain.total_size))
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.results_table.setItem(i, 3, size_item)

            # Actions widget
            actions = QWidget()
            actions_layout = QHBoxLayout(actions)
            actions_layout.setContentsMargins(2, 2, 2, 2)
            actions_layout.setSpacing(2)

            trash_btn = QPushButton("Trash All")
            trash_btn.setMaximumWidth(70)
            trash_btn.setStyleSheet("background-color: #5f6368; color: white;")
            trash_btn.clicked.connect(lambda checked, aid=account_id, d=domain: self.trash_domain(aid, d))
            actions_layout.addWidget(trash_btn)

            spam_btn = QPushButton("Spam All")
            spam_btn.setMaximumWidth(70)
            spam_btn.setStyleSheet("background-color: #ea4335; color: white;")
            spam_btn.clicked.connect(lambda checked, aid=account_id, d=domain: self.spam_domain(aid, d))
            actions_layout.addWidget(spam_btn)

            filter_btn = QPushButton("Filter")
            filter_btn.setMaximumWidth(50)
            filter_btn.setStyleSheet("background-color: #fbbc04; color: #202124;")
            filter_btn.clicked.connect(lambda checked, aid=account_id, d=domain: self.create_filter_domain(aid, d))
            actions_layout.addWidget(filter_btn)

            self.results_table.setCellWidget(i, 4, actions)

    def show_sender_details(self, sender: SenderAggregation):
        """Show email details for a sender."""
        dialog = EmailDetailsDialog(sender, self)
        dialog.exec()

    def trash_sender(self, account_id: str, sender: SenderAggregation):
        """Trash all emails from a sender."""
        reply = QMessageBox.question(self, "Confirm Trash",
            f"Move {sender.count} emails from {sender.name} to trash?",
            QMessageBox.Yes | QMessageBox.No)

        if reply == QMessageBox.Yes:
            self.execute_action(account_id, sender.email, None, 'trash')

    def spam_sender(self, account_id: str, sender: SenderAggregation):
        """Mark all emails from a sender as spam."""
        reply = QMessageBox.question(self, "Confirm Spam",
            f"Mark {sender.count} emails from {sender.name} as spam?",
            QMessageBox.Yes | QMessageBox.No)

        if reply == QMessageBox.Yes:
            self.execute_action(account_id, sender.email, None, 'spam')

    def trash_domain(self, account_id: str, domain: DomainAggregation):
        """Trash all emails from a domain."""
        reply = QMessageBox.question(self, "Confirm Trash",
            f"Move {domain.total_count} emails from {domain.domain} to trash?",
            QMessageBox.Yes | QMessageBox.No)

        if reply == QMessageBox.Yes:
            self.execute_action(account_id, None, domain.domain, 'trash')

    def spam_domain(self, account_id: str, domain: DomainAggregation):
        """Mark all emails from a domain as spam."""
        reply = QMessageBox.question(self, "Confirm Spam",
            f"Mark {domain.total_count} emails from {domain.domain} as spam?",
            QMessageBox.Yes | QMessageBox.No)

        if reply == QMessageBox.Yes:
            self.execute_action(account_id, None, domain.domain, 'spam')

    def create_filter_domain(self, account_id: str, domain: DomainAggregation):
        """Create a filter for a domain."""
        reply = QMessageBox.question(self, "Create Filter",
            f"Create a filter to auto-trash future emails from {domain.domain}?",
            QMessageBox.Yes | QMessageBox.No)

        if reply == QMessageBox.Yes:
            client = self.account_manager.get_account(account_id)
            if client:
                result = client.create_filter(domain=domain.domain, action='trash')
                if result.get('success'):
                    QMessageBox.information(self, "Success",
                        f"Filter created! Future emails from {domain.domain} will be auto-trashed.")
                else:
                    QMessageBox.warning(self, "Error",
                        f"Failed to create filter: {result.get('error')}")

    def execute_action(self, account_id: str, sender_email: Optional[str], domain: Optional[str], action: str):
        """Execute an action on emails."""
        if sender_email:
            message_ids = self.aggregator.get_message_ids_for_sender(account_id, sender_email)
        elif domain:
            message_ids = self.aggregator.get_message_ids_for_domain(account_id, domain)
        else:
            return

        if not message_ids:
            QMessageBox.warning(self, "No Emails", "No emails found to process.")
            return

        client = self.account_manager.get_account(account_id)
        if not client:
            return

        self.statusBar().showMessage(f"Processing {len(message_ids)} emails...")

        self.action_worker = ActionWorker(client, message_ids, action)
        self.action_worker.finished.connect(self.on_action_finished)
        self.action_worker.start()

    def on_action_finished(self, success, message, count):
        """Handle action completion."""
        self.statusBar().showMessage(message)
        if success:
            # Refresh results
            self.update_results()

    def export_csv(self):
        """Export results to CSV."""
        from PySide6.QtWidgets import QFileDialog
        import csv

        filename, _ = QFileDialog.getSaveFileName(self, "Export CSV", "", "CSV Files (*.csv)")
        if not filename:
            return

        try:
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                if self.current_view == 'senders':
                    writer.writerow(['Name', 'Email', 'Domain', 'Count', 'Size'])
                    for _, sender in self.aggregator.get_top_senders(limit=10000):
                        writer.writerow([sender.name, sender.email, sender.domain,
                                       sender.count, sender.total_size])
                else:
                    writer.writerow(['Domain', 'Senders', 'Count', 'Size'])
                    for _, domain in self.aggregator.get_top_domains(limit=10000):
                        writer.writerow([domain.domain, len(domain.senders),
                                       domain.total_count, domain.total_size])

            self.statusBar().showMessage(f"Exported to {filename}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    def show_help(self):
        """Show help dialog."""
        QMessageBox.information(self, "Help",
            "<h3>Gmail Email Cleanmail</h3>"
            "<p>This tool helps you clean up your Gmail inbox by analyzing and organizing emails.</p>"
            "<h4>Quick Start:</h4>"
            "<ol>"
            "<li>Add your Gmail account</li>"
            "<li>Click 'Scan All Emails'</li>"
            "<li>View results by sender or domain</li>"
            "<li>Trash or spam unwanted emails</li>"
            "</ol>"
            "<h4>Filter Examples:</h4>"
            "<ul>"
            "<li><code>category:promotions</code> - Marketing emails</li>"
            "<li><code>older_than:1y</code> - Emails older than 1 year</li>"
            "<li><code>is:unread</code> - Unread emails only</li>"
            "</ul>")

    def show_about(self):
        """Show about dialog."""
        QMessageBox.about(self, "About Gmail Email Cleanmail",
            "<h3>Gmail Email Cleanmail</h3>"
            "<p>Version 1.0</p>"
            "<p>A 100% local Gmail cleanup tool.</p>"
            "<p><b>Privacy First:</b> All data stays on your machine.</p>"
            "<p><a href='https://ko-fi.com/U7U41SAOJ6'>Support on Ko-fi</a></p>")


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    # Set default font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()

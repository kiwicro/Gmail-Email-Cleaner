// Gmail Email Cleanmail - Frontend JavaScript

let currentView = 'senders';
let senderData = [];
let domainData = [];
let expandedDomains = new Set();
let selectedItems = new Set(); // Track selected items for bulk actions
let savedScrollPosition = 0;

// API helper
async function api(endpoint, method = 'GET', data = null) {
    const options = {
        method,
        headers: {
            'Content-Type': 'application/json',
        },
    };
    if (data) {
        options.body = JSON.stringify(data);
    }
    const response = await fetch(endpoint, options);
    return response.json();
}

// Account management
async function addAccount() {
    const btn = document.getElementById('add-account-btn');
    btn.disabled = true;
    btn.textContent = 'Opening Google sign-in...';

    try {
        const result = await api('/api/accounts/add', 'POST', {});
        if (result.success) {
            location.reload();
        } else {
            alert('Error: ' + result.error);
        }
    } catch (err) {
        alert('Error adding account: ' + err.message);
    } finally {
        btn.disabled = false;
        btn.textContent = '+ Add Gmail Account';
    }
}

async function removeAccount(accountId) {
    if (!confirm('Remove this account? This will delete stored credentials.')) {
        return;
    }

    try {
        await api(`/api/accounts/${accountId}/remove`, 'POST');
        location.reload();
    } catch (err) {
        alert('Error removing account: ' + err.message);
    }
}

// Scanning
async function startScan() {
    const query = document.getElementById('query-filter').value;
    const scanBtn = document.getElementById('scan-btn');
    const progressContainer = document.getElementById('scan-progress');
    const progressFill = document.getElementById('progress-fill');
    const progressText = document.getElementById('progress-text');

    scanBtn.disabled = true;
    progressContainer.style.display = 'block';
    progressFill.style.width = '0%';
    progressText.textContent = 'Starting scan (fetching all emails)...';

    try {
        const result = await api('/api/scan', 'POST', {
            query: query
        });

        if (result.success && result.scan_id) {
            // Poll for progress
            await pollScanProgress(result.scan_id, progressFill, progressText);
            await loadResults();
        } else {
            progressText.textContent = 'Error: ' + (result.error || 'Unknown error');
        }
    } catch (err) {
        progressText.textContent = 'Error: ' + err.message;
    } finally {
        scanBtn.disabled = false;
    }
}

async function pollScanProgress(scanId, progressFill, progressText) {
    return new Promise((resolve, reject) => {
        const poll = async () => {
            try {
                const progress = await api(`/api/scan/${scanId}/progress`);

                if (progress.total > 0) {
                    const percent = Math.round((progress.current / progress.total) * 100);
                    progressFill.style.width = percent + '%';
                    progressText.textContent = `Scanning: ${progress.current} / ${progress.total} emails (${percent}%)`;
                } else {
                    progressText.textContent = 'Fetching email list...';
                }

                if (progress.status === 'completed') {
                    progressFill.style.width = '100%';
                    progressText.textContent = 'Scan complete!';
                    resolve();
                } else if (progress.status === 'failed') {
                    progressText.textContent = 'Error: ' + (progress.error || 'Scan failed');
                    reject(new Error(progress.error || 'Scan failed'));
                } else {
                    // Still running, poll again
                    setTimeout(poll, 500);
                }
            } catch (err) {
                progressText.textContent = 'Error checking progress';
                reject(err);
            }
        };

        poll();
    });
}

// Results
async function loadResults() {
    const container = document.getElementById('results-container');
    const section = document.getElementById('results-section');

    container.innerHTML = '<div class="loading">Loading results</div>';
    section.style.display = 'block';

    try {
        // Load both views - get all results
        const [senderResult, domainResult] = await Promise.all([
            api('/api/results?view=senders&limit=10000'),
            api('/api/results?view=domains&limit=10000')
        ]);
        senderData = senderResult.results || [];
        domainData = domainResult.results || [];
        renderResults();
    } catch (err) {
        container.innerHTML = '<p>Error loading results: ' + err.message + '</p>';
    }
}

function switchView(view) {
    currentView = view;
    document.querySelectorAll('.view-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.view === view);
    });
    renderResults();
}

function renderResults() {
    if (currentView === 'senders') {
        renderSendersTable();
    } else {
        renderDomainsTable();
    }
}

function renderSendersTable() {
    const container = document.getElementById('results-container');

    if (!senderData || senderData.length === 0) {
        container.innerHTML = '<p class="no-results">No results yet. Run a scan first.</p>';
        return;
    }

    // Calculate totals
    const totalEmails = senderData.reduce((sum, s) => sum + s.count, 0);
    const totalSenders = senderData.length;
    const selectedCount = selectedItems.size;

    let html = `
        <div class="results-summary">
            <div class="summary-stat">
                <div class="stat-value">${totalEmails.toLocaleString()}</div>
                <div class="stat-label">Total Emails</div>
            </div>
            <div class="summary-stat">
                <div class="stat-value">${totalSenders}</div>
                <div class="stat-label">Unique Senders</div>
            </div>
        </div>
        <div class="bulk-actions ${selectedCount > 0 ? 'visible' : ''}">
            <span class="bulk-count">${selectedCount} selected</span>
            <button class="action-btn trash" onclick="bulkTrash()">Trash Selected</button>
            <button class="action-btn spam" onclick="bulkSpam()">Spam Selected</button>
            <button class="action-btn view" onclick="clearSelection()">Clear Selection</button>
        </div>
        <table class="pivot-table">
            <thead>
                <tr>
                    <th class="col-checkbox"><input type="checkbox" onchange="toggleSelectAll(this)" ${selectedCount === senderData.length && selectedCount > 0 ? 'checked' : ''}></th>
                    <th class="col-sender">Sender</th>
                    <th class="col-domain">Domain</th>
                    <th class="col-count">Count</th>
                    <th class="col-actions">Actions</th>
                </tr>
            </thead>
            <tbody>
    `;

    for (const sender of senderData) {
        const itemKey = `sender:${sender.account_id}:${sender.email}`;
        const isSelected = selectedItems.has(itemKey);
        html += `
            <tr class="sender-row visible ${isSelected ? 'selected' : ''}" data-key="${escapeAttr(itemKey)}">
                <td class="col-checkbox"><input type="checkbox" ${isSelected ? 'checked' : ''} onchange="toggleSelectItem('${escapeAttr(itemKey)}')"></td>
                <td>
                    <span class="sender-name">${escapeHtml(sender.name)}</span>
                    ${sender.has_unsubscribe ? '<span class="unsub-indicator" title="Unsubscribe available"></span>' : ''}
                    <span class="sender-email">${escapeHtml(sender.email)}</span>
                </td>
                <td>${escapeHtml(sender.domain)}</td>
                <td class="sender-count">${sender.count}</td>
                <td class="sender-actions">
                    <button class="action-btn view" onclick="showSenderDetails('${sender.account_id}', '${escapeAttr(sender.email)}')">View</button>
                    ${sender.has_unsubscribe ? `<button class="action-btn unsub" onclick="openUnsubscribe('${sender.account_id}', '${escapeAttr(sender.email)}')">Unsubscribe</button>` : ''}
                    <button class="action-btn trash" onclick="confirmTrash('${sender.account_id}', '${escapeAttr(sender.email)}', null, ${sender.count})">Trash</button>
                    <button class="action-btn spam" onclick="confirmSpam('${sender.account_id}', '${escapeAttr(sender.email)}', null, ${sender.count})">Spam</button>
                </td>
            </tr>
        `;
    }

    html += '</tbody></table>';
    container.innerHTML = html;
}

// Selection functions
function toggleSelectItem(key) {
    if (selectedItems.has(key)) {
        selectedItems.delete(key);
    } else {
        selectedItems.add(key);
    }
    updateSelectionUI();
}

function toggleSelectAll(checkbox) {
    if (checkbox.checked) {
        // Select all visible items
        if (currentView === 'senders') {
            senderData.forEach(s => selectedItems.add(`sender:${s.account_id}:${s.email}`));
        } else {
            domainData.forEach(d => selectedItems.add(`domain:${d.account_id}:${d.domain}`));
        }
    } else {
        selectedItems.clear();
    }
    updateSelectionUI();
}

function clearSelection() {
    selectedItems.clear();
    updateSelectionUI();
}

function updateSelectionUI() {
    // Update checkboxes and row highlights without re-rendering entire table
    const rows = document.querySelectorAll('tr[data-key]');
    rows.forEach(row => {
        const key = row.dataset.key;
        const checkbox = row.querySelector('input[type="checkbox"]');
        const isSelected = selectedItems.has(key);
        if (checkbox) checkbox.checked = isSelected;
        row.classList.toggle('selected', isSelected);
    });

    // Update bulk actions bar
    const bulkBar = document.querySelector('.bulk-actions');
    const bulkCount = document.querySelector('.bulk-count');
    if (bulkBar && bulkCount) {
        bulkBar.classList.toggle('visible', selectedItems.size > 0);
        bulkCount.textContent = `${selectedItems.size} selected`;
    }

    // Update select all checkbox
    const selectAllCheckbox = document.querySelector('th.col-checkbox input[type="checkbox"]');
    if (selectAllCheckbox) {
        const totalItems = currentView === 'senders' ? senderData.length : domainData.length;
        selectAllCheckbox.checked = selectedItems.size === totalItems && totalItems > 0;
    }
}

function saveScrollPosition() {
    savedScrollPosition = window.scrollY;
}

function restoreScrollPosition() {
    window.scrollTo(0, savedScrollPosition);
}

function toggleDomain(domain) {
    if (expandedDomains.has(domain)) {
        expandedDomains.delete(domain);
    } else {
        expandedDomains.add(domain);
    }
    renderDomainsTable();
}

function renderDomainsTable() {
    const container = document.getElementById('results-container');

    if (!domainData || domainData.length === 0) {
        container.innerHTML = '<p class="no-results">No results yet. Run a scan first.</p>';
        return;
    }

    // Calculate totals
    const totalEmails = domainData.reduce((sum, d) => sum + d.total_count, 0);
    const totalDomains = domainData.length;
    const totalSenders = domainData.reduce((sum, d) => sum + d.sender_count, 0);
    const selectedCount = selectedItems.size;

    let html = `
        <div class="results-summary">
            <div class="summary-stat">
                <div class="stat-value">${totalEmails.toLocaleString()}</div>
                <div class="stat-label">Total Emails</div>
            </div>
            <div class="summary-stat">
                <div class="stat-value">${totalDomains}</div>
                <div class="stat-label">Domains</div>
            </div>
            <div class="summary-stat">
                <div class="stat-value">${totalSenders}</div>
                <div class="stat-label">Unique Senders</div>
            </div>
        </div>
        <div class="bulk-actions ${selectedCount > 0 ? 'visible' : ''}">
            <span class="bulk-count">${selectedCount} selected</span>
            <button class="action-btn trash" onclick="bulkTrash()">Trash Selected</button>
            <button class="action-btn spam" onclick="bulkSpam()">Spam Selected</button>
            <button class="action-btn view" onclick="clearSelection()">Clear Selection</button>
        </div>
        <table class="pivot-table">
            <thead>
                <tr>
                    <th class="col-checkbox"><input type="checkbox" onchange="toggleSelectAll(this)" ${selectedCount === domainData.length && selectedCount > 0 ? 'checked' : ''}></th>
                    <th class="col-domain">Domain</th>
                    <th class="col-sender">Senders</th>
                    <th class="col-count">Count</th>
                    <th class="col-actions">Actions</th>
                </tr>
            </thead>
            <tbody>
    `;

    for (const domain of domainData) {
        const isExpanded = expandedDomains.has(domain.domain);
        const itemKey = `domain:${domain.account_id}:${domain.domain}`;
        const isSelected = selectedItems.has(itemKey);

        // Domain row
        html += `
            <tr class="domain-row ${isExpanded ? 'expanded' : ''} ${isSelected ? 'selected' : ''}" data-key="${escapeAttr(itemKey)}">
                <td class="col-checkbox" onclick="event.stopPropagation()"><input type="checkbox" ${isSelected ? 'checked' : ''} onchange="toggleSelectItem('${escapeAttr(itemKey)}')"></td>
                <td onclick="toggleDomain('${escapeAttr(domain.domain)}')">
                    <div class="domain-name">
                        <span class="expand-icon">${isExpanded ? '▼' : '▶'}</span>
                        ${escapeHtml(domain.domain)}
                    </div>
                </td>
                <td onclick="toggleDomain('${escapeAttr(domain.domain)}')">${domain.sender_count} sender${domain.sender_count !== 1 ? 's' : ''}</td>
                <td class="domain-count" onclick="toggleDomain('${escapeAttr(domain.domain)}')">${domain.total_count}</td>
                <td class="domain-actions" onclick="event.stopPropagation()">
                    <button class="action-btn trash" onclick="confirmTrash('${domain.account_id}', null, '${escapeAttr(domain.domain)}', ${domain.total_count})">Trash All</button>
                    <button class="action-btn spam" onclick="confirmSpam('${domain.account_id}', null, '${escapeAttr(domain.domain)}', ${domain.total_count})">Spam All</button>
                </td>
            </tr>
        `;

        // Sender rows (shown when expanded)
        if (isExpanded) {
            for (const sender of domain.senders) {
                html += `
                    <tr class="sender-row visible">
                        <td class="col-checkbox"></td>
                        <td class="sender-indent"></td>
                        <td>
                            <span class="sender-name">${escapeHtml(sender.name)}</span>
                            ${sender.has_unsubscribe ? '<span class="unsub-indicator" title="Unsubscribe available"></span>' : ''}
                            <span class="sender-email">${escapeHtml(sender.email)}</span>
                        </td>
                        <td class="sender-count">${sender.count}</td>
                        <td class="sender-actions">
                            <button class="action-btn view" onclick="showSenderDetails('${domain.account_id}', '${escapeAttr(sender.email)}')">View</button>
                            ${sender.has_unsubscribe ? `<button class="action-btn unsub" onclick="openUnsubscribe('${domain.account_id}', '${escapeAttr(sender.email)}')">Unsubscribe</button>` : ''}
                            <button class="action-btn trash" onclick="confirmTrash('${domain.account_id}', '${escapeAttr(sender.email)}', null, ${sender.count})">Trash</button>
                            <button class="action-btn spam" onclick="confirmSpam('${domain.account_id}', '${escapeAttr(sender.email)}', null, ${sender.count})">Spam</button>
                        </td>
                    </tr>
                `;
            }
        }
    }

    html += '</tbody></table>';
    container.innerHTML = html;
}

// Sender details modal
async function showSenderDetails(accountId, senderEmail) {
    const modal = document.getElementById('detail-modal');
    const body = document.getElementById('modal-body');

    body.innerHTML = '<div class="loading">Loading details</div>';
    modal.style.display = 'flex';

    try {
        const result = await api(`/api/sender/${accountId}/${encodeURIComponent(senderEmail)}/details`);
        body.innerHTML = `
            <h2>${escapeHtml(result.name)}</h2>
            <p><strong>Email:</strong> ${escapeHtml(result.email)}</p>
            <p><strong>Domain:</strong> ${escapeHtml(result.domain)}</p>
            <p><strong>Total emails:</strong> ${result.count}</p>
            ${result.unsubscribe_link ? `
                <p><a href="${escapeAttr(result.unsubscribe_link)}" target="_blank" class="btn btn-small btn-success">Unsubscribe Link</a></p>
            ` : ''}
            <div class="email-list">
                <h3>All Emails (${result.emails.length})</h3>
                ${result.emails.map(email => `
                    <div class="email-item">
                        <div class="email-subject">${escapeHtml(email.subject || '(No subject)')}</div>
                        <div class="email-date">${escapeHtml(email.date)}</div>
                        <div class="email-snippet">${escapeHtml(email.snippet)}</div>
                    </div>
                `).join('')}
            </div>
        `;
    } catch (err) {
        body.innerHTML = '<p>Error loading details: ' + err.message + '</p>';
    }
}

function closeModal() {
    document.getElementById('detail-modal').style.display = 'none';
}

// Unsubscribe
async function openUnsubscribe(accountId, senderEmail) {
    try {
        const result = await api('/api/action/unsubscribe', 'POST', {
            account_id: accountId,
            sender_email: senderEmail
        });

        if (result.success && result.unsubscribe_link) {
            window.open(result.unsubscribe_link, '_blank');
        } else {
            alert('No unsubscribe link found for this sender.');
        }
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

// Confirmation modal
let pendingAction = null;

function confirmSpam(accountId, senderEmail, domain, count) {
    saveScrollPosition();
    const modal = document.getElementById('confirm-modal');
    const title = document.getElementById('confirm-title');
    const message = document.getElementById('confirm-message');
    const actionBtn = document.getElementById('confirm-action-btn');

    title.textContent = 'Mark as Spam';
    message.textContent = `Are you sure you want to mark ${count} email(s) as spam? This will move them to your spam folder.`;
    actionBtn.textContent = 'Mark as Spam';
    actionBtn.className = 'btn btn-danger';
    actionBtn.onclick = () => executeSpam(accountId, senderEmail, domain);

    modal.style.display = 'flex';
}

function confirmTrash(accountId, senderEmail, domain, count) {
    saveScrollPosition();
    const modal = document.getElementById('confirm-modal');
    const title = document.getElementById('confirm-title');
    const message = document.getElementById('confirm-message');
    const actionBtn = document.getElementById('confirm-action-btn');

    title.textContent = 'Move to Trash';
    message.textContent = `Are you sure you want to move ${count} email(s) to trash?`;
    actionBtn.textContent = 'Move to Trash';
    actionBtn.className = 'btn btn-danger';
    actionBtn.onclick = () => executeTrash(accountId, senderEmail, domain);

    modal.style.display = 'flex';
}

function closeConfirmModal() {
    document.getElementById('confirm-modal').style.display = 'none';
    restoreScrollPosition();
}

async function executeSpam(accountId, senderEmail, domain) {
    closeConfirmModal();

    try {
        const result = await api('/api/action/spam', 'POST', {
            account_id: accountId,
            sender_email: senderEmail,
            domain: domain
        });

        if (result.success) {
            // Remove from local data instead of reloading
            removeFromLocalData(accountId, senderEmail, domain);
            renderResults();
            restoreScrollPosition();
        } else {
            alert('Error: ' + result.error);
        }
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

async function executeTrash(accountId, senderEmail, domain) {
    closeConfirmModal();

    try {
        const result = await api('/api/action/trash', 'POST', {
            account_id: accountId,
            sender_email: senderEmail,
            domain: domain
        });

        if (result.success) {
            // Remove from local data instead of reloading
            removeFromLocalData(accountId, senderEmail, domain);
            renderResults();
            restoreScrollPosition();
        } else {
            alert('Error: ' + result.error);
        }
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

function removeFromLocalData(accountId, senderEmail, domain) {
    if (senderEmail) {
        // Remove specific sender
        senderData = senderData.filter(s => !(s.account_id === accountId && s.email === senderEmail));
        // Also remove from domain data
        domainData.forEach(d => {
            if (d.account_id === accountId) {
                d.senders = d.senders.filter(s => s.email !== senderEmail);
                d.sender_count = d.senders.length;
                d.total_count = d.senders.reduce((sum, s) => sum + s.count, 0);
            }
        });
        // Remove empty domains
        domainData = domainData.filter(d => d.senders.length > 0);
    } else if (domain) {
        // Remove entire domain
        domainData = domainData.filter(d => !(d.account_id === accountId && d.domain === domain));
        // Also remove senders from that domain
        senderData = senderData.filter(s => !(s.account_id === accountId && s.domain === domain));
    }
}

// Bulk action functions
async function bulkTrash() {
    if (selectedItems.size === 0) return;

    saveScrollPosition();
    const count = selectedItems.size;
    const modal = document.getElementById('confirm-modal');
    const title = document.getElementById('confirm-title');
    const message = document.getElementById('confirm-message');
    const actionBtn = document.getElementById('confirm-action-btn');

    title.textContent = 'Bulk Move to Trash';
    message.textContent = `Are you sure you want to trash emails from ${count} selected item(s)?`;
    actionBtn.textContent = 'Trash All Selected';
    actionBtn.className = 'btn btn-danger';
    actionBtn.onclick = executeBulkTrash;

    modal.style.display = 'flex';
}

async function bulkSpam() {
    if (selectedItems.size === 0) return;

    saveScrollPosition();
    const count = selectedItems.size;
    const modal = document.getElementById('confirm-modal');
    const title = document.getElementById('confirm-title');
    const message = document.getElementById('confirm-message');
    const actionBtn = document.getElementById('confirm-action-btn');

    title.textContent = 'Bulk Mark as Spam';
    message.textContent = `Are you sure you want to mark emails from ${count} selected item(s) as spam?`;
    actionBtn.textContent = 'Spam All Selected';
    actionBtn.className = 'btn btn-danger';
    actionBtn.onclick = executeBulkSpam;

    modal.style.display = 'flex';
}

async function executeBulkTrash() {
    closeConfirmModal();

    const items = Array.from(selectedItems);
    let successCount = 0;

    for (const item of items) {
        const [type, accountId, identifier] = item.split(':');
        try {
            const result = await api('/api/action/trash', 'POST', {
                account_id: accountId,
                sender_email: type === 'sender' ? identifier : null,
                domain: type === 'domain' ? identifier : null
            });
            if (result.success) {
                removeFromLocalData(accountId, type === 'sender' ? identifier : null, type === 'domain' ? identifier : null);
                successCount++;
            }
        } catch (err) {
            console.error('Error trashing:', err);
        }
    }

    selectedItems.clear();
    renderResults();
    restoreScrollPosition();
}

async function executeBulkSpam() {
    closeConfirmModal();

    const items = Array.from(selectedItems);
    let successCount = 0;

    for (const item of items) {
        const [type, accountId, identifier] = item.split(':');
        try {
            const result = await api('/api/action/spam', 'POST', {
                account_id: accountId,
                sender_email: type === 'sender' ? identifier : null,
                domain: type === 'domain' ? identifier : null
            });
            if (result.success) {
                removeFromLocalData(accountId, type === 'sender' ? identifier : null, type === 'domain' ? identifier : null);
                successCount++;
            }
        } catch (err) {
            console.error('Error spamming:', err);
        }
    }

    selectedItems.clear();
    renderResults();
    restoreScrollPosition();
}

// Utility functions
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function escapeAttr(text) {
    if (!text) return '';
    // Properly escape for HTML attributes to prevent XSS
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/'/g, '&#x27;')
        .replace(/"/g, '&quot;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\\/g, '&#x5c;')
        .replace(/`/g, '&#x60;');
}

// Close modals on escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeModal();
        closeConfirmModal();
    }
});

// Close modals on outside click
document.querySelectorAll('.modal').forEach(modal => {
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.style.display = 'none';
        }
    });
});

/**
 * Atom Voting — Frontend Application Logic
 * Dual-Device verification flow: Device A generates QR, Device B verifies before ledger commit.
 */

// === State & Config ===
const API_BASE = '/api/v1';
let Session = {
    isAuthenticated: false,
    voterId: null,
    credentialHash: null,       // Active credential used when voting
    realCredentialHash: null,   // JCJ: counted in tally
    fakeCredentialHash: null,   // JCJ: discarded at tally (reveal under coercion)
    usingFakeCredential: false, // Currently voting with fake credential?
    currentBallotHash: null,
    pollInterval: null,
    pollNonce: 0,        // Incremented every new vote — guards stale poll callbacks
    qrShownAt: 0,       // Timestamp (ms) when QR view was shown
};

// === DOM Elements ===
const Views = {
    login: document.getElementById('view-login'),
    vote: document.getElementById('view-vote'),
    qr: document.getElementById('view-qr'),
    receipt: document.getElementById('view-receipt'),
    verify: document.getElementById('view-verify'),
};

// === UI Navigation ===
function showView(viewName) {
    Object.values(Views).forEach(v => v.classList.remove('active'));
    Views[viewName].classList.add('active');
}

function showLoading(text) {
    document.getElementById('loading-text').textContent = text;
    document.getElementById('loading-overlay').classList.remove('hidden');
}

function hideLoading() {
    document.getElementById('loading-overlay').classList.add('hidden');
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.getElementById('toast-container').appendChild(toast);
    setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 300); }, 4500);
}

// === Step Indicator Animation ===
function activateStep(stepId) {
    document.querySelectorAll('.crypto-step').forEach(s => s.classList.remove('done'));
    const step = document.getElementById(stepId);
    if (step) step.classList.add('done');
}

// === Authentication (Mock WebAuthn) ===
document.getElementById('btn-authenticate').addEventListener('click', async () => {
    showLoading('Waiting for Hardware Token...');
    await delay(1500);
    Session.isAuthenticated = true;
    Session.voterId = 'voter_' + Math.floor(Math.random() * 10000);

    // Issue JCJ credential pair from the server
    try {
        showLoading('Issuing JCJ Credential Pair...');
        const res = await fetch(`${API_BASE}/auth/credentials/${Session.voterId}`, { method: 'POST' });
        if (res.ok) {
            const creds = await res.json();
            Session.realCredentialHash = creds.real_credential_hash;
            Session.fakeCredentialHash = creds.fake_credential_hash;
            Session.credentialHash = Session.realCredentialHash; // default: real
            Session.usingFakeCredential = false;
        } else {
            // Fallback to client-generated credential (offline mode)
            Session.realCredentialHash = 'cred_' + btoa(Session.voterId).substring(0, 16);
            Session.fakeCredentialHash = 'fake_' + btoa(Session.voterId + '_f').substring(0, 16);
            Session.credentialHash = Session.realCredentialHash;
        }
    } catch (_) {
        Session.realCredentialHash = 'cred_' + btoa(Session.voterId).substring(0, 16);
        Session.fakeCredentialHash = 'fake_' + btoa(Session.voterId + '_f').substring(0, 16);
        Session.credentialHash = Session.realCredentialHash;
    }

    const statusEl = document.getElementById('nav-user-status');
    statusEl.innerHTML = `<span class="status-dot active"></span> ${Session.voterId}`;
    updateCredentialToggleUI();
    hideLoading();
    showToast('Authenticated via hardware token. JCJ credentials issued.', 'info');
    showView('vote');
});

function updateCredentialToggleUI() {
    const toggle = document.getElementById('credential-toggle');
    const label = document.getElementById('credential-label');
    const box = document.getElementById('jcj-toggle-box');
    if (!toggle || !label || !box) return;
    // Show the box once credentials are available
    box.style.display = 'block';
    if (Session.usingFakeCredential) {
        toggle.checked = true;
        label.textContent = '🎭 Fake Credential Active — Coercion Escape Mode';
        label.style.color = 'var(--danger-color)';
    } else {
        toggle.checked = false;
        label.textContent = '🔐 Real Credential Active — Vote will be counted';
        label.style.color = 'var(--success-color)';
    }
}

// === JCJ Credential Toggle Handler ===
document.addEventListener('change', (e) => {
    if (e.target.id !== 'credential-toggle') return;
    Session.usingFakeCredential = e.target.checked;
    Session.credentialHash = Session.usingFakeCredential
        ? Session.fakeCredentialHash
        : Session.realCredentialHash;
    updateCredentialToggleUI();
    showToast(
        Session.usingFakeCredential
            ? '🎭 Coercion escape active. Next vote will use the fake credential.'
            : '🔐 Switched back to real credential.',
        'info'
    );
});

// === Helpers ===
function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

function generateCryptographicPayload() {
    const nonce = 'nonce_' + Math.random().toString(36).substr(2, 9);
    return {
        encrypted_ballot: {
            c1: Array.from({ length: 64 }, () => Math.floor(Math.random() * 16).toString(16)).join(''),
            c2: Array.from({ length: 64 }, () => Math.floor(Math.random() * 16).toString(16)).join(''),
            nonce_id: nonce,
        },
        zk_proof: { proof_data: { challenges: [], responses: [] }, is_stub: true },
        credential_hash: Session.credentialHash,
    };
}

// === Device A: Encrypt → Prepare → Show QR ===
document.getElementById('vote-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const code = parseInt(document.getElementById('candidate-code').value, 10);
    if (isNaN(code) || code <= 0) return showToast('Please enter a valid candidate code.', 'error');
    await submitBallot('prepare', code);
});

document.getElementById('btn-challenge').addEventListener('click', async () => {
    const code = parseInt(document.getElementById('candidate-code').value, 10);
    if (isNaN(code) || code <= 0) return showToast('Please enter a valid candidate code.', 'error');
    await submitBallot('challenge', code);
});

async function submitBallot(action, code) {
    showLoading('Step 1: Generating 2048-bit ElGamal ciphertext...');
    await delay(600);
    activateStep('step-encrypt');

    showLoading('Step 2: Computing Disjunctive ZK Proof...');
    await delay(700);
    activateStep('step-zkp');

    const payload = generateCryptographicPayload();

    if (action === 'challenge') {
        showLoading('Initiating Audit Challenge...');
        try {
            const res = await fetch(`${API_BASE}/ballots`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ...payload, action: 'challenge' }),
            });
            const data = await res.json();
            hideLoading();
            if (!res.ok) throw new Error(data.detail?.message || 'Audit failed');
            showToast(`Audit: ${data.candidate_mapping_hint}. Ballot destroyed.`, 'info');
        } catch (err) {
            hideLoading();
            showToast(err.message, 'error');
        }
        return;
    }

    // DUAL-DEVICE FLOW: POST to /prepare
    showLoading('Step 3: Sending to pending store...');
    try {
        const res = await fetch(`${API_BASE}/ballots/prepare`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await res.json();
        hideLoading();
        if (!res.ok) throw new Error(data.detail?.message || 'Preparation failed');

        Session.currentBallotHash = data.ballot_hash;
        showQRCode(data.ballot_hash, data.verification_url, code, payload.encrypted_ballot.c1, payload.encrypted_ballot.c2);
    } catch (err) {
        hideLoading();
        showToast(err.message, 'error');
    }
}

// === NFC Token Logic (AVT-1) ===
function buildNFCPayload(ballotHash, c1, c2) {
    const buffer = new Uint8Array(138);
    const encoder = new TextEncoder();
    
    // Bytes 0-1: Election ID (simple demo stub)
    buffer[0] = 0x41; buffer[1] = 0x54; // "AT"
    
    // Bytes 42-73: C1 preview (32 hex chars)
    const c1Bytes = encoder.encode(c1.substring(0, 32));
    buffer.set(c1Bytes, 42);
    
    // Bytes 74-105: C2 preview (32 hex chars)
    const c2Bytes = encoder.encode(c2.substring(0, 32));
    buffer.set(c2Bytes, 74);
    
    // Bytes 106-137: Ballot hash
    const hashBytes = encoder.encode(ballotHash.substring(0, 32));
    buffer.set(hashBytes, 106);
    
    return buffer;
}

async function startNFCBroadcasting(ballotHash, c1, c2) {
    const prompt = document.getElementById('nfc-prompt');
    if (!('NDEFReader' in window)) {
        if (prompt) prompt.classList.add('hidden');
        return;
    }

    try {
        const ndef = new NDEFReader();
        const payload = buildNFCPayload(ballotHash, c1, c2);
        
        // Show pulse UI
        if (prompt) prompt.classList.remove('hidden');
        
        await ndef.write({
            records: [{
                recordType: "mime",
                mediaType: "application/atom-voting",
                data: payload
            }]
        });
        
        showToast('NFC Broadcast Active: Tap your AVT-1 Token.', 'info');
    } catch (err) {
        console.warn("NFC error:", err);
        if (prompt) prompt.classList.add('hidden');
    }
}

// === QR Code Display ===
function showQRCode(ballotHash, verificationUrl, candidateCode, c1, c2) {
    activateStep('step-qr');
    document.getElementById('qr-ballot-hash').textContent = ballotHash;

    // Start parallel NFC broadcast for AVT-1 Token
    if (c1 && c2) startNFCBroadcasting(ballotHash, c1, c2);

    // CRITICAL: switch view FIRST so the canvas is visible and has layout dimensions
    // before qrcodejs tries to draw into it. On HTTPS deployments the library fails
    // silently if the container is display:none when it initialises.
    showView('qr');
    Session.qrShownAt = Date.now(); // record when QR was first displayed

    // Use requestAnimationFrame to ensure the browser has completed the layout pass
    requestAnimationFrame(() => {
        const qrCanvas = document.getElementById('qr-canvas');
        qrCanvas.innerHTML = '';
        new QRCode(qrCanvas, {
            text: verificationUrl,
            width: 200,
            height: 200,
            colorDark: '#2D2A26',
            colorLight: '#FCFBF8',
            correctLevel: QRCode.CorrectLevel.H,
        });
    });

    startPollingForConfirmation(ballotHash);
}

// === Polling: Device A waits for Device B to confirm ===
function startPollingForConfirmation(ballotHash) {
    clearPolling();
    // Capture a unique nonce for this poll session.
    // If another vote starts (incrementing pollNonce), all callbacks from THIS
    // poll session will be ignored even if they fire before clearInterval runs.
    const myNonce = ++Session.pollNonce;

    Session.pollInterval = setInterval(async () => {
        // Guard: ignore this callback if a newer poll session has started
        if (Session.pollNonce !== myNonce) return;

        // Guard: don't transition away from the QR view within 4 seconds of showing it.
        // This prevents fast-firing polls from skipping the QR entirely.
        const msOnQrView = Date.now() - Session.qrShownAt;
        if (msOnQrView < 4000) return;

        try {
            const res = await fetch(`${API_BASE}/ballots/verify/${ballotHash}`);
            if (!res.ok) return;
            const data = await res.json();
            if (data.confirmed && Session.pollNonce === myNonce) {
                // Fetch the full confirm result to get revote metadata
                try {
                    const confirmRes = await fetch(`${API_BASE}/ballots/verify/${ballotHash}`);
                    const confirmData = confirmRes.ok ? await confirmRes.json() : {};
                    clearPolling();
                    const isRevote = confirmData.is_revote === 'true';
                    const revoteCount = parseInt(confirmData.revote_count || '1', 10);
                    showToast(
                        isRevote
                            ? `↩️ Revote #${revoteCount} confirmed! Previous vote replaced.`
                            : 'Device B confirmed! Vote is on the ledger.',
                        'info'
                    );
                    document.getElementById('receipt-vote-id').textContent = ballotHash;
                    document.getElementById('receipt-hash').textContent =
                        (isRevote ? `↩️ Revote #${revoteCount} · ` : 'Vote #1 · ') +
                        'Confirmed by Device B · ' + new Date().toLocaleTimeString();
                    showView('receipt');
                } catch (_) {
                    clearPolling();
                    document.getElementById('receipt-vote-id').textContent = ballotHash;
                    document.getElementById('receipt-hash').textContent = 'Confirmed by Device B · ' + new Date().toLocaleTimeString();
                    showView('receipt');
                }
            }
        } catch (_) { /* silently retry */ }
    }, 2000);
}

function clearPolling() {
    if (Session.pollInterval) clearInterval(Session.pollInterval);
    Session.pollInterval = null;
}

document.getElementById('btn-vote-again').addEventListener('click', () => {
    document.getElementById('candidate-code').value = '';
    // Note: we don't need to pass revote_pointer from the frontend anymore.
    // The backend auto-detects it server-side using the credential_hash.
    showView('vote');
});

// === Device B: Verify & Confirm ===
async function loadVerificationView(ballotHash) {
    // Immediately switch to Device B mode UI
    document.getElementById('nav-device-label').textContent = 'Device B \u00b7 Verification';
    document.getElementById('nav-device-label').style.background = 'rgba(76, 175, 80, 0.12)';
    document.getElementById('nav-device-label').style.color = '#4CAF50';
    showView('verify');

    // Show loading state in the verify box
    document.getElementById('verify-hash').textContent = ballotHash;
    document.getElementById('verify-c1').textContent = 'Fetching...';
    document.getElementById('verify-c2').textContent = 'Fetching...';
    document.getElementById('verify-candidate-name').textContent = '...';
    document.getElementById('verify-candidate-name').style.color = ''; // Reset color
    document.querySelector('.verify-candidate-sub').textContent = 'Confirm the candidate code matches your selection on Device A.';
    document.getElementById('verify-status').classList.remove('hidden');
    document.getElementById('verify-confirmed-msg').classList.add('hidden');


    try {
        const res = await fetch(`${API_BASE}/ballots/verify/${ballotHash}`);

        if (!res.ok) {
            // Ballot not found - show clear error within the verify view
            document.getElementById('verify-c1').textContent = '\u2014';
            document.getElementById('verify-c2').textContent = '\u2014';
            document.getElementById('verify-candidate-name').textContent = 'Not Found';
            document.getElementById('verify-candidate-name').style.color = 'var(--danger-color)';
            document.querySelector('.verify-candidate-sub').textContent = 'This ballot hash is invalid or already confirmed. Check the QR code again.';
            document.getElementById('verify-status').classList.add('hidden');
            showToast('Ballot not found. Use the hash from the current QR code on Device A.', 'error');
            return;
        }

        const data = await res.json();

        if (data.confirmed) {
            document.getElementById('verify-status').classList.add('hidden');
            document.getElementById('verify-confirmed-msg').classList.remove('hidden');
        }

        document.getElementById('verify-hash').textContent = data.ballot_hash;
        document.getElementById('verify-c1').textContent = data.encrypted_c1_preview + '...';
        document.getElementById('verify-c2').textContent = data.encrypted_c2_preview + '...';

        // Decode candidate from URL param (if present)
        const urlParams = new URLSearchParams(window.location.search);
        const codeParam = parseInt(urlParams.get('code') || '0', 10);
        const candidateName = codeParam ? `Code Sheet Mapping: ${codeParam}` : 'Verify on your code sheet';
        document.getElementById('verify-candidate-name').textContent = candidateName;

    } catch (err) {
        showToast(err.message, 'error');
    }
}

document.getElementById('btn-confirm-vote').addEventListener('click', async () => {
    const ballotHash = new URLSearchParams(window.location.search).get('verify');
    showLoading('Submitting ballot to Public Ledger...');
    try {
        const res = await fetch(`${API_BASE}/ballots/confirm/${ballotHash}`, { method: 'POST' });
        const data = await res.json();
        hideLoading();
        if (!res.ok) throw new Error(data.detail?.message || 'Confirmation failed');

        document.getElementById('verify-status').classList.add('hidden');
        document.getElementById('verify-confirmed-msg').classList.remove('hidden');
        showToast('Vote successfully submitted to the ledger!', 'info');
    } catch (err) {
        hideLoading();
        showToast(err.message, 'error');
    }
});

document.getElementById('btn-reject-vote').addEventListener('click', () => {
    showToast('Vote rejected. Return to Device A and start over.', 'error');
});

// === Ledger Verification Modal ===
document.getElementById('btn-verify-ledger').addEventListener('click', async () => {
    const voteId = document.getElementById('receipt-vote-id').textContent.trim();
    if (!voteId || voteId === '--') return showToast('No vote ID to verify.', 'error');

    // Set Browse Full Ledger link
    document.getElementById('lm-ledger-link').href = `${API_BASE}/ledger`;

    // Pre-fill with loading state
    ['lm-vote-id','lm-cred','lm-receipt','lm-ts','lm-zkp','lm-latest','lm-revote']
        .forEach(id => { document.getElementById(id).textContent = 'Loading...'; });
    document.getElementById('lm-status').textContent = '';
    document.getElementById('ledger-modal').classList.remove('hidden');

    try {
        const res = await fetch(`${API_BASE}/ledger/${encodeURIComponent(voteId)}`);
        if (!res.ok) {
            document.getElementById('lm-status').textContent = '\u274c Not found on ledger';
            document.getElementById('lm-status').style.color = 'var(--danger-color)';
            ['lm-vote-id','lm-cred','lm-receipt','lm-ts','lm-zkp','lm-latest','lm-revote']
                .forEach(id => { document.getElementById(id).textContent = '\u2014'; });
            return;
        }
        const data = await res.json();
        document.getElementById('lm-vote-id').textContent = data.vote_id;
        document.getElementById('lm-cred').textContent = data.credential_hash;
        document.getElementById('lm-receipt').textContent = data.receipt_hash;
        document.getElementById('lm-ts').textContent = new Date(data.timestamp).toLocaleString();
        document.getElementById('lm-zkp').textContent = data.has_zk_proof ? '\u2705 Yes' : '\u274c No';
        document.getElementById('lm-latest').textContent = data.is_latest_for_credential
            ? '\u2705 Yes \u2014 This vote counts'
            : '\u21a9\ufe0f No \u2014 Superseded by a later revote';
        document.getElementById('lm-revote').textContent = data.revote_pointer || '\u2014 (first vote)';
        document.getElementById('lm-status').textContent = '\u2705 Confirmed on ledger';
        document.getElementById('lm-status').style.color = 'var(--success-color)';
    } catch (err) {
        showToast(err.message, 'error');
    }
});

document.getElementById('btn-close-modal').addEventListener('click', () => {
    document.getElementById('ledger-modal').classList.add('hidden');
});
document.getElementById('ledger-modal').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) e.currentTarget.classList.add('hidden');
});

// === Tally Ceremony (Features 8+9) ===
document.getElementById('btn-run-ceremony').addEventListener('click', async () => {
    const sharesSelect = document.getElementById('trustee-shares');
    const shares = sharesSelect.value;
    const btn = document.getElementById('btn-run-ceremony');
    
    btn.disabled = true;
    btn.textContent = 'Running Ceremony...';
    
    const dashboard = document.getElementById('ceremony-dashboard');
    const logBox = document.getElementById('ceremony-log-content');
    const barsContainer = document.getElementById('tally-bars');
    
    // Reset UI
    dashboard.classList.remove('hidden');
    logBox.innerHTML = '';
    barsContainer.innerHTML = '';
    ['tr-total', 'tr-unique', 'tr-fake'].forEach(id => document.getElementById(id).textContent = '...');

    try {
        const res = await fetch(`${API_BASE}/tally/ceremony?shares=${shares}`, { method: 'POST' });
        const data = await res.json();
        
        if (!res.ok) throw new Error(data.detail?.message || 'Ceremony failed');

        // 1. Stream Logs sequentially for demo effect
        for (const logLine of data.ceremony_log || []) {
            const div = document.createElement('div');
            div.textContent = `> ${logLine}`;
            logBox.appendChild(div);
            logBox.scrollTop = logBox.scrollHeight;
            await delay(400); // UI visual delay
        }

        // 2. Populate stats
        document.getElementById('tr-total').textContent = data.total_votes_cast;
        document.getElementById('tr-unique').textContent = data.total_unique_voters;
        document.getElementById('tr-fake').textContent = data.fake_votes_discarded;

        // 3. Render Bar Chart
        if (data.status === 'no_votes') {
            barsContainer.innerHTML = '<p style="color:var(--text-secondary);font-size:0.9rem;">No valid votes to tally yet.</p>';
        } else {
            const tally = data.tally || {};
            const candidates = Object.keys(tally).sort((a,b) => tally[b] - tally[a]);
            const maxVotes = Math.max(1, ...Object.values(tally));

            for (const cand of candidates) {
                const votes = tally[cand];
                const pct = (votes / maxVotes) * 100;
                
                const row = document.createElement('div');
                row.className = 'tally-bar-row';
                row.innerHTML = `
                    <div class="tally-bar-header">
                        <span>${cand}</span>
                        <span>${votes} vote${votes === 1 ? '' : 's'}</span>
                    </div>
                    <div class="tally-bar-track">
                        <div class="tally-bar-fill" style="width: 0%"></div>
                    </div>
                `;
                barsContainer.appendChild(row);
                
                // Animate bar width on next frame
                requestAnimationFrame(() => {
                    requestAnimationFrame(() => {
                        row.querySelector('.tally-bar-fill').style.width = `${pct}%`;
                    });
                });
                await delay(200);
            }
        }
        
    } catch (err) {
        const errorDiv = document.createElement('div');
        errorDiv.textContent = `> ERROR: ${err.message}`;
        errorDiv.style.color = 'var(--danger-color)';
        logBox.appendChild(errorDiv);
    } finally {
        btn.disabled = false;
        btn.textContent = '▶ Run Full Ceremony';
    }
});

// === WebSocket Ledger ===
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${protocol}//${window.location.host}${API_BASE}/ws/ledger`);
    ws.onmessage = (event) => {
        const message = JSON.parse(event.data);
        if (message.event === 'VOTE_CAST') appendLedgerItem(message.data);
    };
    ws.onclose = () => setTimeout(connectWebSocket, 3000);
}

function appendLedgerItem(data) {
    const list = document.getElementById('ledger-list');
    const empty = list.querySelector('.empty-state');
    if (empty) empty.remove();

    const isRevote = data.is_revote === true || data.is_revote === 'true';
    const icon = isRevote ? '↩️' : '🔐';
    const label = isRevote
        ? `Revote #${data.revote_count} — Previous vote superseded`
        : 'Encrypted Ballot Confirmed';

    const item = document.createElement('div');
    item.className = `ledger-item${isRevote ? ' ledger-item-revote' : ''}`;
    item.innerHTML = `
        <div class="ledger-item-header">
            <span>${icon} ${label}</span>
            <span>${new Date(data.timestamp).toLocaleTimeString()}</span>
        </div>
        <div class="ledger-item-hash">${data.vote_id}</div>
        <div class="ledger-item-receipt">Receipt · ${data.receipt_hash}</div>
    `;
    list.insertBefore(item, list.firstChild);
}

// === Init: Check if this is Device B ===
(function init() {
    const params = new URLSearchParams(window.location.search);
    const verifyHash = params.get('verify');
    if (verifyHash) {
        // This browser is acting as Device B
        loadVerificationView(verifyHash);
    }
    connectWebSocket();
})();

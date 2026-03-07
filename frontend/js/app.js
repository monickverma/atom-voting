/**
 * Atom Voting — Frontend Application Logic
 * Dual-Device verification flow: Device A generates QR, Device B verifies before ledger commit.
 */

// === State & Config ===
const API_BASE = '/api/v1';
let Session = {
    isAuthenticated: false,
    voterId: null,
    credentialHash: null,
    currentBallotHash: null,
    pollInterval: null,
};

// Candidate name lookup by code (mirrors backend CODE_MAP)
const CANDIDATE_MAP = { 4427: 'Candidate B', 8391: 'Candidate A', 9102: 'Candidate C' };

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
    Session.credentialHash = 'cred_' + btoa(Session.voterId).substring(0, 16);
    const statusEl = document.getElementById('nav-user-status');
    statusEl.innerHTML = `<span class="status-dot active"></span> ${Session.voterId}`;
    hideLoading();
    showToast('Authenticated via hardware token.', 'info');
    showView('vote');
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
        showQRCode(data.ballot_hash, data.verification_url, code);
    } catch (err) {
        hideLoading();
        showToast(err.message, 'error');
    }
}

// === QR Code Display ===
function showQRCode(ballotHash, verificationUrl, candidateCode) {
    activateStep('step-qr');
    document.getElementById('qr-ballot-hash').textContent = ballotHash;

    // Clear and generate new QR code
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

    showView('qr');
    startPollingForConfirmation(ballotHash);
}

// === Polling: Device A waits for Device B to confirm ===
function startPollingForConfirmation(ballotHash) {
    clearPolling();
    Session.pollInterval = setInterval(async () => {
        try {
            const res = await fetch(`${API_BASE}/ballots/verify/${ballotHash}`);
            if (!res.ok) return;
            const data = await res.json();
            if (data.confirmed) {
                clearPolling();
                showToast('Device B confirmed! Vote is on the ledger.', 'info');
                document.getElementById('receipt-vote-id').textContent = ballotHash;
                document.getElementById('receipt-hash').textContent = 'Confirmed by Device B · ' + new Date().toLocaleTimeString();
                showView('receipt');
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

        // Decode candidate from URL param
        const urlParams = new URLSearchParams(window.location.search);
        const codeParam = parseInt(urlParams.get('code') || '0', 10);
        const candidateName = CANDIDATE_MAP[codeParam] || 'Verify on your code sheet';
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

    const item = document.createElement('div');
    item.className = 'ledger-item';
    item.innerHTML = `
        <div class="ledger-item-header">
            <span>🔐 Encrypted Ballot Confirmed</span>
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

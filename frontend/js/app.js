/**
 * Atom Voting — Frontend Application Logic
 * Pure Vanilla JS orchestrating WebAuthn mocks, WebSockets, and API routing.
 */

// === State & Config ===
const API_BASE = '/api/v1';
let Session = {
    isAuthenticated: false,
    voterId: null,
    credentialHash: null,
};

// === DOM Elements ===
const Views = {
    login: document.getElementById('view-login'),
    vote: document.getElementById('view-vote'),
    receipt: document.getElementById('view-receipt'),
};

const Elements = {
    btnAuth: document.getElementById('btn-authenticate'),
    voteForm: document.getElementById('vote-form'),
    btnCast: document.getElementById('btn-cast'),
    btnChallenge: document.getElementById('btn-challenge'),
    btnVoteAgain: document.getElementById('btn-vote-again'),
    navStatus: document.getElementById('nav-user-status'),
    ledgerList: document.getElementById('ledger-list'),
    loadingOverlay: document.getElementById('loading-overlay'),
    loadingText: document.getElementById('loading-text'),
};

// === UI Navigation ===
function showView(viewName) {
    Object.values(Views).forEach(v => v.classList.remove('active'));
    Views[viewName].classList.add('active');
}

function showLoading(text) {
    Elements.loadingText.textContent = text;
    Elements.loadingOverlay.classList.remove('hidden');
}

function hideLoading() {
    Elements.loadingOverlay.classList.add('hidden');
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.getElementById('toast-container').appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// === Authentication (Mock WebAuthn) ===
Elements.btnAuth.addEventListener('click', async () => {
    showLoading('Waiting for Hardware Token...');
    
    // Simulate FIDO2 WebAuthn dance
    try {
        // 1. In a real app we'd call /auth/login/options and navigator.credentials.get()
        await new Promise(r => setTimeout(r, 1500)); 
        
        Session.isAuthenticated = true;
        Session.voterId = 'voter_' + Math.floor(Math.random() * 10000);
        // Simple mock credential hash
        Session.credentialHash = 'cred_' + btoa(Session.voterId).substring(0,16);

        Elements.navStatus.innerHTML = `<span class="status-dot active"></span> ${Session.voterId}`;
        
        hideLoading();
        showToast('Successfully authenticated via hardware token.', 'info');
        showView('vote');
        
    } catch (err) {
        hideLoading();
        showToast('Authentication failed', 'error');
    }
});

// === Cryptography Stub (For UI Demo) ===
// Real ElGamal would require heavy JS libraries (e.g. big-integer) or WASM.
// To keep the frontend Vanilla & lightweight, we generate the stub JSON structure 
// that the backend expects, representing (m=code, r=random).
function generateCryptographicPayload(code, action) {
    const nonce = 'nonce_' + Math.random().toString(36).substr(2, 9);
    
    // Real math would go here, calculating c1=g^r, c2=g^m * h^r
    return {
        encrypted_ballot: {
            c1: Math.floor(Math.random() * 999999).toString(16), 
            c2: Math.floor(Math.random() * 999999).toString(16), 
            nonce_id: nonce
        },
        zk_proof: {
            // Mock CDS ZK Proof arrays
            proof_data: {
                challenges: ["a1", "b2"],
                responses: ["c3", "d4"]
            },
            is_stub: true // Allow backend to bypass real math checking for this UI demo payload
        },
        credential_hash: Session.credentialHash,
        action: action
    };
}


// === Voting API Submission ===
async function submitBallot(action) {
    const codeInput = document.getElementById('candidate-code');
    const code = parseInt(codeInput.value, 10);
    
    if (isNaN(code) || code <= 0) {
        showToast('Please enter a valid candidate code from your sheet.', 'error');
        return;
    }

    showLoading(action === 'cast' ? 'Encrypting and generating ZK Proof...' : 'Initiating Audit Challenge...');
    
    // Artificial delay to simulate heavy 2048-bit math
    await new Promise(r => setTimeout(r, 800));

    const payload = generateCryptographicPayload(code, action);

    try {
        const response = await fetch(`${API_BASE}/ballots`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const result = await response.json();
        hideLoading();

        if (!response.ok) {
            throw new Error(result.detail?.message || 'Submission failed');
        }

        if (action === 'challenge') {
            const data = result; // ChallengeResponse
            showToast(`Audit Successful! Server decrypted your code as: ${data.candidate_mapping_hint}. Ballot was destroyed.`, 'info');
            codeInput.value = '';
        } else {
            // Cast successful
            document.getElementById('receipt-vote-id').textContent = result.data.vote_id;
            document.getElementById('receipt-hash').textContent = result.data.receipt_hash;
            showView('receipt');
            codeInput.value = '';
        }

    } catch (err) {
        hideLoading();
        showToast(err.message, 'error');
    }
}

Elements.voteForm.addEventListener('submit', (e) => {
    e.preventDefault();
    submitBallot('cast');
});

Elements.btnChallenge.addEventListener('click', () => {
    submitBallot('challenge');
});

Elements.btnVoteAgain.addEventListener('click', () => {
    showView('vote');
});

// === WebSocket Ledger ===
function connectWebSocket() {
    // Determine WS protocol based on HTTP
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}${API_BASE}/ws/ledger`;
    
    const ws = new WebSocket(wsUrl);
    
    ws.onmessage = (event) => {
        const message = JSON.parse(event.data);
        if (message.event === 'VOTE_CAST') {
            appendLedgerItem(message.data);
        }
    };
    
    ws.onclose = () => {
        // Reconnect after 3 seconds
        setTimeout(connectWebSocket, 3000);
    };
}

function appendLedgerItem(data) {
    // Remove empty state if present
    const emptyState = Elements.ledgerList.querySelector('.empty-state');
    if (emptyState) emptyState.remove();

    const timeString = new Date(data.timestamp).toLocaleTimeString();
    
    const item = document.createElement('div');
    item.className = 'ledger-item';
    item.innerHTML = `
        <div class="ledger-item-header">
            <span>New Encrypted Ballot Cast</span>
            <span>${timeString}</span>
        </div>
        <div class="ledger-item-hash">${data.vote_id}</div>
    `;
    
    // Prepend to top
    Elements.ledgerList.insertBefore(item, Elements.ledgerList.firstChild);
}

// === Init ===
connectWebSocket();

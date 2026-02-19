// Autonomous Research Press - Shared Auth Utilities
// localStorage key: 'research_auth' → {api_key, name, email}

function getAuth() {
    try {
        return JSON.parse(localStorage.getItem('research_auth')) || null;
    } catch (e) { return null; }
}

function setAuth(data) {
    localStorage.setItem('research_auth', JSON.stringify(data));
    // Backward compat: existing code reads this key
    localStorage.setItem('research_api_key', data.api_key);
}

function clearAuth() {
    localStorage.removeItem('research_auth');
    localStorage.removeItem('research_api_key');
}

function getApiKey() {
    var auth = getAuth();
    return auth ? auth.api_key : '';
}

function getAuthHeaders() {
    var headers = { 'Content-Type': 'application/json' };
    var key = getApiKey();
    if (key) headers['X-API-Key'] = key;
    return headers;
}

function logout() {
    clearAuth();
    window.location.href = 'login.html';
}

function _escapeHtmlAuth(text) {
    var div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}

// Render auth state into #auth-nav element
function renderAuthState() {
    var auth = getAuth();
    var container = document.getElementById('auth-nav');
    if (!container) return;

    if (auth) {
        container.innerHTML =
            '<span style="font-size:0.8125rem;color:var(--text-secondary);">' + _escapeHtmlAuth(auth.name) + '</span>' +
            '<button onclick="logout()" class="nav-link" style="cursor:pointer;background:none;border:none;font-size:0.8125rem;color:var(--text-secondary);padding:0;font-family:inherit;">Logout</button>';
    } else {
        container.innerHTML =
            '<a href="login.html" class="nav-link">Login</a>';
    }
}

document.addEventListener('DOMContentLoaded', renderAuthState);

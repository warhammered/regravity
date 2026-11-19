(()=>{
  if (window.__agyAccountSwitcherInjected) return;
  window.__agyAccountSwitcherInjected = true;

  let accountsState = { active: '', accounts: [] };
  let filterText = '';
  let statusFilter = 'all'; // 'all', 'ready', 'expired'
  let isSwitching = false;
  let isLaunchingMap = {};
  let isAuthenticating = false;
  let activeModal = null; // null | { type: 'inspect', data: ... } | { type: 'detect', data: ... }

  function isPageOpen() {
    const page = document.getElementById('agy-account-switcher-page');
    return Boolean(page && page.style.display !== 'none');
  }

  function updateNavButtonState() {
    const btn = document.querySelector('[data-testid="account-switcher-button"]');
    if (!btn) return;
    if (isPageOpen()) {
      btn.className = 'agy-button agy-button-custom inline-flex items-center font-medium transition-colors select-none outline-none cursor-pointer disabled:opacity-50 flex-grow w-full justify-start select-none font-normal min-w-0 gap-1.5 px-2 rounded-lg py-1.5 bg-sidebar-muted text-foreground hover:bg-sidebar-muted';
    } else {
      btn.className = 'agy-button agy-button-custom inline-flex items-center font-medium transition-colors select-none outline-none cursor-pointer disabled:opacity-50 flex-grow w-full justify-start select-none font-normal min-w-0 gap-1.5 px-2 rounded-lg py-1.5 bg-transparent text-secondary-foreground hover:bg-sidebar-muted hover:text-foreground';
    }
  }

  function closeAccountSwitcherPage() {
    const page = document.getElementById('agy-account-switcher-page');
    if (page) page.style.display = 'none';
    const split = document.querySelector('[data-testid="aux-pane-split"]');
    if (split && split.children[0] && split.children[0].firstElementChild) {
      split.children[0].firstElementChild.style.display = '';
    }
    updateNavButtonState();
  }

  function showToast(msg, duration = 3500) {
    const existing = document.querySelector('.pg-toast');
    if (existing) existing.remove();
    const toast = document.createElement('div');
    toast.className = 'pg-toast';
    toast.textContent = msg;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), duration);
  }

  function formatRemaining(secs, isReady, hasRt) {
    if (secs > 0) {
      const m = Math.floor(secs / 60);
      const h = Math.floor(m / 60);
      if (h > 0) return `${h}h ${m % 60}m remaining`;
      return `${m}m remaining`;
    }
    if (isReady && hasRt) {
      return 'Valid (Auto-refresh on use)';
    }
    return 'Expired';
  }

  function formatDynamicCountdown(epochSec) {
    if (!epochSec || epochSec <= 0) return 'Ready';
    const now = Math.floor(Date.now() / 1000);
    const diff = epochSec - now;
    if (diff <= 0) return 'Ready';
    const d = Math.floor(diff / 86400);
    const h = Math.floor((diff % 86400) / 3600);
    const m = Math.floor((diff % 3600) / 60);
    const s = diff % 60;
    if (d > 0) return `${d}d ${h}h`;
    if (h > 0) return `${h}h ${m}m ${s}s`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
  }

  function getQuotaStatus(fiveR, weekly, isExp) {
    if (isExp) {
      return { text: 'Session Expired', color: '#f87171' };
    }
    const fiveStr = fiveR?.reset_time_epoch ? formatDynamicCountdown(fiveR.reset_time_epoch) : (fiveR?.resets_in || 'Ready');
    if (fiveR && fiveR.percentage < 100 && fiveStr !== 'Ready') {
      return { text: `5-Hour refresh in ${fiveStr}`, color: '#f59e0b' };
    }
    const weekStr = weekly?.reset_time_epoch ? formatDynamicCountdown(weekly.reset_time_epoch) : (weekly?.resets_in || 'Ready');
    if (weekly && weekly.percentage < 100 && weekStr !== 'Ready') {
      return { text: `Weekly refresh in ${weekStr}`, color: '#60a5fa' };
    }
    return { text: 'Full Quota Ready', color: '#4ade80' };
  }

  function tickCountdowns() {
    const page = document.getElementById('agy-account-switcher-page');
    if (!page || page.style.display === 'none') return;

    const accounts = accountsState.accounts || [];
    for (const a of accounts) {
      const email = a.email;
      const limits = a.limits || {};
      const fiveR = limits.five_hour || {};
      const weekly = limits.weekly || {};
      const isExp = (a.status === 'expired' && email.toLowerCase() !== (accountsState.active || '').toLowerCase());
      if (isExp) continue;

      const el5h = document.getElementById(`pg-5h-reset-${email}`);
      if (el5h && fiveR.reset_time_epoch) {
        const cur = formatDynamicCountdown(fiveR.reset_time_epoch);
        el5h.textContent = `(${cur})`;
      }

      const elWeek = document.getElementById(`pg-week-reset-${email}`);
      if (elWeek && weekly.reset_time_epoch) {
        const cur = formatDynamicCountdown(weekly.reset_time_epoch);
        elWeek.textContent = `(${cur})`;
      }

      const elPill = document.getElementById(`pg-status-pill-${email}`);
      if (elPill) {
        const st = getQuotaStatus(fiveR, weekly, isExp);
        elPill.textContent = st.text;
        elPill.style.color = st.color;
      }
    }
  }

  function esc(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function renderAccountsUI(page) {
    const activeEmail = accountsState.active || '';
    const allAccounts = accountsState.accounts || [];

    const filtered = allAccounts.filter(a => {
      const isExp = (a.status === 'expired' && a.email.toLowerCase() !== activeEmail.toLowerCase());
      if (statusFilter === 'ready' && isExp) return false;
      if (statusFilter === 'expired' && !isExp) return false;
      if (!filterText) return true;
      const q = filterText.toLowerCase();
      return (a.email || '').toLowerCase().includes(q) || (a.name || '').toLowerCase().includes(q);
    });

    const readyCount = allAccounts.filter(a => !(a.status === 'expired' && a.email.toLowerCase() !== activeEmail.toLowerCase())).length;
    const expiredCount = allAccounts.filter(a => (a.status === 'expired' && a.email.toLowerCase() !== activeEmail.toLowerCase())).length;

    page.innerHTML = `
      <style>
        .pg-root { display: flex; flex-direction: column; height: 100%; width: 100%; background: #0d0d0e; color: #f4f4f5; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; overflow: hidden; position: relative; }
        .pg-header { height: 52px; border-bottom: 1px solid rgba(255, 255, 255, 0.08); padding: 0 120px 0 20px; display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; background: #0e0e10; gap: 12px; position: relative; z-index: 10; }
        .pg-header-actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
        .pg-body { max-width: 960px; margin: 0 auto; width: 100%; flex: 1; display: flex; flex-direction: column; padding: 20px 24px; overflow: hidden; min-height: 0; }
        .pg-controls { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 16px; flex-shrink: 0; flex-wrap: wrap; }
        .pg-search-box { position: relative; flex: 1 1 240px; min-width: 200px; }
        .pg-search { width: 100%; background: #141416; color: #f4f4f5; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px; padding: 8px 12px 8px 34px; font-size: 12px; outline: none; }
        .pg-search:focus { border-color: rgba(255, 255, 255, 0.25); background: #18181b; }
        .pg-filters { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
        .pg-filter-btn { padding: 4px 10px; border-radius: 6px; font-size: 11px; background: transparent; color: #a1a1aa; border: 1px solid rgba(255,255,255,0.08); cursor: pointer; transition: all 0.15s; }
        .pg-filter-btn:hover { background: #1e1e22; color: #f4f4f5; }
        .pg-filter-btn.is-active { background: #27272a; color: #f4f4f5; border-color: rgba(255,255,255,0.2); }
        .pg-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; padding-right: 4px; }
        .pg-card { border-radius: 10px; border: 1px solid rgba(255, 255, 255, 0.08); background: #141416; padding: 14px 18px; display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 14px; transition: all 0.15s; }
        .pg-card.is-active { border-color: rgba(34, 197, 94, 0.4); background: #131714; box-shadow: 0 0 20px rgba(34, 197, 94, 0.06); }
        .pg-card:hover:not(.is-active) { border-color: rgba(255, 255, 255, 0.16); background: #17171a; }
        .pg-card-main { display: flex; align-items: center; gap: 14px; min-width: 260px; flex: 1 1 340px; }
        .pg-avatar-box { position: relative; width: 40px; height: 40px; flex-shrink: 0; }
        .pg-avatar { width: 40px; height: 40px; border-radius: 50%; object-fit: cover; border: 1px solid rgba(255,255,255,0.12); display: block; }
        .pg-avatar-fallback { width: 40px; height: 40px; border-radius: 50%; background: #27272a; color: #f4f4f5; font-size: 15px; font-weight: 600; display: flex; align-items: center; justify-content: center; border: 1px solid rgba(255,255,255,0.12); }
        .pg-card-meta { min-width: 0; display: flex; flex-direction: column; gap: 4px; flex: 1; }
        .pg-meta-header { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
        .pg-name { font-size: 13px; font-weight: 500; color: #f4f4f5; text-overflow: ellipsis; overflow: hidden; white-space: nowrap; max-width: 240px; }
        .pg-meta-sub { display: flex; align-items: center; gap: 8px; font-size: 11px; color: #71717a; flex-wrap: wrap; }
        .pg-email { font-family: monospace; color: #8e8e93; }
        .pg-remaining { color: #a1a1aa; }
        .pg-limits-row { display: flex; align-items: center; gap: 16px; margin-top: 4px; flex-wrap: wrap; }
        .pg-limit-item { display: flex; align-items: center; gap: 6px; font-size: 10px; color: #a1a1aa; flex: 1 1 150px; max-width: 240px; min-width: 140px; }
        .pg-limit-label { font-weight: 600; color: #71717a; font-size: 10px; min-width: 38px; }
        .pg-bar-track { flex: 1; height: 5px; background: rgba(255, 255, 255, 0.08); border-radius: 999px; overflow: hidden; }
        .pg-bar-fill { height: 100%; border-radius: 999px; transition: width 0.3s ease; }
        .pg-limit-val { font-family: monospace; font-size: 10px; color: #d4d4d8; }
        .pg-limit-reset { font-size: 10px; color: #71717a; }
        .pg-exp-notice { font-size: 10px; color: #f87171; margin-top: 2px; }
        .pg-card-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; justify-content: flex-end; flex-shrink: 0; }
        .pg-action-icons { display: flex; align-items: center; gap: 4px; }
        .pg-btn { padding: 6px 14px; border-radius: 6px; font-size: 11px; font-weight: 500; cursor: pointer; transition: all 0.15s; border: 1px solid transparent; display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
        .pg-btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .pg-btn-primary { background: #2563eb; color: #ffffff; border-color: #3b82f6; }
        .pg-btn-primary:hover:not(:disabled) { background: #1d4ed8; }
        .pg-btn-zinc { background: #27272a; color: #f4f4f5; border-color: rgba(255, 255, 255, 0.1); }
        .pg-btn-zinc:hover:not(:disabled) { background: #3f3f46; border-color: rgba(255, 255, 255, 0.2); }
        .pg-btn-sec { background: transparent; color: #a1a1aa; border-color: rgba(255, 255, 255, 0.1); }
        .pg-btn-sec:hover:not(:disabled) { background: #27272a; color: #f4f4f5; }
        .pg-btn-danger { background: transparent; color: #f87171; border-color: rgba(239, 68, 68, 0.2); }
        .pg-btn-danger:hover:not(:disabled) { background: rgba(239, 68, 68, 0.12); color: #fca5a5; }
        .pg-btn-icon { width: 28px; height: 28px; padding: 0; display: inline-flex; align-items: center; justify-content: center; border-radius: 6px; background: transparent; color: #a1a1aa; border: 1px solid rgba(255,255,255,0.08); cursor: pointer; }
        .pg-btn-icon:hover { background: #27272a; color: #f4f4f5; }
        .pg-btn-icon-danger:hover { background: rgba(239, 68, 68, 0.15); color: #f87171; border-color: rgba(239, 68, 68, 0.3); }
        .pg-badge { font-size: 10px; padding: 2px 7px; border-radius: 4px; font-family: monospace; font-weight: 500; }
        .pg-badge-active { background: rgba(34, 197, 94, 0.15); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.3); }
        .pg-badge-ready { background: rgba(255, 255, 255, 0.06); color: #a1a1aa; border: 1px solid rgba(255, 255, 255, 0.1); }
        .pg-badge-expired { background: rgba(239, 68, 68, 0.12); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.25); }
        .pg-badge-running { background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); animation: pulse 2s infinite; }
        .pg-footer { padding-top: 14px; border-top: 1px solid rgba(255, 255, 255, 0.08); display: flex; align-items: center; justify-content: space-between; font-size: 11px; color: #71717a; margin-top: 12px; flex-wrap: wrap; gap: 8px; }
        .pg-toast { position: fixed; bottom: 24px; right: 24px; background: #18181b; border: 1px solid rgba(255, 255, 255, 0.15); color: #f4f4f5; padding: 10px 18px; border-radius: 8px; font-size: 12px; z-index: 999999; box-shadow: 0 8px 24px rgba(0,0,0,0.6); }
        .pg-modal-overlay { position: absolute; inset: 0; background: rgba(0, 0, 0, 0.7); backdrop-filter: blur(4px); display: flex; align-items: center; justify-content: center; z-index: 9999; padding: 24px; }
        .pg-modal { background: #141416; border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 12px; width: 100%; max-width: 540px; box-shadow: 0 16px 48px rgba(0,0,0,0.7); overflow: hidden; display: flex; flex-direction: column; max-height: 85vh; }
        .pg-modal-header { padding: 16px 20px; border-bottom: 1px solid rgba(255, 255, 255, 0.08); display: flex; align-items: center; justify-content: space-between; background: #18181b; }
        .pg-modal-body { padding: 20px; overflow-y: auto; flex: 1; display: flex; flex-direction: column; gap: 16px; font-size: 12px; }
        .pg-modal-footer { padding: 14px 20px; border-top: 1px solid rgba(255, 255, 255, 0.08); display: flex; align-items: center; justify-content: flex-end; gap: 8px; background: #18181b; }
        .pg-spec-row { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05); }
        .pg-spec-label { color: #a1a1aa; font-size: 11px; }
        .pg-spec-val { color: #f4f4f5; font-family: monospace; font-size: 11px; }
        .pg-scope-tag { display: inline-block; padding: 2px 6px; border-radius: 4px; background: #1f1f23; border: 1px solid rgba(255,255,255,0.08); font-size: 10px; font-family: monospace; color: #a1a1aa; margin: 2px; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
        .pg-auth-banner { background: #151922; border: 1px solid rgba(59, 130, 246, 0.35); border-radius: 10px; padding: 14px 18px; margin-bottom: 16px; display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-shrink: 0; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4); }
        .pg-spinner { width: 18px; height: 18px; border: 2px solid rgba(59, 130, 246, 0.25); border-top-color: #3b82f6; border-radius: 50%; animation: pg-spin 0.8s linear infinite; flex-shrink: 0; }
        @keyframes pg-spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
      </style>

      <div class="pg-root">
        <!-- Header (Regravity: Connect Account + Smart Detect + Refresh) -->
        <div class="pg-header">
          <div style="display: flex; align-items: center; gap: 8px; font-size: 13px; min-width: 0;">
            <span style="color: #ffffff; font-weight: 700; font-size: 15px; letter-spacing: -0.02em;">Regravity</span>
            <span style="font-size: 10px; padding: 1px 7px; border-radius: 4px; background: #27272a; color: #a1a1aa; font-family: monospace;">${allAccounts.length} accounts</span>
          </div>
          <div class="pg-header-actions">
            ${isAuthenticating ? `
              <button id="pg-btn-cancel-auth" class="pg-btn pg-btn-danger" title="Cancel ongoing Google OAuth sign-in" onclick="window.__pgCancelAddAccount()">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12"/></svg>
                <span>Cancel Connecting</span>
              </button>
            ` : `
              <button id="pg-btn-add" class="pg-btn pg-btn-primary" title="Connect new Google Account via OAuth 2.0" onclick="window.__pgAddAccount()">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
                <span>Connect Account</span>
              </button>
            `}
            <button id="pg-btn-detect" class="pg-btn pg-btn-sec" ${isAuthenticating ? 'disabled' : ''} title="Smart scan for accounts across active sessions and Credential Manager">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
              <span>Smart Detect</span>
            </button>
            <button id="pg-btn-reload" class="pg-btn-icon" ${isAuthenticating ? 'disabled' : ''} title="Refresh accounts">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 2v6h-6M3 12a9 9 0 0 1 15-6.7L21 8M3 22v-6h6M21 12a9 9 0 0 1-15 6.7L3 16"/></svg>
            </button>
          </div>
        </div>

        <!-- Body -->
        <div class="pg-body">
          ${isAuthenticating ? `
            <div class="pg-auth-banner">
              <div style="display: flex; align-items: center; gap: 12px; min-width: 0;">
                <div class="pg-spinner"></div>
                <div style="min-width: 0;">
                  <div style="font-weight: 600; font-size: 13px; color: #f4f4f5; display: flex; align-items: center; gap: 8px;">
                    <span>Waiting for Google Sign-in in browser</span>
                    <span style="font-size: 10px; padding: 1px 7px; border-radius: 4px; background: rgba(59, 130, 246, 0.2); color: #60a5fa; font-weight: 500;">OAuth 2.0</span>
                  </div>
                  <div style="font-size: 11px; color: #a1a1aa; margin-top: 3px;">
                    Complete sign-in in your default browser to connect. You can cancel anytime without timing out Antigravity.
                  </div>
                </div>
              </div>
              <button class="pg-btn pg-btn-danger" onclick="window.__pgCancelAddAccount()" style="padding: 6px 14px; font-weight: 600;">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12"/></svg>
                <span>Cancel</span>
              </button>
            </div>
          ` : ''}

          <div class="pg-controls">
            <div class="pg-search-box">
              <svg style="position: absolute; left: 10px; top: 9px; width: 14px; height: 14px; color: #71717a; pointer-events: none;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
              <input id="pg-search-input" class="pg-search" type="text" placeholder="Filter accounts by name or email... (/)" value="${esc(filterText)}" />
            </div>
            <div class="pg-filters">
              <button class="pg-filter-btn ${statusFilter === 'all' ? 'is-active' : ''}" onclick="window.__pgSetFilter('all')">All (${allAccounts.length})</button>
              <button class="pg-filter-btn ${statusFilter === 'ready' ? 'is-active' : ''}" onclick="window.__pgSetFilter('ready')">Ready (${readyCount})</button>
              <button class="pg-filter-btn ${statusFilter === 'expired' ? 'is-active' : ''}" onclick="window.__pgSetFilter('expired')">Expired (${expiredCount})</button>
            </div>
          </div>

          <div class="pg-list">
            ${filtered.length === 0 ? `
              <div style="text-align: center; padding: 48px 0; color: #71717a; font-size: 12px; border: 1px dashed rgba(255,255,255,0.08); border-radius: 8px;">
                No accounts match the current filter. Click "Connect Account" to authenticate a new Google account.
              </div>
            ` : filtered.map(a => {
              const isActive = (a.email.toLowerCase() === activeEmail.toLowerCase());
              const isExp = (a.status === 'expired' && !isActive);
              const hasRt = Boolean(a.status !== 'no_token');
              const isLaunching = Boolean(isLaunchingMap[a.email]);
              const isRunning = Boolean(a.is_running);
              const remainingText = formatRemaining(a.expires_in_seconds, a.status === 'ready' || isActive, hasRt);
              const limits = a.limits || {};
              const fiveR = limits.five_hour || { percentage: isExp ? 0 : 100, resets_in: isExp ? 'Expired' : 'Ready' };
              const weekly = limits.weekly || { percentage: isExp ? 0 : 100, resets_in: isExp ? 'Expired' : 'Ready' };
              const quotaStatus = getQuotaStatus(fiveR, weekly, isExp);

              return `
                <div class="pg-card ${isActive ? 'is-active' : ''}">
                  <!-- Left side: Avatar + User Info + Limit Bars -->
                  <div class="pg-card-main">
                    <div class="pg-avatar-box">
                      ${a.picture ? `
                        <img src="${esc(a.picture)}" class="pg-avatar" alt="" onerror="this.style.display='none'; if (this.nextElementSibling) this.nextElementSibling.style.display='flex';" />
                      ` : ''}
                      <div class="pg-avatar-fallback" style="${a.picture ? 'display:none;' : ''}">${esc((a.name || a.email)[0].toUpperCase())}</div>
                    </div>
                    <div class="pg-card-meta">
                      <!-- Row 1: Name and Badges -->
                      <div class="pg-meta-header">
                        <span class="pg-name" title="${esc(a.name || a.email)}">${esc(a.name || a.email)}</span>
                        ${isActive ? '<span class="pg-badge pg-badge-active">Active</span>' : ''}
                        ${isRunning ? `<span class="pg-badge pg-badge-running">Running (PID ${a.pid})</span>` : ''}
                        ${isExp ? '<span class="pg-badge pg-badge-expired">Session Expired</span>' : (!isActive ? '<span class="pg-badge pg-badge-ready">Ready</span>' : '')}
                      </div>

                      <!-- Row 2: Email and Live Quota Reset Status -->
                      <div class="pg-meta-sub">
                        <span class="pg-email">${esc(a.email)}</span>
                        ${!isExp ? `
                          <span>•</span>
                          <span class="pg-remaining" id="pg-status-pill-${esc(a.email)}" style="color: ${quotaStatus.color}; font-weight: 500;" title="Live Antigravity Quota Status">${quotaStatus.text}</span>
                        ` : ''}
                      </div>

                      <!-- Row 3: Dual Rolling Limits (5-Hour and Weekly) -->
                      ${!isExp ? `
                        <div class="pg-limits-row">
                          <!-- 5-Hour Limit Bar -->
                          <div class="pg-limit-item" title="5-Hour Rolling Limit: ${fiveR.percentage}% (${fiveR.resets_in})">
                            <span class="pg-limit-label">5-Hour</span>
                            <div class="pg-bar-track">
                              <div class="pg-bar-fill" style="width: ${Math.min(100, Math.max(0, fiveR.percentage))}%; background: ${fiveR.percentage > 20 ? '#3b82f6' : '#f59e0b'};"></div>
                            </div>
                            <span class="pg-limit-val" id="pg-5h-val-${esc(a.email)}">${fiveR.percentage}%</span>
                            <span class="pg-limit-reset" id="pg-5h-reset-${esc(a.email)}">(${fiveR.resets_in})</span>
                          </div>

                          <!-- Weekly Limit Bar -->
                          <div class="pg-limit-item" title="Weekly Rolling Limit: ${weekly.percentage}% (${weekly.resets_in})">
                            <span class="pg-limit-label">Weekly</span>
                            <div class="pg-bar-track">
                              <div class="pg-bar-fill" style="width: ${Math.min(100, Math.max(0, weekly.percentage))}%; background: #10b981;"></div>
                            </div>
                            <span class="pg-limit-val" id="pg-week-val-${esc(a.email)}">${weekly.percentage}%</span>
                            <span class="pg-limit-reset" id="pg-week-reset-${esc(a.email)}">(${weekly.resets_in})</span>
                          </div>
                        </div>
                      ` : `
                        <div class="pg-exp-notice">
                          Session token expired • Re-authenticate to restore full quota
                        </div>
                      `}
                    </div>
                  </div>

                  <!-- Right side: Actions -->
                  <div class="pg-card-actions">
                    ${!isActive && !isExp ? `
                      <button class="pg-btn pg-btn-zinc" ${isSwitching ? 'disabled' : ''} onclick="window.__pgSwitch('${esc(a.email)}')">
                        ${isSwitching ? 'Switching...' : 'Switch'}
                      </button>
                      <button class="pg-btn pg-btn-sec" ${isLaunching ? 'disabled' : ''} onclick="window.__pgLaunch('${esc(a.email)}')">
                        ${isLaunching ? 'Launching...' : 'Launch Window'}
                      </button>
                    ` : (isExp ? `
                      <button class="pg-btn pg-btn-primary" onclick="window.__pgReauth('${esc(a.email)}')">Re-authenticate</button>
                    ` : '')}

                    <!-- Management Icons -->
                    <div class="pg-action-icons">
                      <button class="pg-btn-icon" title="Detailed View" onclick="window.__pgInspect('${esc(a.email)}')">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
                      </button>
                      <button class="pg-btn-icon" title="Reset Profile State" onclick="window.__pgReset('${esc(a.email)}')">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>
                      </button>
                      ${!isActive ? `
                        <button class="pg-btn-icon pg-btn-icon-danger" title="Remove Account" onclick="window.__pgRemove('${esc(a.email)}')">
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2M10 11v6M14 11v6"/></svg>
                        </button>
                      ` : ''}
                    </div>
                  </div>
                </div>
              `;
            }).join('')}
          </div>

          <!-- Footer -->
          <div class="pg-footer" style="justify-content: flex-end;">
            <span>Version 0.1.0</span>
          </div>
        </div>

        <!-- Modal rendering -->
        ${renderModalHTML()}
      </div>
    `;

    // Bind event handlers
    const searchInput = page.querySelector('#pg-search-input');
    if (searchInput) {
      searchInput.oninput = (e) => {
        filterText = e.target.value;
        renderAccountsUI(page);
        const nextInput = page.querySelector('#pg-search-input');
        if (nextInput) {
          nextInput.focus();
          nextInput.selectionStart = nextInput.selectionEnd = nextInput.value.length;
        }
      };
    }

    const addBtn = page.querySelector('#pg-btn-add');
    if (addBtn) addBtn.onclick = () => window.__pgAddAccount();

    const cancelAuthBtn = page.querySelector('#pg-btn-cancel-auth');
    if (cancelAuthBtn) cancelAuthBtn.onclick = () => window.__pgCancelAddAccount();

    const detectBtn = page.querySelector('#pg-btn-detect');
    if (detectBtn) detectBtn.onclick = () => window.__pgDetectAccounts();

    const reloadBtn = page.querySelector('#pg-btn-reload');
    if (reloadBtn) {
      reloadBtn.onclick = () => {
        showToast('Refreshing live quota from Google Cloud...');
        loadAccounts(page, true);
      };
    }
  }

  function renderModalHTML() {
    if (!activeModal) return '';

    if (activeModal.type === 'inspect') {
      const d = activeModal.data;
      const tok = d.token || {};
      const auth = d.auth || {};
      const isExp = (d.status === 'expired' && !d.is_active);
      const limits = d.limits || {};
      const fiveR = limits.five_hour || { percentage: isExp ? 0 : 100, resets_in: isExp ? 'Expired' : 'Ready' };
      const weekly = limits.weekly || { percentage: isExp ? 0 : 100, resets_in: isExp ? 'Expired' : 'Ready' };

      return `
        <div class="pg-modal-overlay" onclick="if (event.target === this) window.__pgCloseModal();">
          <div class="pg-modal">
            <div class="pg-modal-header">
              <div style="display: flex; align-items: center; gap: 10px;">
                ${d.picture ? `<img src="${esc(d.picture)}" class="pg-avatar" style="width: 26px; height: 26px;" onerror="this.style.display='none';" />` : ''}
                <span style="font-weight: 600; font-size: 13px;">Detailed View</span>
              </div>
              <button class="pg-btn-icon" onclick="window.__pgCloseModal()">✕</button>
            </div>
            <div class="pg-modal-body">
              <!-- Account Banner -->
              <div style="background: #18181b; padding: 12px 14px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.06); display: flex; align-items: center; justify-content: space-between;">
                <div>
                  <div style="font-size: 13px; font-weight: 600; color: #f4f4f5;">${esc(d.name || d.email)}</div>
                  <div style="font-size: 11px; font-family: monospace; color: #71717a; margin-top: 2px;">${esc(d.email)}</div>
                </div>
                <div style="display: flex; gap: 6px; align-items: center;">
                  <span class="pg-badge ${d.is_active ? 'pg-badge-active' : (d.status === 'ready' ? 'pg-badge-ready' : 'pg-badge-expired')}">
                    ${d.is_active ? 'Active' : (d.status === 'ready' ? 'Ready' : 'Session Expired')}
                  </span>
                  <span class="pg-badge pg-badge-ready">${esc(d.tier || 'Google Cloud')}</span>
                </div>
              </div>

              <!-- Quota & Rolling Limits -->
              <div>
                <div style="font-size: 11px; font-weight: 600; color: #71717a; text-transform: uppercase; margin-bottom: 8px;">Quota &amp; Rolling Limits</div>
                <div style="display: flex; flex-direction: column; gap: 10px;">
                  <!-- 5-Hour Limit -->
                  <div style="background: #18181b; border: 1px solid rgba(255,255,255,0.06); padding: 10px 12px; border-radius: 6px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                      <span class="pg-spec-label">5-Hour Rolling Request Limit</span>
                      <span class="pg-spec-val" style="color: ${fiveR.percentage > 20 ? '#60a5fa' : '#f59e0b'};">${fiveR.percentage}%</span>
                    </div>
                    <div style="height: 6px; background: rgba(255,255,255,0.08); border-radius: 999px; overflow: hidden; margin-bottom: 6px;">
                      <div style="height: 100%; width: ${Math.min(100, Math.max(0, fiveR.percentage))}%; background: ${fiveR.percentage > 20 ? '#3b82f6' : '#f59e0b'}; border-radius: 999px;"></div>
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 10px; color: #71717a;">
                      <span>Status: ${isExp ? 'Expired' : 'Healthy'}</span>
                      <span>Resets in: ${fiveR.resets_in}</span>
                    </div>
                  </div>

                  <!-- Weekly Limit -->
                  <div style="background: #18181b; border: 1px solid rgba(255,255,255,0.06); padding: 10px 12px; border-radius: 6px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                      <span class="pg-spec-label">Weekly Rolling Quota</span>
                      <span class="pg-spec-val" style="color: #4ade80;">${weekly.percentage}%</span>
                    </div>
                    <div style="height: 6px; background: rgba(255,255,255,0.08); border-radius: 999px; overflow: hidden; margin-bottom: 6px;">
                      <div style="height: 100%; width: ${Math.min(100, Math.max(0, weekly.percentage))}%; background: #10b981; border-radius: 999px;"></div>
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 10px; color: #71717a;">
                      <span>Status: ${isExp ? 'Expired' : 'Healthy'}</span>
                      <span>Resets in: ${weekly.resets_in}</span>
                    </div>
                  </div>

                  <!-- Active Model Breakdown (Gemini 2.5 Pro / Flash & 3P Models) -->
                  ${limits.models_breakdown && limits.models_breakdown.length > 0 ? `
                    <div style="background: #18181b; border: 1px solid rgba(255,255,255,0.06); padding: 10px 12px; border-radius: 6px;">
                      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span class="pg-spec-label">Individual Model Rolling Limits</span>
                        <span style="font-size: 10px; color: #71717a;">Google Cloud Code PA</span>
                      </div>
                      <div style="display: flex; flex-direction: column; gap: 8px; max-height: 140px; overflow-y: auto; padding-right: 4px;">
                        ${limits.models_breakdown.map(m => `
                          <div>
                            <div style="display: flex; justify-content: space-between; font-size: 11px; margin-bottom: 4px;">
                              <span style="font-family: monospace; color: #d4d4d8;">${esc(m.modelId)}</span>
                              <div style="display: flex; gap: 6px;">
                                <span style="font-weight: 600; color: ${m.percentage > 20 ? '#4ade80' : '#f59e0b'};">${m.percentage}%</span>
                                <span style="color: #71717a; font-size: 10px;">(${esc(m.resets_in)})</span>
                              </div>
                            </div>
                            <div style="height: 4px; background: rgba(255,255,255,0.06); border-radius: 999px; overflow: hidden;">
                              <div style="height: 100%; width: ${Math.min(100, Math.max(0, m.percentage))}%; background: ${m.percentage > 20 ? '#10b981' : '#f59e0b'};"></div>
                            </div>
                          </div>
                        `).join('')}
                      </div>
                    </div>
                  ` : ''}
                </div>
              </div>

              <!-- Authentication & Session Details -->
              <div>
                <div style="font-size: 11px; font-weight: 600; color: #71717a; text-transform: uppercase; margin-bottom: 8px;">Authentication &amp; Session</div>
                <div style="background: #18181b; border: 1px solid rgba(255,255,255,0.06); padding: 8px 14px; border-radius: 6px;">
                  <div class="pg-spec-row"><span class="pg-spec-label">Authentication Method</span><span class="pg-spec-val">${esc(auth.method || 'Google OAuth 2.0 (Consumer)')}</span></div>
                  <div class="pg-spec-row"><span class="pg-spec-label">Token Status</span><span class="pg-spec-val" style="color: ${d.status === 'ready' || d.is_active ? '#4ade80' : '#f87171'};">${d.is_active ? 'Active Session (Hot-swapped)' : (d.status === 'ready' ? 'Ready' : 'Expired')}</span></div>
                  <div class="pg-spec-row"><span class="pg-spec-label">Access Token Expiry</span><span class="pg-spec-val">${esc(tok.expires_in_seconds ? formatRemaining(tok.expires_in_seconds, true, tok.has_refresh_token) : (d.token_expires_in || 'Auto-refreshed'))}</span></div>
                  <div class="pg-spec-row"><span class="pg-spec-label">Refresh Token Stored</span><span class="pg-spec-val">${tok.has_refresh_token ? 'Yes (Local DPAPI Storage)' : 'No'}</span></div>
                  <div class="pg-spec-row"><span class="pg-spec-label">Active Sandbox Window</span><span class="pg-spec-val">${d.is_running ? 'Running (PID ' + d.pid + ')' : 'None'}</span></div>
                </div>
              </div>

              <!-- Scopes -->
              <div>
                <div style="font-size: 11px; font-weight: 600; color: #71717a; text-transform: uppercase; margin-bottom: 6px;">OAuth Scopes</div>
                <div>
                  <span class="pg-scope-tag">userinfo.email</span>
                  <span class="pg-scope-tag">openid</span>
                  <span class="pg-scope-tag">cloud-platform</span>
                  <span class="pg-scope-tag">userinfo.profile</span>
                </div>
              </div>

              ${d.status === 'expired' && !d.is_active ? `
                <div style="background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.25); border-radius: 8px; padding: 12px; color: #f87171; font-size: 11px;">
                  <strong>Session Expired:</strong> ${esc(d.error || 'The refresh token for this account was revoked or expired. Please re-authenticate.')}
                </div>
              ` : ''}
            </div>
            <div class="pg-modal-footer">
              ${d.status === 'expired' && !d.is_active ? `
                <button class="pg-btn pg-btn-primary" onclick="window.__pgCloseModal(); window.__pgReauth('${esc(d.email)}')">Re-authenticate</button>
              ` : `
                ${!d.is_active ? `
                  <button class="pg-btn pg-btn-zinc" onclick="window.__pgCloseModal(); window.__pgSwitch('${esc(d.email)}')">Switch to This Account</button>
                  <button class="pg-btn pg-btn-sec" onclick="window.__pgCloseModal(); window.__pgLaunch('${esc(d.email)}')">Launch Parallel Window</button>
                ` : ''}
              `}
              <button class="pg-btn pg-btn-sec" onclick="window.__pgCloseModal()">Close</button>
            </div>
          </div>
        </div>
      `;
    }

    if (activeModal.type === 'detect') {
      const detected = activeModal.data.detected || [];
      return `
        <div class="pg-modal-overlay" onclick="if (event.target === this) window.__pgCloseModal();">
          <div class="pg-modal">
            <div class="pg-modal-header">
              <span style="font-weight: 600; font-size: 13px;">Smart Detect Accounts</span>
              <button class="pg-btn-icon" onclick="window.__pgCloseModal()">✕</button>
            </div>
            <div class="pg-modal-body">
              <p style="color: #a1a1aa; font-size: 12px; margin: 0;">
                Scanned local sessions and Windows Credential Manager. Found <strong>${detected.length}</strong> candidate account(s):
              </p>
              <div style="display: flex; flex-direction: column; gap: 8px;">
                ${detected.length === 0 ? `
                  <div style="text-align: center; padding: 24px 0; color: #71717a;">No unmanaged accounts detected.</div>
                ` : detected.map(d => `
                  <div class="pg-card" style="padding: 10px 14px;">
                    <div>
                      <div style="font-size: 12px; font-weight: 500; color: #f4f4f5;">${esc(d.email)}</div>
                      <div style="font-size: 10px; color: #71717a;">Source: ${esc(d.source)} • ${d.has_refresh_token ? 'Has Refresh Token' : 'Access Token Only'}</div>
                    </div>
                    <button class="pg-btn pg-btn-primary" onclick="window.__pgCloseModal(); window.__pgReauth('${esc(d.email)}')">Import / Connect</button>
                  </div>
                `).join('')}
              </div>
            </div>
            <div class="pg-modal-footer">
              <button class="pg-btn pg-btn-sec" onclick="window.__pgCloseModal()">Done</button>
            </div>
          </div>
        </div>
      `;
    }

    return '';
  }

  let isFetchingAccounts = false;
  async function loadAccounts(page, force = false, silent = false) {
    if (!window.paragravityNative || !window.paragravityNative.listAccounts) return;
    if (isFetchingAccounts) return;
    isFetchingAccounts = true;
    try {
      const res = await window.paragravityNative.listAccounts(force);
      if (res && res.accounts) {
        accountsState = res;
        const searchInput = document.querySelector('#pg-search-input');
        const isSearching = searchInput && document.activeElement === searchInput;
        if (!silent || !isSearching) {
          renderAccountsUI(page);
        } else {
          tickCountdowns();
        }
      }
    } catch (err) {
      console.error('Failed to load accounts:', err);
    } finally {
      isFetchingAccounts = false;
    }
  }

  window.__pgSetFilter = (f) => {
    statusFilter = f;
    const page = document.getElementById('agy-account-switcher-page');
    if (page) renderAccountsUI(page);
  };

  window.__pgCloseModal = () => {
    activeModal = null;
    const page = document.getElementById('agy-account-switcher-page');
    if (page) renderAccountsUI(page);
  };

  window.__pgSwitch = async (email) => {
    if (isSwitching) return;
    isSwitching = true;
    const page = document.getElementById('agy-account-switcher-page');
    if (page) renderAccountsUI(page);

    showToast('Switching active session to ' + email + '...');
    try {
      const res = await window.paragravityNative.switchAccount(email);
      if (res && res.success) {
        setTimeout(() => window.location.reload(), 300);
      } else {
        alert('Switch failed: ' + (res?.error || 'Unknown error'));
        isSwitching = false;
        if (page) renderAccountsUI(page);
      }
    } catch (err) {
      alert('Switch error: ' + err.message);
      isSwitching = false;
      if (page) renderAccountsUI(page);
    }
  };

  window.__pgLaunch = async (email) => {
    if (isLaunchingMap[email]) return;
    isLaunchingMap[email] = true;
    const page = document.getElementById('agy-account-switcher-page');
    if (page) renderAccountsUI(page);

    showToast('Opening independent Antigravity window for ' + email + '...');
    try {
      const res = await window.paragravityNative.launchAccount(email);
      isLaunchingMap[email] = false;
      if (page) renderAccountsUI(page);
      if (res && res.success) {
        showToast('✓ Window opened successfully (PID ' + res.pid + ')');
        loadAccounts(page);
      } else {
        alert('Launch failed: ' + (res?.error || 'Unknown error'));
      }
    } catch (err) {
      isLaunchingMap[email] = false;
      if (page) renderAccountsUI(page);
      alert('Launch error: ' + err.message);
    }
  };

  window.__pgCancelAddAccount = async () => {
    if (!isAuthenticating) return;
    isAuthenticating = false;
    const page = document.getElementById('agy-account-switcher-page');
    if (page) renderAccountsUI(page);

    showToast('Sign-in cancelled.');
    try {
      fetch('http://127.0.0.1:50000/cancel', { mode: 'no-cors' }).catch(() => {});
      if (window.paragravityNative && window.paragravityNative.cancelAddAccount) {
        await window.paragravityNative.cancelAddAccount();
      }
    } catch (e) {
      console.warn('Cancel add account:', e);
    }
  };

  window.__pgAddAccount = async () => {
    if (isAuthenticating) return;
    isAuthenticating = true;
    const page = document.getElementById('agy-account-switcher-page');
    if (page) renderAccountsUI(page);

    showToast('Opening official Google OAuth sign-in window in default browser...');
    try {
      const res = await window.paragravityNative.addAccount();
      if (!isAuthenticating) return;
      isAuthenticating = false;
      if (page) renderAccountsUI(page);
      if (res && res.success) {
        showToast('✓ Successfully connected ' + res.email);
        loadAccounts(page);
      } else if (res && res.cancelled) {
        showToast('Sign-in cancelled.');
      } else {
        alert('Authentication failed: ' + (res?.error || 'Unknown error'));
      }
    } catch (err) {
      if (!isAuthenticating) return;
      isAuthenticating = false;
      if (page) renderAccountsUI(page);
      alert('Authentication error: ' + err.message);
    }
  };

  window.__pgReauth = async (email) => {
    if (isAuthenticating) return;
    isAuthenticating = true;
    const page = document.getElementById('agy-account-switcher-page');
    if (page) renderAccountsUI(page);

    showToast('Re-authenticating ' + email + ' via official Google OAuth...');
    try {
      const res = await window.paragravityNative.addAccount(email);
      if (!isAuthenticating) return;
      isAuthenticating = false;
      if (page) renderAccountsUI(page);
      if (res && res.success) {
        showToast('✓ Successfully refreshed credentials for ' + email);
        if (page) loadAccounts(page);
      } else if (res && res.cancelled) {
        showToast('Re-authentication cancelled.');
      } else {
        alert('Re-authentication failed: ' + (res?.error || 'Unknown error'));
      }
    } catch (err) {
      if (!isAuthenticating) return;
      isAuthenticating = false;
      if (page) renderAccountsUI(page);
      alert('Re-auth error: ' + err.message);
    }
  };

  window.__pgInspect = async (email) => {
    const page = document.getElementById('agy-account-switcher-page');
    try {
      const res = await window.paragravityNative.inspectAccount(email);
      if (res) {
        activeModal = { type: 'inspect', data: res };
        if (page) renderAccountsUI(page);
      }
    } catch (err) {
      alert('Detailed view error: ' + err.message);
    }
  };

  window.__pgDetectAccounts = async () => {
    const page = document.getElementById('agy-account-switcher-page');
    showToast('Scanning active sessions & Credential Manager...');
    try {
      const res = await window.paragravityNative.detectAccounts();
      if (res) {
        activeModal = { type: 'detect', data: res };
        if (page) renderAccountsUI(page);
      }
    } catch (err) {
      alert('Detection error: ' + err.message);
    }
  };

  window.__pgReset = async (email) => {
    if (!confirm('Reset local state cache for ' + email + '? (OAuth credentials will be preserved)')) return;
    const page = document.getElementById('agy-account-switcher-page');
    try {
      const res = await window.paragravityNative.resetProfile(email);
      if (res && res.success) {
        showToast('✓ Reset profile cache for ' + email);
        loadAccounts(page);
      } else {
        alert('Reset failed: ' + (res?.error || 'Unknown error'));
      }
    } catch (err) {
      alert('Reset error: ' + err.message);
    }
  };

  window.__pgRemove = async (email) => {
    if (!confirm('Are you sure you want to remove account ' + email + '?')) return;
    const page = document.getElementById('agy-account-switcher-page');
    try {
      const res = await window.paragravityNative.removeAccount(email);
      if (res && res.success) {
        showToast('✓ Removed account ' + email);
        loadAccounts(page);
      } else {
        alert('Remove failed: ' + (res?.error || 'Unknown error'));
      }
    } catch (err) {
      alert('Remove error: ' + err.message);
    }
  };

  function openAccountSwitcherPage() {
    const split = document.querySelector('[data-testid="aux-pane-split"]');
    if (!split || !split.children[0]) {
      console.warn('aux-pane-split not found yet');
      return;
    }
    const container = split.children[0];
    if (container.firstElementChild) {
      container.firstElementChild.style.display = 'none';
    }

    let page = document.getElementById('agy-account-switcher-page');
    if (!page) {
      page = document.createElement('div');
      page.id = 'agy-account-switcher-page';
      page.style.position = 'absolute';
      page.style.inset = '0';
      page.style.zIndex = '50';
      page.style.background = '#0d0d0e';
      page.style.display = 'flex';
      page.style.flexDirection = 'column';
      container.appendChild(page);
    } else {
      page.style.display = 'flex';
    }

    updateNavButtonState();
    loadAccounts(page);
  }
  window.__pgOpen = openAccountSwitcherPage;

  function ensureButton() {
    const customizationsLink = document.querySelector('a[href="/customizations"], a[href="/automations"]');
    const newConvoBtn = document.querySelector('[data-testid="new-conversation-button"]');
    const nav = document.querySelector('[data-testid="sidebar-navigation-items"]') ||
                (customizationsLink ? customizationsLink.parentElement : null) ||
                (newConvoBtn ? newConvoBtn.parentElement : null);
    if (!nav) return;
    let btn = nav.querySelector('[data-testid="account-switcher-button"]');
    const buttonTitle = 'Account Manager (Regravity)';
    const buttonHtml = '<span class="shrink-0 flex items-center"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 -960 960 960" fill="currentColor"><path d="M40-160v-112q0-34 17.5-62.5T106-378q62-31 126-46.5T360-440q66 0 130 15.5T614-378q31 15 48.5 43.5T680-272v112H40Zm720 0v-120q0-44-24.5-84.5T666-434q51 6 96 20.5t84 37.5q19 11 26.5 24.5T880-320v160H760ZM360-480q-66 0-113-47t-47-113q0-66 47-113t113-47q66 0 113 47t47 113q0 66-47 113t-113 47Zm400-160q0 66-47 113t-113 47q-9 0-20-1.5t-20-4.5q24-32 37-69.5t13-84.5q0-47-13-84.5T560-709q9-3 20-4.5t20-1.5q66 0 113 47t47 113Z"></path></svg></span><span class="truncate">Account Manager (Regravity)</span>';

    if (!btn) {
      btn = document.createElement('button');
      btn.type = 'button';
      btn.setAttribute('data-testid', 'account-switcher-button');
      btn.className = 'agy-button agy-button-custom inline-flex items-center font-medium transition-colors select-none outline-none cursor-pointer disabled:opacity-50 flex-grow w-full justify-start select-none font-normal min-w-0 gap-1.5 px-2 rounded-lg py-1.5 bg-transparent text-secondary-foreground hover:bg-sidebar-muted hover:text-foreground';
      btn.title = buttonTitle;
      btn.innerHTML = buttonHtml;
      nav.appendChild(btn);
    } else {
      if (btn.title !== buttonTitle) {
        btn.title = buttonTitle;
        btn.innerHTML = buttonHtml;
      }
    }

    // Always organize button placement to be below Automations & Customizations at the lowest
    if (nav.lastElementChild !== btn) {
      nav.appendChild(btn);
    }
    btn.onclick = (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (isPageOpen()) {
        closeAccountSwitcherPage();
      } else {
        openAccountSwitcherPage();
      }
    };
    updateNavButtonState();
  }

  document.addEventListener('click', (e) => {
    const target = e.target;
    if (!target) return;
    const navBtn = target.closest('[data-testid="account-switcher-button"]');
    if (navBtn) return;
    const otherNav = target.closest('[data-testid="new-conversation-button"], [data-testid="automations-button"], a[href="/customizations"], a[href^="/c/"], [data-testid*="conversation"], [data-testid*="project"]');
    if (otherNav && isPageOpen()) {
      closeAccountSwitcherPage();
    }
  }, true);

  function start() {
    const root = document.documentElement || document.body || document;
    const observer = new MutationObserver(() => {
      ensureButton();
    });
    if (root) {
      try {
        observer.observe(root, { childList: true, subtree: true });
      } catch (e) {
        console.error('Account switcher observer error:', e);
      }
    }
    ensureButton();
    setInterval(ensureButton, 1000);
    setInterval(tickCountdowns, 1000);

    // 15-second background auto-polling for live quotas while tab is open
    setInterval(() => {
      if (isPageOpen() && !isSwitching && !isAuthenticating && !activeModal) {
        const page = document.getElementById('agy-account-switcher-page');
        if (page) loadAccounts(page, false, true);
      }
    }, 15000);

    // Listen to cross-window conversation sync events from Electron
    if (window.paragravityNative && window.paragravityNative.onConversationsUpdated) {
      window.paragravityNative.onConversationsUpdated(() => {
        console.log('[Regravity] Cross-window conversations updated');
        window.dispatchEvent(new CustomEvent('paragravity:conversations-changed'));
      });
    }

    // IPC triggers for opening Regravity UI and Modals
    if (window.paragravityNative && window.paragravityNative.onToggleUI) {
      window.paragravityNative.onToggleUI(() => {
        if (isPageOpen()) {
          closeAccountSwitcherPage();
        } else {
          openAccountSwitcherPage();
        }
      });
    }
    if (window.paragravityNative && window.paragravityNative.onOpenModal) {
      window.paragravityNative.onOpenModal((type) => {
        if (!isPageOpen()) openAccountSwitcherPage();
        setTimeout(() => {
          if (type === 'detect') {
            window.__pgDetectAccounts();
          } else if (type && type.startsWith('inspect:')) {
            window.__pgInspect(type.split(':')[1]);
          }
        }, 150);
      });
    }

    // Keyboard shortcut (Alt+A or F9) to toggle Regravity Account Manager
    window.addEventListener('keydown', (e) => {
      if ((e.altKey && (e.key === 'a' || e.key === 'A')) || e.key === 'F9') {
        e.preventDefault();
        e.stopPropagation();
        if (isPageOpen()) {
          closeAccountSwitcherPage();
        } else {
          openAccountSwitcherPage();
        }
      }
    }, true);

    // Auto-dismiss post-onboarding terms modal if ever present
    setInterval(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const continueBtn = btns.find(b => b.textContent.trim() === 'Continue');
      if (continueBtn) {
        const parent = continueBtn.closest('div');
        if (parent && parent.innerText && parent.innerText.includes('One last thing before getting started')) {
          continueBtn.click();
        }
      }
    }, 500);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();

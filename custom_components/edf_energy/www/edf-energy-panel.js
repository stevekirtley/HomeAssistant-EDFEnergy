(function () {
  'use strict';

  // The consumption card lives in its own file so the panel does not carry a charting
  // library's worth of code for a tab most people never open.
  (function () {
    if (customElements.get('edf-energy-consumption-card')) return;
    // Carry this file's own ?v= across to the card. The backend hashes both files into
    // that value, so whenever either changes the card is fetched afresh rather than
    // served out of the browser's cache against an unchanged url.
    const version = (document.currentScript && document.currentScript.src.split('?')[1]) || '';
    const s = document.createElement('script');
    s.src = '/edf_energy/edf-energy-consumption-card.js' + (version ? '?' + version : '');
    document.head.appendChild(s);
  })();

  // ── Helpers ──────────────────────────────────────────────────────────────────

  function localDateKey(date) {
    const d = new Date(date);
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  }

  // Today if there is anything to show for it, otherwise the most recent day that has
  // already happened. Only if every date is in the future - a fresh install whose first
  // data is a booking - does it fall back to the earliest of those.
  function defaultDateKey(dates) {
    if (!dates.length) return null;
    const today = localDateKey(new Date());
    if (dates.includes(today)) return today;
    const past = dates.filter(k => k < today);        // dates are newest first
    return past.length ? past[0] : dates[dates.length - 1];
  }

  function isFutureDateKey(key) {
    return !!key && key > localDateKey(new Date());
  }

  function formatDateLabel(key) {
    const [y, m, d] = key.split('-').map(Number);
    return new Date(y, m-1, d).toLocaleDateString(undefined, {
      weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
    });
  }

  function formatTime(date) {
    return new Date(date).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: false });
  }

  function formatDuration(start, end) {
    const mins = Math.round((new Date(end) - new Date(start)) / 60000);
    const h = Math.floor(mins / 60), m = mins % 60;
    if (h === 0) return `${m}m`;
    return m === 0 ? `${h}h` : `${h}h ${m}m`;
  }

  function formatDateShort(date) {
    return new Date(date).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
  }

  // "Wed 17 Jun, 21:00–23:00", or with both dates when the window crosses midnight.
  function formatWindowLabel(start, end) {
    const s = new Date(start), e = new Date(end);
    if (!end || isNaN(e)) return `${formatDateShort(s)}, ${formatTime(s)}`;
    return s.toDateString() === e.toDateString()
      ? `${formatDateShort(s)}, ${formatTime(s)}–${formatTime(e)}`
      : `${formatDateShort(s)} ${formatTime(s)} – ${formatDateShort(e)} ${formatTime(e)}`;
  }

  // HA serialises these attributes as full ISO timestamps; the card only wants the day.
  // Sunday Saver was retired in 2026 and replaced by Flextras. The card is hidden
  // rather than deleted so it can be brought back if EDF revive the scheme, or
  // reused for whatever Weekend Saver turns into. Flip to true to restore it.
  // The tabs built from entity state, which therefore want re-rendering when a coordinator
  // refreshes. The rest are fed from the websocket commands and sit still until asked.
  const LIVE_TABS = ['overview', 'charging'];

  const SHOW_SUNDAY_SAVER_CARD = false;

  function formatDateOnly(v) {
    if (!v) return '';
    const d = new Date(v);
    if (isNaN(d.getTime())) return String(v);
    return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  }

  function isValidDate(v) {
    return v && v !== 'unknown' && v !== 'unavailable' && !isNaN(Date.parse(v));
  }

  function formatSource(source) {
    if (!source) return '';
    return source.toLowerCase().replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  }

  // Everything in the billing payloads is already in pounds - the integration converts the
  // pence EDF serve on the way through - so this only has to format.
  function money(value, { signed = false } = {}) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
    const n = Number(value);
    // Grouped, because a credit balance on a smart meter account runs to four figures
    // and \u00a31234.56 is harder to read at a glance than \u00a31,234.10.
    const body = `\u00a3${Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    if (!signed) return n < 0 ? `-${body}` : body;
    return n < 0 ? `-${body}` : `+${body}`;
  }

  // EDF give a payment schedule as a day of the month, so it reads as "on the 1st".
  function ordinal(day) {
    const n = Number(day);
    if (!Number.isFinite(n)) return String(day);
    const suffix = (n % 100 >= 11 && n % 100 <= 13) ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] || 'th');
    return `${n}${suffix}`;
  }

  function moneyClass(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '';
    return Number(value) < 0 ? ' out' : ' in';
  }

  // Bills, transactions and referrals carry plain 'YYYY-MM-DD' dates as well as full
  // timestamps, and new Date('2026-10-07') is parsed as UTC midnight - which in a British
  // summer still renders as the 7th, but the same trick in a negative offset timezone
  // would show the 6th. Date-only values are therefore split rather than parsed.
  function formatDay(value) {
    if (!value) return '—';
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value));
    if (match) {
      const d = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
      return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
    }
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime())
      ? String(value)
      : parsed.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
  }

  // EDF's refund statuses come through as enum spellings. Title case reads better in a
  // list and an unrecognised one still renders, just without the tidying.
  function humanise(value) {
    if (!value) return '—';
    return String(value)
      .replace(/_/g, ' ')
      .toLowerCase()
      .replace(/\b\w/g, c => c.toUpperCase());
  }

  const PREDICTOR_ICON = {
    wind: 'mdi:weather-windy', solar: 'mdi:weather-sunny',
    demand: 'mdi:transmission-tower', weather: 'mdi:thermometer',
  };

  const TRANSACTION_ICON = {
    Charge: 'mdi:flash', Payment: 'mdi:bank-transfer-in',
    Credit: 'mdi:plus-circle-outline', Refund: 'mdi:cash-refund',
  };

  function esc(str) {
    return String(str)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function overlapsStarted(start, end, started) {
    if (!started || started.length === 0) return false;
    const s = new Date(start).getTime(), e = new Date(end).getTime();
    return started.some(x => x.start < e && x.end > s);
  }

  // `started` is optional. When passed (dispatch slots), a past slot that never appeared in the
  // started dispatches is treated as cancelled rather than completed - EDF doesn't populate
  // completed_dispatches, so started is the only record of what actually charged. Callers that
  // don't pass it (e.g. Sunday Saver windows) keep the plain time-based behaviour.
  function dispatchStatus(start, end, started) {
    const now = Date.now();
    if (new Date(start) <= now && new Date(end) > now) return 'active';
    if (new Date(end) > now) return 'planned';
    if (started !== undefined && !overlapsStarted(start, end, started)) return 'cancelled';
    return 'completed';
  }

  const DISPATCH_COLOUR = { completed: '#4CAF50', active: '#FF9800', planned: '#2196F3', cancelled: '#F44336' };
  const DISPATCH_LABEL  = { completed: 'Completed', active: 'Active',    planned: 'Planned',   cancelled: 'Cancelled' };

  // Friendly labels for free electricity session sources (Sunday Saver has its own dedicated card).
  const FREE_SESSION_SOURCE_LABEL = { football: 'World Cup', football_et: 'World Cup (extra time)', power_perks: 'Power Perks', flextras_hours: 'Flextras free hours' };
  function freeSessionSourceLabel(source) {
    if (FREE_SESSION_SOURCE_LABEL[source]) return FREE_SESSION_SOURCE_LABEL[source];
    if (!source) return 'Free electricity';
    return source.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  }

  // ── Styles ────────────────────────────────────────────────────────────────────

  const STYLES = `
    :host {
      display: block;
      height: 100%;
      background: var(--primary-background-color);
      overflow-y: auto;
      box-sizing: border-box;
    }

    /* ── Toolbar ── */
    .toolbar {
      display: flex; align-items: center; gap: 12px;
      padding: 0 16px; height: 56px;
      background: var(--app-header-background-color, var(--primary-color, #3d5afe));
      color: var(--app-header-text-color, #fff);
      box-shadow: 0 2px 4px rgba(0,0,0,.2);
      position: sticky; top: 0; z-index: 10;
    }
    .toolbar-title { font-size: 1.1em; font-weight: 500; flex: 1; }
    .toolbar-sub   { font-size: 0.8em; opacity: 0.85; }
    .status-pill {
      font-size: 0.75em; font-weight: 600;
      padding: 3px 10px; border-radius: 12px;
      background: rgba(255,255,255,0.2); white-space: nowrap;
    }
    .status-pill.on { background: #4CAF50; }

    /* ── Layout ── */
    .content {
      max-width: 720px; margin: 0 auto;
      padding: 20px 16px 40px;
      display: flex; flex-direction: column; gap: 16px;
    }
    .card {
      background: var(--card-background-color, #fff);
      border-radius: var(--ha-card-border-radius, 12px);
      box-shadow: var(--ha-card-box-shadow, 0 2px 6px rgba(0,0,0,.1));
      overflow: hidden;
    }

    /* ── Controls ── */
    .section-title {
      font-size: 0.75em; font-weight: 600; text-transform: uppercase;
      letter-spacing: 0.08em; color: var(--secondary-text-color);
      padding: 14px 16px 6px;
    }
    .control-row {
      display: flex; align-items: center;
      padding: 12px 16px;
      border-bottom: 1px solid var(--divider-color, #e0e0e0);
      gap: 12px;
    }
    .control-row:last-child { border-bottom: none; }
    .control-label {
      flex: 1; font-size: 0.95em;
      color: var(--primary-text-color); font-weight: 500;
    }
    .control-sub { font-size: 0.8em; color: var(--secondary-text-color); font-weight: 400; }

    /* Toggle switch */
    .toggle {
      position: relative; width: 44px; height: 26px;
      flex-shrink: 0; cursor: pointer;
    }
    .toggle input { opacity: 0; width: 0; height: 0; position: absolute; }
    .toggle-track {
      position: absolute; inset: 0; border-radius: 13px;
      background: var(--switch-unchecked-color, #bdbdbd);
      transition: background 0.2s;
    }
    .toggle input:checked + .toggle-track { background: var(--switch-checked-color, var(--primary-color, #3d5afe)); }
    .toggle-thumb {
      position: absolute; top: 3px; left: 3px;
      width: 20px; height: 20px; border-radius: 50%;
      background: #fff;
      box-shadow: 0 1px 3px rgba(0,0,0,.3);
      transition: left 0.2s;
    }
    .toggle input:checked ~ .toggle-thumb { left: 21px; }
    .toggle input:disabled + .toggle-track { opacity: 0.4; cursor: default; }
    .toggle input:disabled ~ .toggle-thumb { cursor: default; }

    /* Slider + number */
    .slider-group { display: flex; align-items: center; gap: 10px; flex: 1; min-width: 0; }
    .slider-group input[type=range] {
      flex: 1; min-width: 0; accent-color: var(--primary-color, #3d5afe); cursor: pointer;
    }
    .slider-value {
      font-size: 0.95em; font-weight: 500; min-width: 36px; text-align: right;
      color: var(--primary-text-color);
    }

    /* Time input */
    .time-input {
      border: 1px solid var(--divider-color, #e0e0e0);
      border-radius: 6px; padding: 5px 8px;
      background: var(--input-fill-color, var(--secondary-background-color, #f5f5f5));
      color: var(--primary-text-color);
      font-size: 0.95em; font-family: inherit; cursor: pointer;
    }
    .time-input:focus { outline: 2px solid var(--primary-color, #3d5afe); outline-offset: -1px; }

    /* Apply button */
    .btn-apply {
      background: var(--primary-color, #3d5afe); color: #fff;
      border: none; border-radius: 6px;
      padding: 5px 12px; font-size: 0.85em; font-weight: 600;
      cursor: pointer; white-space: nowrap; transition: opacity 0.15s;
    }
    .btn-apply:hover { opacity: 0.88; }
    .btn-apply:active { opacity: 0.75; }
    .btn-apply.danger { background: #e53935; }

    /* ── Date nav ── */
    .nav-row { display: flex; align-items: center; gap: 8px; padding: 12px 16px; }
    .nav-btn {
      background: none; border: none; border-radius: 50%; padding: 6px;
      cursor: pointer; color: var(--primary-text-color);
      display: flex; align-items: center; transition: background 0.15s; flex-shrink: 0;
    }
    .nav-btn:hover:not(:disabled) { background: rgba(var(--rgb-primary-text-color,0,0,0),0.06); }
    .nav-btn:disabled { opacity: 0.3; cursor: default; }
    .date-select {
      flex: 1;
      background: var(--input-fill-color, var(--secondary-background-color, #f5f5f5));
      border: 1px solid var(--divider-color, #e0e0e0);
      border-radius: 6px; color: var(--primary-text-color);
      font-size: 1em; padding: 8px 12px; cursor: pointer;
      font-family: inherit; text-align: center;
    }
    .date-select:focus { outline: 2px solid var(--primary-color,#3d5afe); outline-offset: -1px; }

    /* ── Dispatch/off-peak lists ── */
    .empty { color: var(--secondary-text-color); font-size: 0.9em; text-align: center; padding: 20px 16px; }
    .section-info { font-size: 0.82em; color: var(--secondary-text-color); padding: 0 16px 12px; line-height: 1.4; }
    .no-entity { padding: 24px; color: var(--secondary-text-color); font-size: 0.9em; text-align: center; }
    .item {
      display: flex; gap: 14px; padding: 12px 16px;
      border-bottom: 1px solid var(--divider-color, #e0e0e0);
      align-items: flex-start;
    }
    .item:last-child { border-bottom: none; }
    .dot { width: 10px; height: 10px; border-radius: 50%; margin-top: 5px; flex-shrink: 0; }
    .info { flex: 1; min-width: 0; }
    .time-str { font-size: 1em; font-weight: 500; color: var(--primary-text-color); }
    .duration { font-weight: 400; color: var(--secondary-text-color); font-size: 0.875em; }
    .meta {
      font-size: 0.82em; color: var(--secondary-text-color);
      margin-top: 4px; display: flex; flex-wrap: wrap; gap: 6px; align-items: center;
    }
    .badge { border-radius: 10px; padding: 2px 8px; font-size: 0.8em; font-weight: 600; color: #fff; }

    .toast {
      position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
      background: #323232; color: #fff;
      padding: 10px 20px; border-radius: 8px;
      font-size: 0.875em; z-index: 100;
      animation: fadeout 2.5s forwards;
    }
    @keyframes fadeout { 0%{opacity:1} 70%{opacity:1} 100%{opacity:0} }

    /* ── Auth expiry banner ── */
    .auth-expiry-card {
      display: flex; align-items: flex-start; gap: 12px;
      padding: 14px 16px;
      border-left: 4px solid;
    }
    .auth-expiry-card.warning { border-color: #FF9800; background: rgba(255,152,0,0.08); }
    .auth-expiry-card.urgent  { border-color: #e53935; background: rgba(229,57,53,0.08); }
    .auth-expiry-card.expired { border-color: #e53935; background: rgba(229,57,53,0.12); }
    .auth-expiry-icon { font-size: 1.4em; flex-shrink: 0; line-height: 1.3; }
    .auth-expiry-text { font-size: 0.88em; color: var(--primary-text-color); line-height: 1.5; }

    /* ── API key ── */
    .api-key-row { display: flex; align-items: center; gap: 8px; margin-top: 4px; padding: 0 16px; flex-wrap: wrap; }
    .api-key-value { flex: 1; min-width: 180px; font-family: monospace; font-size: 0.95em; background: rgba(127,127,127,0.12); border-radius: 6px; padding: 8px 10px; overflow-wrap: anywhere; }
    .api-key-btn { flex-shrink: 0; cursor: pointer; border: 1px solid var(--divider-color, rgba(127,127,127,0.3)); background: transparent; color: var(--primary-text-color); border-radius: 6px; padding: 8px 12px; font-size: 0.88em; }
    .api-key-btn:hover { background: rgba(127,127,127,0.12); }
    .api-key-note { margin-top: 10px; padding: 0 16px 14px; font-size: 0.82em; color: var(--secondary-text-color, #8d95a0); line-height: 1.5; }

    /* ── World Cup banner ── */
    .wc-banner {
      display: flex; align-items: center; gap: 10px;
      padding: 10px 16px 6px;
      font-size: 0.78em; color: var(--secondary-text-color); font-style: italic;
    }
    .wc-flag { font-size: 1.3em; }

    /* ── Menu button ── */
    .menu-btn {
      display: flex;
      background: none; border: none;
      color: inherit; cursor: pointer;
      padding: 6px; margin: -6px 4px -6px -4px;
      border-radius: 50%;
      align-items: center; justify-content: center;
      flex-shrink: 0;
    }
    .menu-btn:hover { background: rgba(255,255,255,0.15); }

    /* ── Flextras free hour booking ── */
    .flex-days { display: flex; flex-wrap: wrap; gap: 6px; padding: 4px 16px 12px; }
    .flex-day {
      background: var(--secondary-background-color, rgba(255,255,255,0.08));
      border: 1px solid transparent; border-radius: 14px;
      color: inherit; cursor: pointer;
      padding: 5px 11px; font-size: 0.8em; font-weight: 600; white-space: nowrap;
    }
    .flex-day:hover { border-color: var(--primary-color, #3d5afe); }
    .flex-day.open { background: var(--primary-color, #3d5afe); color: #fff; }
    .flex-day .count { opacity: 0.75; font-weight: 400; margin-left: 4px; }
    .flex-grid {
      display: grid; grid-template-columns: repeat(auto-fill, minmax(76px, 1fr));
      gap: 6px; padding: 0 16px 12px;
    }
    .flex-slot {
      background: var(--secondary-background-color, rgba(255,255,255,0.08));
      border: 1px solid transparent; border-radius: 6px;
      color: inherit; cursor: pointer;
      padding: 7px 4px; font-size: 0.78em; font-weight: 600;
      font-variant-numeric: tabular-nums;
    }
    .flex-slot:hover:not(:disabled) { border-color: var(--primary-color, #3d5afe); }
    /* Confirmed with EDF: solid. Picked but not saved: outlined, so the grid makes the
       difference between "chosen" and "booked" obvious without reading anything. */
    .flex-slot.booked { background: #2e7d32; color: #fff; }
    .flex-slot.pending {
      background: transparent; color: var(--primary-color, #3d5afe);
      border: 1px dashed var(--primary-color, #3d5afe);
    }
    .flex-slot.dropping { background: transparent; opacity: 0.5; text-decoration: line-through; }
    .flex-slot:disabled { opacity: 0.35; cursor: not-allowed; }
    .flex-slot:disabled.booked { opacity: 0.75; }
    .flex-actions { display: flex; gap: 8px; align-items: center; padding: 0 16px 14px; }
    .flex-actions .spacer { flex: 1; }
    .flex-booked { padding: 2px 16px 10px; font-size: 0.82em; line-height: 1.5; }
    .flex-booked .row { display: flex; gap: 6px; align-items: baseline; }
    .flex-booked .tick { color: #43a047; }
    .flex-pending-note {
      padding: 0 16px 8px; font-size: 0.8em; font-weight: 600;
      color: var(--primary-color, #3d5afe);
    }
    .flex-day.edited { border-color: var(--primary-color, #3d5afe); border-style: dashed; }

    /* ── Tabs ── */
    .tabs {
      display: flex;
      background: var(--card-background-color, #fff);
      border-bottom: 1px solid var(--divider-color, #e0e0e0);
      position: sticky; top: 0; z-index: 8;
    }
    .tab {
      flex: 1; padding: 12px 8px; border: 0; background: none; cursor: pointer;
      font: inherit; font-size: 0.92em; font-weight: 500;
      color: var(--secondary-text-color);
      border-bottom: 3px solid transparent; margin-bottom: -1px;
    }
    .tab.active {
      color: var(--primary-color, #3d5afe);
      border-bottom-color: var(--primary-color, #3d5afe);
    }
    .tab .beta {
      font-size: 0.72em; font-weight: 600; text-transform: uppercase;
      letter-spacing: 0.04em; opacity: 0.75; margin-left: 5px;
      border: 1px solid currentColor; border-radius: 3px; padding: 0 3px;
    }

    /* ── Account tab ── */
    .kv { display: flex; justify-content: space-between; gap: 12px; padding: 7px 0; }
    .kv + .kv { border-top: 1px solid var(--divider-color, #ececec); }
    .kv .k { color: var(--secondary-text-color); }
    .kv .v { text-align: right; font-variant-numeric: tabular-nums; word-break: break-word; }
    .agreement { padding: 12px 0; }
    .agreement + .agreement { border-top: 1px solid var(--divider-color, #ececec); }
    .agreement.past { opacity: 0.62; }
    .agreement-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
    .agreement-head .name { font-weight: 600; flex: 1; min-width: 0; word-break: break-word; }
    .pill-live {
      font-size: 0.72em; font-weight: 600; text-transform: uppercase;
      letter-spacing: 0.04em; padding: 2px 7px; border-radius: 10px;
      background: var(--label-badge-green, #3fae4a); color: #fff; white-space: nowrap;
    }
    .pill-past {
      font-size: 0.72em; font-weight: 600; text-transform: uppercase;
      letter-spacing: 0.04em; padding: 2px 7px; border-radius: 10px;
      background: var(--divider-color, #e0e0e0); color: var(--secondary-text-color);
      white-space: nowrap;
    }

    /* ── Money, statements, ledger, referrals ── */
    /* ── Power Perks Predictor ── */
    .predictor-head { display: flex; align-items: center; gap: 14px; padding: 14px 16px; flex-wrap: wrap; }
    .predictor-art { width: 112px; height: auto; flex-shrink: 0; border-radius: 8px; }
    .predictor-art.small { width: 96px; }
    .predictor-head > div { flex: 1; min-width: 200px; }
    .predictor-tomorrow { display: flex; align-items: center; gap: 14px; padding: 4px 16px 10px; flex-wrap: wrap; }
    .predictor-verdict { font-size: 1.1em; font-weight: 600; margin-bottom: 6px; }
    .predictor-factors { display: flex; flex-wrap: wrap; gap: 4px 14px; margin-top: 6px; }
    .factor {
      display: inline-flex; align-items: center; gap: 4px;
      font-size: 0.82em; color: var(--secondary-text-color);
    }
    .factor ha-icon { --mdc-icon-size: 16px; width: 16px; height: 16px; }
    .factor .trend { opacity: 0.8; }
    .level {
      font-size: 0.7em; text-transform: uppercase; letter-spacing: 0.04em; font-weight: 700;
      padding: 2px 7px; border-radius: 10px; margin-left: 6px; white-space: nowrap;
      background: var(--secondary-background-color, rgba(127,127,127,0.18));
      color: var(--secondary-text-color);
    }
    .level.likely { background: rgba(76,175,80,0.18); color: #2e7d32; }
    .level.good { background: rgba(139,195,74,0.2); color: #558b2f; }
    .level.possible { background: rgba(255,167,38,0.2); color: #ef6c00; }
    .predictor-day .figure-right { text-align: right; }
    .banner {
      display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
      margin: 0 0 12px; padding: 12px 16px; border-radius: 8px;
      background: var(--card-background-color, #fff);
      border-left: 4px solid var(--primary-color, #03a9f4);
      box-shadow: var(--ha-card-box-shadow, 0 2px 2px rgba(0,0,0,0.08));
    }
    .banner.urgent { border-left-color: var(--error-color, #db4437); }
    .banner ha-icon { color: var(--primary-color, #03a9f4); flex-shrink: 0; }
    .banner.urgent ha-icon { color: var(--error-color, #db4437); }
    .banner-body { flex: 1; min-width: 180px; font-size: 0.95em; line-height: 1.4; }
    .figures {
      display: grid; grid-template-columns: repeat(auto-fit, minmax(135px, 1fr));
      gap: 1px; background: var(--divider-color, #ececec);
    }
    .figure { background: var(--card-background-color, #fff); padding: 12px 16px; }
    .figure .label {
      font-size: 0.78em; text-transform: uppercase; letter-spacing: 0.04em;
      color: var(--secondary-text-color); margin-bottom: 4px;
    }
    .figure .amount { font-size: 1.32em; font-weight: 600; font-variant-numeric: tabular-nums; }
    .figure .sub { font-size: 0.82em; color: var(--secondary-text-color); margin-top: 2px; }
    .figure .sub.split { display: flex; justify-content: space-between; gap: 10px; font-variant-numeric: tabular-nums; }
    .figure .sub.split span:last-child { opacity: 0.7; }
    .row {
      display: flex; align-items: center; gap: 12px;
      padding: 11px 16px; border-bottom: 1px solid var(--divider-color, #ececec);
    }
    .row:last-child { border-bottom: none; }
    .row .main { flex: 1; min-width: 0; }
    .row .title { font-weight: 500; word-break: break-word; }
    .row .sub { font-size: 0.82em; color: var(--secondary-text-color); margin-top: 2px; }
    .row .figure-right { text-align: right; white-space: nowrap; }
    .money { font-variant-numeric: tabular-nums; font-weight: 600; }
    .money.out { color: var(--label-badge-red, #df4c1e); }
    .money.in { color: var(--label-badge-green, #3fae4a); }
    .btn-link {
      border: 1px solid var(--divider-color, #e0e0e0); background: none; cursor: pointer;
      font: inherit; font-size: 0.86em; color: var(--primary-color, #3d5afe);
      border-radius: 6px; padding: 5px 10px; white-space: nowrap;
    }
    .btn-link:hover { background: var(--secondary-background-color, #f5f5f5); }
    .btn-link[disabled] { opacity: 0.5; cursor: default; }
    .amount-input {
      font: inherit; padding: 8px 10px; border-radius: 6px; width: 110px;
      border: 1px solid var(--divider-color, #e0e0e0);
      background: var(--card-background-color, #fff); color: var(--primary-text-color);
    }
    .refund-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 0 16px 14px; }
    .notice {
      margin: 0 16px 14px; padding: 10px 12px; border-radius: 8px; font-size: 0.88em;
      background: var(--secondary-background-color, #f5f5f5); color: var(--secondary-text-color);
    }
    .notice.warn {
      background: rgba(255, 152, 0, 0.12); color: var(--primary-text-color);
      border-left: 3px solid #ff9800;
    }
    .load-more { padding: 10px 16px 14px; text-align: center; }
  `;

  // ── Panel element ─────────────────────────────────────────────────────────────

  class EDFEnergyPanel extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: 'open' });
      this._hass = null;
      this._selectedDateKey = null;
      this._lastChanged = null;
      this._apiKeyRevealed = false;
      this._apiKeyValue = null;
      // Track pending edits so a mid-typing re-render doesn't overwrite inputs
      this._pending = {};  // { entityId: value }
      // Flextras hour booking. The selection is held here rather than read back off the
      // grid so a re-render mid-edit - which a coordinator refresh will cause - does not
      // throw away hours the user has picked but not yet saved.
      this._flex = null;          // { days, booked, remaining_hours } from the backend
      this._flexSel = null;       // Set of 'YYYY-MM-DD HH:MM', the full desired booking
      this._flexOpenDate = null;  // which day's grid is expanded
      this._flexSlots = {};       // date -> slots, fetched on demand
      this._flexBusy = false;
      this._flexLoading = false;
      this._flexConfirmCancel = false;
      // Beta features, and the account tab they gate. Both are asked for once and held
      // here, so a coordinator refresh re-rendering the panel does not re-fetch them or
      // throw the user back to the first tab.
      this._beta = null;
      this._betaLoading = false;
      this._activeTab = 'overview';
      this._account = null;
      this._accountLoading = false;
      this._accountError = null;
      this._consumptionCard = null;
      // The money side of the account. Each of these is asked for once, when the tab that
      // needs it is first opened, and then held - none of it changes more than daily and
      // re-fetching on every coordinator refresh would mean a GraphQL round trip a minute
      // for a list nobody is looking at. The refresh button on each card is the way back.
      this._billing = null;
      this._billingLoading = false;
      this._billingError = null;
      this._bills = null;
      this._billsLoading = false;
      this._billsError = null;
      this._billBusyId = null;
      this._transactions = null;
      this._transactionsLoading = false;
      this._transactionsError = null;
      this._referrals = null;
      this._referralsLoading = false;
      this._referralsError = null;
      this._notices = null;
      this._noticesLoading = false;
      this._tabsToggleBusy = false;
      this._predictor = null;
      this._predictorLoading = false;
      this._predictorError = null;
      // Refund request state. The amount is held here so a re-render mid-typing does not
      // throw it away, and the confirm step is deliberately separate from the button that
      // sends it - this moves real money out of the account.
      this._refundAmount = '';
      this._refundConfirm = false;
      this._refundBusy = false;
      this._refundResult = null;
    }

    set hass(hass) {
      const de = this._findDispatchEntity(hass);
      const oe = this._findOffPeakEntity(hass);
      const se = this._findSundaySaverEntity(hass);
      const fse = this._findFreeSessionsEntity(hass);
      const ids = this._getDeviceEntityIds(de, hass);
      const authExpiry = this._findAuthExpirySensor(hass);
      const token = [
        de?.last_changed, oe?.last_changed, se?.last_changed,
        fse?.attributes?.football_free_electricity_enabled,
        fse?.attributes?.football_enrollment_auto_detected,
        (fse?.attributes?.free_electricity_windows || []).map(w => w.code).join(','),
        authExpiry?.state,
        ids.chargeTarget ? hass.states[ids.chargeTarget]?.last_changed : '',
        ids.targetTime   ? hass.states[ids.targetTime]?.last_changed   : '',
        ids.smartCharge  ? hass.states[ids.smartCharge]?.last_changed  : '',
        ids.bumpCharge   ? hass.states[ids.bumpCharge]?.last_changed   : '',
      ].join('|');

      if (token === this._lastChanged && this.shadowRoot.children.length > 0) {
        this._hass = hass;
        return;
      }
      this._lastChanged = token;
      this._hass = hass;

      // Only the overview and smart charging tabs are built from these entities. The
      // others move with the websocket payloads instead, and re-rendering under them tears
      // the consumption chart out of the DOM and rebuilds it for nothing. The tab switch
      // renders anyway, so they catch up the moment it matters.
      if (!LIVE_TABS.includes(this._activeTab) && this.shadowRoot.children.length > 0) return;

      this._render();
    }

    set panel(panel) { this._panel = panel; }

    // ── Entity discovery ────────────────────────────────────────────────────────

    _findDispatchEntity(hass) {
      if (!hass) return null;
      for (const [id, s] of Object.entries(hass.states))
        if (id.startsWith('binary_sensor.') && id.includes('edf_energy') && id.endsWith('_intelligent_dispatching'))
          return s;
      return null;
    }

    _findOffPeakEntity(hass) {
      if (!hass) return null;
      for (const [id, s] of Object.entries(hass.states))
        if (id.startsWith('binary_sensor.') && id.includes('edf_energy') && id.endsWith('_off_peak') && !id.includes('_export_'))
          return s;
      return null;
    }

    _findSundaySaverEntity(hass) {
      if (!hass) return null;
      for (const [id, s] of Object.entries(hass.states))
        if (id.startsWith('sensor.') && id.includes('edf_energy') && id.endsWith('_sunday_saver_start'))
          return s;
      return null;
    }

    _findFlextrasEntity(hass) {
      if (!hass) return null;
      for (const [id, st] of Object.entries(hass.states))
        if (id.startsWith('binary_sensor.') && id.includes('edf_energy') && id.endsWith('_flextras_registered'))
          return st;
      return null;
    }

    _findFreeSessionsEntity(hass) {
      if (!hass) return null;
      for (const [id, s] of Object.entries(hass.states))
        if (id.startsWith('event.') && id.includes('edf_energy') && id.endsWith('_free_electricity_session_events'))
          return s;
      return null;
    }

    _findEventFreeStartEntity(hass) {
      if (!hass) return null;
      for (const [id, s] of Object.entries(hass.states))
        if (id.startsWith('sensor.') && id.includes('edf_energy') && id.endsWith('_event_free_start'))
          return s;
      return null;
    }

    _findAuthExpirySensor(hass) {
      if (!hass) return null;
      for (const [id, s] of Object.entries(hass.states))
        if (id.startsWith('sensor.') && id.includes('edf_energy') && id.endsWith('_auth_token_expiry'))
          return s;
      return null;
    }

    _findAccountId(hass) {
      // Extract account_id from the Sunday Saver entity, falling back to the free sessions entity
      if (!hass) return null;
      for (const id of Object.keys(hass.states)) {
        const m = id.match(/^sensor\.edf_energy_(.+)_sunday_saver_start$/);
        if (m) return m[1];
      }
      for (const id of Object.keys(hass.states)) {
        const m = id.match(/^event\.edf_energy_(.+)_free_electricity_session_events$/);
        if (m) return m[1];
      }
      return null;
    }

    _getDeviceId(dispatchEntity) {
      if (!dispatchEntity) return null;
      const m = dispatchEntity.entity_id.match(/binary_sensor\.edf_energy_(.+)_intelligent_dispatching/);
      return m ? m[1] : null;
    }

    _getDeviceEntityIds(dispatchEntity, hass) {
      const deviceId = this._getDeviceId(dispatchEntity);
      if (!deviceId || !hass) return {};
      // Search all states for entities belonging to this device rather than hardcoding
      // exact suffixes — different charger brands expose differently-named entities.
      const prefix = `edf_energy_${deviceId}_intelligent`;
      const result = {};
      for (const entityId of Object.keys(hass.states)) {
        if (!entityId.includes(prefix)) continue;
        const domain  = entityId.split('.')[0];
        const tail    = entityId.slice(entityId.indexOf(prefix) + prefix.length);
        if (domain === 'number' && tail.includes('charge_target'))              result.chargeTarget = entityId;
        else if ((domain === 'time' || domain === 'select') &&
                 (tail.includes('target_time') || tail.includes('ready_time'))) result.targetTime   = entityId;
        else if (domain === 'switch' && tail.includes('smart_charge'))          result.smartCharge  = entityId;
        else if (domain === 'switch' && tail.includes('bump_charge'))           result.bumpCharge   = entityId;
      }
      return result;
    }

    // ── Data helpers ────────────────────────────────────────────────────────────

    _parseDispatches(entity) {
      if (!entity) return [];
      const { completed_dispatches = [], planned_dispatches = [] } = entity.attributes;
      const seen = new Set(), result = [];
      for (const d of [...completed_dispatches, ...planned_dispatches]) {
        const key = `${d.start}|${d.end}`;
        if (!seen.has(key)) { seen.add(key); result.push(d); }
      }
      return result;
    }

    _parseStartedDispatches(entity) {
      if (!entity) return [];
      return (entity.attributes.started_dispatches || [])
        .map(d => ({ start: new Date(d.start).getTime(), end: new Date(d.end).getTime() }))
        .filter(d => !isNaN(d.start) && !isNaN(d.end));
    }

    _parseOffPeakWindows(entity) {
      if (!entity) return [];
      return entity.attributes.off_peak_windows || [];
    }

    _parseSundaySaverWindows(entity) {
      if (!entity) return [];
      return entity.attributes.sunday_saver_windows || [];
    }

    _parseFreeSessionWindows(entity) {
      // Sunday Saver sessions have their own dedicated card, so exclude them here to avoid duplication.
      if (!entity) return [];
      return (entity.attributes.free_electricity_windows || []).filter(w => w.source !== 'sunday_saver');
    }

    _allDates(dispatches, offPeakWindows, sundaySaverWindows, freeSessionWindows = []) {
      const keys = new Set([
        ...dispatches.map(d => localDateKey(d.start)),
        ...offPeakWindows.map(w => localDateKey(w.start)),
        ...sundaySaverWindows.map(w => localDateKey(w.start)),
        ...freeSessionWindows.map(w => localDateKey(w.start)),
      ]);
      return [...keys].sort((a, b) => b.localeCompare(a));
    }

    _deviceLabel(entity) {
      const a = entity?.attributes || {};
      const parts = [a.provider];
      if (a.vehicle_battery_size_in_kwh) parts.push(`${a.vehicle_battery_size_in_kwh} kWh battery`);
      if (a.charge_point_power_in_kw)    parts.push(`${a.charge_point_power_in_kw} kW charger`);
      return parts.filter(Boolean).join(' · ');
    }

    _stateLabel(dispatchEntity) {
      if (!this._hass || !dispatchEntity) return null;
      const devicePart = dispatchEntity.entity_id
        .replace('binary_sensor.edf_energy_', '')
        .replace('_intelligent_dispatching', '');
      const e = this._hass.states[`sensor.edf_energy_${devicePart}_intelligent_state`];
      if (!e) return null;
      return e.state.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
    }

    // ── Service calls ───────────────────────────────────────────────────────────

    _callSwitch(entityId, turnOn) {
      this._hass.callService('switch', turnOn ? 'turn_on' : 'turn_off', { entity_id: entityId });
    }

    _callNumber(entityId, value) {
      delete this._pending[entityId];
      this._hass.callService('number', 'set_value', { entity_id: entityId, value: String(value) });
      this._toast(`Charge target set to ${value}%`);
    }

    _callTime(entityId, value) {
      delete this._pending[entityId];
      const domain = entityId.split('.')[0];
      if (domain === 'select') {
        this._hass.callService('select', 'select_option', { entity_id: entityId, option: value });
      } else {
        // HA time.set_value needs HH:MM:SS
        this._hass.callService('time', 'set_value', { entity_id: entityId, value: value.length === 5 ? value + ':00' : value });
      }
      this._toast(`Ready-by time set to ${value}`);
    }

    _toast(msg) {
      const existing = this.shadowRoot.querySelector('.toast');
      if (existing) existing.remove();
      const el = document.createElement('div');
      el.className = 'toast';
      el.textContent = msg;
      this.shadowRoot.appendChild(el);
      setTimeout(() => el.remove(), 2600);
    }

    // ── Render helpers ──────────────────────────────────────────────────────────

    _renderToggle(id, checked, disabled = false) {
      return `
        <label class="toggle">
          <input type="checkbox" ${checked ? 'checked' : ''} ${disabled ? 'disabled' : ''} data-entity="${esc(id)}">
          <div class="toggle-track"></div>
          <div class="toggle-thumb"></div>
        </label>
      `;
    }

    _renderControls(ids) {
      const hass = this._hass;
      const rows = [];

      // ── Smart Charge toggle ──────────────────────────────────────────────────
      if (ids.smartCharge) {
        const e = hass.states[ids.smartCharge];
        const on = e?.state === 'on';
        rows.push(`
          <div class="control-row">
            <div class="control-label">
              Smart Charging
              <div class="control-sub">Allow EDF to schedule overnight charging</div>
            </div>
            ${this._renderToggle(ids.smartCharge, on)}
          </div>
        `);
      }

      // ── Boost Charge toggle ──────────────────────────────────────────────────
      if (ids.bumpCharge) {
        const e = hass.states[ids.bumpCharge];
        const on = e?.state === 'on';
        rows.push(`
          <div class="control-row">
            <div class="control-label">
              Boost Charge Now
              <div class="control-sub">Override schedule and charge immediately</div>
            </div>
            ${this._renderToggle(ids.bumpCharge, on)}
          </div>
        `);
      }

      // ── Charge Target ────────────────────────────────────────────────────────
      if (ids.chargeTarget) {
        const e = hass.states[ids.chargeTarget];
        const current = parseFloat(e?.state) || 80;
        const val = this._pending[ids.chargeTarget] ?? current;
        rows.push(`
          <div class="control-row" style="flex-wrap:wrap;gap:8px">
            <div class="control-label">
              Charge Target
              <div class="control-sub">Minimum state of charge to reach by ready-by time</div>
            </div>
            <div class="slider-group" style="width:100%">
              <input type="range" min="10" max="100" step="1" value="${val}"
                     data-entity="${esc(ids.chargeTarget)}" id="slider-charge-target">
              <span class="slider-value" id="slider-charge-value">${val}%</span>
              <button class="btn-apply" data-action="set-charge-target" data-entity="${esc(ids.chargeTarget)}">Set</button>
            </div>
          </div>
        `);
      }

      // ── Ready-By Time ────────────────────────────────────────────────────────
      if (ids.targetTime) {
        const e = hass.states[ids.targetTime];
        // State may be HH:MM:SS (time entity) or HH:MM (select option) — normalise to HH:MM
        const rawState = e?.state || '07:00';
        const currentHHMM = rawState.slice(0, 5);
        const val = this._pending[ids.targetTime] ?? currentHHMM;

        // 30-min increments 04:00 – 11:00
        const timeOpts = [];
        for (let h = 4; h <= 11; h++) {
          for (const m of [0, 30]) {
            if (h === 11 && m === 30) break;
            timeOpts.push(`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}`);
          }
        }

        rows.push(`
          <div class="control-row">
            <div class="control-label">
              Ready By
              <div class="control-sub">Time the car should be charged to the target</div>
            </div>
            <div style="display:flex;gap:8px;align-items:center">
              <select class="time-input" id="select-target-time" data-entity="${esc(ids.targetTime)}">
                ${timeOpts.map(t => `<option value="${t}"${val === t ? ' selected' : ''}>${t}</option>`).join('')}
              </select>
              <button class="btn-apply" data-action="set-target-time" data-entity="${esc(ids.targetTime)}">Set</button>
            </div>
          </div>
        `);
      }

      if (rows.length === 0) return '';
      return `
        <div class="card">
          <div class="section-title">Controls</div>
          ${rows.join('')}
        </div>
      `;
    }

    // ── World Cup free electricity card ────────────────────────────────────────

    _renderWorldCupCard() {
      // Show only during World Cup 2026 (June 11 – July 19 inclusive)
      const now = new Date();
      const wcEnd = new Date('2026-07-20T00:00:00Z');
      if (now >= wcEnd) return '';

      const fse = this._findFreeSessionsEntity(this._hass);
      const enabled = fse?.attributes?.football_free_electricity_enabled ?? false;
      const autoDetected = fse?.attributes?.football_enrollment_auto_detected ?? false;

      // Auto-detected not enrolled → hide the card entirely
      if (autoDetected && !enabled) return '';

      if (autoDetected) {
        // Enrolled, confirmed from EDF account — show read-only status
        return `
          <div class="card">
            <div class="section-title">&#x26BD; World Cup 2026 Free Electricity</div>
            <div class="control-row">
              <div class="control-label">
                World Cup free electricity
                <div class="control-sub">Enrolled &#x2014; match windows added to your free electricity feed automatically</div>
              </div>
              <span style="font-size:1.3em" title="Enrolled (detected from your EDF account)">&#x2705;</span>
            </div>
            ${this._nextEventWindowRow()}
          </div>`;
      }

      // Manual toggle fallback (API unavailable or returned null)
      return `
        <div class="card">
          <div class="section-title">&#x26BD; World Cup 2026 Free Electricity</div>
          <div class="wc-banner">
            <span class="wc-flag">&#x1F3F4;&#xE0067;&#xE0062;&#xE0065;&#xE006E;&#xE0067;&#xE007F;&#x1F3F4;&#xE0067;&#xE0062;&#xE0073;&#xE0063;&#xE0074;&#xE007F;</span>
            EDF are offering 2 hours of free electricity for every England &amp; Scotland match.
            Enable this only if your account is enrolled in the offer.
          </div>
          <div class="control-row">
            <div class="control-label">
              I'm enrolled in World Cup free electricity
              <div class="control-sub">Adds match kick-off windows to the free electricity session feed</div>
            </div>
            <label class="toggle">
              <input type="checkbox" id="football-toggle" ${enabled ? 'checked' : ''}>
              <div class="toggle-track"></div>
              <div class="toggle-thumb"></div>
            </label>
          </div>
          ${enabled ? this._nextEventWindowRow() : ''}
        </div>
      `;
    }

    // The next (or currently-active) event free-electricity window — used by the
    // World Cup card. Reads the event free start sensor, which carries the match
    // name plus start/end and an is_active flag.
    _nextEventWindowRow() {
      const efs = this._findEventFreeStartEntity(this._hass);
      if (!efs) return '';
      const st = efs.state;
      const end = efs.attributes?.end;
      const name = efs.attributes?.event_name;
      const active = efs.attributes?.is_active === true;
      const etStart = efs.attributes?.extra_time_session_start;
      const etEnd   = efs.attributes?.extra_time_session_end;
      const hasEt   = isValidDate(etStart) && isValidDate(etEnd);
      const nowMs   = Date.now();
      const etActive = hasEt && new Date(etStart).getTime() <= nowMs && nowMs <= new Date(etEnd).getTime();

      let value, sub;
      if (active && isValidDate(st)) {
        value = '&#x1F7E2; Free now';
        sub = end ? `Until ${esc(formatTime(end))}` : '';
        if (hasEt) sub += ` · extra time until ${esc(formatTime(etEnd))}`;
      } else if (etActive) {
        value = '&#x1F7E2; Free now (extra time)';
        sub = etEnd ? `Until ${esc(formatTime(etEnd))}` : '';
      } else if (isValidDate(st) && new Date(st) > nowMs) {
        value = esc(formatWindowLabel(st, end));
        sub = name ? esc(name) : '';
        if (hasEt) sub += (sub ? ' · ' : '') + `extra time ${esc(formatTime(etStart))}–${esc(formatTime(etEnd))}`;
      } else {
        value = 'None scheduled';
        sub = '';
      }
      return `
        <div class="control-row">
          <div class="control-label">
            Next match window
            ${sub ? `<div class="control-sub">${sub}</div>` : ''}
          </div>
          <div style="text-align:right;font-weight:600;white-space:nowrap">${value}</div>
        </div>`;
    }

    // ── Flextras card ─────────────────────────────────────────────────────────
    // Flextras replaced Sunday Saver in 2026. Joining the schemes beneath it is only
    // possible in the EDF mobile app, so this card is read-only apart from joining and
    // claiming the bonus hours. Spending those hours is the card below.
    _renderFlextrasCard() {
      const fe = this._findFlextrasEntity(this._hass);
      if (!fe) return '';

      const a = fe.attributes || {};
      const registered = fe.state === 'on';
      const optedOut = a.opted_out === true;

      let badge;
      if (registered) badge = `<span class="status-pill on">Registered</span>`;
      else if (optedOut) badge = `<span class="status-pill">Opted out</span>`;
      else badge = `<span class="status-pill">Not registered</span>`;

      const rows = [];

      // Bonus hours - the one action we can perform from HA.
      const hours = a.bonus_hours_awarded;
      if (hours != null) {
        const claimed = a.bonus_hours_claimed === true;
        rows.push(`
          <div class="control-row">
            <div class="control-label">
              Joining bonus
              <div class="control-sub">${claimed ? 'Claimed - use on a weekend of your choice' : 'Not yet claimed'}</div>
            </div>
            <div style="text-align:right;font-weight:600;white-space:nowrap">${esc(String(hours))}h</div>
          </div>`);
      }

      // Weekend Saver - hidden outright where the tariff rules the account out
      // (a permanently blocked row is noise); otherwise show EDF's own reason,
      // which is actionable for gates like a missing mobile number.
      const canSignUp = a.weekend_saver_can_sign_up;
      const blockers = Array.isArray(a.weekend_saver_blockers) ? a.weekend_saver_blockers : [];
      const wsExcluded = a.weekend_saver_tariff_excluded === true;
      if (!wsExcluded && (canSignUp != null || blockers.length)) {
        const sub = canSignUp === true
          ? 'Eligible to join'
          : (blockers.length ? blockers.map(b => esc(String(b))).join('; ') : 'Not eligible');
        rows.push(`
          <div class="control-row">
            <div class="control-label">
              Weekend Saver
              <div class="control-sub">${sub}</div>
            </div>
            <div style="text-align:right;font-weight:600;white-space:nowrap">${canSignUp === true ? '&#x2705;' : '&#x2014;'}</div>
          </div>`);
      }

      // Power Perks - field exists ahead of launch, so absence is expected.
      // Power Perks - hidden where the tariff cannot join (e.g. FreePhase, which
      // already includes free electricity events).
      const perks = a.power_perks_signup_date;
      if (a.power_perks_excluded !== true) rows.push(`
        <div class="control-row">
          <div class="control-label">
            Power Perks
            <div class="control-sub">${perks ? 'Signed up ' + esc(formatDateOnly(perks)) : 'Not signed up'}</div>
          </div>
          <div style="text-align:right;font-weight:600;white-space:nowrap">${perks ? '&#x2705;' : '&#x2014;'}</div>
        </div>`);

      if (a.tastecard_activation_date) {
        rows.push(`
          <div class="control-row">
            <div class="control-label">
              Tastecard
              <div class="control-sub">Activated ${esc(formatDateOnly(a.tastecard_activation_date))}</div>
            </div>
            <div style="text-align:right;font-weight:600">&#x2705;</div>
          </div>`);
      }

      // Joining is a plain no-body POST, so it can be done from here rather than
      // sending people to the app. Rejoining after opting out is non-destructive,
      // but it does reset the registration date, so the copy differs.
      const banner = registered ? '' : `
        <div class="wc-banner">
          ${optedOut
            ? 'You have opted out of Flextras. Rejoining keeps your bonus hours, tastecard and Power Perks, but resets your registration date to today.'
            : 'Join Flextras for monthly challenges, free energy events and exclusive benefits.'}
          <div style="margin-top:8px">
            <button class="btn-apply" data-action="join-flextras">
              ${optedOut ? 'Rejoin Flextras' : 'Join Flextras'}
            </button>
          </div>
        </div>`;

      return `
        <div class="card">
          <div class="section-title">&#x2B50; Flextras</div>
          <div class="control-row">
            <div class="control-label">
              Flextras membership
              <div class="control-sub">${a.registration_date ? 'Registered ' + esc(formatDateOnly(a.registration_date)) : 'Monthly challenges, free energy events and perks'}</div>
            </div>
            ${badge}
          </div>
          ${banner}
          ${rows.join('')}
        </div>`;
    }

    // ── Flextras free hours card ───────────────────────────────────────────────
    // The hours earned through Flextras are spent on weekend slots of the customer's
    // choosing. EDF's booking call replaces the whole set at once, so the selection here
    // is always the complete desired booking rather than a delta, and Save sends it as
    // such. That mirrors the API exactly and makes moving an hour the same action as
    // booking one.
    _renderFlextrasHoursCard() {
      const flex = this._flex;
      if (!flex) return '';
      const days = (flex.days || []).filter(d => d.available);
      const booked = flex.booked || [];
      if (!days.length && !booked.length) return '';

      const sel = this._flexSel || new Set();
      // A missing counter means "not told", not "none left". Blocking the grid on an
      // unknown would lock out a customer EDF would happily have let book, and the
      // backend refuses an overspend anyway.
      const allowanceKnown = flex.remaining_hours != null;
      const allowance = booked.length + (flex.remaining_hours ?? 0);
      const chosen = sel.size;
      const dirty = this._flexDirty();

      // Nothing booked and nothing to spend is the ordinary resting state for anyone on a
      // time-of-use tariff: Weekend Saver, which earns the hours, is for non-time-of-use
      // tariffs only. Showing a grid of hours that cannot be clicked would read as broken,
      // so say why instead.
      if (allowanceKnown && allowance === 0 && !booked.length) {
        return `
          <div class="card">
            <div class="section-title">&#x23F1;&#xFE0F; Your free hours</div>
            <div class="section-info">
              No free hours to spend at the moment. When Flextras awards you some, book
              them here for any Saturday or Sunday between 12am and 3pm.
            </div>
          </div>`;
      }

      const bookedKeys = new Set(booked.map(h => `${h[0]} ${h[1]}`));
      const adding = [...sel].filter(k => !bookedKeys.has(k));
      const dropping = [...bookedKeys].filter(k => !sel.has(k));

      const dayChips = days.map(d => {
        const onThisDay = [...sel].filter(k => k.startsWith(d.date)).length;
        const open = this._flexOpenDate === d.date;
        const edited = [...adding, ...dropping].some(k => k.startsWith(d.date));
        const label = new Date(d.date + 'T12:00:00')
          .toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' });
        return `<button class="flex-day${open ? ' open' : ''}${edited ? ' edited' : ''}" data-flex-day="${esc(d.date)}">
          ${esc(label)}${onThisDay ? `<span class="count">${onThisDay}h</span>` : ''}
        </button>`;
      }).join('');

      let grid = '';
      if (this._flexOpenDate) {
        const slots = this._flexSlots[this._flexOpenDate];
        if (!slots) {
          grid = `<div class="section-info">Loading hours&hellip;</div>`;
        } else if (!slots.length) {
          grid = `<div class="section-info">EDF is not offering any hours on this day.</div>`;
        } else {
          grid = `<div class="flex-grid">` + slots.map(slot => {
            const key = `${slot.date} ${slot.start_time}`;
            const picked = sel.has(key);
            const isBooked = bookedKeys.has(key);
            // Three states worth seeing apart: held by EDF, picked but not yet saved, and
            // booked but about to be given back.
            let cls = '';
            if (picked && isBooked) cls = ' booked';
            else if (picked) cls = ' pending';
            else if (isBooked) cls = ' dropping';
            // Anything EDF will not sell, and anything beyond the allowance once the
            // allowance is spent, is shown but not selectable.
            const blocked = !slot.available || (allowanceKnown && !picked && chosen >= allowance);
            const label = isBooked && !picked ? 'booked, will be given back'
              : picked && !isBooked ? 'chosen, not saved yet'
              : isBooked ? 'booked' : 'free';
            return `<button class="flex-slot${cls}"
              data-flex-slot="${esc(key)}" ${blocked ? 'disabled' : ''}
              title="${esc(slot.start_time)}&ndash;${esc(slot.end_time)} &middot; ${label}">
              ${esc(slot.start_time)}
            </button>`;
          }).join('') + `</div>`;
        }
      }

      const summary = allowanceKnown && allowance
        ? `${chosen} of ${allowance} hour${allowance === 1 ? '' : 's'} chosen`
        : `${chosen} hour${chosen === 1 ? '' : 's'} chosen`;

      // What is actually held with EDF, stated plainly and permanently. A toast is not
      // enough: after saving there has to be something on screen that says it worked.
      // Unused challenge hours get booked for you by EDF once they near expiry, so an
      // expiry worth acting on belongs on screen rather than only in an attribute.
      const expiring = (flex.entitlements || [])
        .filter(e => e.expires && e.hours_left !== 0)
        .sort((a, b) => String(a.expires).localeCompare(String(b.expires)))[0];
      const expiryNote = expiring ? `
        <div class="flex-booked"><div class="control-sub">
          ${esc(expiring.title || 'Hours')}:
          ${expiring.hours_left != null ? esc(String(expiring.hours_left)) + 'h ' : ''}expires
          ${esc(formatDateOnly(expiring.expires))}
        </div></div>` : '';

      const bookedList = booked.length ? `
        <div class="flex-booked">
          ${this._flexBookedWindows(booked).map(w => `
            <div class="row"><span class="tick">&#x2714;</span>
              <span>${esc(w)}</span></div>`).join('')}
        </div>` : `
        <div class="flex-booked"><div class="control-sub">
          No hours booked yet${allowanceKnown && allowance ? ` &mdash; you have ${allowance} to spend` : ''}.
        </div></div>`;

      // Spell out what Save will do, so the button is never a mystery.
      const pendingNote = dirty ? `
        <div class="flex-pending-note">
          ${[adding.length ? `booking ${adding.length} hour${adding.length === 1 ? '' : 's'}` : '',
             dropping.length ? `giving back ${dropping.length}` : '']
            .filter(Boolean).join(', ')} when you save
        </div>` : '';

      const saveLabel = this._flexBusy ? 'Saving&hellip;'
        : dirty ? 'Save changes'
        : booked.length ? 'Saved &#x2714;'
        : 'Save';

      const actions = `
        <div class="flex-actions">
          <div class="control-sub">${esc(summary)}</div>
          <div class="spacer"></div>
          ${booked.length ? `<button class="btn-apply danger" data-action="flex-cancel-all"
            ${this._flexBusy ? 'disabled' : ''}>${
              this._flexConfirmCancel ? 'Really cancel all?' : 'Cancel all'
            }</button>` : ''}
          ${dirty && !this._flexBusy ? `<button class="btn-apply" data-action="flex-revert"
            style="background:transparent;color:var(--secondary-text-color)">Undo</button>` : ''}
          <button class="btn-apply" data-action="flex-save"
            ${this._flexBusy || !dirty ? 'disabled' : ''}>${saveLabel}</button>
        </div>`;

      const note = flex.available === false
        ? `<div class="wc-banner">EDF's booking service could not be reached, so these may be out of date.</div>`
        : '';

      return `
        <div class="card">
          <div class="section-title">&#x23F1;&#xFE0F; Your free hours</div>
          <div class="section-info">
            Pick the hours you want your earned free electricity on. Whole hours, as many
            days as you like, and you can change your mind until 11:59pm on the Thursday
            before.
          </div>
          ${note}
          ${bookedList}
          ${expiryNote}
          ${days.length ? `<div class="flex-days">${dayChips}</div>` : ''}
          ${grid}
          ${pendingNote}
          ${actions}
        </div>`;
    }

    // The booked hours as readable windows, adjacent hours joined, e.g.
    // "Sat 10 Oct, 10:00-12:00". Mirrors the merging the backend does for the calendar.
    _flexBookedWindows(booked) {
      const byDay = {};
      booked.forEach(([date, time]) => (byDay[date] = byDay[date] || []).push(time));
      return Object.keys(byDay).sort().map(date => {
        const hours = byDay[date].map(t => parseInt(t, 10)).sort((a, b) => a - b);
        const spans = [];
        hours.forEach(h => {
          const last = spans[spans.length - 1];
          if (last && h === last[1]) last[1] = h + 1;
          else spans.push([h, h + 1]);
        });
        const label = new Date(date + 'T12:00:00')
          .toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' });
        const times = spans
          .map(([a, b]) => `${String(a).padStart(2, '0')}:00–${String(b).padStart(2, '0')}:00`)
          .join(', ');
        return `${label}, ${times}`;
      });
    }

    // True when the selection differs from what EDF currently holds, which is what
    // decides whether Save does anything.
    _flexDirty() {
      if (!this._flex || !this._flexSel) return false;
      const booked = new Set((this._flex.booked || []).map(h => `${h[0]} ${h[1]}`));
      if (booked.size !== this._flexSel.size) return true;
      for (const key of this._flexSel) if (!booked.has(key)) return true;
      return false;
    }

    _flexResetSelection() {
      this._flexSel = new Set((this._flex?.booked || []).map(h => `${h[0]} ${h[1]}`));
    }

    async _loadFlextrasHours() {
      const accountId = this._findAccountId(this._hass);
      if (!accountId || !this._hass) return;
      try {
        const res = await this._hass.callWS({
          type: 'edf_energy/flextras_bookable_days', account_id: accountId,
        });
        this._flex = res;
        // Only adopt EDF's booking as the selection when there is no unsaved edit in
        // progress, so a background refresh cannot discard what is being chosen.
        if (!this._flexSel || !this._flexDirty()) this._flexResetSelection();
        this._render();
      } catch (err) {
        this._flex = null;
      }
    }

    async _loadFlextrasDaySlots(date) {
      const accountId = this._findAccountId(this._hass);
      if (!accountId || !this._hass) return;
      try {
        const res = await this._hass.callWS({
          type: 'edf_energy/flextras_day_slots', account_id: accountId, date,
        });
        this._flexSlots[date] = res.slots || [];
      } catch (err) {
        this._flexSlots[date] = [];
        this._toast('Could not load the hours for that day');
      }
      this._render();
    }

    async _saveFlextrasHours(hours) {
      const accountId = this._findAccountId(this._hass);
      if (!accountId || !this._hass) return;
      this._flexBusy = true;
      this._render();
      try {
        const res = await this._hass.callWS({
          type: 'edf_energy/flextras_book_hours',
          account_id: accountId, hours, mode: 'replace',
        });
        this._toast(hours.length
          ? `Booked ${res.hours_booked ?? hours.length}h, ${res.remaining_hours ?? 0}h left`
          : 'All booked hours cancelled');
        // Re-read rather than trusting the local selection: EDF is the record.
        this._flexSel = null;
        this._flexSlots = {};
        await this._loadFlextrasHours();
        if (this._flexOpenDate) await this._loadFlextrasDaySlots(this._flexOpenDate);
      } catch (err) {
        this._toast(err?.message || 'Booking failed');
      } finally {
        this._flexBusy = false;
        this._render();
      }
    }

    // ── Sunday Saver card ──────────────────────────────────────────────────────
    _renderSundaySaverCard() {
      if (!SHOW_SUNDAY_SAVER_CARD) return '';

      const se = this._findSundaySaverEntity(this._hass);
      if (!se) return '';

      const a = se.attributes || {};
      const active   = a.is_active === true;
      const hasEvent = a.has_event === true;
      const windows  = Array.isArray(a.sunday_saver_windows) ? a.sunday_saver_windows : [];
      const st = se.state, end = a.end, freeHours = a.free_hours;
      const futureStart = isValidDate(st) && new Date(st) > Date.now();
      const enrolled = active || hasEvent || windows.length > 0 || a.is_enrolled === true;

      let badge, body;
      if (active && isValidDate(st)) {
        badge = `<span class="status-pill on">Active now</span>`;
        body = `
          <div class="control-row">
            <div class="control-label">
              Free electricity
              ${freeHours != null ? `<div class="control-sub">${esc(String(freeHours))}h session</div>` : ''}
            </div>
            <div style="text-align:right;font-weight:600;white-space:nowrap">${end ? `&#x1F7E2; Until ${esc(formatTime(end))}` : '&#x1F7E2; Active'}</div>
          </div>`;
      } else if (hasEvent && futureStart) {
        badge = `<span class="status-pill on">Scheduled</span>`;
        body = `
          <div class="control-row">
            <div class="control-label">
              Next session
              ${freeHours != null ? `<div class="control-sub">${esc(String(freeHours))}h free</div>` : ''}
            </div>
            <div style="text-align:right;font-weight:600;white-space:nowrap">${esc(formatWindowLabel(st, end))}</div>
          </div>`;
      } else if (enrolled) {
        badge = `<span class="status-pill on">Enrolled</span>`;
        body = `
          <div class="control-row">
            <div class="control-label">
              Next session
              <div class="control-sub">No upcoming session scheduled yet</div>
            </div>
            <div style="text-align:right;font-weight:600">&#x2014;</div>
          </div>`;
      } else {
        // Sunday Saver was retired in 2026 and replaced by Flextras. With no
        // enrolment, no scheduled session and no history left to show, the card
        // has nothing to say, so hide it rather than advertising a dead scheme.
        // It reappears automatically if EDF ever schedule a session again.
        return '';
      }

      return `
        <div class="card">
          <div class="section-title">&#x1F5D3;&#xFE0F; Sunday Saver Free Electricity</div>
          <div class="control-row">
            <div class="control-label">
              Sunday Saver free electricity
              <div class="control-sub">Up to ~16h of free electricity on selected Sundays</div>
            </div>
            ${badge}
          </div>
          ${body}
        </div>`;
    }

    _renderAuthExpiryBanner() {
      const sensor = this._findAuthExpirySensor(this._hass);
      if (!sensor || !sensor.state || sensor.state === 'unavailable' || sensor.state === 'unknown') return '';

      const expiry = new Date(sensor.state);
      if (isNaN(expiry)) return '';
      const msRemaining = expiry - Date.now();
      const daysRemaining = Math.ceil(msRemaining / 86400000);

      if (daysRemaining > 7) return '';

      if (daysRemaining <= 0) {
        return `
          <div class="card auth-expiry-card expired">
            <div class="auth-expiry-icon">⚠️</div>
            <div class="auth-expiry-text">
              <strong>EDF Energy authentication has expired.</strong><br>
              Go to Settings → Integrations → EDF Energy → Reconfigure to log in again.
            </div>
          </div>`;
      }

      const daysText = daysRemaining === 1 ? '1 day' : `${daysRemaining} days`;
      const urgency  = daysRemaining <= 2 ? 'urgent' : 'warning';
      const hint     = daysRemaining <= 2
        ? '<br>Re-authenticate now: Settings → Integrations → EDF Energy → Reconfigure.'
        : '';

      return `
        <div class="card auth-expiry-card ${urgency}">
          <div class="auth-expiry-icon">${daysRemaining <= 2 ? '⚠️' : '🔑'}</div>
          <div class="auth-expiry-text">
            EDF Energy authentication expires in <strong>${esc(daysText)}</strong> (${esc(expiry.toLocaleDateString())}).${hint}
          </div>
        </div>`;
    }

    _renderApiKeyCard() {
      if (!this._findAccountId(this._hass)) return '';
      // Refresh-token accounts have a LIVE expiry sensor; API-key accounts don't
      // (it's absent, or lingers as an unavailable orphan after migration). Only
      // show the key card for API-key accounts.
      const expiry = this._findAuthExpirySensor(this._hass);
      if (expiry && expiry.state && expiry.state !== 'unavailable' && expiry.state !== 'unknown') return '';

      const revealed = this._apiKeyRevealed && this._apiKeyValue;
      const display = revealed ? esc(this._apiKeyValue) : '••••••••••••••••••••••••';

      return `
        <div class="card">
          <div class="section-title">API key</div>
          <div class="section-info">Use this key to connect other tools to your EDF account. Treat it like a password. Generating a new key anywhere — here or elsewhere — invalidates this one.</div>
          <div class="api-key-row">
            <code class="api-key-value" id="api-key-value">${display}</code>
            <button class="api-key-btn" id="api-key-reveal">${revealed ? 'Hide' : 'Reveal'}</button>
            <button class="api-key-btn" id="api-key-copy">Copy</button>
          </div>
          <div class="api-key-note">EDF intend to add an API key to Your Account in the future which you will be able to share with any applications you grant access to your account data.</div>
        </div>`;
    }

    async _fetchApiKey() {
      if (this._apiKeyValue) return this._apiKeyValue;
      const accountId = this._findAccountId(this._hass);
      if (!accountId || !this._hass) return null;
      try {
        const res = await this._hass.callWS({ type: 'edf_energy/get_api_key', account_id: accountId });
        this._apiKeyValue = res && res.api_key ? res.api_key : null;
      } catch (err) {
        this._toast('Could not read API key (admin only)');
        this._apiKeyValue = null;
      }
      return this._apiKeyValue;
    }

    // ── Full render ─────────────────────────────────────────────────────────────

    // ── Account tab ─────────────────────────────────────────────────────────────

    async _loadBetaFeatures() {
      const accountId = this._findAccountId(this._hass);
      if (!accountId) { this._beta = {}; return; }
      try {
        this._beta = await this._hass.callWS({
          type: 'edf_energy/beta_features', account_id: accountId,
        });
      } catch (e) {
        // An older backend than the panel, or an account it cannot match. Either way the
        // beta tab stays hidden rather than the whole panel failing to draw.
        this._beta = {};
      }
      this._render();
    }

    async _loadAccountSummary() {
      const accountId = this._findAccountId(this._hass);
      if (!accountId) { this._accountError = 'No EDF account found.'; return; }
      try {
        this._account = await this._hass.callWS({
          type: 'edf_energy/account_summary', account_id: accountId,
        });
        this._accountError = null;
      } catch (e) {
        this._accountError = e?.message || 'Could not load account information.';
      }
      this._render();
    }

    _showAccountTab() {
      return this._beta !== null && this._beta.show_account_tab === true;
    }

    // Writes the same stored option as the Configure form, so the two always agree. Shown
    // at the foot of the overview in both states - the way back has to live somewhere you
    // can find it, and the overview is the one tab that is always there.
    _renderTabsToggleCard() {
      if (this._beta === null) return '';
      const on = this._showAccountTab();
      // Only an administrator may change configuration, so for anybody else this is a
      // statement of how the panel is set up rather than a control.
      const allowed = this._beta.can_change !== false;

      return `
        <div class="card">
          <div class="control-row">
            <div class="control-label">
              Dashboard tabs (beta)
              <div class="control-sub">
                ${on
                  ? 'Charging, Usage, Perks and Account alongside this page. Turn off for the single screen.'
                  : 'Split the panel into Overview, Charging, Usage, Perks and Account. Nothing is taken off this page.'}
                ${allowed ? '' : ' Only an administrator can change this.'}
              </div>
            </div>
            ${allowed
              ? `<label class="toggle">
                   <input type="checkbox" id="tabs-toggle" ${on ? 'checked' : ''} ${this._tabsToggleBusy ? 'disabled' : ''}>
                   <div class="toggle-track"></div>
                   <div class="toggle-thumb"></div>
                 </label>`
              : `<span class="pill-past">${on ? 'On' : 'Off'}</span>`}
          </div>
        </div>`;
    }

    async _setShowTabs(enabled) {
      const accountId = this._findAccountId(this._hass);
      if (!accountId || this._tabsToggleBusy) return;
      this._tabsToggleBusy = true;
      // Moved straight away rather than after the round trip, so the switch does not feel
      // stuck; put back if the write is refused.
      const previous = this._beta;
      this._beta = { ...this._beta, show_account_tab: enabled };
      if (!enabled) this._activeTab = 'overview';
      this._render();
      try {
        await this._hass.callWS({ type: 'edf_energy/set_show_tabs', account_id: accountId, enabled });
      } catch (e) {
        this._beta = previous;
        this._toast(e?.message || 'Could not change that');
      }
      this._tabsToggleBusy = false;
      this._render();
    }

    async _loadPredictor(force = false) {
      if (this._predictorLoading || (this._predictor !== null && !force)) return;
      this._predictorLoading = true;
      try {
        this._predictor = await this._hass.callWS({ type: 'edf_energy/predictor' });
        this._predictorError = null;
      } catch (e) {
        this._predictorError = e?.message || 'Could not reach the Power Perks Predictor.';
      }
      this._predictorLoading = false;
      this._render();
    }

    // Steve's predictor, rendered here rather than framed: the site forbids framing, and a
    // frame would bring its own theme and chrome into a tab that is meant to match
    // everything around it. The art and the link come from the site so it still looks and
    // feels like his, and the link is there because the site is the real thing.
    _renderPredictorView() {
      const site = this._predictor?.site || 'https://powerperkspredictor.app';
      const art = u => `${site}/assets/${u}`;

      const header = `
        <div class="card predictor-head">
          <img class="predictor-art" src="${esc(art('mascot.webp'))}" alt="" width="180" height="139" loading="lazy">
          <div>
            <div class="section-title" style="padding-left:0">Power Perks Predictor</div>
            <div class="section-info" style="padding:0">
              Will EDF give away free electricity? This reads the day-ahead auction and the week's
              weather. Check the latest from anywhere at
              <a href="${esc(site)}" target="_blank" rel="noopener noreferrer">powerperkspredictor.app</a>.
            </div>
          </div>
        </div>`;

      if (this._predictorError) {
        return `${header}<div class="card"><div class="notice warn">${esc(this._predictorError)}</div></div>`;
      }
      if (this._predictor === null) {
        return `${header}<div class="card"><div class="empty">Asking the predictor…</div></div>`;
      }

      return `
        ${header}
        ${this._renderPredictorTomorrow(art)}
        ${this._renderPredictorOutlook()}
        ${this._renderPredictorRecord()}
        <div class="section-info" style="padding:0 16px 16px">
          Fetched from ${esc(site)} only while this tab is open - nothing is polled in the
          background and nothing is stored.
        </div>`;
    }

    _renderPredictorTomorrow(art) {
      const t = this._predictor?.tomorrow;
      if (!t) return '';
      // 'firm' means it has read the published auction rather than forecast it, which is the
      // difference between a call and a guess - so it is worth saying which this is.
      const firm = (t.status || '').toLowerCase() === 'firm';

      return `
        <div class="card">
          <div class="section-title" style="display:flex;align-items:center;gap:8px">
            <span style="flex:1">Tomorrow${t.date ? ` - ${esc(formatDay(t.date))}` : ''}</span>
            ${t.status ? `<span class="${firm ? 'pill-live' : 'pill-past'}">${esc(humanise(t.status))}</span>` : ''}
          </div>
          <div class="predictor-tomorrow">
            ${t.free ? `<img class="predictor-art small" src="${esc(art('next-art.webp'))}" alt="" width="242" height="208" loading="lazy">` : ''}
            <div style="flex:1;min-width:180px">
              <div class="predictor-verdict">${t.free ? 'Free electricity expected' : t.marginal ? 'Close, but probably not free' : 'No free electricity expected'}</div>
              ${t.windows.length
                ? `<div class="sub">${t.windows.map(w => esc([w.start, w.end].filter(Boolean).join(' - '))).join(' · ')}</div>`
                : ''}
              <div class="kv"><span class="k">Cheapest hour</span><span class="v">${t.cheapest_hour ? esc(t.cheapest_hour) : '—'}${
                t.cheapest_hour_price !== null && t.cheapest_hour_price !== undefined ? ` at ${t.cheapest_hour_price.toFixed(1)}p` : ''}</span></div>
              ${t.free_hours ? `<div class="kv"><span class="k">Free hours</span><span class="v">${t.free_hours}</span></div>` : ''}
              ${t.night_block_possible ? `<div class="kv"><span class="k">Overnight block</span><span class="v">Possible</span></div>` : ''}
            </div>
          </div>
          ${t.source ? `<div class="section-info">${esc(t.source)}</div>` : ''}
        </div>`;
    }

    _renderPredictorOutlook() {
      const o = this._predictor?.outlook;
      if (!o || !o.days.length) return '';

      return `
        <div class="card">
          <div class="section-title">The week ahead</div>
          ${o.days.map(d => `
            <div class="row predictor-day">
              <div class="main">
                <div class="title">${esc(formatDay(d.date))}
                  ${d.band ? `<span class="level ${esc(d.tone || 'unknown')}">${esc(d.band)}</span>` : ''}
                </div>
                ${d.summary ? `<div class="sub">${esc(d.summary)}</div>` : ''}
                ${d.factors.length
                  ? `<div class="predictor-factors">${d.factors.map(f =>
                      `<span class="factor"><ha-icon icon="${PREDICTOR_ICON[f.kind] || 'mdi:information-outline'}"></ha-icon>${esc(f.text)}${
                        f.trend ? ` <span class="trend">${f.trend === 'up' ? '↑' : f.trend === 'down' ? '↓' : '→'}</span>` : ''}</span>`).join('')}</div>`
                  : ''}
              </div>
            </div>`).join('')}
        </div>`;
    }

    _renderPredictorRecord() {
      const s = this._predictor?.scores;
      if (!s) return '';
      const hasTally = s.correct !== null && s.correct !== undefined && s.scored_days;

      return `
        <div class="card">
          <div class="section-title">How it has done</div>
          ${hasTally ? `
            <div class="figures">
              <div class="figure">
                <div class="label">Outlook called right</div>
                <div class="amount">${s.correct} of ${s.scored_days}</div>
                <div class="sub">days scored so far</div>
              </div>
            </div>` : ''}
          ${s.note ? `<div class="section-info">${esc(s.note)}</div>` : ''}
        </div>`;
    }

    // The tab bar only appears with the beta flag on. With it off the panel is exactly the
    // page it has always been: one screen, no chrome above it, nothing moved.
    _renderTabs() {
      if (!this._showAccountTab()) return '';
      const tab = (id, label) => `
        <button class="tab${this._activeTab === id ? ' active' : ''}" data-tab="${id}">${label}</button>`;
      return `<div class="tabs">
        ${tab('overview', 'Overview')}
        ${tab('charging', 'Charging')}
        ${tab('usage', 'Usage')}
        ${tab('predictor', 'Predictor')}
        ${tab('perks', 'Perks')}
        ${tab('account', 'Account')}
      </div>`;
    }

    _renderAgreement(agreement) {
      const live = agreement.is_active === true;
      // EDF only give us the codes here, not the name they market the tariff under. The
      // product code is the closest thing to a readable name, so it leads and the full
      // tariff code sits underneath for anyone matching it against a bill.
      return `
        <div class="agreement${live ? '' : ' past'}">
          <div class="agreement-head">
            <div class="name">${esc(agreement.product_code || agreement.tariff_code || 'Unknown tariff')}</div>
            <span class="${live ? 'pill-live' : 'pill-past'}">${live ? 'Live' : 'Ended'}</span>
          </div>
          <div class="kv"><span class="k">Tariff code</span><span class="v">${esc(agreement.tariff_code || '—')}</span></div>
          <div class="kv"><span class="k">Valid</span><span class="v">${esc(formatDateOnly(agreement.start) || '—')} – ${agreement.end ? esc(formatDateOnly(agreement.end)) : 'open ended'}</span></div>
        </div>`;
    }

    _renderMeterPoint(point, isGas) {
      const identifier = isGas ? point.mprn : point.mpan;
      const label = isGas ? 'Gas' : (point.is_export ? 'Electricity — Export' : 'Electricity — Import');
      const agreements = point.agreements || [];
      const current = agreements.filter(a => a.is_active === true);
      const past = agreements.filter(a => a.is_active !== true);

      return `
        <div class="card">
          <div class="section-title">${esc(label)}</div>
          <div style="padding:0 16px 12px">
            <div class="kv"><span class="k">${isGas ? 'MPRN' : 'MPAN'}</span><span class="v">${esc(identifier || '—')}</span></div>
            ${(point.meters || []).map(m => `
              <div class="kv"><span class="k">Meter serial</span><span class="v">${esc(m.serial_number || '—')}</span></div>
              ${m.manufacturer ? `<div class="kv"><span class="k">Make</span><span class="v">${esc([m.manufacturer, m.model].filter(Boolean).join(' '))}</span></div>` : ''}
              ${m.firmware ? `<div class="kv"><span class="k">Firmware</span><span class="v">${esc(m.firmware)}</span></div>` : ''}
              <div class="kv"><span class="k">Smart meter</span><span class="v">${m.is_smart_meter ? 'Yes' : 'No'}</span></div>
            `).join('')}
          </div>
          <div style="padding:0 16px 12px">
            ${current.length ? current.map(a => this._renderAgreement(a)).join('') : '<div class="empty">No agreement in force.</div>'}
            ${past.length ? `
              <div class="section-title" style="padding-left:0;margin-top:10px">Previous</div>
              ${past.map(a => this._renderAgreement(a)).join('')}
            ` : ''}
          </div>
        </div>`;
    }

    // ── Money: billing, statements, ledger, referrals, refunds ──────────────────

    // One shape for all of them: ask once, hold the answer, hold the error, and let a
    // refresh button clear it. `force` is what that button passes.
    async _loadBilling(force = false) {
      if (this._billingLoading || (this._billing !== null && !force)) return;
      const accountId = this._findAccountId(this._hass);
      if (!accountId) { this._billingError = 'No EDF account found.'; return; }
      this._billingLoading = true;
      try {
        this._billing = await this._hass.callWS({
          type: 'edf_energy/billing_summary', account_id: accountId,
        });
        this._billingError = null;
      } catch (e) {
        this._billingError = e?.message || 'Could not load the billing summary.';
      }
      this._billingLoading = false;
      this._render();
    }

    async _loadBills(force = false) {
      if (this._billsLoading || (this._bills !== null && !force)) return;
      const accountId = this._findAccountId(this._hass);
      if (!accountId) return;
      this._billsLoading = true;
      try {
        const result = await this._hass.callWS({
          type: 'edf_energy/bills', account_id: accountId,
        });
        this._bills = result;
        this._billsError = null;
      } catch (e) {
        this._billsError = e?.message || 'Could not load statements.';
      }
      this._billsLoading = false;
      this._render();
    }

    // Paging appends rather than replaces, so "older statements" grows the list the way
    // scrolling one would.
    async _loadMoreBills() {
      const accountId = this._findAccountId(this._hass);
      if (!accountId || this._billsLoading || !this._bills?.has_more) return;
      this._billsLoading = true;
      this._render();
      try {
        const page = await this._hass.callWS({
          type: 'edf_energy/bills', account_id: accountId, cursor: this._bills.cursor,
        });
        this._bills = {
          bills: [...(this._bills.bills || []), ...(page.bills || [])],
          cursor: page.cursor,
          has_more: page.has_more,
        };
      } catch (e) {
        this._billsError = e?.message || 'Could not load more statements.';
      }
      this._billsLoading = false;
      this._render();
    }

    // The link EDF hand back is pre-signed and expires within the hour, so it is fetched
    // at the moment it is wanted and opened straight away. Nothing holds on to it.
    async _openBill(billId, billType) {
      const accountId = this._findAccountId(this._hass);
      if (!accountId) return;
      this._billBusyId = billId;
      this._render();
      try {
        const attachment = await this._hass.callWS({
          type: 'edf_energy/bill_url', account_id: accountId,
          bill_id: String(billId), bill_type: billType || 'STATEMENT',
        });
        if (attachment?.url) window.open(attachment.url, '_blank', 'noopener');
        else this._toast('EDF have no document for that statement');
      } catch (e) {
        this._toast(e?.message || 'Could not open that statement');
      }
      this._billBusyId = null;
      this._render();
    }

    async _loadTransactions(force = false) {
      if (this._transactionsLoading || (this._transactions !== null && !force)) return;
      const accountId = this._findAccountId(this._hass);
      if (!accountId) return;
      this._transactionsLoading = true;
      try {
        this._transactions = await this._hass.callWS({
          type: 'edf_energy/transactions', account_id: accountId,
        });
        this._transactionsError = null;
      } catch (e) {
        this._transactionsError = e?.message || 'Could not load transactions.';
      }
      this._transactionsLoading = false;
      this._render();
    }

    async _loadMoreTransactions() {
      const accountId = this._findAccountId(this._hass);
      if (!accountId || this._transactionsLoading || !this._transactions?.has_more) return;
      this._transactionsLoading = true;
      this._render();
      try {
        const page = await this._hass.callWS({
          type: 'edf_energy/transactions', account_id: accountId, cursor: this._transactions.cursor,
        });
        this._transactions = {
          transactions: [...(this._transactions.transactions || []), ...(page.transactions || [])],
          cursor: page.cursor,
          has_more: page.has_more,
        };
      } catch (e) {
        this._transactionsError = e?.message || 'Could not load more transactions.';
      }
      this._transactionsLoading = false;
      this._render();
    }

    // Dismissals live in this browser only - there is nothing here worth a server round
    // trip, and storage can be unavailable or throw in a private window, so a failure to
    // read or write it just means the banner shows.
    _dismissKey(kind, token) { return `edf-energy-dismissed:${kind}:${token}`; }

    _isDismissed(kind, token) {
      if (!token) return false;
      try { return localStorage.getItem(this._dismissKey(kind, token)) !== null; }
      catch (e) { return false; }
    }

    _dismiss(kind, token) {
      if (!token) return;
      try { localStorage.setItem(this._dismissKey(kind, token), '1'); } catch (e) { /* not important enough to report */ }
      this._render();
    }

    async _loadNotices(force = false) {
      if (this._noticesLoading || (this._notices !== null && !force)) return;
      const accountId = this._findAccountId(this._hass);
      if (!accountId) return;
      this._noticesLoading = true;
      try {
        this._notices = await this._hass.callWS({ type: 'edf_energy/notices', account_id: accountId });
      } catch (e) {
        // An older backend has no such command. There is nothing useful to say about that
        // on screen, so the banners simply never appear.
        this._notices = { release: null, notice: null };
      }
      this._noticesLoading = false;
      this._render();
    }

    // The urgent notice shows on every tab, because it is the one that cannot wait for
    // somebody to wander back to the overview. The release banner is the overview's alone.
    _renderBanners(tab) {
      const data = this._notices;
      if (!data) return '';
      let out = '';

      const notice = data.notice;
      if (notice && notice.message && !this._isDismissed('notice', notice.id)) {
        const urgent = notice.severity === 'urgent';
        out += `
          <div class="banner${urgent ? ' urgent' : ''}">
            <ha-icon icon="${urgent ? 'mdi:alert' : 'mdi:information-outline'}"></ha-icon>
            <div class="banner-body">${esc(notice.message)}</div>
            ${notice.url ? `<a class="btn-link" href="${esc(notice.url)}" target="_blank" rel="noopener noreferrer">Details</a>` : ''}
            <button class="btn-link" data-dismiss="notice" data-token="${esc(notice.id)}">Dismiss</button>
          </div>`;
      }

      const release = data.release;
      if (tab === 'overview' && release && release.latest && !this._isDismissed('release', release.latest)) {
        out += `
          <div class="banner">
            <ha-icon icon="mdi:package-up"></ha-icon>
            <div class="banner-body">
              <strong>EDF Energy ${esc(release.latest)} is available.</strong>
              You are on ${esc(release.installed)} - update through HACS.
            </div>
            ${release.url ? `<a class="btn-link" href="${esc(release.url)}" target="_blank" rel="noopener noreferrer">Release notes</a>` : ''}
            <button class="btn-link" data-dismiss="release" data-token="${esc(release.latest)}">Dismiss</button>
          </div>`;
      }

      return out;
    }

    async _loadReferrals(force = false) {
      if (this._referralsLoading || (this._referrals !== null && !force)) return;
      const accountId = this._findAccountId(this._hass);
      if (!accountId) return;
      this._referralsLoading = true;
      try {
        this._referrals = await this._hass.callWS({
          type: 'edf_energy/referrals', account_id: accountId,
        });
        this._referralsError = null;
      } catch (e) {
        this._referralsError = e?.message || 'Could not load referrals.';
      }
      this._referralsLoading = false;
      this._render();
    }

    // Sent only after the confirm step, and the backend checks the amount against EDF's
    // own maximum again before it goes anywhere.
    async _requestRefund() {
      const accountId = this._findAccountId(this._hass);
      const amount = Number(this._refundAmount);
      if (!accountId || !Number.isFinite(amount) || amount <= 0) {
        this._toast('Enter the amount you want refunded');
        return;
      }
      this._refundBusy = true;
      this._refundConfirm = false;
      this._render();
      try {
        const result = await this._hass.callWS({
          type: 'edf_energy/request_refund', account_id: accountId, amount,
        });
        this._refundResult = result;
        this._refundAmount = '';
        this._toast(`Refund requested — ${humanise(result?.status)}`);
        // The backend clears its cache and re-polls, so pull the new position in rather
        // than leaving the card showing the state from before the request.
        this._billing = null;
        await this._loadBilling(true);
      } catch (e) {
        this._toast(e?.message || 'EDF would not accept that refund request');
      }
      this._refundBusy = false;
      this._render();
    }

    _renderRefreshButton(target) {
      return `<button class="btn-link" data-refresh="${target}">Refresh</button>`;
    }

    _renderBillingFigures() {
      if (this._billingError)
        return `<div class="card"><div class="no-entity">${esc(this._billingError)}</div></div>`;
      if (this._billing === null)
        return `<div class="card"><div class="empty">Loading account balance…</div></div>`;

      const b = this._billing;
      const bill = b.last_bill || {};
      const schedule = b.payment_schedule || {};
      const refund = b.refund || {};

      // A variable schedule means EDF collect whatever the period came to, so there is no
      // figure to show until the statement is cut - saying so beats showing £0.00.
      const paymentAmount = schedule.is_variable === true
        ? 'Varies'
        : money(schedule.amount);
      const paymentSub = schedule.day
        ? `${schedule.frequency ? humanise(schedule.frequency) : 'Monthly'}, on the ${ordinal(schedule.day)}`
        : 'No payment schedule';

      return `
        <div class="card">
          <div class="figures">
            <div class="figure">
              <div class="label">Balance</div>
              <div class="amount">${money(b.balance)}</div>
              <div class="sub">${b.balance >= 0 ? 'In credit' : 'Owed'}</div>
            </div>
            <div class="figure">
              <div class="label">Last bill</div>
              <div class="amount">${money(bill.amount)}</div>
              <div class="sub">${bill.issued_date ? esc(formatDay(bill.issued_date)) : 'No statements yet'}</div>
            </div>
            <div class="figure">
              <div class="label">Next payment</div>
              <div class="amount">${esc(paymentAmount)}</div>
              <div class="sub">${esc(paymentSub)}</div>
            </div>
            <div class="figure">
              <div class="label">Refundable</div>
              <div class="amount">${money(refund.maximum)}</div>
              <div class="sub">${refund.can_request === true ? 'Available to request' : 'EDF say not now'}</div>
            </div>
          </div>
        </div>`;
    }

    _renderBillsCard() {
      const bills = this._bills?.bills || [];
      return `
        <div class="card">
          <div class="section-title" style="display:flex;align-items:center;gap:8px">
            <span style="flex:1">Statements</span>
            ${this._renderRefreshButton('bills')}
          </div>
          ${this._billsError ? `<div class="notice warn">${esc(this._billsError)}</div>` : ''}
          ${this._bills === null
            ? '<div class="empty">Loading statements…</div>'
            : bills.length === 0
              ? '<div class="empty">No statements on this account yet.</div>'
              : bills.map(bill => `
                  <div class="row">
                    <div class="main">
                      <div class="title">${esc(formatDay(bill.from_date))} – ${esc(formatDay(bill.to_date))}</div>
                      <div class="sub">
                        Issued ${esc(formatDay(bill.issued_date))}${bill.due_date ? ` · due ${esc(formatDay(bill.due_date))}` : ''}
                        ${bill.is_final === true ? ' · final bill' : ''}
                      </div>
                    </div>
                    <div class="figure-right">
                      <div class="money">${money(bill.charges)}</div>
                      <div class="sub">bal ${money(bill.closing_balance)}</div>
                    </div>
                    <button class="btn-link" data-bill="${esc(String(bill.id))}" data-bill-type="${esc(bill.bill_type || 'STATEMENT')}"
                      ${this._billBusyId === bill.id ? 'disabled' : ''}>
                      ${this._billBusyId === bill.id ? 'Opening…' : 'Open'}
                    </button>
                  </div>`).join('')
          }
          ${this._bills?.has_more
            ? `<div class="load-more">
                 <button class="btn-link" data-action="more-bills" ${this._billsLoading ? 'disabled' : ''}>
                   ${this._billsLoading ? 'Loading…' : 'Older statements'}
                 </button>
               </div>`
            : ''}
          <div class="section-info">Statements open as a PDF straight from EDF. The link is created when you press Open and stops working shortly after, so nothing is stored here.</div>
        </div>`;
    }

    _renderTransactionsCard() {
      const transactions = this._transactions?.transactions || [];
      return `
        <div class="card">
          <div class="section-title" style="display:flex;align-items:center;gap:8px">
            <span style="flex:1">Transactions</span>
            ${this._renderRefreshButton('transactions')}
          </div>
          ${this._transactionsError ? `<div class="notice warn">${esc(this._transactionsError)}</div>` : ''}
          ${this._transactions === null
            ? '<div class="empty">Loading transactions…</div>'
            : transactions.length === 0
              ? '<div class="empty">No transactions on this account yet.</div>'
              : transactions.map(t => `
                  <div class="row">
                    <div class="main">
                      <div class="title">${esc(t.title || humanise(t.type))}</div>
                      <div class="sub">
                        ${esc(formatDay(t.posted_date || t.created_at))}
                        ${t.note ? ` · ${esc(t.note)}` : ''}
                        ${t.is_reversed === true ? ' · reversed' : ''}
                      </div>
                    </div>
                    <div class="figure-right">
                      <div class="money${moneyClass(t.signed_amount)}">${money(t.signed_amount, { signed: true })}</div>
                      ${t.balance_carried_forward !== null && t.balance_carried_forward !== undefined
                        ? `<div class="sub">bal ${money(t.balance_carried_forward)}</div>` : ''}
                    </div>
                  </div>`).join('')
          }
          ${this._transactions?.has_more
            ? `<div class="load-more">
                 <button class="btn-link" data-action="more-transactions" ${this._transactionsLoading ? 'disabled' : ''}>
                   ${this._transactionsLoading ? 'Loading…' : 'Older transactions'}
                 </button>
               </div>`
            : ''}
        </div>`;
    }

    _renderRefundCard() {
      if (this._billing === null) return '';
      const refund = this._billing.refund || {};
      const requests = refund.requests || [];
      const maximum = refund.maximum;
      // EDF's eligibility flag is advisory, not binding: requests have been accepted and paid
      // out on this account while it said no, with HAS_NOT_GIVEN_READINGS_RECENTLY as the
      // reason. So the reason is shown as a caveat and the form stays open - it is EDF's
      // decision to make when the request arrives, not ours to pre-empt.
      const discouraged = refund.can_request !== true;

      return `
        <div class="card">
          <div class="section-title">Refunds</div>
          <div style="padding:0 16px 10px">
            <div class="kv"><span class="k">Available to refund</span><span class="v">${money(maximum)}</span></div>
            <div class="kv"><span class="k">Account balance</span><span class="v">${money(this._billing.balance)}</span></div>
          </div>
          <div class="section-info">EDF only refund what has been paid in by direct debit, which is why the refundable amount is usually well below the balance.</div>
          ${discouraged
            ? `<div class="notice warn">
                 EDF say they are not accepting a refund request on this account${refund.reason ? ` — ${esc(humanise(refund.reason))}` : ''}.
                 They have paid out despite saying this before, so a request may still be worth making.
               </div>`
            : ''}
          ${`
              <div class="refund-row">
                <input class="amount-input" id="refund-amount" type="number" inputmode="decimal"
                  min="0.01" step="0.01" ${maximum ? `max="${maximum}"` : ''}
                  placeholder="0.00" value="${esc(this._refundAmount)}">
                ${maximum ? `<button class="btn-link" data-action="refund-max">Max (${money(maximum)})</button>` : ''}
                <button class="btn-apply${this._refundConfirm ? ' danger' : ''}" data-action="refund-request"
                  ${this._refundBusy ? 'disabled' : ''}>
                  ${this._refundBusy
                    ? 'Sending…'
                    : this._refundConfirm
                      ? `Confirm ${money(Number(this._refundAmount))}`
                      : 'Request refund'}
                </button>
              </div>
              ${this._refundConfirm
                ? `<div class="notice warn">This asks EDF to pay ${money(Number(this._refundAmount))} back to your bank account. Press confirm to send it.</div>`
                : ''}`
          }
          ${requests.length
            ? `
              <div class="section-title" style="margin-top:4px">Past requests</div>
              ${requests.map(r => `
                <div class="row">
                  <div class="main">
                    <div class="title">${money(r.amount)}</div>
                    <div class="sub">
                      ${r.reason ? esc(humanise(r.reason)) : 'Refund'}
                      ${r.payment_date ? ` · ${esc(formatDay(r.payment_date))}` : ''}
                    </div>
                  </div>
                  <span class="${(r.status || '').toUpperCase() === 'PAID' ? 'pill-live' : 'pill-past'}">${esc(humanise(r.status))}</span>
                </div>`).join('')}`
            : '<div class="empty">No refund requests on this account.</div>'
          }
        </div>`;
    }

    _renderReferralsCard() {
      const scheme = this._referrals?.scheme;
      const referrals = this._referrals?.referrals || [];

      // A referral counts as paid once EDF put a payment date on it; the status text is a
      // display string and reads differently between schemes, so the date is the safer test.
      const isPaid = r => !!r.payment_date || (r.status || '').toLowerCase() === 'paid';
      const sumRewards = list => list.reduce((total, r) => total + (Number(r.reward) || 0), 0);
      const paidList = referrals.filter(isPaid);
      const pendingList = referrals.filter(r => !isPaid(r));
      // EDF's own total is everything the link has earned, settled or not, so it is the two
      // figures added together rather than what has landed - on an account with 76 paid and 16
      // still switching it read higher than what has been paid. The split only comes from the
      // rows, and the total is kept to show alongside them.
      const paidTotal = sumRewards(paidList);
      const expectedTotal = sumRewards(pendingList);
      const schemeTotal = this._referrals?.total_earned;

      return `
        <div class="card">
          <div class="section-title" style="display:flex;align-items:center;gap:8px">
            <span style="flex:1">Referrals</span>
            ${this._renderRefreshButton('referrals')}
          </div>
          ${this._referralsError ? `<div class="notice warn">${esc(this._referralsError)}</div>` : ''}
          ${this._referrals === null
            ? '<div class="empty">Loading referrals…</div>'
            : `
              ${scheme || referrals.length ? `
                <div class="figures">
                  <div class="figure">
                    <div class="label">Joined on your link</div>
                    <div class="amount">${this._referrals.total ?? referrals.length}</div>
                    <div class="sub">${scheme?.code ? esc(scheme.code) : ''}</div>
                  </div>
                  <div class="figure">
                    <div class="label">Referral total</div>
                    <div class="amount">${money(schemeTotal ?? paidTotal + expectedTotal)}</div>
                    <div class="sub split"><span>${money(paidTotal)} paid</span><span>${paidList.length}</span></div>
                    <div class="sub split"><span>${money(expectedTotal)} pending</span><span>${pendingList.length}</span></div>
                  </div>
                  ${scheme ? `
                    <div class="figure">
                      <div class="label">You get</div>
                      <div class="amount">${money(scheme.referrer_reward)}</div>
                      <div class="sub">per sign up</div>
                    </div>
                    <div class="figure">
                      <div class="label">They get</div>
                      <div class="amount">${money(scheme.referred_reward)}</div>
                      <div class="sub">when they join</div>
                    </div>` : ''}
                </div>
                ${scheme?.url ? `
                  <div class="refund-row" style="padding-top:12px">
                    <div class="main" style="flex:1;min-width:0;word-break:break-all">${esc(scheme.display_url || scheme.url)}</div>
                    <button class="btn-link" data-action="copy-referral">Copy link</button>
                  </div>` : ''}
              ` : ''}
              ${referrals.length === 0
                ? '<div class="empty">Nobody has joined on your link yet.</div>'
                : referrals.map(r => `
                    <div class="row">
                      <div class="main">
                        <div class="title">${esc(r.name || 'Unnamed')}</div>
                        <div class="sub">
                          Joined ${esc(formatDay(r.joined))}
                          ${r.payment_date ? ` · paid ${esc(formatDay(r.payment_date))}` : ''}
                        </div>
                      </div>
                      <div class="figure-right"><div class="money">${money(r.reward)}</div></div>
                      <span class="${(r.status || '').toLowerCase() === 'paid' ? 'pill-live' : 'pill-past'}">${esc(r.status || 'Pending')}</span>
                    </div>`).join('')
              }`
          }
          <div class="section-info">Referral names come from EDF when this tab is open and are not stored in Home Assistant — there is no sensor or attribute holding them.</div>
        </div>`;
    }

    // ── Tab bodies ──────────────────────────────────────────────────────────────

    _renderAccountView() {
      if (this._accountError)
        return `<div class="card"><div class="no-entity">${esc(this._accountError)}</div></div>`;
      if (this._account === null)
        return `<div class="card"><div class="empty">Loading account information…</div></div>`;

      const electricity = this._account.electricity || [];
      const gas = this._account.gas || [];

      return `
        ${this._renderBillingFigures()}
        <div class="card">
          <div class="section-title">Account</div>
          <div style="padding:0 16px 12px">
            <div class="kv"><span class="k">Account number</span><span class="v">${esc(this._account.account_id || '—')}</span></div>
            ${this._billing?.status ? `<div class="kv"><span class="k">Status</span><span class="v">${esc(humanise(this._billing.status))}</span></div>` : ''}
          </div>
        </div>
        ${this._renderBillsCard()}
        ${this._renderTransactionsCard()}
        ${this._renderRefundCard()}
        <div class="section-title" style="padding-top:4px">Tariffs &amp; meters</div>
        ${electricity.map(p => this._renderMeterPoint(p, false)).join('')}
        ${gas.map(p => this._renderMeterPoint(p, true)).join('')}
        ${!electricity.length && !gas.length
          ? '<div class="card"><div class="empty">No meter points on this account.</div></div>' : ''}
        ${this._renderApiKeyCard()}`;
    }

    // Usage is the consumption chart and nothing else competing with it. The chart needs
    // the meter list from the account summary, so it says so rather than drawing empty.
    _renderUsageView() {
      if (this._accountError)
        return `<div class="card"><div class="no-entity">${esc(this._accountError)}</div></div>`;
      if (this._account === null)
        return `<div class="card"><div class="empty">Loading meters…</div></div>`;

      return `
        <div id="consumption-slot"></div>
        <div class="card">
          <div class="section-info">
            Consumption comes from the statistics this integration records, which are built from
            EDF's own half hourly readings. EDF publish those a day or two behind the meter, so the
            most recent day or two will usually be missing.
          </div>
        </div>`;
    }

    // Everything the account earns rather than spends: the schemes, the free hours, and
    // the referral link. The cards are the overview's own, so a change to one shows up in
    // both places.
    _renderPerksView(dayFreeSessions) {
      return `
        ${this._renderWorldCupCard()}
        ${this._renderFlextrasCard()}
        ${this._renderFlextrasHoursCard()}
        ${this._renderSundaySaverCard()}
        ${this._renderFreeSessionsCard(dayFreeSessions)}
        ${this._renderReferralsCard()}`;
    }

    // ── History cards ───────────────────────────────────────────────────────────
    // Lifted out of the one template render used to be, so the same cards can appear on
    // the overview and on the charging tab without being written twice.

    _renderDateNavCard(dates, canOlder, canNewer) {
      return `
              <div class="card">
                <div class="section-title">Off-Peak &amp; Dispatch History</div>
                <div class="section-info">A record of off-peak windows, Sunday Saver events, free electricity sessions, and smart charging dispatches for up to the past 60 days, accumulated as data is refreshed.</div>
                <div class="nav-row">
                  <button class="nav-btn" id="btn-older" ${!canOlder ? 'disabled' : ''} title="Older">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M15.41 7.41L14 6l-6 6 6 6 1.41-1.41L10.83 12z"/>
                    </svg>
                  </button>
                  <select class="date-select" id="date-select">
                    ${dates.map(dk =>
                      // Upcoming dates are marked, because the list only holds days that
                      // have data and future ones are sparse: a booking three weeks out
                      // sits straight after tomorrow, with nothing between. Without the
                      // marker that gap reads as missing days rather than days that have
                      // simply not been priced yet.
                      `<option value="${esc(dk)}"${dk === this._selectedDateKey ? ' selected' : ''}>${
                        esc(formatDateLabel(dk))}${isFutureDateKey(dk) ? ' — upcoming' : ''}</option>`
                    ).join('')}
                  </select>
                  <button class="nav-btn" id="btn-newer" ${!canNewer ? 'disabled' : ''} title="Newer">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z"/>
                    </svg>
                  </button>
                </div>
              </div>
      `;
    }

    _renderOffPeakCard(dayOffPeak) {
      return `
              <div class="card">
                <div class="section-title">Off-Peak Windows</div>
                ${dayOffPeak.length === 0
                  ? `<div class="empty">No off-peak windows recorded for this date.</div>`
                  : dayOffPeak.map(w => {
                      const colour = w.is_intelligent_adjusted ? '#7B1FA2' : '#1565C0';
                      const label  = w.is_intelligent_adjusted ? 'Smart Charging Extended' : 'Standard Tariff';
                      return `
                        <div class="item">
                          <div class="dot" style="background:${colour}"></div>
                          <div class="info">
                            <div class="time-str">
                              ${formatTime(w.start)} – ${formatTime(w.end)}
                              <span class="duration">(${formatDuration(w.start, w.end)})</span>
                            </div>
                            <div class="meta">
                              <span class="badge" style="background:${colour}">${label}</span>
                            </div>
                          </div>
                        </div>
                      `;
                    }).join('')
                }
              </div>
      `;
    }

    _renderSundaySaverWindowsCard(se, daySundaySaver) {
      return `
              ${se && daySundaySaver.length > 0 ? `<div class="card">
                <div class="section-title">Sunday Saver Windows</div>
                ${daySundaySaver.length === 0
                  ? `<div class="empty">No Sunday Saver events recorded for this date.</div>`
                  : daySundaySaver.map(w => {
                      const status = dispatchStatus(w.start, w.end);
                      const colour = DISPATCH_COLOUR[status];
                      return `
                        <div class="item">
                          <div class="dot" style="background:${colour}"></div>
                          <div class="info">
                            <div class="time-str">
                              ${formatTime(w.start)} – ${formatTime(w.end)}
                              <span class="duration">(${formatDuration(w.start, w.end)})</span>
                            </div>
                            <div class="meta">
                              ${w.free_hours != null ? `<span>${w.free_hours}h free</span>` : ''}
                              <span class="badge" style="background:${colour}">${DISPATCH_LABEL[status]}</span>
                            </div>
                          </div>
                        </div>
                      `;
                    }).join('')
                }
              </div>` : ''}
      `;
    }

    _renderFreeSessionsCard(dayFreeSessions) {
      return `
              ${dayFreeSessions.length ? `<div class="card">
                <div class="section-title">Free Electricity Sessions</div>
                ${dayFreeSessions.map(w => {
                      const status = dispatchStatus(w.start, w.end);
                      const colour = DISPATCH_COLOUR[status];
                      return `
                        <div class="item">
                          <div class="dot" style="background:${colour}"></div>
                          <div class="info">
                            <div class="time-str">
                              ${formatTime(w.start)} – ${formatTime(w.end)}
                              <span class="duration">(${formatDuration(w.start, w.end)})</span>
                            </div>
                            <div class="meta">
                              <span>${esc(freeSessionSourceLabel(w.source))}</span>
                              <span class="badge" style="background:${colour}">${DISPATCH_LABEL[status]}</span>
                            </div>
                          </div>
                        </div>
                      `;
                    }).join('')
                }
              </div>` : ''}
      `;
    }

    _renderDispatchesCard(de, dayDispatches, startedDispatches) {
      return `
              ${de ? `<div class="card">
                <div class="section-title">Smart Charging Dispatch Windows</div>
                ${dayDispatches.length === 0
                  ? `<div class="empty">No dispatch windows recorded for this date.</div>`
                  : dayDispatches.map(d => {
                      const status = dispatchStatus(d.start, d.end, startedDispatches);
                      const colour = DISPATCH_COLOUR[status];
                      return `
                        <div class="item">
                          <div class="dot" style="background:${colour}"></div>
                          <div class="info">
                            <div class="time-str">
                              ${formatTime(d.start)} – ${formatTime(d.end)}
                              <span class="duration">(${formatDuration(d.start, d.end)})</span>
                            </div>
                            <div class="meta">
                              ${d.charge_in_kwh != null && status !== 'cancelled' ? `<span>${Number(d.charge_in_kwh).toFixed(1)} kWh</span>` : ''}
                              ${d.source ? `<span>${esc(formatSource(d.source))}</span>` : ''}
                              <span class="badge" style="background:${colour}">${DISPATCH_LABEL[status]}</span>
                            </div>
                          </div>
                        </div>
                      `;
                    }).join('')
                }
              </div>` : ''}
      `;
    }

    // The day-by-day record: which day is being looked at, then what happened on it.
    _renderHistory(ctx) {
      if (ctx.dates.length === 0)
        return `<div class="card"><div class="empty">No data yet — check back after the next rate refresh.</div></div>`;

      return `
        ${this._renderDateNavCard(ctx.dates, ctx.canOlder, ctx.canNewer)}
        ${this._renderOffPeakCard(ctx.dayOffPeak)}
        ${this._renderSundaySaverWindowsCard(ctx.se, ctx.daySundaySaver)}
        ${this._renderFreeSessionsCard(ctx.dayFreeSessions)}
        ${this._renderDispatchesCard(ctx.de, ctx.dayDispatches, ctx.startedDispatches)}`;
    }

    // The overview is the page this panel has always been, unchanged. Everything the beta
    // tabs show is either a cut of this or new material of its own - nothing was taken
    // off here to make room for them.
    _renderOverviewView(ctx) {
      if (!ctx.hasAny)
        return `<div class="card"><div class="no-entity">No EDF Energy entities found. Check the integration is set up correctly.</div></div>`;

      return `
        ${this._renderAuthExpiryBanner()}
        ${this._renderControls(ctx.ids)}
        ${this._renderWorldCupCard()}
        ${this._renderFlextrasCard()}
        ${this._renderFlextrasHoursCard()}
        ${this._renderSundaySaverCard()}
        ${this._renderApiKeyCard()}
        ${this._renderHistory(ctx)}
        ${this._renderTabsToggleCard()}`;
    }

    // The charging tab is the overview with the perks and the account furniture taken
    // away: the car controls and the windows that drive them, nothing else.
    _renderChargingView(ctx) {
      if (!ctx.hasAny)
        return `<div class="card"><div class="no-entity">No EDF Energy entities found. Check the integration is set up correctly.</div></div>`;

      return `
        ${this._renderAuthExpiryBanner()}
        ${this._renderControls(ctx.ids)}
        ${this._renderDateNavCard(ctx.dates, ctx.canOlder, ctx.canNewer)}
        ${this._renderOffPeakCard(ctx.dayOffPeak)}
        ${this._renderDispatchesCard(ctx.de, ctx.dayDispatches, ctx.startedDispatches)}`;
    }

    // What each beta tab needs before it can draw. Fetched when the tab is first opened
    // rather than up front, so turning the flag on does not cost five GraphQL calls to
    // somebody who only ever looks at the charging screen.
    _loadForTab(tab) {
      if (tab === 'account') {
        this._loadBilling();
        this._loadBills();
        this._loadTransactions();
      } else if (tab === 'perks') {
        this._loadReferrals();
      } else if (tab === 'predictor') {
        // Only here: nothing fetches the predictor unless somebody opens its tab.
        this._loadPredictor();
      } else if (tab === 'overview') {
        // The at-a-glance figures at the top of the account tab are cheap and come from a
        // coordinator that is polling anyway, so the overview asks for them too.
        this._loadBilling();
      }
    }

    _render() {
      if (!this._hass) return;

      // Asked for once. Until it lands the panel draws exactly as it always has, so a
      // backend without the command - or with the flag off - is simply the old panel.
      if (this._beta === null && !this._betaLoading) {
        this._betaLoading = true;
        this._loadBetaFeatures();
      }

      if (this._showAccountTab() && this._account === null && !this._accountLoading && !this._accountError) {
        this._accountLoading = true;
        this._loadAccountSummary();
      }

      if (this._showAccountTab()) this._loadForTab(this._activeTab);

      // Not behind the beta flag: being told about a release, or about something urgent,
      // is not a beta feature.
      this._loadNotices();

      // Fetched over the websocket rather than from an entity, because the bookable days
      // and their slots are far too much state to put in attributes. Fired once; the card
      // renders empty until it lands and then re-renders itself.
      if (this._flex === null && !this._flexLoading) {
        this._flexLoading = true;
        this._loadFlextrasHours();
      }

      const de  = this._findDispatchEntity(this._hass);
      const oe  = this._findOffPeakEntity(this._hass);
      const se  = this._findSundaySaverEntity(this._hass);
      const fse = this._findFreeSessionsEntity(this._hass);
      const ids = this._getDeviceEntityIds(de, this._hass);

      const dispatches          = this._parseDispatches(de);
      const startedDispatches   = this._parseStartedDispatches(de);
      const offPeakWindows      = this._parseOffPeakWindows(oe);
      const sundaySaverWindows  = this._parseSundaySaverWindows(se);
      const freeSessionWindows  = this._parseFreeSessionWindows(fse);
      const dates               = this._allDates(dispatches, offPeakWindows, sundaySaverWindows, freeSessionWindows);

      // Open on today, not on dates[0]. The list is newest first, and until Flextras the
      // newest date was always today or tomorrow, so dates[0] was a reasonable default.
      // Flextras hours are booked up to three weeks ahead, so dates[0] became a date far
      // in the future and the panel opened on it looking like today's view.
      if (!this._selectedDateKey || !dates.includes(this._selectedDateKey))
        this._selectedDateKey = defaultDateKey(dates);

      const idx      = dates.indexOf(this._selectedDateKey);
      const canOlder = idx < dates.length - 1;
      const canNewer = idx > 0;

      const dayDispatches = dispatches
        .filter(d => localDateKey(d.start) === this._selectedDateKey)
        .sort((a, b) => new Date(a.start) - new Date(b.start));

      const dayOffPeak = offPeakWindows
        .filter(w => localDateKey(w.start) === this._selectedDateKey)
        .sort((a, b) => new Date(a.start) - new Date(b.start));

      const daySundaySaver = sundaySaverWindows
        .filter(w => localDateKey(w.start) === this._selectedDateKey)
        .sort((a, b) => new Date(a.start) - new Date(b.start));

      const dayFreeSessions = freeSessionWindows
        .filter(w => localDateKey(w.start) === this._selectedDateKey)
        .sort((a, b) => new Date(a.start) - new Date(b.start));

      const deviceLabel = this._deviceLabel(de);
      const stateLabel  = this._stateLabel(de);
      const isActive    = de?.state === 'on';
      const hasAny      = de || oe || se || fse;

      const ctx = {
        de, oe, se, fse, ids, dates, idx, canOlder, canNewer, hasAny,
        dispatches, startedDispatches, dayDispatches, dayOffPeak, daySundaySaver, dayFreeSessions,
      };

      // With the flag off there is one tab and it is the overview, so the switch below
      // collapses to the page as it was.
      const showTabs = this._showAccountTab();
      const tab = showTabs ? this._activeTab : 'overview';
      let body;
      if (tab === 'account')      body = this._renderAccountView();
      else if (tab === 'usage')   body = this._renderUsageView();
      else if (tab === 'predictor') body = this._renderPredictorView();
      else if (tab === 'perks')   body = this._renderPerksView(dayFreeSessions);
      else if (tab === 'charging') body = this._renderChargingView(ctx);
      else                        body = this._renderOverviewView(ctx);

      // The toolbar names the tab rather than always claiming to be the charging screen,
      // which is what it did when it was the only thing here. With the tabs hidden there is
      // no tab to name, so that original title is kept rather than relabelling the one screen
      // non-beta users see.
      const tabTitle = showTabs
        ? ({ overview: 'Overview', account: 'Account', usage: 'Usage', perks: 'Perks', charging: 'Smart Charging',
             predictor: 'Power Perks Predictor' }[tab]
            || 'Overview')
        : (de ? 'Smart Charging' : null);

      this.shadowRoot.innerHTML = `
        <style>${STYLES}</style>

        <div class="toolbar">
          <button class="menu-btn" id="menu-btn" title="Menu">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
              <path d="M3 18h18v-2H3v2zm0-5h18v-2H3v2zm0-7v2h18V6H3z"/>
            </svg>
          </button>
          <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor" style="flex-shrink:0">
            <path d="M7 2v11h3v9l7-12h-4l4-8z"/>
          </svg>
          <div style="flex:1;min-width:0">
            <div class="toolbar-title">EDF Energy${tabTitle ? ` \u00b7 ${esc(tabTitle)}` : ''}</div>
            ${deviceLabel ? `<div class="toolbar-sub">${esc(deviceLabel)}</div>` : ''}
          </div>
          ${stateLabel ? `<div class="status-pill${isActive ? ' on' : ''}">${esc(stateLabel)}</div>` : ''}
        </div>

        ${this._renderTabs()}

        <div class="content">${this._renderBanners(tab)}${body}</div>
      `;

      this._attachListeners(ids, dates, idx, canOlder, canNewer);
    }

    _attachListeners(ids, dates, idx, canOlder, canNewer) {
      const root = this.shadowRoot;

      // ── Consumption card ──────────────────────────────────────────────────
      // Re-homed rather than recreated on every render, so changing period or unit is not
      // undone the next time a coordinator refresh redraws the panel.
      const slot = root.getElementById('consumption-slot');
      if (slot && this._account) {
        if (!this._consumptionCard)
          this._consumptionCard = document.createElement('edf-energy-consumption-card');
        if (!slot.contains(this._consumptionCard)) slot.appendChild(this._consumptionCard);

        const card = this._consumptionCard;
        const feed = () => {
          card.hass = this._hass;
          card.meters = [
            ...(this._account.electricity || []),
            ...(this._account.gas || []),
          ];
        };
        // The card's script is loaded alongside this one and may not have defined the
        // element yet. Setting properties on it before then would shadow its setters and
        // the card would never draw, so wait for the definition the first time.
        if (customElements.get('edf-energy-consumption-card')) feed();
        else customElements.whenDefined('edf-energy-consumption-card').then(feed);
      }

      root.getElementById('tabs-toggle')?.addEventListener('change', e => {
        this._setShowTabs(e.target.checked);
      });

      root.querySelectorAll('[data-dismiss]').forEach(btn => {
        btn.addEventListener('click', () => this._dismiss(btn.dataset.dismiss, btn.dataset.token));
      });

      // ── Tab switching ─────────────────────────────────────────────────────
      root.querySelectorAll('.tab').forEach(btn => {
        btn.addEventListener('click', () => {
          this._activeTab = btn.dataset.tab;
          this._render();
        });
      });

      // ── Statements, ledger, referrals, refunds ────────────────────────────
      root.querySelectorAll('[data-refresh]').forEach(btn => {
        btn.addEventListener('click', () => {
          const target = btn.dataset.refresh;
          if (target === 'bills') { this._bills = null; this._loadBills(true); }
          else if (target === 'transactions') { this._transactions = null; this._loadTransactions(true); }
          else if (target === 'referrals') { this._referrals = null; this._loadReferrals(true); }
          this._billing = null;
          this._loadBilling(true);
        });
      });

      root.querySelectorAll('[data-bill]').forEach(btn => {
        btn.addEventListener('click', () => this._openBill(btn.dataset.bill, btn.dataset.billType));
      });

      root.querySelector('[data-action="more-bills"]')?.addEventListener('click', () => this._loadMoreBills());
      root.querySelector('[data-action="more-transactions"]')?.addEventListener('click', () => this._loadMoreTransactions());

      root.querySelector('[data-action="copy-referral"]')?.addEventListener('click', async () => {
        const url = this._referrals?.scheme?.url;
        if (!url) return;
        try {
          await navigator.clipboard.writeText(url);
          this._toast('Referral link copied');
        } catch (err) {
          this._toast('Copy failed — select the link and copy it manually');
        }
      });

      // Held in state rather than read off the input when the button is pressed, because a
      // coordinator refresh can re-render between typing the amount and sending it.
      const refundInput = root.getElementById('refund-amount');
      refundInput?.addEventListener('input', e => {
        this._refundAmount = e.target.value;
        // A changed amount is a different request, so a confirm already armed no longer
        // applies to it.
        this._refundConfirm = false;
      });

      root.querySelector('[data-action="refund-max"]')?.addEventListener('click', () => {
        const maximum = this._billing?.refund?.maximum;
        if (maximum === null || maximum === undefined) return;
        this._refundAmount = String(maximum);
        this._refundConfirm = false;
        this._render();
      });

      root.querySelector('[data-action="refund-request"]')?.addEventListener('click', () => {
        const amount = Number(this._refundAmount);
        if (!Number.isFinite(amount) || amount <= 0) {
          this._toast('Enter the amount you want refunded');
          return;
        }
        const maximum = this._billing?.refund?.maximum;
        if (maximum !== null && maximum !== undefined && amount > maximum) {
          this._toast(`EDF will only refund up to ${money(maximum)}`);
          return;
        }
        // Two presses, deliberately. The first arms it and says what it is about to do;
        // the second sends it. Money leaves the account on the second one.
        if (!this._refundConfirm) {
          this._refundConfirm = true;
          this._render();
          clearTimeout(this._refundConfirmTimer);
          this._refundConfirmTimer = setTimeout(() => {
            this._refundConfirm = false;
            this._render();
          }, 10000);
          return;
        }
        clearTimeout(this._refundConfirmTimer);
        this._requestRefund();
      });

      // ── Menu button (opens HA navigation sidebar) ─────────────────────────
      root.getElementById('menu-btn')?.addEventListener('click', () => {
        // Fire on window (where HA's shell listens) and bubble out of the shadow root
        window.dispatchEvent(new CustomEvent('hass-toggle-menu'));
        this.dispatchEvent(new CustomEvent('hass-toggle-menu', { bubbles: true, composed: true }));
      });

      // ── Date navigation ────────────────────────────────────────────────────
      root.getElementById('date-select')?.addEventListener('change', e => {
        this._selectedDateKey = e.target.value;
        this._render();
      });
      root.getElementById('btn-older')?.addEventListener('click', () => {
        if (canOlder) { this._selectedDateKey = dates[idx + 1]; this._render(); }
      });
      root.getElementById('btn-newer')?.addEventListener('click', () => {
        if (canNewer) { this._selectedDateKey = dates[idx - 1]; this._render(); }
      });

      // ── World Cup opt-in toggle ────────────────────────────────────────────
      root.getElementById('football-toggle')?.addEventListener('change', e => {
        const accountId = this._findAccountId(this._hass);
        const data = accountId ? { enabled: e.target.checked, account_id: accountId } : { enabled: e.target.checked };
        this._hass.callService('edf_energy', 'set_football_free_electricity', data);
      });

      // ── API key reveal / copy ──────────────────────────────────────────────
      root.getElementById('api-key-reveal')?.addEventListener('click', async () => {
        if (this._apiKeyRevealed) {
          this._apiKeyRevealed = false;
          this._render();
          return;
        }
        const key = await this._fetchApiKey();
        if (key) { this._apiKeyRevealed = true; this._render(); }
      });
      root.getElementById('api-key-copy')?.addEventListener('click', async () => {
        const key = await this._fetchApiKey();
        if (!key) return;
        try {
          await navigator.clipboard.writeText(key);
          this._toast('API key copied');
        } catch (err) {
          this._toast('Copy failed — reveal and copy manually');
        }
      });

      // ── EV control toggle switches ─────────────────────────────────────────
      root.querySelectorAll('.toggle input[type=checkbox]:not(#football-toggle):not(#tabs-toggle)').forEach(checkbox => {
        checkbox.addEventListener('change', e => {
          this._callSwitch(e.target.dataset.entity, e.target.checked);
        });
      });

      // ── Charge target slider (live label update, Set button to apply) ──────
      const slider = root.getElementById('slider-charge-target');
      const sliderVal = root.getElementById('slider-charge-value');
      if (slider && sliderVal) {
        slider.addEventListener('input', e => {
          sliderVal.textContent = `${e.target.value}%`;
          this._pending[slider.dataset.entity] = e.target.value;
        });
      }

      root.querySelector('[data-action="set-charge-target"]')?.addEventListener('click', () => {
        const val = root.getElementById('slider-charge-target')?.value;
        if (val && ids.chargeTarget) this._callNumber(ids.chargeTarget, parseInt(val, 10));
      });

      // ── Ready-by time select (Set button to apply) ────────────────────────
      const timeSelect = root.getElementById('select-target-time');
      if (timeSelect) {
        timeSelect.addEventListener('change', e => {
          this._pending[timeSelect.dataset.entity] = e.target.value;
        });
      }

      root.querySelector('[data-action="set-target-time"]')?.addEventListener('click', () => {
        const val = root.getElementById('select-target-time')?.value;
        if (val && ids.targetTime) this._callTime(ids.targetTime, val);
      });

      // ── Flextras free hour booking ────────────────────────────────────────
      root.querySelectorAll('[data-flex-day]').forEach(chip => {
        chip.addEventListener('click', () => {
          const date = chip.dataset.flexDay;
          this._flexOpenDate = this._flexOpenDate === date ? null : date;
          if (this._flexOpenDate && !this._flexSlots[this._flexOpenDate]) {
            this._loadFlextrasDaySlots(this._flexOpenDate);
          }
          this._render();
        });
      });

      root.querySelectorAll('[data-flex-slot]').forEach(slot => {
        slot.addEventListener('click', () => {
          const key = slot.dataset.flexSlot;
          if (!this._flexSel) this._flexResetSelection();
          if (this._flexSel.has(key)) this._flexSel.delete(key);
          else this._flexSel.add(key);
          this._render();
        });
      });

      root.querySelector('[data-action="flex-save"]')?.addEventListener('click', () => {
        this._saveFlextrasHours([...(this._flexSel || [])].sort());
      });

      root.querySelector('[data-action="flex-revert"]')?.addEventListener('click', () => {
        this._flexResetSelection();
        this._render();
      });

      root.querySelector('[data-action="flex-cancel-all"]')?.addEventListener('click', () => {
        if (!this._flexConfirmCancel) {
          this._flexConfirmCancel = true;
          this._render();
          // Arm it only briefly, so it cannot sit waiting to be hit by accident later.
          clearTimeout(this._flexConfirmTimer);
          this._flexConfirmTimer = setTimeout(() => {
            this._flexConfirmCancel = false;
            this._render();
          }, 5000);
          return;
        }
        clearTimeout(this._flexConfirmTimer);
        this._flexConfirmCancel = false;
        this._saveFlextrasHours([]);
      });

      root.querySelector('[data-action="join-flextras"]')?.addEventListener('click', e => {
        // Guard against a double-tap firing two registrations.
        e.target.disabled = true;
        e.target.textContent = 'Joining…';
        this._hass.callService('edf_energy', 'join_flextras', {});
      });
    }
  }

  if (!customElements.get('edf-energy-panel')) {
    customElements.define('edf-energy-panel', EDFEnergyPanel);
    console.info(
      '%c EDF ENERGY PANEL %c Loaded ',
      'color:#fff;background:#1a237e;font-weight:700;padding:1px 6px;border-radius:3px 0 0 3px',
      'background:#3949ab;color:#fff;padding:1px 6px;border-radius:0 3px 3px 0'
    );
  }
})();

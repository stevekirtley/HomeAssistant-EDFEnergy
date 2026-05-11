(function () {
  'use strict';

  // ── Helpers ──────────────────────────────────────────────────────────────────

  function localDateKey(date) {
    const d = new Date(date);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  }

  function formatDateLabel(key) {
    const [y, m, d] = key.split('-').map(Number);
    return new Date(y, m - 1, d).toLocaleDateString(undefined, {
      weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
    });
  }

  function formatTime(date) {
    return new Date(date).toLocaleTimeString(undefined, {
      hour: '2-digit', minute: '2-digit', hour12: false,
    });
  }

  function formatDuration(start, end) {
    const mins = Math.round((new Date(end) - new Date(start)) / 60000);
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    if (h === 0) return `${m}m`;
    return m === 0 ? `${h}h` : `${h}h ${m}m`;
  }

  function formatSource(source) {
    if (!source) return '';
    return source.toLowerCase().replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  }

  function esc(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function getDispatchStatus(start, end) {
    const now = Date.now();
    if (new Date(end) <= now)   return 'completed';
    if (new Date(start) <= now) return 'active';
    return 'planned';
  }

  const DISPATCH_COLOUR = { completed: '#4CAF50', active: '#FF9800', planned: '#2196F3' };
  const DISPATCH_LABEL  = { completed: 'Completed', active: 'Active',    planned: 'Planned'   };

  // ── CSS shared by both card sections ─────────────────────────────────────────

  const STYLES = `
    :host {
      display: block;
      height: 100%;
      background: var(--primary-background-color);
      overflow-y: auto;
      box-sizing: border-box;
    }

    .toolbar {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 0 16px;
      height: 56px;
      background: var(--app-header-background-color, var(--primary-color, #3d5afe));
      color: var(--app-header-text-color, #fff);
      box-shadow: 0 2px 4px rgba(0,0,0,.2);
      position: sticky;
      top: 0;
      z-index: 10;
    }
    .toolbar-title { font-size: 1.1em; font-weight: 500; flex: 1; }
    .toolbar-sub   { font-size: 0.8em; opacity: 0.85; }
    .status-pill {
      font-size: 0.75em;
      font-weight: 600;
      padding: 3px 10px;
      border-radius: 12px;
      background: rgba(255,255,255,0.2);
      white-space: nowrap;
    }
    .status-pill.on { background: #4CAF50; }

    .content {
      max-width: 720px;
      margin: 0 auto;
      padding: 20px 16px 40px;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    .card {
      background: var(--card-background-color, #fff);
      border-radius: var(--ha-card-border-radius, 12px);
      box-shadow: var(--ha-card-box-shadow, 0 2px 6px rgba(0,0,0,.1));
      overflow: hidden;
    }

    .nav-row {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 12px 16px;
    }
    .nav-btn {
      background: none;
      border: none;
      border-radius: 50%;
      padding: 6px;
      cursor: pointer;
      color: var(--primary-text-color);
      display: flex;
      align-items: center;
      transition: background 0.15s;
      flex-shrink: 0;
    }
    .nav-btn:hover:not(:disabled) {
      background: rgba(var(--rgb-primary-text-color,0,0,0), 0.06);
    }
    .nav-btn:disabled { opacity: 0.3; cursor: default; }
    .date-select {
      flex: 1;
      background: var(--input-fill-color, var(--secondary-background-color, #f5f5f5));
      border: 1px solid var(--divider-color, #e0e0e0);
      border-radius: 6px;
      color: var(--primary-text-color);
      font-size: 1em;
      padding: 8px 12px;
      cursor: pointer;
      font-family: inherit;
      text-align: center;
    }
    .date-select:focus {
      outline: 2px solid var(--primary-color, #3d5afe);
      outline-offset: -1px;
    }

    .section-title {
      font-size: 0.75em;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--secondary-text-color);
      padding: 14px 16px 6px;
    }
    .empty {
      color: var(--secondary-text-color);
      font-size: 0.9em;
      text-align: center;
      padding: 20px 16px;
    }
    .no-entity {
      padding: 24px;
      color: var(--secondary-text-color);
      font-size: 0.9em;
      text-align: center;
    }

    .item {
      display: flex;
      gap: 14px;
      padding: 12px 16px;
      border-bottom: 1px solid var(--divider-color, #e0e0e0);
      align-items: flex-start;
    }
    .item:last-child { border-bottom: none; }
    .dot {
      width: 10px; height: 10px;
      border-radius: 50%;
      margin-top: 5px;
      flex-shrink: 0;
    }
    .info { flex: 1; min-width: 0; }
    .time {
      font-size: 1em;
      font-weight: 500;
      color: var(--primary-text-color);
    }
    .duration {
      font-weight: 400;
      color: var(--secondary-text-color);
      font-size: 0.875em;
    }
    .meta {
      font-size: 0.82em;
      color: var(--secondary-text-color);
      margin-top: 4px;
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      align-items: center;
    }
    .badge {
      border-radius: 10px;
      padding: 2px 8px;
      font-size: 0.8em;
      font-weight: 600;
      color: #fff;
    }
  `;

  // ── Panel element ─────────────────────────────────────────────────────────────

  class EDFEnergyPanel extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: 'open' });
      this._hass = null;
      this._selectedDateKey = null;
      this._lastChanged = null;
    }

    set hass(hass) {
      // Re-render only when a relevant entity changes
      const dispatchEntity = this._findDispatchEntity(hass);
      const offPeakEntity  = this._findOffPeakEntity(hass);
      const token = [
        dispatchEntity?.last_changed,
        offPeakEntity?.last_changed,
      ].join('|');

      if (token === this._lastChanged && this.shadowRoot.children.length > 0) {
        this._hass = hass;
        return;
      }

      this._lastChanged = token;
      this._hass = hass;
      this._render();
    }

    set panel(panel) {
      this._panel = panel;
    }

    // ── Entity discovery ────────────────────────────────────────────────────────

    _findDispatchEntity(hass) {
      if (!hass) return null;
      for (const [id, state] of Object.entries(hass.states)) {
        if (id.startsWith('binary_sensor.') && id.includes('edf_energy') && id.endsWith('_intelligent_dispatching'))
          return state;
      }
      return null;
    }

    _findOffPeakEntity(hass) {
      if (!hass) return null;
      for (const [id, state] of Object.entries(hass.states)) {
        // Exclude export meters (_export_off_peak)
        if (id.startsWith('binary_sensor.') && id.includes('edf_energy') &&
            id.endsWith('_off_peak') && !id.includes('_export_'))
          return state;
      }
      return null;
    }

    // ── Data parsing ────────────────────────────────────────────────────────────

    _parseDispatches(entity) {
      if (!entity) return [];
      const { completed_dispatches = [], planned_dispatches = [] } = entity.attributes;
      const seen = new Set();
      const result = [];
      for (const d of [...completed_dispatches, ...planned_dispatches]) {
        const key = `${d.start}|${d.end}`;
        if (!seen.has(key)) {
          seen.add(key);
          result.push({ start: d.start, end: d.end, charge_in_kwh: d.charge_in_kwh ?? null, source: d.source ?? null });
        }
      }
      return result;
    }

    _parseOffPeakWindows(entity) {
      if (!entity) return [];
      return (entity.attributes.off_peak_windows || []).map(w => ({
        start: w.start,
        end:   w.end,
        is_intelligent_adjusted: w.is_intelligent_adjusted ?? false,
      }));
    }

    // ── Date helpers ────────────────────────────────────────────────────────────

    _allDates(dispatches, offPeakWindows) {
      const keys = new Set([
        ...dispatches.map(d => localDateKey(d.start)),
        ...offPeakWindows.map(w => localDateKey(w.start)),
      ]);
      return [...keys].sort((a, b) => b.localeCompare(a)); // newest first
    }

    // ── Device info helpers ─────────────────────────────────────────────────────

    _deviceLabel(entity) {
      const a = entity?.attributes || {};
      const parts = [a.provider];
      if (a.vehicle_battery_size_in_kwh) parts.push(`${a.vehicle_battery_size_in_kwh} kWh battery`);
      if (a.charge_point_power_in_kw)    parts.push(`${a.charge_point_power_in_kw} kW charger`);
      return parts.filter(Boolean).join(' · ');
    }

    _currentStateLabel(dispatchEntity) {
      if (!this._hass || !dispatchEntity) return null;
      const devicePart = dispatchEntity.entity_id
        .replace('binary_sensor.edf_energy_', '')
        .replace('_intelligent_dispatching', '');
      const stateEntity = this._hass.states[`sensor.edf_energy_${devicePart}_intelligent_state`];
      if (!stateEntity) return null;
      return stateEntity.state
        .replace(/_/g, ' ')
        .toLowerCase()
        .replace(/\b\w/g, c => c.toUpperCase());
    }

    // ── Render ──────────────────────────────────────────────────────────────────

    _render() {
      if (!this._hass) return;

      const dispatchEntity  = this._findDispatchEntity(this._hass);
      const offPeakEntity   = this._findOffPeakEntity(this._hass);

      const dispatches      = this._parseDispatches(dispatchEntity);
      const offPeakWindows  = this._parseOffPeakWindows(offPeakEntity);
      const dates           = this._allDates(dispatches, offPeakWindows);

      if (!this._selectedDateKey || !dates.includes(this._selectedDateKey))
        this._selectedDateKey = dates[0] || null;

      const idx      = dates.indexOf(this._selectedDateKey);
      const canOlder = idx < dates.length - 1;
      const canNewer = idx > 0;

      const dayDispatches = dispatches
        .filter(d => localDateKey(d.start) === this._selectedDateKey)
        .sort((a, b) => new Date(a.start) - new Date(b.start));

      const dayOffPeak = offPeakWindows
        .filter(w => localDateKey(w.start) === this._selectedDateKey)
        .sort((a, b) => new Date(a.start) - new Date(b.start));

      const deviceLabel = this._deviceLabel(dispatchEntity);
      const stateLabel  = this._currentStateLabel(dispatchEntity);
      const isActive    = dispatchEntity?.state === 'on';

      const hasAny = dispatchEntity || offPeakEntity;

      this.shadowRoot.innerHTML = `
        <style>${STYLES}</style>

        <div class="toolbar">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor" style="flex-shrink:0">
            <path d="M7 2v11h3v9l7-12h-4l4-8z"/>
          </svg>
          <div style="flex:1;min-width:0">
            <div class="toolbar-title">EDF Energy · Smart Charging</div>
            ${deviceLabel ? `<div class="toolbar-sub">${esc(deviceLabel)}</div>` : ''}
          </div>
          ${stateLabel ? `<div class="status-pill${isActive ? ' on' : ''}">${esc(stateLabel)}</div>` : ''}
        </div>

        <div class="content">
          ${!hasAny
            ? `<div class="card"><div class="no-entity">No EDF Energy Smart Charging entities found. Make sure the integration is set up with an Intelligent tariff.</div></div>`
            : dates.length === 0
            ? `<div class="card"><div class="empty">No dispatch or off-peak data recorded yet. Check back after the next rate refresh.</div></div>`
            : `
            <!-- Date navigation -->
            <div class="card">
              <div class="nav-row">
                <button class="nav-btn" id="btn-older" ${!canOlder ? 'disabled' : ''} title="Older">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M15.41 7.41L14 6l-6 6 6 6 1.41-1.41L10.83 12z"/>
                  </svg>
                </button>
                <select class="date-select" id="date-select">
                  ${dates.map(dk =>
                    `<option value="${esc(dk)}"${dk === this._selectedDateKey ? ' selected' : ''}>${esc(formatDateLabel(dk))}</option>`
                  ).join('')}
                </select>
                <button class="nav-btn" id="btn-newer" ${!canNewer ? 'disabled' : ''} title="Newer">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z"/>
                  </svg>
                </button>
              </div>
            </div>

            <!-- Off-peak windows -->
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
                          <div class="time">
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

            <!-- Smart Charging dispatch windows -->
            <div class="card">
              <div class="section-title">Smart Charging Dispatch Windows</div>
              ${dayDispatches.length === 0
                ? `<div class="empty">No dispatch windows recorded for this date.</div>`
                : dayDispatches.map(d => {
                    const status = getDispatchStatus(d.start, d.end);
                    const colour = DISPATCH_COLOUR[status];
                    return `
                      <div class="item">
                        <div class="dot" style="background:${colour}"></div>
                        <div class="info">
                          <div class="time">
                            ${formatTime(d.start)} – ${formatTime(d.end)}
                            <span class="duration">(${formatDuration(d.start, d.end)})</span>
                          </div>
                          <div class="meta">
                            ${d.charge_in_kwh != null ? `<span>${d.charge_in_kwh.toFixed(1)} kWh</span>` : ''}
                            ${d.source ? `<span>${esc(formatSource(d.source))}</span>` : ''}
                            <span class="badge" style="background:${colour}">${DISPATCH_LABEL[status]}</span>
                          </div>
                        </div>
                      </div>
                    `;
                  }).join('')
              }
            </div>
          `}
        </div>
      `;

      if (hasAny && dates.length > 0) {
        this.shadowRoot.getElementById('date-select')?.addEventListener('change', e => {
          this._selectedDateKey = e.target.value;
          this._render();
        });
        this.shadowRoot.getElementById('btn-older')?.addEventListener('click', () => {
          if (canOlder) { this._selectedDateKey = dates[idx + 1]; this._render(); }
        });
        this.shadowRoot.getElementById('btn-newer')?.addEventListener('click', () => {
          if (canNewer) { this._selectedDateKey = dates[idx - 1]; this._render(); }
        });
      }
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

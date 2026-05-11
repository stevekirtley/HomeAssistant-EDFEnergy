(function () {
  'use strict';

  // ── Helpers ──────────────────────────────────────────────────────────────────

  function localDateKey(date) {
    const d = new Date(date);
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
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

  function formatSource(source) {
    if (!source) return '';
    return source.toLowerCase().replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  }

  function esc(str) {
    return String(str)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function dispatchStatus(start, end) {
    const now = Date.now();
    if (new Date(end) <= now)   return 'completed';
    if (new Date(start) <= now) return 'active';
    return 'planned';
  }

  const DISPATCH_COLOUR = { completed: '#4CAF50', active: '#FF9800', planned: '#2196F3' };
  const DISPATCH_LABEL  = { completed: 'Completed', active: 'Active',    planned: 'Planned'   };

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
  `;

  // ── Panel element ─────────────────────────────────────────────────────────────

  class EDFEnergyPanel extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: 'open' });
      this._hass = null;
      this._selectedDateKey = null;
      this._lastChanged = null;
      // Track pending edits so a mid-typing re-render doesn't overwrite inputs
      this._pending = {};  // { entityId: value }
    }

    set hass(hass) {
      const de = this._findDispatchEntity(hass);
      const oe = this._findOffPeakEntity(hass);
      const ids = this._getDeviceEntityIds(de, hass);
      const token = [
        de?.last_changed, oe?.last_changed,
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

    _parseOffPeakWindows(entity) {
      if (!entity) return [];
      return entity.attributes.off_peak_windows || [];
    }

    _allDates(dispatches, offPeakWindows) {
      const keys = new Set([
        ...dispatches.map(d => localDateKey(d.start)),
        ...offPeakWindows.map(w => localDateKey(w.start)),
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

    // ── Full render ─────────────────────────────────────────────────────────────

    _render() {
      if (!this._hass) return;

      const de  = this._findDispatchEntity(this._hass);
      const oe  = this._findOffPeakEntity(this._hass);
      const ids = this._getDeviceEntityIds(de, this._hass);

      const dispatches     = this._parseDispatches(de);
      const offPeakWindows = this._parseOffPeakWindows(oe);
      const dates          = this._allDates(dispatches, offPeakWindows);

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

      const deviceLabel = this._deviceLabel(de);
      const stateLabel  = this._stateLabel(de);
      const isActive    = de?.state === 'on';
      const hasAny      = de || oe;

      this.shadowRoot.innerHTML = `
        <style>${STYLES}</style>

        <div class="toolbar">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor" style="flex-shrink:0">
            <path d="M7 2v11h3v9l7-12h-4l4-8z"/>
          </svg>
          <div style="flex:1;min-width:0">
            <div class="toolbar-title">EDF Energy${de ? ' · Smart Charging' : ''}</div>
            ${deviceLabel ? `<div class="toolbar-sub">${esc(deviceLabel)}</div>` : ''}
          </div>
          ${stateLabel ? `<div class="status-pill${isActive ? ' on' : ''}">${esc(stateLabel)}</div>` : ''}
        </div>

        <div class="content">
          ${!hasAny
            ? `<div class="card"><div class="no-entity">No EDF Energy entities found. Check the integration is set up correctly.</div></div>`
            : `
            ${this._renderControls(ids)}

            ${dates.length === 0
              ? `<div class="card"><div class="empty">No data yet — check back after the next rate refresh.</div></div>`
              : `
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

              ${de ? `<div class="card">
                <div class="section-title">Smart Charging Dispatch Windows</div>
                ${dayDispatches.length === 0
                  ? `<div class="empty">No dispatch windows recorded for this date.</div>`
                  : dayDispatches.map(d => {
                      const status = dispatchStatus(d.start, d.end);
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
                              ${d.charge_in_kwh != null ? `<span>${Number(d.charge_in_kwh).toFixed(1)} kWh</span>` : ''}
                              ${d.source ? `<span>${esc(formatSource(d.source))}</span>` : ''}
                              <span class="badge" style="background:${colour}">${DISPATCH_LABEL[status]}</span>
                            </div>
                          </div>
                        </div>
                      `;
                    }).join('')
                }
              </div>` : ''}
            `}
          `}
        </div>
      `;

      this._attachListeners(ids, dates, idx, canOlder, canNewer);
    }

    _attachListeners(ids, dates, idx, canOlder, canNewer) {
      const root = this.shadowRoot;

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

      // ── Toggle switches ────────────────────────────────────────────────────
      root.querySelectorAll('.toggle input[type=checkbox]').forEach(checkbox => {
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

(function () {
  'use strict';

  // ── Shared helpers (duplicated from the Lovelace card so the panel is self-contained) ──

  function localDateKey(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
  }

  function formatDateLabel(key) {
    const [y, m, d] = key.split('-').map(Number);
    return new Date(y, m - 1, d).toLocaleDateString(undefined, {
      weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
    });
  }

  function formatTime(date) {
    return date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: false });
  }

  function formatDuration(start, end) {
    const mins = Math.round((end - start) / 60000);
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    if (h === 0) return `${m}m`;
    return m === 0 ? `${h}h` : `${h}h ${m}m`;
  }

  function formatSource(source) {
    if (!source) return '';
    return source.toLowerCase().replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  }

  function getStatus(dispatch) {
    const now = new Date();
    if (dispatch.end <= now)   return 'completed';
    if (dispatch.start <= now) return 'active';
    return 'planned';
  }

  function esc(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  const STATUS_COLOUR = { completed: '#4CAF50', active: '#FF9800', planned: '#2196F3' };
  const STATUS_LABEL  = { completed: 'Completed', active: 'Active', planned: 'Planned' };

  // ── Panel element ────────────────────────────────────────────────────────────

  class EDFEnergyPanel extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: 'open' });
      this._hass = null;
      this._panel = null;
      this._selectedDateKey = null;
      this._lastEntityChanged = null;
    }

    // HA sets these properties on the panel element
    set hass(hass) {
      const entity = this._findEntity(hass);
      const token  = entity ? entity.last_changed : 'none';

      if (token === this._lastEntityChanged && this.shadowRoot.children.length > 0) {
        this._hass = hass;
        return;
      }

      this._lastEntityChanged = token;
      this._hass = hass;
      this._render();
    }

    set panel(panel) {
      this._panel = panel;
    }

    // ── Entity discovery ──────────────────────────────────────────────────────

    _findAllEntities(hass) {
      if (!hass) return [];
      return Object.entries(hass.states)
        .filter(([id]) =>
          id.startsWith('binary_sensor.') &&
          id.includes('edf_energy') &&
          id.endsWith('_intelligent_dispatching')
        )
        .map(([, state]) => state);
    }

    _findEntity(hass) {
      const all = this._findAllEntities(hass);
      return all[0] || null;
    }

    // ── Data helpers ──────────────────────────────────────────────────────────

    _parseDispatches(entity) {
      if (!entity) return [];
      const { completed_dispatches = [], planned_dispatches = [] } = entity.attributes;
      const seen = new Set();
      const result = [];

      for (const d of [...completed_dispatches, ...planned_dispatches]) {
        const key = `${d.start}|${d.end}`;
        if (!seen.has(key)) {
          seen.add(key);
          result.push({
            start:         new Date(d.start),
            end:           new Date(d.end),
            charge_in_kwh: d.charge_in_kwh ?? null,
            source:        d.source        ?? null,
            location:      d.location      ?? null,
          });
        }
      }
      return result;
    }

    _sortedDates(dispatches) {
      const keys = [...new Set(dispatches.map(d => localDateKey(d.start)))];
      return keys.sort((a, b) => b.localeCompare(a));
    }

    _deviceLabel(entity) {
      const attrs = entity.attributes;
      const parts = [attrs.provider];
      if (attrs.vehicle_battery_size_in_kwh) parts.push(`${attrs.vehicle_battery_size_in_kwh} kWh battery`);
      if (attrs.charge_point_power_in_kw)    parts.push(`${attrs.charge_point_power_in_kw} kW charger`);
      return parts.filter(Boolean).join(' · ');
    }

    _currentStateLabel(entity) {
      if (!this._hass) return null;
      // Find the matching intelligent_state sensor for this device
      const dispatchId = entity.entity_id; // binary_sensor.edf_energy_DEVICE_intelligent_dispatching
      const devicePart = dispatchId.replace('binary_sensor.edf_energy_', '').replace('_intelligent_dispatching', '');
      const stateEntityId = `sensor.edf_energy_${devicePart}_intelligent_state`;
      const stateEntity = this._hass.states[stateEntityId];
      if (!stateEntity) return null;
      return stateEntity.state
        .replace(/_/g, ' ')
        .toLowerCase()
        .replace(/\b\w/g, c => c.toUpperCase());
    }

    // ── Render ────────────────────────────────────────────────────────────────

    _render() {
      if (!this._hass) return;

      const entity     = this._findEntity(this._hass);
      const all        = this._parseDispatches(entity);
      const dates      = this._sortedDates(all);

      if (!this._selectedDateKey || !dates.includes(this._selectedDateKey)) {
        this._selectedDateKey = dates[0] || null;
      }

      const idx      = dates.indexOf(this._selectedDateKey);
      const canOlder = idx < dates.length - 1;
      const canNewer = idx > 0;

      const dayDispatches = all
        .filter(d => localDateKey(d.start) === this._selectedDateKey)
        .sort((a, b) => a.start - b.start);

      const deviceLabel = entity ? this._deviceLabel(entity) : '';
      const stateLabel  = entity ? this._currentStateLabel(entity) : null;
      const isActive    = entity?.state === 'on';

      this.shadowRoot.innerHTML = `
        <style>
          :host {
            display: block;
            height: 100%;
            background: var(--primary-background-color);
            overflow-y: auto;
            box-sizing: border-box;
          }

          /* ── Top bar ── */
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
          .toolbar-icon {
            display: flex;
            align-items: center;
            flex-shrink: 0;
          }
          .toolbar-title {
            font-size: 1.1em;
            font-weight: 500;
            flex: 1;
          }
          .toolbar-sub {
            font-size: 0.8em;
            opacity: 0.85;
          }
          .status-pill {
            font-size: 0.75em;
            font-weight: 600;
            padding: 3px 10px;
            border-radius: 12px;
            background: rgba(255,255,255,0.2);
            white-space: nowrap;
          }
          .status-pill.on { background: #4CAF50; }

          /* ── Content ── */
          .content {
            max-width: 720px;
            margin: 0 auto;
            padding: 20px 16px 40px;
          }

          /* ── Date nav ── */
          .nav-card {
            background: var(--card-background-color, #fff);
            border-radius: var(--ha-card-border-radius, 12px);
            box-shadow: var(--ha-card-box-shadow, 0 2px 6px rgba(0,0,0,.1));
            padding: 12px 16px;
            margin-bottom: 16px;
          }
          .nav-row {
            display: flex;
            align-items: center;
            gap: 8px;
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

          /* ── Dispatch items ── */
          .dispatch-card {
            background: var(--card-background-color, #fff);
            border-radius: var(--ha-card-border-radius, 12px);
            box-shadow: var(--ha-card-box-shadow, 0 2px 6px rgba(0,0,0,.1));
            overflow: hidden;
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
            padding: 24px 16px;
          }
          .no-entity {
            background: var(--card-background-color, #fff);
            border-radius: var(--ha-card-border-radius, 12px);
            box-shadow: var(--ha-card-box-shadow, 0 2px 6px rgba(0,0,0,.1));
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
            width: 10px;
            height: 10px;
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
        </style>

        <div class="toolbar">
          <div class="toolbar-icon">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor">
              <path d="M7 2v11h3v9l7-12h-4l4-8z"/>
            </svg>
          </div>
          <div style="flex:1;min-width:0">
            <div class="toolbar-title">EDF Energy · Smart Charging</div>
            ${deviceLabel ? `<div class="toolbar-sub">${esc(deviceLabel)}</div>` : ''}
          </div>
          ${stateLabel
            ? `<div class="status-pill${isActive ? ' on' : ''}">${esc(stateLabel)}</div>`
            : ''
          }
        </div>

        <div class="content">
          ${!entity
            ? `<div class="no-entity">No Smart Charging device found. Make sure the EDF Energy integration is set up with an Intelligent tariff.</div>`
            : `
            <div class="nav-card">
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

            <div class="dispatch-card">
              <div class="section-title">Dispatch Windows</div>
              ${dayDispatches.length === 0
                ? `<div class="empty">No dispatches recorded for this date.</div>`
                : dayDispatches.map(d => {
                    const status = getStatus(d);
                    const colour = STATUS_COLOUR[status];
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
                            <span class="badge" style="background:${colour}">${STATUS_LABEL[status]}</span>
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

      if (entity) {
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

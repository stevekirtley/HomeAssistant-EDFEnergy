(function () {
  'use strict';

  class EDFEnergyDispatchesCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: 'open' });
      this._config = {};
      this._hass = null;
      this._selectedDateKey = null;
      this._lastEntityChanged = null;
    }

    setConfig(config) {
      this._config = config || {};
    }

    set hass(hass) {
      const entity = this._findEntity(hass);
      const changeToken = entity ? entity.last_changed : 'none';

      // Skip re-render if entity hasn't changed and card is already drawn
      if (changeToken === this._lastEntityChanged && this.shadowRoot.children.length > 0) {
        this._hass = hass;
        return;
      }

      this._lastEntityChanged = changeToken;
      this._hass = hass;
      this._render();
    }

    // ── Entity discovery ────────────────────────────────────────────────────

    _findEntity(hass) {
      if (!hass) return null;
      const { states } = hass;

      if (this._config.device_id) {
        return states[`binary_sensor.edf_energy_${this._config.device_id}_intelligent_dispatching`] || null;
      }

      for (const [id, state] of Object.entries(states)) {
        if (
          id.startsWith('binary_sensor.') &&
          id.includes('edf_energy') &&
          id.endsWith('_intelligent_dispatching')
        ) {
          return state;
        }
      }
      return null;
    }

    // ── Data helpers ────────────────────────────────────────────────────────

    _parseDispatches(entity) {
      if (!entity) return [];
      const { completed_dispatches = [], planned_dispatches = [] } = entity.attributes;
      const seen = new Set();
      const result = [];

      // Completed first so dedup keeps the richer completed record
      for (const d of [...completed_dispatches, ...planned_dispatches]) {
        const key = `${d.start}|${d.end}`;
        if (!seen.has(key)) {
          seen.add(key);
          result.push({
            start: new Date(d.start),
            end:   new Date(d.end),
            charge_in_kwh: d.charge_in_kwh ?? null,
            source:        d.source        ?? null,
            location:      d.location      ?? null,
          });
        }
      }
      return result;
    }

    _localDateKey(date) {
      const y = date.getFullYear();
      const m = String(date.getMonth() + 1).padStart(2, '0');
      const d = String(date.getDate()).padStart(2, '0');
      return `${y}-${m}-${d}`;
    }

    _sortedDates(dispatches) {
      const keys = [...new Set(dispatches.map(d => this._localDateKey(d.start)))];
      return keys.sort((a, b) => b.localeCompare(a)); // newest first
    }

    _getStatus(dispatch) {
      const now = new Date();
      if (dispatch.end <= now)   return 'completed';
      if (dispatch.start <= now) return 'active';
      return 'planned';
    }

    // ── Formatting ──────────────────────────────────────────────────────────

    _formatDateLabel(key) {
      const [y, m, d] = key.split('-').map(Number);
      return new Date(y, m - 1, d).toLocaleDateString(undefined, {
        weekday: 'short', day: 'numeric', month: 'short', year: 'numeric',
      });
    }

    _formatTime(date) {
      return date.toLocaleTimeString(undefined, {
        hour: '2-digit', minute: '2-digit', hour12: false,
      });
    }

    _formatDuration(start, end) {
      const mins = Math.round((end - start) / 60000);
      const h = Math.floor(mins / 60);
      const m = mins % 60;
      if (h === 0) return `${m}m`;
      return m === 0 ? `${h}h` : `${h}h ${m}m`;
    }

    _formatSource(source) {
      if (!source) return '';
      return source
        .toLowerCase()
        .replace(/-/g, ' ')
        .replace(/\b\w/g, c => c.toUpperCase());
    }

    _esc(str) {
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }

    // ── Render ──────────────────────────────────────────────────────────────

    _render() {
      if (!this._hass) return;

      const entity    = this._findEntity(this._hass);
      const all       = this._parseDispatches(entity);
      const dates     = this._sortedDates(all);  // newest at index 0

      // Keep selected date valid
      if (!this._selectedDateKey || !dates.includes(this._selectedDateKey)) {
        this._selectedDateKey = dates[0] || null;
      }

      const idx      = dates.indexOf(this._selectedDateKey);
      const canOlder = idx < dates.length - 1; // ◀ goes back in time = higher index
      const canNewer = idx > 0;                // ▶ goes forward in time = lower index

      const dayDispatches = all
        .filter(d => this._localDateKey(d.start) === this._selectedDateKey)
        .sort((a, b) => a.start - b.start);

      const title = this._esc(this._config.title || 'Smart Charging Dispatches');

      const STATUS_COLOUR = { completed: '#4CAF50', active: '#FF9800', planned: '#2196F3' };
      const STATUS_LABEL  = { completed: 'Completed', active: 'Active', planned: 'Planned' };

      this.shadowRoot.innerHTML = `
        <style>
          :host { display: block; }

          .card-header {
            padding: 16px 16px 0;
            font-size: 1.25em;
            font-weight: 500;
            color: var(--ha-card-header-color, var(--primary-text-color));
            line-height: 1.3;
          }

          .nav-row {
            display: flex;
            align-items: center;
            padding: 10px 12px 6px;
            gap: 6px;
          }

          .nav-btn {
            background: none;
            border: none;
            border-radius: 50%;
            padding: 5px;
            cursor: pointer;
            color: var(--primary-text-color);
            display: flex;
            align-items: center;
            justify-content: center;
            transition: background 0.15s;
            flex-shrink: 0;
          }
          .nav-btn:hover:not(:disabled) {
            background: rgba(var(--rgb-primary-text-color, 0,0,0), 0.06);
          }
          .nav-btn:disabled { opacity: 0.3; cursor: default; }

          .date-select {
            flex: 1;
            background: var(--input-fill-color, var(--secondary-background-color, #f5f5f5));
            border: 1px solid var(--divider-color, #e0e0e0);
            border-radius: 4px;
            color: var(--primary-text-color);
            font-size: 0.9em;
            padding: 6px 10px;
            cursor: pointer;
            font-family: inherit;
            text-align: center;
          }
          .date-select:focus {
            outline: 2px solid var(--primary-color, #3d5afe);
            outline-offset: -1px;
          }

          .dispatch-list { padding: 2px 16px 14px; }

          .empty {
            color: var(--secondary-text-color);
            font-size: 0.875em;
            text-align: center;
            padding: 16px 0;
          }

          .no-entity {
            padding: 16px;
            color: var(--secondary-text-color);
            font-size: 0.875em;
          }

          .item {
            display: flex;
            gap: 12px;
            padding: 10px 0;
            border-bottom: 1px solid var(--divider-color, #e0e0e0);
            align-items: flex-start;
          }
          .item:last-child { border-bottom: none; }

          .dot {
            width: 9px;
            height: 9px;
            border-radius: 50%;
            margin-top: 5px;
            flex-shrink: 0;
          }

          .info { flex: 1; min-width: 0; }

          .time {
            font-size: 0.95em;
            font-weight: 500;
            color: var(--primary-text-color);
          }
          .duration {
            font-weight: 400;
            color: var(--secondary-text-color);
            font-size: 0.875em;
          }

          .meta {
            font-size: 0.8em;
            color: var(--secondary-text-color);
            margin-top: 3px;
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            align-items: center;
          }

          .badge {
            border-radius: 10px;
            padding: 1px 7px;
            font-size: 0.8em;
            font-weight: 500;
            color: #fff;
          }
        </style>

        <ha-card>
          <div class="card-header">${title}</div>

          ${!entity
            ? `<div class="no-entity">No Smart Charging dispatch entity found. Specify a <code>device_id</code> in the card config if you have multiple EV devices.</div>`
            : `
            <div class="nav-row">
              <button class="nav-btn" id="btn-older" ${!canOlder ? 'disabled' : ''} title="Older">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M15.41 7.41L14 6l-6 6 6 6 1.41-1.41L10.83 12z"/>
                </svg>
              </button>

              <select class="date-select" id="date-select">
                ${dates.map(dk =>
                  `<option value="${this._esc(dk)}"${dk === this._selectedDateKey ? ' selected' : ''}>${this._esc(this._formatDateLabel(dk))}</option>`
                ).join('')}
              </select>

              <button class="nav-btn" id="btn-newer" ${!canNewer ? 'disabled' : ''} title="Newer">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z"/>
                </svg>
              </button>
            </div>

            <div class="dispatch-list">
              ${dayDispatches.length === 0
                ? `<div class="empty">No dispatches for this date.</div>`
                : dayDispatches.map(d => {
                    const status = this._getStatus(d);
                    const colour = STATUS_COLOUR[status];
                    const label  = STATUS_LABEL[status];
                    const kwhStr = d.charge_in_kwh != null
                      ? `<span>${d.charge_in_kwh.toFixed(1)} kWh</span>`
                      : '';
                    const srcStr = d.source
                      ? `<span>${this._esc(this._formatSource(d.source))}</span>`
                      : '';
                    return `
                      <div class="item">
                        <div class="dot" style="background:${colour}"></div>
                        <div class="info">
                          <div class="time">
                            ${this._formatTime(d.start)} – ${this._formatTime(d.end)}
                            <span class="duration">(${this._formatDuration(d.start, d.end)})</span>
                          </div>
                          <div class="meta">
                            ${kwhStr}${srcStr}
                            <span class="badge" style="background:${colour}">${label}</span>
                          </div>
                        </div>
                      </div>
                    `;
                  }).join('')
              }
            </div>
          `}
        </ha-card>
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

    getCardSize() {
      return 4;
    }

    static getStubConfig() {
      return { title: 'Smart Charging Dispatches' };
    }
  }

  if (!customElements.get('edf-energy-dispatches-card')) {
    customElements.define('edf-energy-dispatches-card', EDFEnergyDispatchesCard);
    console.info(
      '%c EDF ENERGY DISPATCHES CARD %c Loaded ',
      'color:#fff;background:#1a237e;font-weight:700;padding:1px 6px;border-radius:3px 0 0 3px',
      'background:#3949ab;color:#fff;padding:1px 6px;border-radius:0 3px 3px 0'
    );
  }
})();

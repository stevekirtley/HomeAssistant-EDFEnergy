(function () {
  'use strict';

  // ── ApexCharts loader ─────────────────────────────────────────────────────────
  // Served by the integration from its own www folder, not fetched from a CDN, so this
  // works on an install with no outbound internet.

  let apexPromise = null;

  function ensureApexCharts() {
    if (window.ApexCharts) return Promise.resolve(window.ApexCharts);
    if (apexPromise) return apexPromise;
    apexPromise = new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = '/edf_energy/vendor/apexcharts.min.js';
      s.onload = () => resolve(window.ApexCharts);
      s.onerror = () => reject(new Error('Could not load the charting library'));
      document.head.appendChild(s);
    });
    return apexPromise;
  }

  // ── Helpers ───────────────────────────────────────────────────────────────────

  function esc(str) {
    return String(str == null ? '' : str).replace(/[&<>"']/g, c => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
  }

  // Colours are picked so the three streams stay distinguishable rather than matching
  // the EDF brand: import is the one people read first, export is the one that pays.
  const SERIES = {
    import: { label: 'Electricity', colour: '#5661f6' },
    export: { label: 'Export',      colour: '#2e9e5b' },
    gas:    { label: 'Gas',         colour: '#e4567c' },
  };

  const PERIODS = [
    { id: 'day',   label: 'Day' },
    { id: 'month', label: 'Month' },
    { id: 'year',  label: 'Year' },
  ];

  const STYLES = `
    :host { display: block; }
    .card {
      background: var(--card-background-color, #fff);
      border-radius: var(--ha-card-border-radius, 12px);
      box-shadow: var(--ha-card-box-shadow, 0 2px 4px rgba(0,0,0,0.08));
      margin: 0 0 12px; overflow: hidden;
    }
    .title { font-size: 1.05em; font-weight: 600; padding: 16px 16px 4px; }
    .controls { display: flex; gap: 8px; padding: 10px 16px; flex-wrap: wrap; align-items: center; }
    .seg { display: flex; border: 1px solid var(--divider-color, #e0e0e0); border-radius: 8px; overflow: hidden; }
    .seg button {
      border: 0; background: none; font: inherit; font-size: 0.85em; cursor: pointer;
      padding: 6px 12px; color: var(--secondary-text-color);
    }
    .seg button.active { background: var(--primary-color, #3d5afe); color: #fff; }
    .spacer { flex: 1; }
    .nav { display: flex; align-items: center; gap: 10px; padding: 0 16px 6px; }
    .nav button {
      border: 1px solid var(--divider-color, #e0e0e0); background: none; cursor: pointer;
      border-radius: 6px; width: 30px; height: 30px; font: inherit; line-height: 1;
      color: var(--primary-text-color);
    }
    .nav button[disabled] { opacity: 0.35; cursor: default; }
    .nav .label { flex: 1; text-align: center; font-weight: 600; }
    .totals { display: flex; flex-wrap: wrap; gap: 14px; padding: 4px 16px 12px; }
    .total { display: flex; align-items: baseline; gap: 6px; font-size: 0.9em; }
    .total .dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
    .total .v { font-weight: 600; font-variant-numeric: tabular-nums; }
    .chart { padding: 0 6px 10px; min-height: 260px; }
    .msg { padding: 24px 16px; text-align: center; color: var(--secondary-text-color); }
  `;

  class EDFEnergyConsumptionCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: 'open' });
      this._hass = null;
      this._meters = [];
      this._period = 'day';
      this._unit = 'kwh';
      // 0 is the period containing today, 1 the one before it, and so on. EDF's readings
      // run a day or two behind, so the current period is always partly empty - that is
      // the data lagging, not a gap in the meter.
      this._offset = 0;
      this._chart = null;
      this._data = null;
      this._loading = false;
      this._error = null;
      this._fetchToken = 0;
      this._built = false;
    }

    set hass(hass) {
      const first = this._hass === null;
      this._hass = hass;
      if (first) this._refresh();
    }

    /** Meter points, as the panel's account summary returns them. */
    set meters(meters) {
      const key = JSON.stringify(meters || []);
      if (key === this._metersKey) return;
      this._metersKey = key;
      this._meters = meters || [];
      this._refresh();
    }

    // ── Statistic ids ───────────────────────────────────────────────────────────

    _streams() {
      const out = [];
      for (const point of this._meters) {
        for (const meter of point.meters || []) {
          if (!meter.serial_number) continue;
          // The integration lowercases the whole id before writing it, and meter serials
          // carry letters ("20L1234567"), so building it in the API's casing finds
          // nothing at all.
          const serial = String(meter.serial_number).toLowerCase();
          if (point.mprn) {
            out.push({
              kind: 'gas',
              id: `edf_energy:gas_${serial}_${point.mprn}_previous_accumulative_consumption_kwh`,
              costId: `edf_energy:gas_${serial}_${point.mprn}_previous_accumulative_cost_includingsc`,
            });
          } else if (point.mpan) {
            const suffix = point.is_export ? '_export' : '';
            out.push({
              kind: point.is_export ? 'export' : 'import',
              id: `edf_energy:electricity_${serial}_${point.mpan}${suffix}_previous_accumulative_consumption`,
              // Export meters have no standing charge, so they have no _includingsc
              // statistic - their cost view falls back to the plain one.
              costId: point.is_export
                ? `edf_energy:electricity_${serial}_${point.mpan}_export_previous_accumulative_cost`
                : `edf_energy:electricity_${serial}_${point.mpan}_previous_accumulative_cost_includingsc`,
            });
          }
        }
      }
      // One meter can appear under several agreements; the same statistic twice would
      // double every bar.
      const seen = new Set();
      return out.filter(s => (seen.has(s.id) ? false : seen.add(s.id)));
    }

    // ── Period maths ────────────────────────────────────────────────────────────

    _range() {
      const now = new Date();
      if (this._period === 'day') {
        const start = new Date(now.getFullYear(), now.getMonth() - this._offset, 1);
        const end = new Date(start.getFullYear(), start.getMonth() + 1, 1);
        return { start, end, bucket: 'day',
                 label: start.toLocaleDateString(undefined, { month: 'long', year: 'numeric' }) };
      }
      if (this._period === 'month') {
        const start = new Date(now.getFullYear() - this._offset, 0, 1);
        const end = new Date(start.getFullYear() + 1, 0, 1);
        return { start, end, bucket: 'month', label: String(start.getFullYear()) };
      }
      // Years are aggregated here from monthly buckets, because the statistics API has no
      // yearly period of its own.
      const span = 5;
      const endYear = now.getFullYear() - (this._offset * span);
      const start = new Date(endYear - span + 1, 0, 1);
      const end = new Date(endYear + 1, 0, 1);
      return { start, end, bucket: 'month',
               label: `${start.getFullYear()} – ${endYear}` };
    }

    _bucketKey(date, range) {
      const d = new Date(date);
      if (this._period === 'day') return String(d.getDate());
      if (this._period === 'month') return d.toLocaleDateString(undefined, { month: 'short' });
      return String(d.getFullYear());
    }

    _categories(range) {
      if (this._period === 'day') {
        const days = new Date(range.end.getFullYear(), range.end.getMonth(), 0).getDate();
        return Array.from({ length: days }, (_, i) => String(i + 1));
      }
      if (this._period === 'month') {
        return Array.from({ length: 12 }, (_, i) =>
          new Date(2000, i, 1).toLocaleDateString(undefined, { month: 'short' }));
      }
      const out = [];
      for (let y = range.start.getFullYear(); y <= range.end.getFullYear() - 1; y++) out.push(String(y));
      return out;
    }

    // ── Data ────────────────────────────────────────────────────────────────────

    async _refresh() {
      if (!this._hass || !this._meters.length) return;
      const streams = this._streams();
      if (!streams.length) { this._data = null; this._render(); return; }

      const range = this._range();
      const ids = streams.map(s => (this._unit === 'cost' ? s.costId : s.id));
      const token = ++this._fetchToken;
      this._loading = true;
      this._error = null;
      this._render();

      let stats;
      try {
        stats = await this._hass.callWS({
          type: 'recorder/statistics_during_period',
          start_time: range.start.toISOString(),
          end_time: range.end.toISOString(),
          statistic_ids: ids,
          period: range.bucket,
          // "change" is the movement within each bucket. Asking for "sum" instead would
          // hand back a running total that has to be differenced, and the first bucket of
          // the window would have nothing to difference against.
          types: ['change'],
        });
      } catch (e) {
        if (token !== this._fetchToken) return;
        this._loading = false;
        this._error = e?.message || 'Could not read the statistics.';
        this._render();
        return;
      }

      // A slower earlier request must not overwrite a newer one.
      if (token !== this._fetchToken) return;

      const categories = this._categories(range);
      const byKind = {};
      for (let i = 0; i < streams.length; i++) {
        const stream = streams[i];
        const rows = stats[ids[i]] || [];
        const totals = byKind[stream.kind] || (byKind[stream.kind] = new Array(categories.length).fill(0));
        for (const row of rows) {
          const key = this._bucketKey(row.start, range);
          const index = categories.indexOf(key);
          if (index === -1) continue;
          const value = Number(row.change);
          if (!isNaN(value)) totals[index] += value;
        }
      }

      this._loading = false;
      this._data = { categories, byKind, label: range.label };
      this._render();
      this._draw();
    }

    // ── Rendering ───────────────────────────────────────────────────────────────

    _format(value) {
      if (this._unit === 'cost') return `£${value.toFixed(2)}`;
      return `${value.toFixed(value >= 100 ? 0 : 1)} kWh`;
    }

    _render() {
      const seg = (name, items, active) => `
        <div class="seg">
          ${items.map(i => `
            <button data-${name}="${i.id}" class="${i.id === active ? 'active' : ''}">${esc(i.label)}</button>
          `).join('')}
        </div>`;

      let body;
      if (this._error) {
        body = `<div class="msg">${esc(this._error)}</div>`;
      } else if (!this._meters.length) {
        body = `<div class="msg">No meters on this account.</div>`;
      } else if (this._data === null) {
        body = `<div class="msg">${this._loading ? 'Loading…' : 'No consumption statistics yet.'}</div>`;
      } else {
        const kinds = Object.keys(this._data.byKind);
        const anything = kinds.some(k => this._data.byKind[k].some(v => v !== 0));
        body = `
          <div class="totals">
            ${kinds.map(k => {
              const total = this._data.byKind[k].reduce((a, b) => a + b, 0);
              return `<div class="total">
                <span class="dot" style="background:${SERIES[k].colour}"></span>
                <span>${esc(SERIES[k].label)}</span>
                <span class="v">${esc(this._format(total))}</span>
              </div>`;
            }).join('')}
          </div>
          <div class="chart" id="chart">${anything ? '' : '<div class="msg">Nothing recorded for this period yet. EDF publish readings a day or two behind.</div>'}</div>`;
      }

      this.shadowRoot.innerHTML = `
        <style>${STYLES}</style>
        <div class="card">
          <div class="title">Consumption</div>
          <div class="controls">
            ${seg('period', PERIODS, this._period)}
            <span class="spacer"></span>
            ${seg('unit', [{ id: 'kwh', label: 'kWh' }, { id: 'cost', label: '£' }], this._unit)}
          </div>
          <div class="nav">
            <button id="prev" title="Earlier">‹</button>
            <div class="label">${esc(this._data?.label || this._range().label)}</div>
            <button id="next" title="Later"${this._offset === 0 ? ' disabled' : ''}>›</button>
          </div>
          ${body}
        </div>`;

      this.shadowRoot.querySelectorAll('[data-period]').forEach(b =>
        b.addEventListener('click', () => {
          if (this._period === b.dataset.period) return;
          this._period = b.dataset.period;
          this._offset = 0;
          this._refresh();
        }));
      this.shadowRoot.querySelectorAll('[data-unit]').forEach(b =>
        b.addEventListener('click', () => {
          if (this._unit === b.dataset.unit) return;
          this._unit = b.dataset.unit;
          this._refresh();
        }));
      this.shadowRoot.getElementById('prev')?.addEventListener('click', () => {
        this._offset += 1; this._refresh();
      });
      this.shadowRoot.getElementById('next')?.addEventListener('click', () => {
        if (this._offset === 0) return;
        this._offset -= 1; this._refresh();
      });
    }

    async _draw() {
      const container = this.shadowRoot.getElementById('chart');
      if (!container || !this._data) return;

      const kinds = Object.keys(this._data.byKind);
      if (!kinds.some(k => this._data.byKind[k].some(v => v !== 0))) return;

      let ApexCharts;
      try {
        ApexCharts = await ensureApexCharts();
      } catch (e) {
        container.innerHTML = `<div class="msg">${esc(e.message)}</div>`;
        return;
      }

      if (this._chart) { this._chart.destroy(); this._chart = null; }

      const unit = this._unit;
      const chart = new ApexCharts(container, {
        chart: { type: 'bar', height: 280, stacked: true, toolbar: { show: false },
                 fontFamily: 'inherit', background: 'transparent', animations: { enabled: false } },
        theme: { mode: 'light' },
        series: kinds.map(k => ({ name: SERIES[k].label, data: this._data.byKind[k].map(v => +v.toFixed(3)) })),
        colors: kinds.map(k => SERIES[k].colour),
        xaxis: { categories: this._data.categories, tickPlacement: 'on',
                 labels: { rotate: 0, hideOverlappingLabels: true } },
        yaxis: { labels: { formatter: v => (unit === 'cost' ? `£${Number(v).toFixed(2)}` : Number(v).toFixed(0)) } },
        legend: { show: false },
        dataLabels: { enabled: false },
        grid: { borderColor: 'rgba(127,127,127,0.18)' },
        tooltip: {
          shared: true,
          y: { formatter: v => (v == null ? '—' : (unit === 'cost' ? `£${Number(v).toFixed(2)}` : `${Number(v).toFixed(2)} kWh`)) },
        },
        plotOptions: { bar: { columnWidth: '68%', borderRadius: 2 } },
      });
      this._chart = chart;
      chart.render();
    }

    disconnectedCallback() {
      if (this._chart) { this._chart.destroy(); this._chart = null; }
    }
  }

  if (!customElements.get('edf-energy-consumption-card'))
    customElements.define('edf-energy-consumption-card', EDFEnergyConsumptionCard);
})();

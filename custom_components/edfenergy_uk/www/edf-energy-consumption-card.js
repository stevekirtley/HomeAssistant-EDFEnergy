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

  // Import split by rate, where the tariff had one. The integration writes these per day,
  // deciding from how many distinct rates that day had - so a single rate customer has
  // none of them, except on a day a free session added a second rate. Shades of the
  // electricity colour, so a split bar still reads as the same fuel.
  const SEGMENTS = {
    free:     { label: 'Free',            colour: '#f0a92b' },
    off_peak: { label: 'Off-peak',        colour: '#949cfb' },
    standard: { label: 'Standard',        colour: '#6771f7' },
    peak:     { label: 'Peak',            colour: '#2f3ad0' },
    standing: { label: 'Standing charge', colour: '#8a8f99' },
  };
  // Drawn in this order from the bottom of the bar up.
  const SEGMENT_ORDER = ['off_peak', 'standard', 'peak', 'standing'];

  // Rough luminance of a CSS colour, used only to decide light or dark chrome. Anything
  // it cannot parse falls back to light, which is what the card looked like before.
  function isDark(colour) {
    const m = String(colour || '').match(/\d+(\.\d+)?/g);
    if (!m || m.length < 3) return false;
    const [r, g, b] = m.slice(0, 3).map(Number);
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) < 128;
  }

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
    .total.net { padding-left: 14px; border-left: 1px solid rgba(127,127,127,0.28); }
    .promo { margin: 0 16px 12px; padding: 10px 12px; border-radius: 8px;
             background: rgba(240, 169, 43, 0.10); border-left: 3px solid #f0a92b; }
    .promo-figure { display: flex; align-items: baseline; gap: 6px; font-size: 0.9em; }
    .promo-figure .dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
    .promo-figure .v { font-weight: 600; font-variant-numeric: tabular-nums; }
    .promo-credit { font-size: 0.92em; opacity: 0.85; }
    .promo-note { margin-top: 6px; font-size: 0.82em; opacity: 0.8; line-height: 1.45; }
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
      this._metersKey = null;
      this._accountId = null;
      this._resizeObserver = null;
      this._drawnWidth = 0;
    }

    set hass(hass) {
      const first = this._hass === null;
      this._hass = hass;
      if (first) this._refresh();
    }

    /** The account the panel is showing, needed to ask about free promotions. */
    set accountId(id) {
      if (id === this._accountId) return;
      const first = this._accountId === null;
      this._accountId = id;
      // Set before the meters on the way in, so the first fetch already has it. Only a
      // later change needs a refresh of its own.
      if (!first) this._refresh();
    }

    /** Meter points, as the panel's account summary returns them. */
    set meters(meters) {
      const key = JSON.stringify(meters || []);
      if (key === this._metersKey) return;
      this._metersKey = key;
      this._meters = meters || [];
      this._refresh();
    }

    /** Re-read the statistics behind the chart, keeping the period and unit on screen.
     *  The panel calls this when it has just filled in days that were missing, because
     *  nothing about the card's own inputs has changed - only the data underneath them. */
    reload() {
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
            const base = `edf_energy:electricity_${serial}_${point.mpan}${suffix}`;
            out.push({
              kind: point.is_export ? 'export' : 'import',
              // Only import is split. Export has the same statistics but a bar of what was
              // sold at which rate answers a question nobody asked.
              splits: point.is_export ? [] : ['off_peak', 'standard', 'peak'].map(type => ({
                type,
                id: `${base}_previous_accumulative_consumption_${type}`,
                costId: `${base}_previous_accumulative_cost_${type}`,
              })),
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
      const isCost = this._unit === 'cost';
      const ids = streams.map(s => (isCost ? s.costId : s.id));
      // Asked for alongside the totals rather than in a second call. The recorder is happy
      // to be handed ids it holds nothing for, and one round trip means the chart does not
      // draw once without the split and again with it.
      const splitIds = [];
      for (const stream of streams)
        for (const split of stream.splits || []) {
          splitIds.push({ type: split.type, id: isCost ? split.costId : split.id });
          // The other half of the pair, so a band charged at nothing can be named as free
          // rather than filed under whichever rate slot it happened to take.
          splitIds.push({ type: split.type, id: isCost ? split.id : split.costId,
                          measure: isCost ? 'usage' : 'cost' });
        }
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
          statistic_ids: [...ids, ...splitIds.map(s => s.id)],
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
        const totals = byKind[stream.kind] || (byKind[stream.kind] = new Array(categories.length).fill(0));
        this._bucket(stats[ids[i]] || [], categories, range, totals);
      }

      const bySegment = {};
      const otherMeasure = {};
      for (const split of splitIds) {
        const rows = stats[split.id];
        if (!rows || !rows.length) continue;
        const into = split.measure ? otherMeasure : bySegment;
        const totals = into[split.type] || (into[split.type] = new Array(categories.length).fill(0));
        this._bucket(rows, categories, range, totals);
      }
      const segments = byKind.import
        ? this._assessSplit(byKind.import, bySegment, isCost)
        : null;
      const freeTypes = segments
        ? this._freeSegments(
            isCost ? otherMeasure : bySegment,
            isCost ? bySegment : otherMeasure,
            Object.keys(segments))
        : [];

      const freePromo = await this._freePromoUsage(range, isCost);
      if (token !== this._fetchToken) return;

      this._loading = false;
      this._data = { categories, byKind, segments, freeTypes, freePromo, label: range.label };
      this._render();
      this._draw();
    }

    /** Add a statistic's rows into per-bucket totals. */
    _bucket(rows, categories, range, into) {
      for (const row of rows) {
        const key = this._bucketKey(row.start, range);
        const index = categories.indexOf(key);
        if (index === -1) continue;
        const value = Number(row.change);
        if (!isNaN(value)) into[index] += value;
      }
    }

    /** A date as the notes read it, rather than as the chart axis does. */
    _shortDate(value) {
      const date = new Date(value);
      if (isNaN(date)) return '';
      return date.toLocaleDateString(undefined,
                                     { day: 'numeric', month: 'short', year: 'numeric' });
    }

    /** The promotion estimate and what it does and does not mean. */
    _renderFreePromo() {
      const promo = this._data.freePromo;
      if (!promo) return '';
      const sessions = promo.sessions === 1 ? 'one free session' : `${promo.sessions} free sessions`;
      return `
        <div class="promo">
          <div class="promo-figure">
            <span class="dot" style="background:${SEGMENTS.free.colour}"></span>
            <span>Free promo (estimated)</span>
            <span class="v">${esc(promo.consumption.toFixed(2))} kWh</span>
            ${promo.cost > 0
              ? `<span class="promo-credit">about ${esc(`£${Number(promo.cost).toFixed(2)}`)}
                 to come back as credit</span>`
              : ''}
          </div>
          <div class="promo-note">
            Estimated from the times of ${sessions} in this period. EDF bill these hours at
            your normal rate and credit the cost back weeks later, so they are not free on
            the bars above or on your bill. The credit is worked out from EDF's own half
            hourly readings, so it will not match this to the penny.
            ${promo.partial
              ? `No session times are held before ${esc(this._shortDate(promo.history_from))}, so
                 anything earlier in this period is not counted here.`
              : ''}
          </div>
        </div>`;
    }

    /** What a free promotion is reckoned to have covered in this period, or null.
     *
     *  Both halves are worth having: what was used, and what those hours were charged at,
     *  which is what the promotion should put back as credit weeks later.
     */
    async _freePromoUsage(range, isCost) {
      if (!this._accountId) return null;
      try {
        const result = await this._hass.callWS({
          type: 'edf_energy/free_promo_usage',
          account_id: this._accountId,
          start: range.start.toISOString(),
          end: range.end.toISOString(),
        });
        if (!result || !(result.consumption > 0) || !(result.sessions > 0)) return null;
        // Windows used to be kept for sixty days, so an install that predates the change can
        // be looking further back than it has any record of. Better to say so than to let a
        // figure that is quietly short pass for the whole period.
        result.partial = !!(result.history_from
                            && new Date(result.history_from) > range.start);
        return result;
      } catch (e) {
        // An estimate that would not load is not worth taking the chart down over.
        return null;
      }
    }

    /** How a band should be drawn and named, which is not always what it was filed under. */
    _segmentStyle(type) {
      return (this._data.freeTypes || []).includes(type) ? SEGMENTS.free : SEGMENTS[type];
    }

    /** Which rate bands were charged at nothing, and so are free rather than cheap.
     *
     *  A tariff with a scheduled free window publishes it as a rate of zero, so the band
     *  shows usage against no cost. That is a real billed zero, not a promotion credited
     *  back later - those never reach the published rates at all.
     *
     *  Named by what it is rather than by the slot it fell into: the integration labels
     *  rate bands cheapest first, so on a three rate day the free one takes the "off peak"
     *  name and the genuine off peak rate is pushed along to "standard".
     */
    _freeSegments(usageByType, costByType, types) {
      const sum = arr => (arr || []).reduce((a, b) => a + b, 0);
      return types.filter(type => {
        if (type === 'standing') return false;
        const usage = sum(usageByType[type]);
        const cost = sum(costByType[type]);
        // A band has to have been used before its cost means anything, and the threshold
        // is above a rounded-down penny rather than at zero.
        return usage > 0.05 && Math.abs(cost) < 0.005;
      });
    }

    /** The import bar split by rate, or null to draw it whole.
     *
     *  Only worth showing when every bucket adds up. Coverage is decided per day, from how
     *  many distinct rates that day had, so one window can hold a mix - a free session on
     *  an otherwise single rate tariff writes a split for that day alone. Drawing some bars
     *  split and the rest whole invites exactly the wrong comparison, so it is all or
     *  nothing across the window.
     *
     *  In the cost view the total carries the standing charge and the rate series do not,
     *  so what is left over becomes a segment of its own rather than a discrepancy.
     */
    _assessSplit(totals, bySegment, isCost) {
      const present = SEGMENT_ORDER.filter(t => t !== 'standing' && bySegment[t]);
      if (!present.length) return null;

      const standing = isCost ? new Array(totals.length).fill(0) : null;
      let anything = false;

      for (let i = 0; i < totals.length; i++) {
        const total = totals[i];
        const segs = present.reduce((a, t) => a + bySegment[t][i], 0);
        if (Math.abs(total) < 0.0005 && Math.abs(segs) < 0.0005) continue;
        anything = true;
        // Proportional, since a year of kWh and a single day are not owed the same absolute
        // accuracy, with a floor so buckets near zero are not held to an impossible standard.
        const tolerance = Math.max(0.05, Math.abs(total) * 0.005);
        if (isCost) {
          // The rate series have to account for the usage, leaving the standing charge. A
          // bucket where they came back empty would hand the whole bar to the standing
          // charge, which is nonsense, so that fails here rather than being drawn.
          const rest = total - segs;
          if (segs <= 0 || rest < -tolerance) return null;
          standing[i] = Math.max(rest, 0);
        } else if (Math.abs(total - segs) > tolerance) {
          return null;
        }
      }
      if (!anything) return null;

      const out = {};
      for (const type of present) out[type] = bySegment[type];
      if (isCost && standing.some(v => v > 0.005)) out.standing = standing;
      return out;
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
            ${this._renderTotals(kinds)}
            ${this._renderNetTotal(kinds)}
          </div>
          ${this._renderFreePromo()}
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

    /** The figures above the chart. With the rate split drawn, electricity is listed by
     *  segment instead of as one number, so the key matches the bar underneath it. */
    _renderTotals(kinds) {
      const sum = arr => arr.reduce((a, b) => a + b, 0);
      const entry = (label, colour, total) => `
        <div class="total">
          <span class="dot" style="background:${colour}"></span>
          <span>${esc(label)}</span>
          <span class="v">${esc(this._format(total))}</span>
        </div>`;
      const out = [];
      for (const k of kinds) {
        if (k === 'import' && this._data.segments) {
          for (const type of SEGMENT_ORDER) {
            if (!this._data.segments[type]) continue;
            const style = this._segmentStyle(type);
            out.push(entry(style.label, style.colour, sum(this._data.segments[type])));
          }
        } else {
          out.push(entry(SERIES[k].label, SERIES[k].colour, sum(this._data.byKind[k])));
        }
      }
      return out.join('');
    }

    /** What the period actually cost once export earnings are taken off. Only in the cost
     *  view, and only when there is an export meter - in kWh a net figure would be two
     *  different things subtracted from each other. */
    _renderNetTotal(kinds) {
      if (this._unit !== 'cost' || !kinds.includes('export')) return '';
      const sum = kind => this._data.byKind[kind].reduce((a, b) => a + b, 0);
      const paid = kinds.filter(k => k !== 'export').reduce((a, k) => a + sum(k), 0);
      const net = paid - sum('export');
      const text = `${net < 0 ? '-' : ''}£${Math.abs(net).toFixed(2)}`;
      return `
        <div class="total net">
          <span>Net cost</span>
          <span class="v">${esc(text)}</span>
        </div>`;
    }

    /** Width of the chart area, or 0 while the browser has yet to lay it out. */
    _measure(container) {
      const width = container.getBoundingClientRect().width || container.clientWidth || 0;
      return Math.floor(width);
    }

    async _draw(attempt = 0) {
      const container = this.shadowRoot.getElementById('chart');
      if (!container || !this._data) return;

      const kinds = Object.keys(this._data.byKind);
      if (!kinds.some(k => this._data.byKind[k].some(v => v !== 0))) return;

      // ApexCharts works its own width out by walking offsetParent and computed styles,
      // which does not resolve inside a shadow root - it ends up with NaN and throws
      // while writing the svg's width attribute, so no chart appears and the only sign
      // is a console error. Measuring here and handing it an explicit pixel width takes
      // that guesswork away from it entirely.
      const width = this._measure(container);
      if (width <= 0) {
        // Laid out on a later frame - a tab that was just switched to, say. Give it a
        // few frames rather than forever, so a container that is genuinely never shown
        // does not leave a callback spinning.
        if (attempt < 10) requestAnimationFrame(() => this._draw(attempt + 1));
        return;
      }

      let ApexCharts;
      try {
        ApexCharts = await ensureApexCharts();
      } catch (e) {
        container.innerHTML = `<div class="msg">${esc(e.message)}</div>`;
        return;
      }

      if (this._chart) { this._chart.destroy(); this._chart = null; }

      const unit = this._unit;
      // Follow whatever theme Home Assistant is wearing rather than guessing from the
      // operating system, which gets it wrong for anyone running a dark HA theme on a
      // light desktop. The card's own background colour is the honest signal.
      const styles = getComputedStyle(this);
      const foreColor = (styles.getPropertyValue('--primary-text-color') || '').trim();
      const dark = isDark(styles.getPropertyValue('--card-background-color'));

      const segments = this._data.segments;
      const series = [];
      for (const k of kinds) {
        if (k === 'import' && segments) {
          for (const type of SEGMENT_ORDER) {
            if (!segments[type]) continue;
            const style = this._segmentStyle(type);
            series.push({ name: style.label, group: 'import', color: style.colour,
                          data: segments[type].map(v => +v.toFixed(3)) });
          }
        } else {
          series.push({ name: SERIES[k].label, group: k, color: SERIES[k].colour,
                        data: this._data.byKind[k].map(v => +v.toFixed(3)) });
        }
      }

      const chart = new ApexCharts(container, {
        // Stacking is only switched on when there is something to stack. Without the rate
        // split every series is its own group, and asking for groups there gains nothing.
        chart: { type: 'bar', width, height: 280, stacked: !!segments, toolbar: { show: false },
                 fontFamily: 'inherit', background: 'transparent',
                 foreColor: foreColor || undefined, animations: { enabled: false } },
        theme: { mode: dark ? 'dark' : 'light' },
        series,
        colors: series.map(s => s.color),
        xaxis: { categories: this._data.categories, tickPlacement: 'on',
                 labels: { rotate: 0, hideOverlappingLabels: true } },
        yaxis: { labels: { formatter: v => (unit === 'cost' ? `£${Number(v).toFixed(2)}` : Number(v).toFixed(0)) } },
        legend: { show: false },
        dataLabels: { enabled: false },
        grid: { borderColor: 'rgba(127,127,127,0.18)' },
        tooltip: {
          // Bar charts default intersect to true, and ApexCharts throws outright rather
          // than warning if that is left on with a shared tooltip. All the fuels want
          // reading together for one day, so shared stays and intersect goes.
          shared: true,
          intersect: false,
          y: { formatter: v => (v == null ? '—' : (unit === 'cost' ? `£${Number(v).toFixed(2)}` : `${Number(v).toFixed(2)} kWh`)) },
        },
        plotOptions: { bar: { columnWidth: '85%', borderRadius: 2 } },
      });
      this._chart = chart;
      this._drawnWidth = width;
      chart.render();
      this._watchWidth(container);
    }

    /** Redraw at the new size when the panel is resized, since the width is now fixed. */
    _watchWidth(container) {
      if (typeof ResizeObserver === 'undefined') return;
      // Every render rebuilds the card's markup, so #chart is a new node each time and
      // an observer kept from last time would be watching one that is no longer there.
      if (this._resizeObserver) this._resizeObserver.disconnect();
      this._resizeObserver = new ResizeObserver(() => {
        const slot = this.shadowRoot.getElementById('chart');
        if (!slot || !this._chart) return;
        const width = this._measure(slot);
        // Only on a real change, or the observer's own redraw would retrigger it.
        if (width > 0 && Math.abs(width - (this._drawnWidth || 0)) > 8) {
          this._drawnWidth = width;
          this._chart.updateOptions({ chart: { width } }, false, false);
        }
      });
      this._resizeObserver.observe(container);
    }

    connectedCallback() {
      // The panel may well have set hass and meters before this script finished loading.
      // Assigning to a custom element that has not been upgraded yet leaves own data
      // properties sitting on top of the prototype setters, which then never run again -
      // so the card would stay empty forever. Take those values back and feed them
      // through the setters properly.
      this._upgradeProperty('hass');
      this._upgradeProperty('meters');

      // A panel re-render rebuilds its shadow DOM, so this element gets moved into the
      // fresh slot - a disconnect and reconnect, not a teardown. Put the chart back.
      if (this._data !== null) { this._render(); this._draw(); }
    }

    _upgradeProperty(name) {
      if (!Object.prototype.hasOwnProperty.call(this, name)) return;
      const value = this[name];
      delete this[name];
      this[name] = value;
    }

    disconnectedCallback() {
      // Only the chart instance goes; _data is kept so a reconnect can redraw without
      // going back to the recorder.
      if (this._chart) { this._chart.destroy(); this._chart = null; }
      if (this._resizeObserver) { this._resizeObserver.disconnect(); this._resizeObserver = null; }
    }
  }

  if (!customElements.get('edf-energy-consumption-card'))
    customElements.define('edf-energy-consumption-card', EDFEnergyConsumptionCard);
})();

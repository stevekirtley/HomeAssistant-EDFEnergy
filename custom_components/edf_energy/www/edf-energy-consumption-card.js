(function () {
  'use strict';

  // ── ApexCharts loader ─────────────────────────────────────────────────────────

  let _apexPromise = null;
  function ensureApexCharts() {
    if (_apexPromise) return _apexPromise;
    _apexPromise = new Promise((resolve, reject) => {
      if (window.ApexCharts) { resolve(window.ApexCharts); return; }
      const s = document.createElement('script');
      s.src = 'https://cdn.jsdelivr.net/npm/apexcharts@3/dist/apexcharts.min.js';
      s.onload = () => resolve(window.ApexCharts);
      s.onerror = () => reject(new Error('Failed to load ApexCharts'));
      document.head.appendChild(s);
    });
    return _apexPromise;
  }

  // ── Styles ────────────────────────────────────────────────────────────────────

  const STYLES = `
    :host { display: block; }
    ha-card { overflow: hidden; }

    .card-header {
      padding: 16px 16px 0;
      font-size: 1.15em; font-weight: 500;
      color: var(--ha-card-header-color, var(--primary-text-color));
    }

    .meter-tabs {
      display: flex; gap: 4px; padding: 10px 16px 0; overflow-x: auto;
      scrollbar-width: none;
    }
    .meter-tabs::-webkit-scrollbar { display: none; }

    .meter-tab {
      padding: 5px 13px; border-radius: 16px;
      border: 1px solid var(--divider-color, #e0e0e0);
      background: none; color: var(--secondary-text-color);
      font-size: 0.82em; cursor: pointer; white-space: nowrap;
      font-family: inherit; transition: all 0.15s; flex-shrink: 0;
    }
    .meter-tab.active {
      background: var(--primary-color, #3d5afe); color: #fff; border-color: transparent;
    }

    .controls-row {
      display: flex; align-items: center; justify-content: space-between;
      padding: 8px 16px;
    }

    .btn-group {
      display: flex; border: 1px solid var(--divider-color, #e0e0e0);
      border-radius: 6px; overflow: hidden;
    }
    .btn-group button {
      background: none; border: none; padding: 4px 11px;
      font-size: 0.8em; cursor: pointer; font-family: inherit;
      color: var(--secondary-text-color);
      border-right: 1px solid var(--divider-color, #e0e0e0);
      transition: all 0.15s;
    }
    .btn-group button:last-child { border-right: none; }
    .btn-group button.active {
      background: var(--primary-color, #3d5afe); color: #fff;
    }

    .chart-wrap { padding: 0 4px 4px; min-height: 180px; }
    .chart-container { width: 100%; }

    .summary {
      display: flex; gap: 8px; padding: 0 16px 16px; flex-wrap: wrap;
    }
    .summary-item {
      flex: 1; min-width: 70px;
      background: var(--secondary-background-color, rgba(0,0,0,0.04));
      border-radius: 8px; padding: 8px 10px;
    }
    .summary-label { font-size: 0.72em; color: var(--secondary-text-color); }
    .summary-value { font-size: 1em; font-weight: 600; color: var(--primary-text-color); margin-top: 2px; }

    .nav-row {
      display: flex; align-items: center; justify-content: center;
      gap: 8px; padding: 0 16px 6px;
    }
    .nav-btn {
      background: none; border: 1px solid var(--divider-color, #e0e0e0);
      border-radius: 4px; padding: 2px 10px; cursor: pointer;
      font-size: 1.1em; line-height: 1.4; color: var(--primary-text-color);
      font-family: inherit; transition: background 0.15s;
    }
    .nav-btn:disabled { opacity: 0.3; cursor: default; }
    .nav-btn:hover:not(:disabled) { background: rgba(var(--rgb-primary-text-color,0,0,0),0.06); }
    .period-label {
      font-size: 0.82em; color: var(--secondary-text-color);
      min-width: 140px; text-align: center;
    }

    .state-msg {
      padding: 28px 16px; text-align: center;
      color: var(--secondary-text-color); font-size: 0.9em; min-height: 60px;
    }
  `;

  // ── Card ──────────────────────────────────────────────────────────────────────

  class EDFEnergyConsumptionCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: 'open' });
      this._config = {};
      this._hass = null;
      this._meters = null;
      this._tabs = [];
      this._activeTab = null;
      this._activeView = 'halfhourly';
      this._activeUnit = 'kwh';
      this._periodOffset = 1; // default to yesterday — today's data lags by a day
      this._chart = null;
      this._metersKey = null;
      this._renderedKey = null;
      this._updateTimer = null;
    }

    setConfig(config) {
      this._config = config || {};
    }

    set hass(hass) {
      this._hass = hass;
      const meters = this._discoverMeters(hass);
      const key = JSON.stringify(meters);
      if (key !== this._metersKey) {
        this._metersKey = key;
        this._meters = meters;
        this._tabs = this._buildTabs(meters);
        if (!this._tabs.find(t => t.id === this._activeTab))
          this._activeTab = this._tabs[0]?.id || null;
        this._buildShell();
      }
      this._scheduleUpdate();
    }

    // ── Discovery ─────────────────────────────────────────────────────────────

    _discoverMeters(hass) {
      const m = {};
      if (!hass) return m;
      for (const id of Object.keys(hass.states)) {
        if (!id.startsWith('sensor.edf_energy_')) continue;
        if (!id.endsWith('_previous_accumulative_cost')) continue;
        if (id.includes('_electricity_') && !id.includes('_export_')) {
          if (!m.import) m.import = id;
        } else if (id.includes('_electricity_') && id.includes('_export_')) {
          if (!m.export) m.export = id;
        } else if (id.includes('_gas_')) {
          if (!m.gas) m.gas = id;
        }
      }
      return m;
    }

    _buildTabs(meters) {
      const tabs = [];
      if (meters.import) tabs.push({ id: 'import', label: 'Electricity', entity: meters.import });
      if (meters.export) tabs.push({ id: 'export', label: 'Export',      entity: meters.export });
      if (meters.gas)    tabs.push({ id: 'gas',    label: 'Gas',         entity: meters.gas    });
      if (meters.import && meters.export)
        tabs.push({ id: 'net', label: 'Net Cost', entity: null });
      return tabs;
    }

    // ── ID helpers ────────────────────────────────────────────────────────────

    _toStatId(entityId) {
      return entityId.replace(/^sensor\.edf_energy_/, 'edf_energy:');
    }

    _kwhStatId(entityId) {
      const base = this._toStatId(entityId);
      return entityId.includes('_gas_')
        ? base.replace('_previous_accumulative_cost', '_previous_accumulative_consumption_kwh')
        : base.replace('_previous_accumulative_cost', '_previous_accumulative_consumption');
    }

    _currentAccEntity(entityId) {
      return entityId.replace('_previous_accumulative_cost', '_current_accumulative_cost');
    }

    _standingChargePerDay(entityId) {
      if (!entityId) return 0;
      const scId = entityId.replace('_previous_accumulative_cost', '_current_standing_charge');
      const v = parseFloat(this._hass?.states[scId]?.state);
      return isNaN(v) ? 0 : v;
    }

    // ── Shell ─────────────────────────────────────────────────────────────────

    _buildShell() {
      if (this._chart) { this._chart.destroy(); this._chart = null; }
      this._renderedKey = null;

      const title = this._config.title || 'Consumption';
      const noEntities = this._tabs.length === 0;

      const tabsHtml = this._tabs.map(t =>
        `<button class="meter-tab${t.id === this._activeTab ? ' active' : ''}" data-tab="${t.id}">${t.label}</button>`
      ).join('');

      this.shadowRoot.innerHTML = `
        <style>${STYLES}</style>
        <ha-card>
          <div class="card-header">${title}</div>
          ${noEntities
            ? `<div class="state-msg">No EDF Energy consumption entities found.</div>`
            : `
          <div class="meter-tabs">${tabsHtml}</div>
          <div class="controls-row">
            <div class="btn-group" id="view-btns">
              <button data-view="halfhourly" class="${this._activeView === 'halfhourly' ? 'active' : ''}">Today</button>
              <button data-view="weekly"     class="${this._activeView === 'weekly'     ? 'active' : ''}">Weekly</button>
              <button data-view="monthly"    class="${this._activeView === 'monthly'    ? 'active' : ''}">Monthly</button>
            </div>
            <div class="btn-group" id="unit-btns" style="${this._activeTab === 'net' ? 'display:none' : ''}">
              <button data-unit="kwh"  class="${this._activeUnit === 'kwh'  ? 'active' : ''}">kWh</button>
              <button data-unit="cost" class="${this._activeUnit === 'cost' ? 'active' : ''}">£</button>
            </div>
          </div>
          <div class="nav-row">
            <button class="nav-btn" id="btn-prev">&#8249;</button>
            <span class="period-label" id="period-label"></span>
            <button class="nav-btn" id="btn-next" disabled>&#8250;</button>
          </div>
          <div class="chart-wrap">
            <div id="chart-container" class="chart-container"></div>
            <div id="state-msg" class="state-msg">Loading…</div>
          </div>
          <div class="summary" id="summary"></div>
          `}
        </ha-card>
      `;

      if (!noEntities) { this._attachListeners(); this._syncControls(); }
    }

    _syncControls() {
      this.shadowRoot.querySelectorAll('.meter-tab').forEach(b =>
        b.classList.toggle('active', b.dataset.tab === this._activeTab));
      this.shadowRoot.querySelectorAll('#view-btns button').forEach(b =>
        b.classList.toggle('active', b.dataset.view === this._activeView));
      this.shadowRoot.querySelectorAll('#unit-btns button').forEach(b =>
        b.classList.toggle('active', b.dataset.unit === this._activeUnit));
      const unitBtns = this.shadowRoot.getElementById('unit-btns');
      if (unitBtns)
        unitBtns.style.display = this._activeTab === 'net' ? 'none' : '';

      const btnPrev = this.shadowRoot.getElementById('btn-prev');
      const btnNext = this.shadowRoot.getElementById('btn-next');
      const labelEl = this.shadowRoot.getElementById('period-label');
      const maxOffset = this._activeView === 'halfhourly' ? 60 : 99;
      if (btnPrev) btnPrev.disabled = this._periodOffset >= maxOffset;
      if (btnNext) btnNext.disabled = this._periodOffset <= 0;
      if (labelEl)  labelEl.textContent = this._navLabel();
    }

    _navLabel() {
      const o = this._periodOffset;
      if (this._activeView === 'halfhourly') {
        if (o === 0) return 'Today';
        if (o === 1) return 'Yesterday';
        const d = new Date();
        d.setDate(d.getDate() - o);
        return d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
      }
      const { start, end } = this._periodRange();
      const fmt = this._activeView === 'monthly'
        ? { month: 'short', year: 'numeric' }
        : { day: 'numeric', month: 'short' };
      return `${start.toLocaleDateString(undefined, fmt)} – ${end.toLocaleDateString(undefined, fmt)}`;
    }

    _attachListeners() {
      this.shadowRoot.querySelectorAll('.meter-tab').forEach(btn => {
        btn.addEventListener('click', () => {
          this._activeTab = btn.dataset.tab;
          if (this._activeTab === 'net') this._activeUnit = 'cost';
          this._periodOffset = 0;
          this._syncControls();
          this._scheduleUpdate(0);
        });
      });
      this.shadowRoot.querySelectorAll('#view-btns button').forEach(btn => {
        btn.addEventListener('click', () => {
          this._activeView = btn.dataset.view;
          this._periodOffset = btn.dataset.view === 'halfhourly' ? 1 : 0;
          this._syncControls();
          this._scheduleUpdate(0);
        });
      });
      this.shadowRoot.getElementById('btn-prev')?.addEventListener('click', () => {
        if (this._activeView === 'halfhourly' && this._periodOffset >= 1) return;
        this._periodOffset++;
        this._syncControls();
        this._scheduleUpdate(0);
      });
      this.shadowRoot.getElementById('btn-next')?.addEventListener('click', () => {
        if (this._periodOffset <= 0) return;
        this._periodOffset--;
        this._syncControls();
        this._scheduleUpdate(0);
      });
      this.shadowRoot.querySelectorAll('#unit-btns button').forEach(btn => {
        btn.addEventListener('click', () => {
          this._activeUnit = btn.dataset.unit;
          this._syncControls();
          this._scheduleUpdate(0);
        });
      });
    }

    // ── Update ────────────────────────────────────────────────────────────────

    _dataKey() {
      return `${this._activeTab}|${this._activeView}|${this._periodOffset}|${this._activeUnit}`;
    }

    _scheduleUpdate(delay = 300) {
      clearTimeout(this._updateTimer);
      // Only today/yesterday halfhourly is live; everything else is cached by _dataKey
      const isLive = this._activeView === 'halfhourly' && this._periodOffset <= 1;
      if (delay === 300 && !isLive && this._dataKey() === this._renderedKey) return;
      this._updateTimer = setTimeout(() => this._doUpdate(), delay);
    }

    async _doUpdate() {
      if (!this._hass || !this._activeTab) return;
      this._showMsg('Loading…');
      try {
        let result;
        if (this._activeView === 'halfhourly' && this._periodOffset <= 1) {
          result = this._getHalfHourlyData();
        } else if (this._activeView === 'halfhourly') {
          result = await this._getHourlyData();
        } else if (this._activeTab === 'net') {
          result = await this._getNetCostData();
        } else {
          result = await this._getStatData();
        }
        await this._applyChart(result);
      } catch (e) {
        console.error('[EDF Consumption Card]', e);
        this._showMsg('Error loading data.');
      }
    }

    // ── Half-hourly data ──────────────────────────────────────────────────────

    _getHalfHourlyData() {
      const tabInfo = this._tabs.find(t => t.id === this._activeTab);
      if (!tabInfo?.entity) return null;

      const currState = this._hass.states[this._currentAccEntity(tabInfo.entity)];
      const prevState = this._hass.states[tabInfo.entity];
      // offset 0 = today (current only), offset 1 = yesterday (previous only)
      let charges = this._periodOffset === 0
        ? (currState?.attributes?.charges || [])
        : (prevState?.attributes?.charges || []);
      charges = [...charges].sort((a, b) => new Date(a.start) - new Date(b.start));
      if (!charges.length) return null;

      const date = new Date(charges[0].start);
      const isToday = new Date().toDateString() === date.toDateString();
      const dateLabel = isToday
        ? 'Today'
        : date.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });

      const categories = charges.map(c => {
        const d = new Date(c.start);
        return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
      });
      const kwhData   = charges.map(c => +(parseFloat(c.consumption) || 0).toFixed(4));
      const costData  = charges.map(c => +(parseFloat(c.cost) || 0).toFixed(4));
      const totalKwh  = kwhData.reduce((a, b) => a + b, 0);
      const totalCost = costData.reduce((a, b) => a + b, 0);
      const showCost  = this._activeUnit === 'cost';

      const summary = showCost
        ? [
            { label: dateLabel,  value: '£' + totalCost.toFixed(2) },
            { label: 'kWh',      value: totalKwh.toFixed(2) },
          ]
        : [
            { label: dateLabel,  value: totalKwh.toFixed(2) + ' kWh' },
            ...(totalCost > 0 ? [{ label: 'Unit cost', value: '£' + totalCost.toFixed(2) }] : []),
          ];

      return {
        series: [{ name: showCost ? '£' : 'kWh', data: showCost ? costData : kwhData }],
        categories,
        unit: showCost ? '£' : 'kWh',
        isHalfHourly: true,
        summary,
      };
    }

    // ── Hourly data (historical days via stats API) ───────────────────────────

    async _getHourlyData() {
      const tabInfo = this._tabs.find(t => t.id === this._activeTab);
      if (!tabInfo?.entity) return null;

      const target = new Date();
      target.setDate(target.getDate() - this._periodOffset);

      const dayStart = new Date(target);
      dayStart.setHours(0, 0, 0, 0);
      const dayEnd = new Date(target);
      dayEnd.setHours(23, 59, 59, 999);
      const refStart = new Date(dayStart);
      refStart.setHours(refStart.getHours() - 1);

      const costStatId = this._toStatId(tabInfo.entity);
      const kwhStatId  = this._kwhStatId(tabInfo.entity);
      const scPerDay   = this._standingChargePerDay(tabInfo.entity);
      const showCost   = this._activeUnit === 'cost';

      const result  = await this._fetchStats([costStatId, kwhStatId], 'hour', refStart, dayEnd);
      const startMs = dayStart.getTime();
      const { window: costStats, refSum: refCostSum } = this._splitRef(result[costStatId] || [], startMs);
      const { window: kwhStats,  refSum: refKwhSum  } = this._splitRef(result[kwhStatId]  || [], startMs);

      const refStats = costStats.length ? costStats : kwhStats;
      if (!refStats.length) return null;

      const scPerHour  = scPerDay / 24;
      const categories = refStats.map(s => {
        const d = new Date(s.start);
        return `${String(d.getHours()).padStart(2, '0')}:00`;
      });
      const costData  = costStats.map((s, i) => +(this._sumChange(costStats, i, refCostSum) + scPerHour).toFixed(4));
      const kwhData   = kwhStats.map((s, i)  => +(this._sumChange(kwhStats,  i, refKwhSum)).toFixed(3));
      const totalCost = costData.reduce((a, b) => a + b, 0);
      const totalKwh  = kwhData.reduce((a, b) => a + b, 0);

      const series = showCost
        ? [{ name: '£',   data: costData.length ? costData : Array(refStats.length).fill(0) }]
        : [{ name: 'kWh', data: kwhData.length  ? kwhData  : Array(refStats.length).fill(0) }];

      const dateLabel = target.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
      const summary = showCost
        ? [{ label: dateLabel, value: '£' + totalCost.toFixed(2) }, { label: 'kWh', value: totalKwh.toFixed(2) }]
        : [
            { label: dateLabel, value: totalKwh.toFixed(2) + ' kWh' },
            ...(totalCost > 0 ? [{ label: 'Unit cost', value: '£' + totalCost.toFixed(2) }] : []),
          ];

      return { series, categories, unit: showCost ? '£' : 'kWh', summary };
    }

    // ── Statistics data ───────────────────────────────────────────────────────

    async _fetchStats(statIds, period, startTime, endTime = null) {
      const msg = {
        type: 'recorder/statistics_during_period',
        start_time: startTime.toISOString(),
        ...(endTime ? { end_time: endTime.toISOString() } : {}),
        statistic_ids: statIds,
        period,
        types: ['sum'],
        units: { energy: 'kWh' },
      };
      if (this._hass.callWS) return this._hass.callWS(msg);
      return this._hass.connection.sendMessagePromise(msg);
    }

    _periodRange() {
      const o = this._periodOffset;
      const now = new Date();
      let start, end;

      if (this._activeView === 'weekly') {
        end = new Date(now);
        end.setDate(end.getDate() - o * 7);
        end.setHours(23, 59, 59, 999);
        start = new Date(end);
        start.setDate(start.getDate() - 6);
        start.setHours(0, 0, 0, 0);
      } else {
        // monthly
        end = new Date(now);
        end.setMonth(end.getMonth() - o * 12);
        end.setHours(23, 59, 59, 999);
        start = new Date(end);
        start.setFullYear(start.getFullYear() - 1);
        start.setDate(1);
        start.setHours(0, 0, 0, 0);
      }
      return { start, end };
    }

    _sumChange(stats, i, refSum) {
      const prev = i === 0 ? refSum : (stats[i - 1].sum || 0);
      return Math.max(0, (stats[i].sum || 0) - (prev || 0));
    }

    _splitRef(allStats, startMs) {
      const window = allStats.filter(s => s.start >= startMs);
      const refEntry = allStats.filter(s => s.start < startMs).at(-1);
      return { window, refSum: refEntry?.sum ?? null };
    }

    _periodLabel(startMs, period) {
      const d = new Date(startMs);
      return period === 'month'
        ? d.toLocaleDateString(undefined, { month: 'short', year: '2-digit' })
        : d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
    }

    _daysInMonth(startMs) {
      const d = new Date(startMs);
      return new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate();
    }

    async _getStatData() {
      const tabInfo = this._tabs.find(t => t.id === this._activeTab);
      if (!tabInfo?.entity) return null;

      const period     = this._activeView === 'monthly' ? 'month' : 'day';
      const { start, end } = this._periodRange();
      const costStatId = this._toStatId(tabInfo.entity);
      const kwhStatId  = this._kwhStatId(tabInfo.entity);
      const scPerDay   = this._standingChargePerDay(tabInfo.entity);
      const showCost   = this._activeUnit === 'cost';

      // Fetch one extra period before window start to get a reference sum
      const refStart = new Date(start);
      if (period === 'day') refStart.setDate(refStart.getDate() - 1);
      else refStart.setMonth(refStart.getMonth() - 1);

      const result   = await this._fetchStats([costStatId, kwhStatId], period, refStart, this._periodOffset > 0 ? end : null);
      const startMs  = start.getTime();
      const { window: costStats, refSum: refCostSum } = this._splitRef(result[costStatId] || [], startMs);
      const { window: kwhStats,  refSum: refKwhSum  } = this._splitRef(result[kwhStatId]  || [], startMs);

      const refStats = costStats.length ? costStats : kwhStats;
      if (!refStats.length) return null;

      const categories = refStats.map(s => this._periodLabel(s.start, period));

      const costData = costStats.map((s, i) => {
        const unitCost = this._sumChange(costStats, i, refCostSum);
        const standing = period === 'month' ? scPerDay * this._daysInMonth(s.start) : scPerDay;
        return +(unitCost + standing).toFixed(4);
      });

      const kwhData   = kwhStats.map((s, i) => +(this._sumChange(kwhStats, i, refKwhSum)).toFixed(3));
      const totalCost = costData.reduce((a, b) => a + b, 0);
      const totalKwh  = kwhData.reduce((a, b) => a + b, 0);

      const series = showCost
        ? [{ name: '£',   data: costData.length ? costData : Array(refStats.length).fill(0) }]
        : [{ name: 'kWh', data: kwhData.length  ? kwhData  : Array(refStats.length).fill(0) }];

      const summary = [];
      if (kwhData.length)  summary.push({ label: 'Total',   value: totalKwh.toFixed(1) + ' kWh' });
      if (costData.length) summary.push({ label: 'Cost',    value: '£' + totalCost.toFixed(2) });
      if (scPerDay > 0)    summary.push({ label: 'Standing', value: '£' + scPerDay.toFixed(2) + '/day' });

      return { series, categories, unit: showCost ? '£' : 'kWh', summary };
    }

    async _getNetCostData() {
      if (!this._meters.import || !this._meters.export) return null;

      const period   = this._activeView === 'monthly' ? 'month' : 'day';
      const { start, end } = this._periodRange();
      const importId = this._toStatId(this._meters.import);
      const exportId = this._toStatId(this._meters.export);

      const refStart = new Date(start);
      if (period === 'day') refStart.setDate(refStart.getDate() - 1);
      else refStart.setMonth(refStart.getMonth() - 1);

      const result  = await this._fetchStats([importId, exportId], period, refStart, this._periodOffset > 0 ? end : null);
      const startMs = start.getTime();
      const { window: importStats, refSum: refImportSum } = this._splitRef(result[importId] || [], startMs);
      const { window: exportStats, refSum: refExportSum } = this._splitRef(result[exportId] || [], startMs);
      if (!importStats.length) return null;

      const exportByStart = {};
      exportStats.forEach((s, i) => { exportByStart[s.start] = this._sumChange(exportStats, i, refExportSum); });

      const scPerDay   = this._standingChargePerDay(this._meters.import);
      const categories = importStats.map(s => this._periodLabel(s.start, period));

      const netData = importStats.map((s, i) => {
        const imp      = this._sumChange(importStats, i, refImportSum);
        const exp      = exportByStart[s.start] || 0;
        const standing = period === 'month' ? scPerDay * this._daysInMonth(s.start) : scPerDay;
        return +(imp + standing - exp).toFixed(4);
      });

      const total = netData.reduce((a, b) => a + b, 0);
      return {
        series: [{ name: 'Net £', data: netData }],
        categories,
        unit: '£',
        summary: [{ label: 'Net cost', value: (total >= 0 ? '£' : '-£') + Math.abs(total).toFixed(2) }],
      };
    }

    // ── Chart ─────────────────────────────────────────────────────────────────

    async _applyChart(data) {
      if (!data?.series?.length || data.series.every(s => !s.data.length)) {
        this._showMsg('No data available for this period.');
        return;
      }

      const container = this.shadowRoot.getElementById('chart-container');
      if (!container) return;

      let ApexCharts;
      try {
        ApexCharts = await ensureApexCharts();
      } catch {
        this._showMsg('Chart library failed to load. Check your network connection.');
        return;
      }

      const msgEl = this.shadowRoot.getElementById('state-msg');
      if (msgEl) msgEl.style.display = 'none';
      container.style.display = '';

      if (this._chart) { this._chart.destroy(); this._chart = null; }

      const isDark = !!document.querySelector('home-assistant')?.shadowRoot
        ?.querySelector('home-assistant-main')
        ?.getAttribute('data-theme')?.includes('dark')
        || window.matchMedia('(prefers-color-scheme: dark)').matches;

      const isPound = data.unit === '£';

      const opts = {
        chart: {
          type: 'bar',
          height: 220,
          background: 'transparent',
          toolbar: { show: false },
          animations: { enabled: false },
          fontFamily: 'inherit',
        },
        theme: { mode: isDark ? 'dark' : 'light' },
        series: data.series,
        xaxis: {
          categories: data.categories,
          labels: {
            rotate: -45,
            style: { fontSize: '10px' },
            hideOverlappingLabels: true,
            maxHeight: 60,
            formatter: data.isHalfHourly
              ? (val, opts) => {
                  // ApexCharts passes index as number or inside an opts object
                  const idx = typeof opts === 'number' ? opts : opts?.dataPointIndex;
                  return (typeof idx === 'number' && idx % 4 === 0) ? val : '';
                }
              : val => val,
          },
          axisBorder: { show: false },
          axisTicks: { show: false },
        },
        yaxis: {
          min: 0,
          labels: {
            formatter: v => isPound ? '£' + v.toFixed(2) : v.toFixed(2) + ' kWh',
            style: { fontSize: '10px' },
          },
        },
        dataLabels: { enabled: false },
        tooltip: {
          shared: false,
          intersect: false,
          x: { show: true },
          y: {
            title: { formatter: () => '' },
            formatter: v => isPound ? '£' + v.toFixed(3) : v.toFixed(3) + ' kWh',
          },
        },
        grid: {
          borderColor: isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.08)',
          strokeDashArray: 3,
          padding: { left: 0, right: 0 },
        },
        colors: [this._tabColor()],
        plotOptions: {
          bar: { columnWidth: '70%', borderRadius: 2, borderRadiusApplication: 'end' },
        },
      };

      container.innerHTML = '';
      this._chart = new ApexCharts(container, opts);
      await this._chart.render();
      this._renderedKey = this._dataKey();

      const summaryEl = this.shadowRoot.getElementById('summary');
      if (summaryEl) {
        summaryEl.innerHTML = (data.summary || []).map(i =>
          `<div class="summary-item">
            <div class="summary-label">${i.label}</div>
            <div class="summary-value">${i.value}</div>
          </div>`
        ).join('');
      }
    }

    _tabColor() {
      switch (this._activeTab) {
        case 'export': return '#2E7D32';
        case 'gas':    return '#E65100';
        case 'net':    return '#6A1B9A';
        default:       return '#1565C0';
      }
    }

    _showMsg(msg) {
      const container = this.shadowRoot.getElementById('chart-container');
      if (container) container.style.display = 'none';
      const msgEl = this.shadowRoot.getElementById('state-msg');
      if (msgEl) { msgEl.textContent = msg; msgEl.style.display = ''; }
      const summaryEl = this.shadowRoot.getElementById('summary');
      if (summaryEl) summaryEl.innerHTML = '';
    }

    // ── Boilerplate ───────────────────────────────────────────────────────────

    getCardSize() { return 5; }
    static getStubConfig() { return { title: 'Consumption' }; }
  }

  if (!customElements.get('edf-energy-consumption-card')) {
    customElements.define('edf-energy-consumption-card', EDFEnergyConsumptionCard);
    console.info(
      '%c EDF ENERGY CONSUMPTION CARD %c Loaded ',
      'color:#fff;background:#1a237e;font-weight:700;padding:1px 6px;border-radius:3px 0 0 3px',
      'background:#3949ab;color:#fff;padding:1px 6px;border-radius:0 3px 3px 0'
    );
  }
})();

// <kindle-panel-editor>: HA sidebar panel for laying out the Kindle screen.
// Layout data is edited locally (draft) and rendered by the server ("preview") so the stage shows
// exactly what the Kindle will paint.

const PREVIEW_DELAY = 160;
const POLL_SECONDS = 15;

class KindlePanelEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: 'open'});
    Object.assign(this, {
      data: null, draft: null, frame: null, views: {}, dirty: false, saving: false, error: '', notice: '',
      pageIndex: 0, selection: null, tab: 'edit', mobileTab: 'stage', previewDevice: null, pairUrl: '',
      picker: null, drag: null, serial: 0,
    });
  }

  // ------------------------------------------------------------------ HA lifecycle
  set hass(value) {
    const previous = this._hass;
    this._hass = value;
    if (!this.data && !this._loading && this.isConnected) this.load();
    else if (this.draft && previous && this.tileEntities().some(id => previous.states[id] !== value.states[id])) {
      this.schedulePreview(1000);
    }
    if (this.picker) this.renderPicker();
  }
  get hass() { return this._hass; }
  set narrow(value) { this.toggleAttribute('narrow', !!value); if (this.draft) this.renderAll(); }
  get demo() { return this.hasAttribute('preview'); }

  connectedCallback() {
    if (!this.shadowRoot.firstChild) this.shell();
    if (this._hass && !this.data) this.load();
    this.poll = setInterval(() => { if (this.data && !this.dirty && !this.drag && !this.saving) this.load(true); }, POLL_SECONDS * 1000);
    this.resize = new ResizeObserver(() => this.renderStage());
    this.resize.observe(this);
    this.keys = event => this.onKey(event);
    window.addEventListener('keydown', this.keys);
  }
  disconnectedCallback() {
    clearInterval(this.poll);
    clearTimeout(this.previewTimer);
    this.resize?.disconnect();
    window.removeEventListener('keydown', this.keys);
  }

  call(action, values = {}) { return this._hass.callWS({type: 'kindle_panel/manage', action, ...values}); }

  async load(background = false) {
    this._loading = true;
    try {
      const data = await this.call('load', this.previewDevice ? {device_id: this.previewDevice} : {});
      const changed = !this.data || data.revision !== this.data.revision;
      this.data = data;
      if (!this.pairUrl) this.pairUrl = data.suggested_url || (location.protocol === 'http:' ? location.origin : '');
      if (!this.dirty && (changed || !background)) {
        this.draft = clone(data.layout);
        this.frame = data.frame;
        this.views = data.views;
        this.pageIndex = clamp(this.pageIndex, 0, this.draft.pages.length - 1);
        if (!this.selection || !this.lookup(this.selection)) this.selection = this.firstSelection();
        this.renderAll();
      } else if (!this.dirty) {
        this.frame = data.frame;
        this.views = data.views;
        this.renderList(); this.renderStage(); this.renderTop();
        if (this.tab === 'devices') this.renderInspector();
      } else {
        this.renderTop();
      }
    } catch (error) {
      this.error = error.message || '读取配置失败';
      this.renderAll();
    } finally {
      this._loading = false;
    }
  }

  // ------------------------------------------------------------------ model helpers
  get page() { return this.draft.pages[this.pageIndex]; }
  tileEntities() { return this.draft ? this.draft.pages.flatMap(p => p.sections.flatMap(s => s.tiles.map(t => t.entity_id))) : []; }
  firstSelection() {
    const section = this.page.sections[0];
    return section.tiles[0] ? {type: 'tile', id: section.tiles[0].id} : {type: 'section', id: section.id};
  }
  lookup(selection) {
    for (const [pageIndex, page] of this.draft.pages.entries()) {
      if (selection.type === 'page' && page.id === selection.id) return {page, pageIndex};
      for (const section of page.sections) {
        if (selection.type === 'section' && section.id === selection.id) return {page, pageIndex, section};
        const tile = section.tiles.find(t => t.id === selection.id);
        if (selection.type === 'tile' && tile) return {page, pageIndex, section, tile};
      }
    }
    return null;
  }
  usedRows(page, except) { return page.sections.reduce((n, s) => n + (s === except ? 0 : s.rows), 0); }
  tileCount() { return this.draft.pages.reduce((n, p) => n + p.sections.reduce((m, s) => m + s.tiles.length, 0), 0); }
  entityName(id) { return this._hass?.states[id]?.attributes?.friendly_name || id; }

  /** Free cell for a w×h tile in a section (client-side mirror of place_tiles), or null. */
  findSpot(section, columns, w, h, ignore) {
    const used = Array.from({length: section.rows}, () => Array(columns).fill(false));
    for (const tile of section.tiles) {
      if (tile === ignore || tile.x == null) continue;
      for (let y = tile.y; y < Math.min(section.rows, tile.y + tile.h); y++)
        for (let x = tile.x; x < Math.min(columns, tile.x + tile.w); x++) used[y][x] = true;
    }
    for (let y = 0; y + h <= section.rows; y++)
      for (let x = 0; x + w <= columns; x++) {
        let free = true;
        for (let i = y; i < y + h && free; i++) for (let j = x; j < x + w; j++) if (used[i][j]) { free = false; break; }
        if (free) return {x, y};
      }
    return null;
  }
  /** Mirror of protocol.place_tiles: keep valid explicit positions, first-fit the rest. Map of id → {x, y}, or null. */
  pack(tiles, columns, rows) {
    const used = Array.from({length: rows}, () => Array(columns).fill(false));
    const fits = (x, y, w, h) => x >= 0 && y >= 0 && x + w <= columns && y + h <= rows &&
      used.slice(y, y + h).every(row => row.slice(x, x + w).every(cell => !cell));
    const occupy = (t, x, y) => { for (let i = y; i < y + t.h; i++) for (let j = x; j < x + t.w; j++) used[i][j] = true; placed.set(t.id, {x, y}); };
    const placed = new Map(), pending = [];
    for (const t of tiles) (t.x != null && fits(t.x, t.y, t.w, t.h)) ? occupy(t, t.x, t.y) : pending.push(t);
    for (const t of pending) {
      let spot = null;
      for (let y = 0; y + t.h <= rows && !spot; y++) for (let x = 0; x + t.w <= columns && !spot; x++) if (fits(x, y, t.w, t.h)) spot = {x, y};
      if (!spot) return null;
      occupy(t, spot.x, spot.y);
    }
    return placed;
  }
  /** Put `tile` at `rect` in `section`; tiles it covers swap into its old spot or re-pack. False (no change) if impossible. */
  relocate(section, columns, tile, rect, swap = true) {
    const others = section.tiles.filter(t => t !== tile).map(t => ({...t, w: t.w ?? 1, h: t.h ?? 1}));
    const covered = t => t.x != null && t.x < rect.x + rect.w && rect.x < t.x + t.w && t.y < rect.y + rect.h && rect.y < t.y + t.h;
    const attempt = shifted => this.pack([{...tile, ...rect}, ...others.map(t => !covered(t) ? t
      : shifted ? {...t, x: t.x - rect.x + tile.x, y: t.y - rect.y + tile.y} : {...t, x: null, y: null})], columns, section.rows);
    const placed = (swap && tile.x != null && attempt(true)) || attempt(false);
    if (!placed) {
      this.error = '这里放不下，已取消调整；可以先缩小其他卡片或增加分组行数';
      this.renderTop(); this.renderStage();
      return false;
    }
    if (!section.tiles.includes(tile)) section.tiles.push(tile);
    Object.assign(tile, rect);
    for (const t of section.tiles) Object.assign(t, placed.get(t.id));
    this.error = '';
    return true;
  }

  changed({inspector = false} = {}) {
    this.dirty = true;
    this.notice = '';
    this.renderTop(); this.renderList();
    if (inspector) this.renderInspector();
    this.schedulePreview();
  }

  schedulePreview(delay = PREVIEW_DELAY) {
    clearTimeout(this.previewTimer);
    const serial = ++this.serial;
    this.previewTimer = setTimeout(async () => {
      try {
        const result = await this.call('preview', {layout: clone(this.draft), ...(this.previewDevice ? {device_id: this.previewDevice} : {})});
        if (serial !== this.serial || !this.isConnected) return;
        this.error = '';
        this.mergePlacement(result.layout);
        this.frame = result.frame;
        this.views = result.views;
        this.renderStage(); this.renderList(); this.renderTop();
        if (this.selection?.type === 'tile') this.renderInspectorHeader();
      } catch (error) {
        if (serial !== this.serial) return;
        this.error = error.message || '请检查布局设置';
        this.renderTop(); this.renderStage();
      }
    }, delay);
  }

  /** Adopt server-assigned positions/sizes without disturbing fields the user is typing in. */
  mergePlacement(layout) {
    const placed = new Map();
    for (const page of layout.pages) for (const section of page.sections) for (const tile of section.tiles) placed.set(tile.id, tile);
    for (const page of this.draft.pages) for (const section of page.sections) {
      for (const tile of section.tiles) {
        const server = placed.get(tile.id);
        if (server) Object.assign(tile, {x: server.x, y: server.y, w: server.w, h: server.h, kind: server.kind});
      }
      section.tiles.sort((a, b) => (a.y - b.y) || (a.x - b.x));
    }
  }

  // ------------------------------------------------------------------ rendering
  shell() {
    this.shadowRoot.innerHTML = `<style>${EDITOR_CSS}${PAINTER_CSS}</style><div class="app">
      <header class="topbar" id="top"></header>
      ${this.demo ? '<div class="demo-note">本地模拟预览：使用示例状态，不连接 Home Assistant，不会操作任何设备。</div>' : ''}
      <nav class="mtabs" id="mtabs"></nav>
      <main class="workspace">
        <aside class="pane left" id="list"></aside>
        <section class="stage" id="stage"></section>
        <aside class="pane right" id="inspector"></aside>
      </main></div><div id="dialog"></div>`;
    const root = this.shadowRoot;
    root.addEventListener('click', event => this.onClick(event));
    root.addEventListener('input', event => this.onInput(event));
    root.addEventListener('change', event => this.onInput(event, true));
    root.addEventListener('pointerdown', event => this.onPointerDown(event));
    root.addEventListener('dragstart', event => this.onDragStart(event));
    root.addEventListener('dragover', event => this.onDragOver(event));
    root.addEventListener('dragleave', event => event.target.closest?.('.tile-list')?.classList.remove('drop'));
    root.addEventListener('drop', event => this.onDrop(event));
  }

  renderAll() {
    if (!this.shadowRoot.firstChild) this.shell();
    if (!this.draft) {
      this.shadowRoot.querySelector('#stage').innerHTML = `<p class="stage-hint">${escapeHtml(this.error || '正在载入 Kindle 面板…')}</p>`;
      return;
    }
    this.renderTop(); this.renderMobileTabs(); this.renderList(); this.renderStage(); this.renderInspector();
  }

  deviceById(id) { return this.data?.devices.find(d => d.id === id); }
  online(device) { return device && Date.now() / 1000 - (device.last_seen || 0) < 90; }

  renderTop() {
    const top = this.shadowRoot.querySelector('#top');
    if (!top || !this.data) return;
    const device = this.deviceById(this.previewDevice) || this.data.devices[0];
    const notice = this.error ? `<span class="notice error" title="${escapeHtml(this.error)}">${escapeHtml(this.error)}</span>`
      : this.dirty ? '<span class="notice dirty">有修改尚未同步到 Kindle</span>'
      : `<span class="notice">${escapeHtml(this.notice || '布局已保存')}</span>`;
    const chip = device
      ? `<span class="chip hide-narrow"><span class="dot ${this.online(device) ? '' : 'off'}"></span>${escapeHtml(device.name)} · ${this.online(device) ? '在线' : '休眠或离线'}${device.battery != null ? ' · ' + Math.round(device.battery) + '%' : ''}</span>`
      : '<span class="chip hide-narrow"><span class="dot off"></span>尚未配对 Kindle</span>';
    top.innerHTML = `<button class="menu-btn" data-action="menu" aria-label="打开侧边栏">${ui('menu')}</button>
      <span class="brand">Kindle 面板</span><span class="spacer"></span>${notice}${chip}
      <button class="btn text hide-narrow" data-action="discard" ${this.dirty ? '' : 'disabled'}>${ui('undo')}放弃修改</button>
      <button class="btn primary" data-action="save" ${this.dirty && !this.saving ? '' : 'disabled'}>${ui('sync')}${this.hasAttribute('narrow') ? '保存' : '保存并同步'}</button>`;
  }

  renderMobileTabs() {
    const tabs = [['stage', '预览'], ['list', '卡片'], ['inspector', '编辑'], ['panel', '设置'], ['devices', '设备']];
    this.shadowRoot.querySelector('#mtabs').innerHTML = tabs.map(([key, label]) =>
      `<button class="${this.mobileTab === key ? 'on' : ''}" data-action="mobile-tab" data-value="${key}">${label}</button>`).join('');
    const map = {stage: '#stage', list: '#list', inspector: '#inspector', panel: '#inspector', devices: '#inspector'};
    for (const id of ['#stage', '#list', '#inspector']) this.shadowRoot.querySelector(id).classList.toggle('show', map[this.mobileTab] === id);
  }

  renderList() {
    const list = this.shadowRoot.querySelector('#list');
    if (!list || !this.draft) return;
    const page = this.page, sel = this.selection || {};
    const chips = this.draft.pages.map((p, i) => `<button class="page-chip ${i === this.pageIndex ? 'on' : ''}" data-action="page" data-value="${i}">${escapeHtml(p.title)}</button>`).join('');
    const sections = page.sections.map((section, index) => {
      const rows = section.tiles.map(tile => {
        const view = this.views[tile.id] || {};
        const stateClass = view.available === false ? 'off' : view.on ? 'on' : '';
        return `<div class="row ${sel.type === 'tile' && sel.id === tile.id ? 'sel' : ''}" draggable="true" data-tile="${tile.id}" data-action="select-tile" data-value="${tile.id}">
          <span class="grip">${ui('grip')}</span><span class="ico">${iconSvg(tile.icon, 'currentColor', 1.8)}</span>
          <span style="min-width:0"><div class="name">${escapeHtml(tile.title)}</div><div class="mono">${escapeHtml(tile.entity_id)}</div></span>
          <span class="state ${stateClass}">${escapeHtml(view.text ?? '')}${view.unit ? ' ' + escapeHtml(view.unit) : ''}</span></div>`;
      }).join('');
      return `<div class="section-head ${sel.type === 'section' && sel.id === section.id ? 'sel' : ''}" data-action="select-section" data-value="${section.id}">
          <span class="name">${escapeHtml(section.title || `分组 ${index + 1}（不显示标题）`)}</span><small>${section.tiles.length} 张 · ${section.rows} 行</small>
          <button class="icon-btn" data-action="select-section" data-value="${section.id}" aria-label="分组设置">${ui('gear')}</button></div>
        <div class="tile-list" data-section="${section.id}">${rows || '<div class="empty">拖入卡片，或点击下方添加</div>'}</div>
        <button class="add-row" data-action="add-tile" data-value="${section.id}">${ui('plus')}添加卡片</button>`;
    }).join('');
    list.innerHTML = `<div class="pages">${chips}<button class="page-chip" data-action="add-page" ${this.draft.pages.length >= 8 ? 'disabled' : ''}>${ui('plus')}页面</button>
        <button class="page-chip" data-action="select-page" aria-label="页面设置">${ui('gear')}页面设置</button></div>
      ${sections}
      <div class="list-foot"><button class="btn small block" data-action="add-section" ${page.sections.length >= 6 || this.usedRows(page) >= 8 ? 'disabled' : ''}>${ui('folder')}添加分组（房间）</button>
      <p class="hint">共 ${this.tileCount()} / 60 张卡片 · 本页已用 ${this.usedRows(page)} / 8 行</p></div>`;
  }

  stageScale(stage) {
    const screen = this.frame?.screen || {width: 758, height: 1024};
    const width = stage.clientWidth - 70, height = stage.clientHeight - (this.hasAttribute('narrow') ? 120 : 190);
    return clamp(Math.min(width / screen.width, height / screen.height), 0.25, 1);
  }

  renderStage() {
    const stage = this.shadowRoot.querySelector('#stage');
    if (!stage || !this.frame || !this.draft) return;
    const frame = this.frame, page = frame.pages[this.pageIndex] || frame.pages[0];
    const screen = frame.screen, scale = this.stageScale(stage);
    const device = this.deviceById(this.previewDevice) || this.data.devices[0];
    const tokens = {status: kindleStatus(), battery: device?.battery != null ? Math.round(device.battery) + '%' : '82%'};
    const sel = this.selection || {};
    const hots = page.cards.map(card => `<div class="hot ${sel.type === 'tile' && sel.id === card.id ? 'sel' : ''}" data-card="${card.id}"
      style="left:${card.x * scale}px;top:${card.y * scale}px;width:${card.w * scale}px;height:${card.h * scale}px;border-radius:${card.r * scale}px">
      <span class="resize" data-resize="${card.id}"></span></div>`).join('');
    const sectionHots = page.sections.filter(s => s.head).map(s => `<div class="section-hot" data-action="select-section" data-value="${s.id}"
      style="left:${s.grid.x * scale}px;top:${s.y * scale}px;width:${(screen.width - 2 * s.grid.x) * scale}px;height:${s.head * scale}px"></div>`).join('');
    const pages = frame.pages.length;
    stage.innerHTML = `<div class="stage-top"><span>预览尺寸：${device ? escapeHtml(device.name) + ' · ' : ''}${screen.width} × ${screen.height}</span><span>${escapeHtml(this.draft.pages[this.pageIndex]?.title || '')} · 第 ${this.pageIndex + 1} / ${pages} 页</span></div>
      <div class="bezel"><div class="crop" style="width:${screen.width * scale}px;height:${screen.height * scale}px">
        <div class="kindle-screen" style="width:${screen.width}px;height:${screen.height}px;transform:scale(${scale})">${paintPage(page, screen, tokens)}</div>
        <div class="overlay" id="overlay">${sectionHots}${hots}</div></div></div>
      <div class="pager"><button class="pg" data-action="page" data-value="${this.pageIndex - 1}" ${this.pageIndex === 0 ? 'disabled' : ''} aria-label="上一页">${ui('left')}</button>
        <span>第 ${this.pageIndex + 1} / ${pages} 页</span>
        <button class="pg" data-action="page" data-value="${this.pageIndex + 1}" ${this.pageIndex >= pages - 1 ? 'disabled' : ''} aria-label="下一页">${ui('right')}</button></div>
      <div class="stage-hint">点击卡片编辑 · 拖动卡片换位置 · 拖右下角改大小 · 预览不会操作真实设备</div>
      ${this.error ? `<div class="stage-error">${escapeHtml(this.error)}</div>` : ''}`;
    this.stageScaleValue = scale;
  }

  renderInspector() {
    const inspector = this.shadowRoot.querySelector('#inspector');
    if (!inspector || !this.draft) return;
    const narrow = this.hasAttribute('narrow');
    const tab = narrow ? ({panel: 'panel', devices: 'devices'}[this.mobileTab] || 'edit') : this.tab;
    const tabs = [['edit', '编辑'], ['panel', '面板设置'], ['devices', `设备 ${this.data.devices.length}`]];
    const body = tab === 'panel' ? this.panelSettings() : tab === 'devices' ? this.devicesView() : this.editView();
    inspector.innerHTML = `<div class="tabs">${tabs.map(([key, label]) => `<button class="${key === tab ? 'on' : ''}" data-action="tab" data-value="${key}">${label}</button>`).join('')}</div>${body}`;
  }

  renderInspectorHeader() {
    const head = this.shadowRoot.querySelector('#inspector [data-head]');
    const found = this.selection && this.lookup(this.selection);
    if (head && found?.tile) head.innerHTML = this.tileHeader(found);
  }

  tileHeader({tile, section, page}) {
    const view = this.views[tile.id] || {};
    return `<span class="ico">${iconSvg(tile.icon, 'currentColor', 1.8)}</span><div style="min-width:0"><b>${escapeHtml(tile.title)}<span class="kind">${KIND_NAMES[kindOf(tile.entity_id)]}</span></b>
      <small>${tile.w ?? 1}×${tile.h ?? 1} · ${escapeHtml(page.title)}${section.title ? ' / ' + escapeHtml(section.title) : ''} · ${escapeHtml(view.text ?? '')}${view.unit ? ' ' + escapeHtml(view.unit) : ''}</small></div>`;
  }

  stepper(action, value, low, high, suffix = '') {
    return `<div class="stepper"><button data-action="${action}" data-value="-1" ${value <= low ? 'disabled' : ''} aria-label="减少">${ui('minus')}</button>
      <span>${value}${suffix}</span><button data-action="${action}" data-value="1" ${value >= high ? 'disabled' : ''} aria-label="增加">${ui('plus')}</button></div>`;
  }

  editView() {
    const found = this.selection && this.lookup(this.selection);
    if (!found) return '<div class="section"><p class="hint">在左侧或预览中选择一张卡片、一个分组或页面。</p></div>';
    if (found.tile) return this.tileView(found);
    if (found.section) return this.sectionView(found);
    return this.pageView(found);
  }

  tileView(found) {
    const {tile, section, page} = found;
    const state = this._hass?.states[tile.entity_id];
    const sections = this.draft.pages.flatMap(p => p.sections.map((s, i) => ({p, s, i})));
    return `<div class="section"><div class="head-card" data-head>${this.tileHeader(found)}</div></div>
      <div class="section"><h3>内容</h3>
        <div class="field"><label for="tile-title">显示名称</label><input class="input" id="tile-title" data-field="tile-title" maxlength="40" value="${escapeHtml(tile.title)}"></div>
        <div class="field"><span class="label">Home Assistant 实体</span><button class="picker" data-action="change-entity">
          <span class="ico">${iconSvg(defaultIcon(tile.entity_id, state?.attributes?.device_class), 'currentColor', 1.8)}</span>
          <span class="t"><b>${escapeHtml(state ? this.entityName(tile.entity_id) : '实体不存在')}</b><span class="mono">${escapeHtml(tile.entity_id)}</span></span><span class="change">更换</span></button>
          ${state ? '' : '<p class="hint error">这个实体在 HA 中不存在，保存前请更换。</p>'}</div></div>
      <div class="section"><h3>大小与位置</h3>
        <div class="grid2"><div class="field"><span class="label">宽（格）</span>${this.stepper('tile-w', tile.w ?? 1, 1, page.columns)}</div>
          <div class="field"><span class="label">高（格）</span>${this.stepper('tile-h', tile.h ?? 1, 1, section.rows)}</div></div>
        <div class="field"><label for="tile-section">所在分组</label><select class="input" id="tile-section" data-field="tile-section">
          ${sections.map(({p, s, i}) => `<option value="${s.id}" ${s === section ? 'selected' : ''}>${escapeHtml(p.title)} / ${escapeHtml(s.title || '分组 ' + (i + 1))}</option>`).join('')}</select>
          <p class="hint">也可以直接在预览里拖动卡片、拖右下角改大小，或把左侧列表的卡片拖进其他分组。</p></div></div>
      <div class="section"><h3>图标</h3><div class="icons">${(this.data.icons || Object.keys(ICON_NAMES)).map(name =>
        `<button class="${tile.icon === name ? 'on' : ''}" data-action="tile-icon" data-value="${name}" title="${ICON_NAMES[name] || name}" aria-label="${ICON_NAMES[name] || name}">${iconSvg(name, 'currentColor', 1.8)}</button>`).join('')}</div></div>
      <div class="section"><button class="btn small danger" data-action="remove-tile">${ui('trash')}从面板移除此卡片</button></div>`;
  }

  sectionView({section, page}) {
    const index = page.sections.indexOf(section);
    const maxRows = 8 - this.usedRows(page, section);
    return `<div class="section"><div class="head-card"><span class="ico">${ui('folder')}</span><div><b>${escapeHtml(section.title || '未命名分组')}</b><small>${escapeHtml(page.title)} · ${section.tiles.length} 张卡片 · ${section.rows} 行</small></div></div></div>
      <div class="section"><h3>分组（房间）</h3>
        <div class="field"><label for="section-title">分组名称</label><input class="input" id="section-title" data-field="section-title" maxlength="16" placeholder="留空则不显示标题栏" value="${escapeHtml(section.title)}"></div>
        <div class="field"><span class="label">占几行</span>${this.stepper('section-rows', section.rows, 1, maxRows)}<p class="hint">一页所有分组合计最多 8 行，行高按整页高度自动分配。</p></div>
        <div class="field"><button class="switch-row" data-action="section-summary"><span><b style="font-weight:500">显示房间小结</b><br><small class="hint">如「2 盏灯开着 · 25.8°C」，显示在标题栏右侧</small></span><span class="toggle ${section.summary !== false ? 'on' : ''}"></span></button></div></div>
      <div class="section"><div class="actions-row">
        <button class="btn small" data-action="move-section" data-value="-1" ${index === 0 ? 'disabled' : ''}>${ui('up')}上移</button>
        <button class="btn small" data-action="move-section" data-value="1" ${index === page.sections.length - 1 ? 'disabled' : ''}>${ui('down')}下移</button>
        <button class="btn small danger" data-action="remove-section" ${page.sections.length === 1 ? 'disabled' : ''}>${ui('trash')}删除分组</button></div>
        ${page.sections.length === 1 ? '<p class="hint">每页至少保留一个分组。</p>' : ''}</div>`;
  }

  pageView({page, pageIndex}) {
    const used = this.usedRows(page);
    return `<div class="section"><div class="head-card"><span class="ico">${ui('page')}</span><div><b>${escapeHtml(page.title)}</b><small>第 ${pageIndex + 1} 页 · ${page.sections.length} 个分组 · ${page.columns} 列</small></div></div></div>
      <div class="section"><h3>页面</h3>
        <div class="field"><label for="page-title">页面名称</label><input class="input" id="page-title" data-field="page-title" maxlength="16" value="${escapeHtml(page.title)}"><p class="hint">显示在 Kindle 顶部和底部页签上。</p></div>
        <div class="field"><span class="label">每行几列</span><div class="seg">${[1, 2, 3, 4].map(n => `<button class="${page.columns === n ? 'on' : ''}" data-action="page-columns" data-value="${n}">${n} 列</button>`).join('')}</div></div>
        <div class="field"><span class="label">已用行数</span><div class="meter ${used >= 8 ? 'full' : ''}"><i style="width:${used / 8 * 100}%"></i></div><p class="hint">${used} / 8 行。在各分组里调整行数；常用组合：2×3、3×6、4×6。</p></div></div>
      <div class="section"><div class="actions-row">
        <button class="btn small" data-action="move-page" data-value="-1" ${pageIndex === 0 ? 'disabled' : ''}>${ui('left')}前移</button>
        <button class="btn small" data-action="move-page" data-value="1" ${pageIndex === this.draft.pages.length - 1 ? 'disabled' : ''}>${ui('right')}后移</button>
        <button class="btn small danger" data-action="remove-page" ${this.draft.pages.length === 1 ? 'disabled' : ''}>${ui('trash')}删除页面</button></div></div>`;
  }

  panelSettings() {
    const d = this.draft, system = this.data.system_unit;
    const units = [['auto', `跟随 HA（${system}）`], ['°C', '摄氏 °C'], ['°F', '华氏 °F']];
    const intervals = [[15, '15 秒'], [30, '30 秒'], [60, '1 分'], [120, '2 分'], [300, '5 分']];
    const power = [['external-refresh', '接电常亮，电池省电', '接电时持续刷新；用电池时允许休眠，屏幕保留最后画面'],
      ['always-refresh', '始终常亮', '无论是否接电都持续刷新，耗电较快']];
    return `<div class="section"><h3>温度单位</h3><div class="field"><div class="seg">${units.map(([v, l]) => `<button class="${d.temperature_unit === v ? 'on' : ''}" data-action="unit" data-value="${v}">${l}</button>`).join('')}</div>
        <p class="hint">空调与温度传感器统一换算后显示，Kindle 上加减温度也按此单位。HA 系统单位为 ${system}。</p></div></div>
      <div class="section"><h3>刷新与电源</h3>
        <div class="field"><span class="label">刷新间隔</span><div class="seg">${intervals.map(([v, l]) => `<button class="${d.refresh_seconds === v ? 'on' : ''}" data-action="interval" data-value="${v}">${l}</button>`).join('')}</div></div>
        <div class="field"><span class="label">常驻方式</span>${power.map(([v, title, text]) => `<button class="radio-card ${d.power_mode === v ? 'on' : ''}" data-action="power" data-value="${v}"><span class="r"></span><span><b>${title}</b><small>${text}</small></span></button>`).join('')}</div></div>
      <div class="section"><p class="hint">Kindle 面板 ${escapeHtml(this.data.version || '')} · 背光在 Kindle 顶部的太阳按钮里调节。</p></div>`;
  }

  devicesView() {
    const devices = this.data.devices;
    const list = devices.map(device => {
      const online = this.online(device), current = device.revision === this.data.revision;
      const preview = (this.previewDevice || devices[0]?.id) === device.id;
      return `<div class="device ${online ? '' : 'offline'} ${preview ? 'preview' : ''}"><div class="top"><span class="kico"></span>
          <div style="flex:1;min-width:0"><b>${escapeHtml(device.name)}</b><small>${device.width}×${device.height}${preview ? ' · 预览中' : ''}</small></div>
          <span class="chip" style="height:26px"><span class="dot ${online ? '' : 'off'}"></span>${online ? '在线' : '休眠或离线'}</span></div>
        <div class="meta"><div><span>电量</span><strong>${device.battery != null ? Math.round(device.battery) + '%' : '—'}${device.charging ? ' 充电' : ''}</strong></div>
          <div><span>最近同步</span><strong>${ago(device.last_seen)}</strong></div>
          <div><span>布局</span><strong class="${current ? '' : 'warn'}">${current ? '已是最新' : '待同步'}</strong></div></div>
        <div class="acts"><button class="btn small" data-action="preview-device" data-value="${device.id}" ${preview ? 'disabled' : ''}>设为预览尺寸</button>
          <button class="btn small text danger" data-action="revoke" data-value="${device.id}">撤销配对</button></div></div>`;
    }).join('');
    const url = this.pairUrl.trim(), valid = /^http:\/\/[\w.-]+(:\d+)?\/?$/.test(url);
    return `<div class="section"><h3>已配对设备 · ${devices.length}/5</h3>${list || '<p class="hint">还没有配对的 Kindle。</p>'}</div>
      <div class="section"><div class="pair-card"><b>添加一台 Kindle</b>
        <ol><li>点击下方按钮，下载一次性配对文件（10 分钟有效）</li><li>USB 连接 Kindle，放进 <span class="code">nativeha/</span> 文件夹</li><li>拔线后在 Kindle 打开面板，自动完成配对</li></ol>
        <div class="field"><label for="pair-url">Kindle 连接 HA 的地址</label><input class="input ${url && !valid ? 'invalid' : ''}" id="pair-url" data-field="pair-url" placeholder="http://192.168.1.20:8123" value="${escapeHtml(this.pairUrl)}">
          <p class="hint ${url && !valid ? 'error' : ''}">Kindle 只支持局域网 http 地址，例如 http://192.168.1.20:8123${location.protocol === 'https:' ? '；当前浏览器使用 https，请填写 HA 的内网地址' : ''}。</p></div>
        <button class="btn primary block" data-action="pair" ${valid && devices.length < 5 ? '' : 'disabled'}>${ui('file')}下载配对文件</button>
        ${devices.length >= 5 ? '<p class="hint error">最多配对 5 台，请先撤销不用的设备。</p>' : ''}</div></div>`;
  }

  // ------------------------------------------------------------------ entity picker
  openPicker(mode, sectionId) {
    this.picker = {mode, sectionId, query: '', filter: 'all', index: 0};
    this.renderPicker();
    this.shadowRoot.querySelector('#picker-search')?.focus();
  }
  closePicker() { this.picker = null; this.shadowRoot.querySelector('#dialog').innerHTML = ''; }

  pickerEntries() {
    const {query, filter} = this.picker, q = query.trim().toLowerCase();
    const used = new Set(this.tileEntities());
    const areas = this._hass?.areas || {}, registry = this._hass?.entities || {}, devices = this._hass?.devices || {};
    const all = Object.values(this._hass?.states || {}).map(state => {
      const id = state.entity_id, reg = registry[id] || {};
      const area = areas[reg.area_id || devices[reg.device_id]?.area_id]?.name || '';
      return {id, state, name: state.attributes?.friendly_name || id, area, kind: kindOf(id), domain: domainOf(id), used: used.has(id)};
    }).filter(e => !q || e.name.toLowerCase().includes(q) || e.id.includes(q) || e.area.toLowerCase().includes(q));
    const groups = {all: () => true, control: e => e.kind === 'toggle' || e.kind === 'climate', sensor: e => e.kind === 'sensor', action: e => e.kind === 'action'};
    const counts = Object.fromEntries(Object.entries(groups).map(([k, f]) => [k, all.filter(f).length]));
    const shown = all.filter(groups[filter]).sort((a, b) => (a.domain.localeCompare(b.domain)) || a.name.localeCompare(b.name, 'zh'));
    return {shown: shown.slice(0, 300), counts, total: shown.length};
  }

  renderPicker() {
    const box = this.shadowRoot.querySelector('#dialog');
    if (!this.picker) { box.innerHTML = ''; return; }
    const {shown, counts, total} = this.pickerEntries();
    this.picker.index = clamp(this.picker.index, 0, Math.max(0, shown.length - 1));
    this.pickerShown = shown;
    const q = this.picker.query.trim();
    const mark = text => {
      const safe = escapeHtml(text);
      if (!q) return safe;
      const i = text.toLowerCase().indexOf(q.toLowerCase());
      return i < 0 ? safe : escapeHtml(text.slice(0, i)) + '<mark>' + escapeHtml(text.slice(i, i + q.length)) + '</mark>' + escapeHtml(text.slice(i + q.length));
    };
    let last = '';
    const rows = shown.map((e, i) => {
      const group = e.domain !== last ? `<div class="gl">${escapeHtml(DOMAIN_NAMES[e.domain] || e.domain)}</div>` : '';
      last = e.domain;
      const unit = e.state.attributes?.unit_of_measurement || '';
      return `${group}<button class="res ${i === this.picker.index ? 'hl' : ''} ${e.used ? 'added' : ''}" data-action="pick" data-value="${escapeHtml(e.id)}">
        <span class="ico">${iconSvg(defaultIcon(e.id, e.state.attributes?.device_class), 'currentColor', 1.8)}</span>
        <span style="min-width:0"><b>${mark(e.name)}</b><span class="mono">${mark(e.id)}${e.area ? ' · ' + escapeHtml(e.area) : ''}</span></span>
        <span class="v">${escapeHtml(e.state.state)}${unit ? ' ' + escapeHtml(unit) : ''}${e.used ? '<small>已在面板</small>' : ''}</span></button>`;
    }).join('');
    const filters = [['all', '全部'], ['control', '可控制'], ['sensor', '状态/传感器'], ['action', '场景与按钮']];
    const existing = box.querySelector('#picker-search');
    const html = `<div class="filters">${filters.map(([k, l]) => `<button class="${this.picker.filter === k ? 'on' : ''}" data-action="picker-filter" data-value="${k}">${l}<i>${counts[k]}</i></button>`).join('')}</div>
      <div class="results" id="picker-results">${rows || '<p class="empty">没有匹配的实体</p>'}</div>
      <div class="df"><span>↑↓ 选择 · Enter 确认 · Esc 关闭</span><span>${total > 300 ? '仅显示前 300 个，请输入关键词' : total + ' 个实体'}</span></div>`;
    if (existing) {
      box.querySelector('#picker-body').innerHTML = html;
    } else {
      box.innerHTML = `<div class="scrim" data-action="picker-close"><div class="dialog" role="dialog" aria-modal="true" aria-label="选择实体">
        <div class="dh"><h2>${this.picker.mode === 'replace' ? '更换实体' : '添加卡片'}</h2><button class="icon-btn" data-action="picker-close" aria-label="关闭">${ui('x')}</button></div>
        <label class="search">${ui('search')}<input id="picker-search" data-field="picker-search" placeholder="搜索名称、实体 ID 或区域" autocomplete="off"></label>
        <div id="picker-body" style="display:flex;flex-direction:column;min-height:0;flex:1">${html}</div></div></div>`;
    }
    box.querySelector('.res.hl')?.scrollIntoView({block: 'nearest'});
  }

  pick(entityId) {
    const state = this._hass.states[entityId];
    const name = (state?.attributes?.friendly_name || entityId).slice(0, 40);
    const icon = defaultIcon(entityId, state?.attributes?.device_class);
    if (this.picker.mode === 'replace') {
      const {tile} = this.lookup(this.selection);
      Object.assign(tile, {entity_id: entityId, title: name, icon});
      this.closePicker();
      return this.changed({inspector: true});
    }
    const found = this.lookup({type: 'section', id: this.picker.sectionId});
    const {page, section} = found;
    const climate = kindOf(entityId) === 'climate';
    let w = climate ? Math.min(page.columns, Math.max(2, page.columns - 1)) : 1;
    let h = climate && section.rows >= 2 && page.columns >= 2 ? 2 : 1;
    let spot = this.findSpot(section, page.columns, w, h) || this.findSpot(section, page.columns, w = 1, h = 1);
    if (!spot) {
      if (this.usedRows(page) >= 8) { this.error = '这一页已经用满 8 行，请先缩小卡片或新建页面'; this.closePicker(); return this.renderTop(); }
      section.rows += 1;
      spot = this.findSpot(section, page.columns, w, h);
    }
    const tile = {id: uid('tile'), entity_id: entityId, title: name, icon, w, h, ...spot};
    section.tiles.push(tile);
    this.selection = {type: 'tile', id: tile.id};
    this.closePicker();
    this.changed({inspector: true});
  }

  // ------------------------------------------------------------------ events
  onKey(event) {
    if (!this.picker) return;
    const shown = this.pickerShown || [];
    if (event.key === 'Escape') { this.closePicker(); event.preventDefault(); }
    else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      this.picker.index = clamp(this.picker.index + (event.key === 'ArrowDown' ? 1 : -1), 0, shown.length - 1);
      this.renderPicker(); event.preventDefault();
    } else if (event.key === 'Enter' && shown[this.picker.index]) { this.pick(shown[this.picker.index].id); event.preventDefault(); }
  }

  onInput(event, committed = false) {
    const field = event.target.dataset?.field;
    if (!field) return;
    const value = event.target.value;
    if (field === 'picker-search') { if (!this.picker) return; this.picker.query = value; this.picker.index = 0; return this.renderPicker(); }
    if (field === 'pair-url') {
      this.pairUrl = value;
      if (committed) this.renderInspector();
      return;
    }
    const found = this.lookup(this.selection);
    if (field === 'tile-title') found.tile.title = value;
    else if (field === 'section-title') found.section.title = value;
    else if (field === 'page-title') found.page.title = value;
    else if (field === 'tile-section' && committed) {
      const target = this.lookup({type: 'section', id: value});
      found.section.tiles.splice(found.section.tiles.indexOf(found.tile), 1);
      delete found.tile.x; delete found.tile.y;
      target.section.tiles.push(found.tile);
      this.pageIndex = target.pageIndex;
      return this.changed({inspector: true});
    } else return;
    this.changed();
  }

  onClick(event) {
    const target = event.target.closest('[data-action]');
    if (!target || target.disabled) return;
    const action = target.dataset.action, value = target.dataset.value;
    if (action === 'picker-close' && target.classList.contains('scrim') && event.target !== target) return;
    const found = this.selection && this.lookup(this.selection);
    const select = selection => { this.selection = selection; this.tab = 'edit'; if (this.hasAttribute('narrow')) this.mobileTab = 'inspector'; this.renderAll(); };
    switch (action) {
      case 'menu': this.dispatchEvent(new CustomEvent('hass-toggle-menu', {bubbles: true, composed: true})); break;
      case 'save': this.save(); break;
      case 'discard': this.discard(); break;
      case 'mobile-tab': this.mobileTab = value; this.renderMobileTabs(); this.renderInspector(); this.renderStage(); break;
      case 'tab': this.tab = value; this.renderInspector(); break;
      case 'page': {
        const index = Number(value);
        if (index < 0 || index >= this.draft.pages.length) return;
        this.pageIndex = index;
        if (found?.pageIndex !== index) this.selection = this.firstSelection();
        this.renderAll(); break;
      }
      case 'select-tile': select({type: 'tile', id: value}); break;
      case 'select-section': event.stopPropagation(); select({type: 'section', id: value}); break;
      case 'select-page': select({type: 'page', id: this.page.id}); break;
      case 'add-page': {
        const page = {id: uid('page'), title: `新页面 ${this.draft.pages.length + 1}`, columns: 2,
          sections: [{id: uid('section'), title: '', rows: 3, summary: true, tiles: []}]};
        this.draft.pages.push(page);
        this.pageIndex = this.draft.pages.length - 1;
        this.selection = {type: 'page', id: page.id};
        this.renderAll(); this.changed({inspector: true}); break;
      }
      case 'add-section': {
        const section = {id: uid('section'), title: `房间 ${this.page.sections.length + 1}`, rows: Math.min(2, 8 - this.usedRows(this.page)), summary: true, tiles: []};
        this.page.sections.push(section);
        this.selection = {type: 'section', id: section.id};
        this.changed({inspector: true}); break;
      }
      case 'add-tile':
        if (this.tileCount() >= 60) { this.error = '最多支持 60 张卡片'; return this.renderTop(); }
        this.openPicker('add', value); break;
      case 'change-entity': this.openPicker('replace'); break;
      case 'picker-close': this.closePicker(); break;
      case 'picker-filter': this.picker.filter = value; this.picker.index = 0; this.renderPicker(); break;
      case 'pick': this.pick(value); break;
      case 'tile-icon': found.tile.icon = value; this.changed({inspector: true}); break;
      case 'tile-w': case 'tile-h': {
        const {tile, page, section} = found;
        const rect = {w: tile.w ?? 1, h: tile.h ?? 1};
        if (action === 'tile-w') rect.w = clamp(rect.w + Number(value), 1, page.columns);
        else rect.h = clamp(rect.h + Number(value), 1, section.rows);
        rect.x = Math.min(tile.x ?? 0, page.columns - rect.w);
        rect.y = Math.min(tile.y ?? 0, section.rows - rect.h);
        if (this.relocate(section, page.columns, tile, rect, false)) this.changed({inspector: true});
        break;
      }
      case 'remove-tile':
        found.section.tiles.splice(found.section.tiles.indexOf(found.tile), 1);
        this.selection = found.section.tiles[0] ? {type: 'tile', id: found.section.tiles[0].id} : {type: 'section', id: found.section.id};
        this.changed({inspector: true}); break;
      case 'section-rows': {
        const needed = Math.max(1, ...found.section.tiles.map(t => t.h ?? 1));
        found.section.rows = clamp(found.section.rows + Number(value), needed, 8 - this.usedRows(found.page, found.section));
        this.changed({inspector: true}); break;
      }
      case 'section-summary': found.section.summary = found.section.summary === false; this.changed({inspector: true}); break;
      case 'move-section': case 'move-page': {
        const list = action === 'move-page' ? this.draft.pages : found.page.sections;
        const item = action === 'move-page' ? found.page : found.section;
        const from = list.indexOf(item), to = from + Number(value);
        list.splice(from, 1); list.splice(to, 0, item);
        if (action === 'move-page') this.pageIndex = to;
        this.renderAll(); this.changed({inspector: true}); break;
      }
      case 'remove-section':
        if (found.section.tiles.length && !confirm(`删除分组会同时移除其中 ${found.section.tiles.length} 张卡片，确定吗？`)) return;
        found.page.sections.splice(found.page.sections.indexOf(found.section), 1);
        this.selection = this.firstSelection(); this.changed({inspector: true}); break;
      case 'remove-page':
        if (!confirm(`删除页面「${found.page.title}」及其中所有卡片？`)) return;
        this.draft.pages.splice(found.pageIndex, 1);
        this.pageIndex = clamp(this.pageIndex, 0, this.draft.pages.length - 1);
        this.selection = this.firstSelection(); this.renderAll(); this.changed({inspector: true}); break;
      case 'page-columns': found.page.columns = Number(value); this.changed({inspector: true}); break;
      case 'unit': this.draft.temperature_unit = value; this.changed({inspector: true}); break;
      case 'interval': this.draft.refresh_seconds = Number(value); this.changed({inspector: true}); break;
      case 'power': this.draft.power_mode = value; this.changed({inspector: true}); break;
      case 'preview-device': this.previewDevice = value; this.schedulePreview(0); this.renderInspector(); this.renderTop(); break;
      case 'revoke': this.revoke(value); break;
      case 'pair': this.pair(); break;
    }
  }

  // drag tiles between sections in the list (HTML5 drag & drop)
  onDragStart(event) {
    const row = event.target.closest?.('[data-tile]');
    if (row) { event.dataTransfer.setData('text/kindle-tile', row.dataset.tile); event.dataTransfer.effectAllowed = 'move'; }
  }
  onDragOver(event) {
    const list = event.target.closest?.('.tile-list');
    if (list && event.dataTransfer.types.includes('text/kindle-tile')) { event.preventDefault(); list.classList.add('drop'); }
  }
  onDrop(event) {
    const list = event.target.closest?.('.tile-list');
    const id = event.dataTransfer.getData('text/kindle-tile');
    if (!list || !id) return;
    event.preventDefault();
    const from = this.lookup({type: 'tile', id}), to = this.lookup({type: 'section', id: list.dataset.section});
    if (!from || !to || from.section === to.section) return this.renderList();
    from.section.tiles.splice(from.section.tiles.indexOf(from.tile), 1);
    delete from.tile.x; delete from.tile.y;
    to.section.tiles.push(from.tile);
    this.changed({inspector: true});
  }

  // move / resize cards directly on the preview (pointer events, snapped to the section grid)
  onPointerDown(event) {
    const hot = event.target.closest?.('.hot');
    if (!hot || event.button !== 0) return;
    const id = hot.dataset.card, found = this.lookup({type: 'tile', id});
    if (!found) return;
    event.preventDefault();
    const resize = !!event.target.dataset.resize;
    const page = this.frame.pages[this.pageIndex];
    const overlay = this.shadowRoot.querySelector('#overlay'), rect = overlay.getBoundingClientRect();
    const scale = this.stageScaleValue;
    const card = page.cards.find(c => c.id === id);
    this.drag = {id, found, resize, page, overlay, rect, scale, startX: event.clientX, startY: event.clientY, card, moved: false, result: null};
    const move = e => this.onPointerMove(e), up = e => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      this.onPointerUp(e);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  }

  onPointerMove(event) {
    const drag = this.drag;
    if (!drag) return;
    const dx = event.clientX - drag.startX, dy = event.clientY - drag.startY;
    if (!drag.moved && Math.hypot(dx, dy) < 6) return;
    drag.moved = true;
    const sx = (event.clientX - drag.rect.left) / drag.scale, sy = (event.clientY - drag.rect.top) / drag.scale;
    const {tile} = drag.found;
    let result;
    if (drag.resize) {
      const box = drag.page.sections.find(s => s.id === drag.found.section.id).grid;
      const w = clamp(Math.round((sx - (box.x + tile.x * (box.cw + box.gap)) + box.gap) / (box.cw + box.gap)), 1, box.columns - tile.x);
      const h = clamp(Math.round((sy - (box.y + tile.y * (box.ch + box.gap)) + box.gap) / (box.ch + box.gap)), 1, box.rows - tile.y);
      result = {section: drag.found.section.id, box, x: tile.x, y: tile.y, w, h};
    } else {
      const box = drag.page.sections.find(s => sy >= s.grid.y - s.head && sy < s.grid.y + s.grid.rows * (s.grid.ch + s.grid.gap)) ||
        drag.page.sections.find(s => s.id === drag.found.section.id);
      const g = box.grid;
      const w = Math.min(tile.w, g.columns), h = Math.min(tile.h, g.rows);
      const left = sx - (drag.startX - drag.rect.left) / drag.scale + drag.card.x;
      const top = sy - (drag.startY - drag.rect.top) / drag.scale + drag.card.y;
      const x = clamp(Math.round((left - g.x) / (g.cw + g.gap)), 0, g.columns - w);
      const y = clamp(Math.round((top - g.y) / (g.ch + g.gap)), 0, g.rows - h);
      result = {section: box.id, box: g, x, y, w, h};
    }
    drag.result = result;
    const g = result.box, s = drag.scale;
    const ghost = `<div class="ghost" id="ghost" style="left:${(g.x + result.x * (g.cw + g.gap)) * s}px;top:${(g.y + result.y * (g.ch + g.gap)) * s}px;width:${(result.w * g.cw + (result.w - 1) * g.gap) * s}px;height:${(result.h * g.ch + (result.h - 1) * g.gap) * s}px"></div>`;
    if (!drag.cells) {
      drag.cells = true;
      const cells = drag.page.sections.flatMap(sec => Array.from({length: sec.grid.rows * sec.grid.columns}, (_, i) => {
        const cx = i % sec.grid.columns, cy = Math.floor(i / sec.grid.columns), b = sec.grid;
        return `<div class="cell" style="left:${(b.x + cx * (b.cw + b.gap)) * s}px;top:${(b.y + cy * (b.ch + b.gap)) * s}px;width:${b.cw * s}px;height:${b.ch * s}px"></div>`;
      })).join('');
      drag.overlay.insertAdjacentHTML('afterbegin', cells);
    }
    drag.overlay.querySelector('#ghost')?.remove();
    drag.overlay.insertAdjacentHTML('beforeend', ghost);
  }

  onPointerUp() {
    const drag = this.drag;
    this.drag = null;
    if (!drag) return;
    if (!drag.moved) {
      this.selection = {type: 'tile', id: drag.id};
      this.tab = 'edit';
      if (this.hasAttribute('narrow')) { this.mobileTab = 'inspector'; this.renderMobileTabs(); }
      this.renderList(); this.renderStage(); this.renderInspector();
      return;
    }
    const result = drag.result;
    const {tile, section} = drag.found;
    if (!result) return this.renderStage();
    const rect = {x: result.x, y: result.y, w: result.w, h: result.h};
    const columns = drag.found.page.columns;
    if (result.section !== section.id) {
      const target = this.lookup({type: 'section', id: result.section}).section;
      const index = section.tiles.indexOf(tile);
      section.tiles.splice(index, 1);
      if (!this.relocate(target, columns, tile, rect, false)) { section.tiles.splice(index, 0, tile); return; }
    } else if (!this.relocate(section, columns, tile, rect, !drag.resize)) return;
    this.selection = {type: 'tile', id: tile.id};
    this.changed({inspector: true});
    this.renderStage();
  }

  // ------------------------------------------------------------------ server actions
  async save() {
    this.saving = true; this.renderTop();
    try {
      const data = await this.call('save', {layout: clone(this.draft), revision: this.data.revision, ...(this.previewDevice ? {device_id: this.previewDevice} : {})});
      Object.assign(this, {data, draft: clone(data.layout), frame: data.frame, views: data.views, dirty: false, error: '',
        notice: 'Kindle 会在下一次刷新时同步'});
      if (!this.lookup(this.selection)) this.selection = this.firstSelection();
      this.renderAll();
    } catch (error) {
      this.error = error.message || '保存失败';
    } finally {
      this.saving = false; this.renderTop();
    }
  }

  discard() {
    if (!confirm('放弃所有尚未保存的修改？')) return;
    Object.assign(this, {draft: clone(this.data.layout), frame: this.data.frame, views: this.data.views, dirty: false, error: ''});
    this.pageIndex = clamp(this.pageIndex, 0, this.draft.pages.length - 1);
    if (!this.lookup(this.selection)) this.selection = this.firstSelection();
    this.renderAll();
  }

  async revoke(id) {
    const device = this.deviceById(id);
    if (!confirm(`撤销「${device?.name}」的配对？这台 Kindle 需要重新配对才能再连接。`)) return;
    try {
      const data = await this.call('revoke', {device_id: id});
      this.data = {...this.data, devices: data.devices};
      if (this.previewDevice === id) { this.previewDevice = null; this.schedulePreview(0); }
      this.notice = '已撤销配对';
      this.renderTop(); this.renderInspector();
    } catch (error) { this.error = error.message || '撤销失败'; this.renderTop(); }
  }

  async pair() {
    if (this.demo) { this.notice = '这是本地预览；安装到 HA 后即可配对 Kindle'; return this.renderTop(); }
    try {
      const result = await this.call('pair');
      const file = {server_url: this.pairUrl.trim().replace(/\/+$/, ''), code: result.code, name: 'Kindle 控制屏', expires: result.expires};
      const url = URL.createObjectURL(new Blob([JSON.stringify(file, null, 2)], {type: 'application/json'}));
      const link = document.createElement('a');
      link.href = url; link.download = 'kindle-pairing.json'; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 30000);
      this.notice = '配对文件已下载：10 分钟内放进 Kindle 的 nativeha 文件夹，再打开面板';
      this.renderTop();
    } catch (error) { this.error = error.message || '生成配对文件失败'; this.renderTop(); }
  }
}

customElements.define('kindle-panel-editor', KindlePanelEditor);

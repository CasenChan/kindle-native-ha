const ICONS = {"bulb": "<path d='M9 18h6M9 21h6M8.7 14.5a6 6 0 1 1 6.6 0c-.8.6-1.3 1.4-1.3 2.5h-4c0-1.1-.5-1.9-1.3-2.5Z'/>", "thermostat": "<circle cx='12' cy='12' r='8'/><path d='M12 6v6l4 2M5 3l-2 2m16-2 2 2'/>", "temperature": "<path d='M9 14.5V5a3 3 0 0 1 6 0v9.5a5 5 0 1 1-6 0Z'/><path d='M12 8v10'/><circle cx='12' cy='18' r='1.5'/>", "humidity": "<path d='M12 2s-7 7.5-7 12a7 7 0 0 0 14 0c0-4.5-7-12-7-12Z'/><path d='M8 15a4 4 0 0 0 4 4'/>", "power": "<path d='M12 2v10M6 5a9 9 0 1 0 12 0'/>", "fan": "<circle cx='12' cy='12' r='2'/><path d='M12 10c-4-9 6-10 6-4 0 3-3 5-4 5m-1 3c9-4 10 6 4 6-3 0-5-3-5-4m-2-3c4 9-6 10-6 4 0-3 3-5 4-5m1-2C0 14-1 4 5 4c3 0 5 3 5 4'/>", "home": "<path d='m3 10 9-7 9 7v11h-6v-7H9v7H3Z'/>", "scene": "<path d='m12 2 2.5 6.5L21 11l-6.5 2.5L12 20l-2.5-6.5L3 11l6.5-2.5Z'/><path d='m20 18 1 3m-2-1h3'/>", "plug": "<path d='M8 2v5m8-5v5M6 7h12v4a6 6 0 0 1-12 0ZM12 17v5'/>", "sensor": "<rect x='5' y='3' width='14' height='18' rx='3'/><circle cx='12' cy='10' r='3'/><path d='M9 17h6'/>"};
const clone = value => JSON.parse(JSON.stringify(value));
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const iconNames = {bulb:'灯泡',thermostat:'空调',temperature:'温度',humidity:'湿度',power:'电源',fan:'风扇',home:'房屋',scene:'场景',plug:'插座',sensor:'传感器'};
const modes = {cool:'制冷',heat:'制热',auto:'自动',heat_cool:'自动',dry:'除湿',fan_only:'送风',off:'关机'};
const svg = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ICONS.sensor}</svg>`;
const entityKind = id => {
  const domain = id.split('.')[0];
  return ['switch','light','fan'].includes(domain) ? 'toggle' : domain === 'climate' ? 'climate' : ['scene','script','button'].includes(domain) ? 'action' : 'sensor';
};

class KindlePanelEditor extends HTMLElement {
  constructor() {
    super(); this.attachShadow({mode:'open'}); this._page=0; this._dirty=false; this._selected=null; this._previewSerial=0;
  }
  set hass(value) {
    const previous=this._hass; this._hass=value;
    if (this.isConnected && !this._loaded && !this._loading) this._load();
    else if (this.draft && this.draft.tiles.some(tile => previous?.states?.[tile.entity_id] !== value.states?.[tile.entity_id])) this._schedulePreview();
  }
  get hass() { return this._hass; }
  connectedCallback() {
    if (this._hass && !this._loaded) this._load();
    this._poll=setInterval(()=>{ if(this._loaded && !this._loading) this._load(true); },10000);
  }
  disconnectedCallback() { clearInterval(this._poll); clearTimeout(this._previewTimer); this._resizeObserver?.disconnect(); this._resizeObserver=null; }
  async _call(action, values={}) { return this._hass.callWS({type:'kindle_panel/manage',action,...values}); }
  async _load(background=false) {
    this._loading=true;
    try {
      const data=await this._call('load'); const changed=data.revision!==this._baseRevision; this.data=data; this._loaded=true;
      if (!this.draft || !this._dirty) {
        if(!this.draft || changed || !background){this.draft=clone(data.layout);this._baseRevision=data.revision;}
        this.preview=data;
        if(!this._selected || !this.draft.tiles.some(t=>t.id===this._selected)) this._selected=this.draft.tiles[0]?.id;
        if(!background || changed || !this.shadowRoot.querySelector('.app')) this._render();
        else { this._renderPreview(); this._updateStatus(); }
      } else this._updateStatus();
    } catch(error) { this._error=error.message || '读取配置失败'; if(!background)this._render(); }
    finally { this._loading=false; }
  }
  _changed(rebuild=false) {
    this._dirty=true; this._notice=''; this._error='';
    if(rebuild)this._render(); else this._updateStatus();
    this._schedulePreview();
  }
  _schedulePreview() {
    clearTimeout(this._previewTimer); const serial=++this._previewSerial;
    this._previewTimer=setTimeout(async()=>{
      try {
        const preview=await this._call('preview',{layout:clone(this.draft),...(this._deviceId?{device_id:this._deviceId}:{})});
        if(serial!==this._previewSerial || !this.isConnected)return;
        this.preview=preview; this._error=''; this._renderPreview(); this._updateStatus();
      } catch(error) { if(serial===this._previewSerial){this._error=error.message || '请检查卡片设置';this._updateStatus();} }
    },180);
  }
  _deviceStatus() {
    const devices=this.data?.devices || [];
    if(!devices.length)return '尚未配对';
    const device=devices.find(d=>d.id===this._deviceId) || devices[0];
    const age=Date.now()/1000-(device.last_seen || 0);
    return age<90 ? `已连接${device.battery!=null?' · '+Math.round(device.battery)+'%':''}` : '休眠或离线';
  }
  _updateStatus() {
    const status=this.shadowRoot.querySelector('#notice');
    if(status){status.textContent=this._error || this._notice || (this._dirty?'有修改尚未同步':'布局已保存');status.classList.toggle('error',!!this._error);}
    const pill=this.shadowRoot.querySelector('#device-status'); if(pill)pill.textContent=this._deviceStatus();
    const save=this.shadowRoot.querySelector('#save');if(save)save.disabled=this._saving || !this._dirty;
    this._renderList();
  }
  _entityOptions(selected) {
    const entries=Object.entries(this._hass?.states || {}).sort((a,b)=>(a[1].attributes?.friendly_name||a[0]).localeCompare(b[1].attributes?.friendly_name||b[0],'zh'));
    if(selected && !entries.some(([id])=>id===selected)) entries.unshift([selected,{attributes:{friendly_name:'实体暂不可用'}}]);
    return entries.map(([id,state])=>`<option value="${escapeHtml(id)}" ${id===selected?'selected':''}>${escapeHtml(state.attributes?.friendly_name||id)} · ${escapeHtml(id)}</option>`).join('');
  }
  _render() {
    if(!this.draft){this.shadowRoot.innerHTML=`<p style="padding:32px">${escapeHtml(this._error||'正在载入 Kindle 面板…')}</p>`;return;}
    const tile=this.draft.tiles.find(t=>t.id===this._selected) || this.draft.tiles[0];
    this.shadowRoot.innerHTML=`<style>
      :host{display:block;height:100%;color:var(--primary-text-color,#24313d);font-family:var(--paper-font-body1_-_font-family,Roboto,Arial),"Microsoft YaHei",sans-serif;background:var(--primary-background-color,#f3f5f7)}
      *{box-sizing:border-box}button,input,select{font:inherit}button{cursor:pointer}button:disabled{cursor:default;opacity:.45}button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #77b7ff;outline-offset:2px}
      .app{max-width:1400px;margin:auto;padding:26px 30px 40px}.toolbar{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:22px}.eyebrow{font-size:12px;letter-spacing:1.8px;color:#74818c;font-weight:700}.toolbar h1{font-size:26px;line-height:1.3;margin:5px 0 0}.actions{display:flex;align-items:center;gap:10px}.btn{border:1px solid #d8e0e6;border-radius:10px;background:var(--card-background-color,#fff);color:inherit;padding:11px 16px;font-weight:600}.primary{background:#1672cc;border-color:#1672cc;color:white}.pill{display:inline-block;border:1px solid #dce5de;border-radius:20px;padding:7px 12px;font-size:12px;background:#eef6f0;color:#4b6854;white-space:nowrap}
      .workspace{display:grid;grid-template-columns:minmax(300px,355px) minmax(360px,1fr);gap:26px;align-items:start}.card{border:1px solid var(--divider-color,#e0e5e9);background:var(--card-background-color,#fff);border-radius:16px;padding:20px;margin-bottom:16px}.card h2{font-size:16px;margin:0 0 18px}.card h3{font-size:14px;margin:20px 0 10px}.field{display:block;margin-top:14px}.field>span{display:block;font-size:12px;font-weight:600;color:#71808c;margin-bottom:7px}.field input,.field select{width:100%;padding:11px;border:1px solid var(--divider-color,#dce2e7);border-radius:8px;background:var(--secondary-background-color,#fff);color:inherit;min-width:0}.field input[type=number]{appearance:textfield}.two{display:grid;grid-template-columns:1fr 1fr;gap:12px}.muted{color:#7b8791;font-size:12px;line-height:1.7}.list{display:grid;gap:8px;margin-bottom:14px}.listrow{display:grid;grid-template-columns:34px 1fr 26px 26px;align-items:center;border:1px solid var(--divider-color,#e0e5e9);border-radius:10px;padding:9px;gap:6px}.listrow.selected{border-color:#1672cc;background:#1672cc09}.listrow .mini{width:24px;height:24px}.listrow .name{background:none;border:0;text-align:left;color:inherit;padding:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.arrow{background:none;border:0;color:#83909a;padding:4px}.listrow[draggable=true]{cursor:grab}.icons{display:grid;grid-template-columns:repeat(5,1fr);gap:7px}.icon-choice{padding:9px;border:1px solid var(--divider-color,#e1e5e9);border-radius:9px;background:transparent;color:inherit}.icon-choice svg{width:25px;height:25px}.icon-choice.selected{color:#1672cc;border-color:#1672cc;background:#1672cc09}.danger{font-size:12px;color:#b55555;background:none;border:0;padding:13px 0 0}.full{width:100%}
      .preview-wrap{position:sticky;top:20px}.preview-top{display:flex;align-items:center;justify-content:space-between;margin:0 0 12px;padding:0 8px}.preview-top h2{font-size:15px;margin:0}.preview-meta{font-size:12px;color:#7e8991}.device-stage{display:flex;justify-content:center;min-height:200px;overflow:hidden}.bezel{background:#292c2e;border-radius:25px;padding:16px 14px 32px;box-shadow:0 18px 50px #1a293225,0 2px 4px #0003}.screen-crop{overflow:hidden;border-radius:3px;background:#fafbf8}.screen{position:relative;transform-origin:top left;background:#fafbf8;color:#171a18;font-family:"Noto Sans CJK SC","Microsoft YaHei",sans-serif}.screen-header{position:absolute;display:flex;align-items:center;justify-content:space-between;font-weight:700;letter-spacing:1px}.screen-header svg{width:32px;height:32px}.tile{position:absolute;border:1.5px solid #c8ccc6;border-radius:15px;background:#fff;text-align:left;color:#171a18;padding:0;overflow:hidden}.tile.active{background:#eef0ea}.tile.chosen{outline:4px solid #3a83d2;outline-offset:3px}.tile:not(.climate){display:flex;flex-direction:column;align-items:flex-start;justify-content:center;padding:28px;gap:14px}.tile .tile-icon{display:block;flex:0 0 auto}.tile-icon svg,.mini svg{width:100%;height:100%;display:block}.tile .tile-title{font-weight:500;max-width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.tile .tile-value{font-weight:700;letter-spacing:-.6px;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.tile .tile-unit{font-size:.52em;font-weight:400;margin-left:5px}.tile .tile-caption{color:#7a8179;font-size:19px}.climate .tile-icon{position:absolute;left:28px;top:25px}.climate .tile-title{position:absolute;left:112px;top:28px;max-width:calc(100% - 140px)}.climate .climate-mode{position:absolute;left:112px;top:66px;color:#778075;font-size:19px}.climate .current{position:absolute;left:28px;top:113px;font-size:45px;font-weight:600}.climate .target{position:absolute;right:30px;top:111px;font-size:45px;font-weight:600}.climate .clabel{font-size:17px;color:#7a8179;font-weight:400;display:block;margin-bottom:3px}.climate-controls{position:absolute;bottom:0;left:0;right:0;height:60px;border-top:1px solid #d4d8d1;display:grid;grid-template-columns:1fr 1fr 1fr}.climate-controls span{display:grid;place-items:center;font-size:28px}.climate-controls span+span{border-left:1px solid #d4d8d1}.climate-controls svg{width:27px;height:27px}.screen-footer{position:absolute;color:#8a9086;display:flex;align-items:center;justify-content:space-between;font-size:18px}.brand{text-align:center;color:#a2a8a9;font-size:12px;letter-spacing:2px;margin-top:18px}.preview-bottom{display:flex;justify-content:center;gap:12px;align-items:center;margin:16px 0;color:#71808c;font-size:12px}.preview-bottom button{padding:7px 12px;border:1px solid #d9e0e5;border-radius:7px;background:var(--card-background-color,#fff);color:inherit}.hint{text-align:center;font-size:12px;color:#859099;margin:10px 0}.notice{min-height:22px;font-size:12px;color:#5f7c65;margin-top:12px}.notice.error{color:#bd5656}.demo-note{background:#fff4d8;color:#8d7137;border-radius:10px;padding:10px 15px;margin-bottom:15px;font-size:12px}
      @media(max-width:850px){.app{padding:18px 14px}.toolbar{align-items:flex-start;flex-wrap:wrap}.toolbar h1{font-size:22px}.actions{flex-wrap:wrap}.workspace{grid-template-columns:1fr}.preview-wrap{position:static;grid-row:1}.card{padding:16px}.preview-top{padding:0}.pill{display:none}}
    </style><div class="app">
      ${this.hasAttribute('preview')?'<div class="demo-note">本地模拟预览 · 展示示例状态，点击卡片只用于编辑，不会操作家中设备。</div>':''}
      <header class="toolbar"><div><div class="eyebrow">KINDLE PANEL</div><h1>把家，放在墨水屏上</h1></div><div class="actions"><span class="pill" id="device-status"></span><button class="btn" id="pair">配对 Kindle</button><button class="btn primary" id="save">保存并同步</button></div></header>
      <main class="workspace"><section class="editor">
        <div class="card"><h2>屏幕上的卡片</h2><div class="list" id="tile-list"></div><button class="btn full" id="add">＋ 添加实体</button><p class="muted">拖动卡片调整顺序。点选预览中的卡片，也可以在这里修改。</p>
        ${tile?`<h3>编辑卡片</h3><label class="field"><span>显示名称</span><input id="tile-title" maxlength="40" value="${escapeHtml(tile.title)}"></label><label class="field"><span>Home Assistant 实体</span><select id="tile-entity">${this._entityOptions(tile.entity_id)}</select></label><label class="field"><span>卡片宽度</span><select id="tile-span" ${entityKind(tile.entity_id)==='climate'?'disabled':''}><option value="1" ${tile.span===1?'selected':''}>半行</option><option value="2" ${tile.span===2?'selected':''}>整行</option></select></label><h3>图标</h3><div class="icons">${Object.keys(ICONS).map(name=>`<button class="icon-choice ${tile.icon===name?'selected':''}" data-icon="${name}" aria-label="${iconNames[name]}" title="${iconNames[name]}">${svg(name)}</button>`).join('')}</div><button class="danger" id="remove">移除此卡片</button>`:''}</div>
        <div class="card"><h2>显示与常驻</h2><label class="field"><span>面板标题</span><input id="panel-title" maxlength="24" value="${escapeHtml(this.draft.title)}"></label><div class="two"><label class="field"><span>列数</span><select id="columns">${[1,2].map(n=>`<option value="${n}" ${n===this.draft.columns?'selected':''}>${n} 列</option>`).join('')}</select></label><label class="field"><span>每页行数</span><select id="rows">${[2,3,4].map(n=>`<option value="${n}" ${n===this.draft.rows?'selected':''}>${n} 行</option>`).join('')}</select></label></div><label class="field"><span>刷新间隔</span><select id="interval">${[15,30,60,120,300].map(n=>`<option value="${n}" ${n===this.draft.refresh_seconds?'selected':''}>${n} 秒</option>`).join('')}</select></label><label class="field"><span>电源策略</span><select id="power"><option value="external-refresh" ${this.draft.power_mode==='external-refresh'?'selected':''}>接电持续刷新，电池省电保留画面</option><option value="always-refresh" ${this.draft.power_mode==='always-refresh'?'selected':''}>始终持续刷新</option></select></label><div class="notice" id="notice"></div></div>
      </section><section class="preview-wrap"><div class="preview-top"><h2>Kindle 实时预览</h2><span class="preview-meta" id="resolution">758 × 1024 · 黑白墨水屏</span></div><div class="device-stage" id="device-stage"></div><div class="preview-bottom"><button id="previous">←</button><span id="pages">第 1 页</span><button id="next">→</button></div><p class="hint">预览与 Kindle 使用同一份卡片位置和尺寸</p></section></main>
    </div>`;
    this._bind(tile); this._renderList(); this._renderPreview(); this._updateStatus();
    if(!this._resizeObserver){this._resizeObserver=new ResizeObserver(()=>this._renderPreview());this._resizeObserver.observe(this);}
  }
  _renderList() {
    const list=this.shadowRoot.querySelector('#tile-list');if(!list || !this.draft)return;
    list.innerHTML=this.draft.tiles.map((tile,index)=>`<div class="listrow ${tile.id===this._selected?'selected':''}" draggable="true" data-id="${tile.id}"><span class="mini">${svg(tile.icon)}</span><button class="name" data-select="${tile.id}">${escapeHtml(tile.title)}</button><button class="arrow" data-move="${index}" data-direction="-1" aria-label="上移 ${escapeHtml(tile.title)}">↑</button><button class="arrow" data-move="${index}" data-direction="1" aria-label="下移 ${escapeHtml(tile.title)}">↓</button></div>`).join('');
    list.querySelectorAll('[data-select]').forEach(button=>button.onclick=()=>{this._selected=button.dataset.select;this._render();});
    list.querySelectorAll('[data-move]').forEach(button=>button.onclick=()=>{const i=Number(button.dataset.move),j=i+Number(button.dataset.direction);if(j<0||j>=this.draft.tiles.length)return;[this.draft.tiles[i],this.draft.tiles[j]]=[this.draft.tiles[j],this.draft.tiles[i]];this._changed(true);});
    list.querySelectorAll('[draggable]').forEach(row=>{row.ondragstart=event=>event.dataTransfer.setData('text/plain',row.dataset.id);row.ondragover=event=>event.preventDefault();row.ondrop=event=>{event.preventDefault();this._moveTo(event.dataTransfer.getData('text/plain'),row.dataset.id);};});
  }
  _moveTo(fromId,toId) {
    const from=this.draft.tiles.findIndex(t=>t.id===fromId),to=this.draft.tiles.findIndex(t=>t.id===toId);
    if(from<0||to<0||from===to)return;const [tile]=this.draft.tiles.splice(from,1);this.draft.tiles.splice(to,0,tile);this._changed(true);
  }
  _bind(tile) {
    const root=this.shadowRoot;
    root.querySelector('#save').onclick=()=>this._save();root.querySelector('#pair').onclick=()=>this._pair();
    root.querySelector('#add').onclick=()=>{
      if(this.draft.tiles.length>=24){this._error='最多支持 24 张卡片';this._updateStatus();return;}
      const id=Object.keys(this._hass.states).find(id=>['switch','light','sensor','climate'].includes(id.split('.')[0]));if(!id)return;
      const newTile={id:'tile-'+Math.random().toString(36).slice(2,11),entity_id:id,title:(this._hass.states[id].attributes?.friendly_name||id).slice(0,40),icon:'sensor',span:entityKind(id)==='climate'?2:1};this.draft.tiles.push(newTile);this._selected=newTile.id;this._changed(true);
    };
    if(tile){
      root.querySelector('#tile-title').oninput=event=>{tile.title=event.target.value;this._changed();};
      root.querySelector('#tile-entity').onchange=event=>{tile.entity_id=event.target.value;tile.title=(this._hass.states[tile.entity_id]?.attributes?.friendly_name||tile.entity_id).slice(0,40);tile.span=entityKind(tile.entity_id)==='climate'?2:1;this._changed(true);};
      root.querySelector('#tile-span').onchange=event=>{tile.span=Number(event.target.value);this._changed();};
      root.querySelectorAll('[data-icon]').forEach(button=>button.onclick=()=>{tile.icon=button.dataset.icon;this._changed(true);});
      root.querySelector('#remove').onclick=()=>{if(this.draft.tiles.length===1){this._error='请至少保留一张卡片';this._updateStatus();return;}this.draft.tiles=this.draft.tiles.filter(t=>t.id!==tile.id);this._selected=this.draft.tiles[0].id;this._changed(true);};
    }
    root.querySelector('#panel-title').oninput=event=>{this.draft.title=event.target.value;this._changed();};
    for(const [id,key]of [['columns','columns'],['rows','rows'],['interval','refresh_seconds']])root.querySelector('#'+id).onchange=event=>{this.draft[key]=Number(event.target.value);if(key==='columns')this._page=0;this._changed();};
    root.querySelector('#power').onchange=event=>{this.draft.power_mode=event.target.value;this._changed();};
    root.querySelector('#previous').onclick=()=>{this._page=Math.max(0,this._page-1);this._renderPreview();};
    root.querySelector('#next').onclick=()=>{this._page=Math.min((this.preview?.geometry?.pages||1)-1,this._page+1);this._renderPreview();};
  }
  _renderPreview() {
    const stage=this.shadowRoot.querySelector('#device-stage'),g=this.preview?.geometry;if(!stage||!g||!this.draft)return;
    this._page=Math.max(0,Math.min(this._page,g.pages-1));
    const available=this.shadowRoot.querySelector('.preview-wrap').clientWidth || 600;
    const scale=Math.min(.55,Math.max(.25,(available-50)/g.width));
    const f=g.fonts,tiles=new Map(this.draft.tiles.map(t=>[t.id,t]));
    const cards=g.cards.filter(card=>card.page===this._page).map(card=>{
      const tile=tiles.get(card.id);if(!tile)return '';const kind=entityKind(tile.entity_id),state=this.preview.states?.[tile.id]||{state:'unavailable',attributes:{}};const attr=state.attributes||{};const active=state.available&&(state.state==='on'||kind==='climate'&&state.state!=='off');
      const m=card.metrics||{pad:28,icon_size:64,icon_y:50,title_y:128,value_y:167,title_font:25,value_font:38,small_font:19,climate_title_x:112,mode_y:63,current_y:113,climate_value_font:45,label_font:17,control_h:60,control_font:28};
      const climate=kind==='climate',unit=this.preview.temperature_unit||this.data.temperature_unit||'°C';
      const iconSize=climate?(m.climate_icon_size||m.icon_size):m.icon_size;
      let content=`<span class="tile-icon" style="position:absolute;left:${m.pad}px;top:${climate?m.pad:m.icon_y}px;width:${iconSize}px;height:${iconSize}px">${svg(tile.icon)}</span><span class="tile-title" style="position:absolute;left:${climate?m.climate_title_x:m.pad}px;top:${climate?m.pad:m.title_y}px;font-size:${m.title_font}px;max-width:calc(100% - ${climate?m.climate_title_x+m.pad:2*m.pad}px)">${escapeHtml(tile.title)}</span>`;
      if(climate)content+=`<span class="climate-mode" style="left:${m.climate_title_x}px;top:${m.mode_y}px;font-size:${m.small_font}px">${escapeHtml(modes[state.state]||(!state.available?'未连接':state.state))}</span><span class="current" style="left:${m.pad}px;top:${m.current_y}px;font-size:${m.climate_value_font}px"><span class="clabel" style="font-size:${m.label_font}px">当前温度</span>${escapeHtml(attr.current_temperature??'—')}<small class="tile-unit">${escapeHtml(unit)}</small></span><span class="target" style="right:${m.pad}px;top:${m.current_y}px;font-size:${m.climate_value_font}px"><span class="clabel" style="font-size:${m.label_font}px">目标温度</span>${escapeHtml(attr.temperature??'—')}<small class="tile-unit">${escapeHtml(unit)}</small></span><div class="climate-controls" style="height:${m.control_h}px"><span style="font-size:${m.control_font}px">−</span><span>${svg('power')}</span><span style="font-size:${m.control_font}px">＋</span></div>`;
      else{let value=!state.available?'未连接':kind==='toggle'?(state.state==='on'?'开启':'关闭'):kind==='action'?'轻触执行':state.state;content+=`<span class="tile-value" style="position:absolute;left:${m.pad}px;top:${m.value_y}px;font-size:${m.value_font}px;max-width:calc(100% - ${2*m.pad}px)">${escapeHtml(value)}<small class="tile-unit">${escapeHtml(kind==='sensor'?attr.unit_of_measurement||'':'')}</small></span>`;}
      return `<button class="tile ${kind==='climate'?'climate':''} ${active?'active':''} ${tile.id===this._selected?'chosen':''}" data-preview-id="${tile.id}" draggable="true" style="left:${card.x}px;top:${card.y}px;width:${card.w}px;height:${card.h}px" aria-label="编辑 ${escapeHtml(tile.title)}">${content}</button>`;
    }).join('');
    stage.innerHTML=`<div class="bezel"><div class="screen-crop" style="width:${g.width*scale}px;height:${g.height*scale}px"><div class="screen" style="width:${g.width}px;height:${g.height}px;transform:scale(${scale})"><div class="screen-header" style="left:${g.margin}px;right:${g.margin}px;top:32px;font-size:${f.header}px"><span>${escapeHtml(this.draft.title)}</span>${svg('home')}</div>${cards}<div class="screen-footer" style="left:${g.margin}px;right:${g.margin}px;bottom:20px"><span>${this.hasAttribute('preview')?'示例状态':'Home Assistant'}</span><span>${this.draft.refresh_seconds} 秒刷新 · ${this._page+1}/${g.pages}</span></div></div></div><div class="brand">kindle</div></div>`;
    stage.querySelectorAll('[data-preview-id]').forEach(button=>{button.onclick=()=>{this._selected=button.dataset.previewId;this._render();};button.ondragstart=event=>event.dataTransfer.setData('text/plain',button.dataset.previewId);button.ondragover=event=>event.preventDefault();button.ondrop=event=>{event.preventDefault();this._moveTo(event.dataTransfer.getData('text/plain'),button.dataset.previewId);};});
    this.shadowRoot.querySelector('#pages').textContent=`第 ${this._page+1} / ${g.pages} 页`;
    this.shadowRoot.querySelector('#resolution').textContent=`${g.width} × ${g.height} · 黑白墨水屏`;
    this.shadowRoot.querySelector('#previous').disabled=this._page===0;this.shadowRoot.querySelector('#next').disabled=this._page>=g.pages-1;
  }
  async _save() {
    this._saving=true;this._updateStatus();
    try{const data=await this._call('save',{layout:clone(this.draft),revision:this._baseRevision});this.data=data;this.preview=data;this.draft=clone(data.layout);this._baseRevision=data.revision;this._dirty=false;this._error='';this._notice='已保存，Kindle 会在下一次刷新时同步';this._render();}
    catch(error){this._error=error.message||'保存失败';}
    finally{this._saving=false;this._updateStatus();}
  }
  async _pair() {
    if(this.hasAttribute('preview')){this._notice='这是本地预览；安装到 HA 后即可配对 Kindle';this._updateStatus();return;}
    try{
      const result=await this._call('pair');
      const file={server_url:location.origin,code:result.code,name:'Kindle 控制屏',expires:result.expires};
      const url=URL.createObjectURL(new Blob([JSON.stringify(file,null,2)],{type:'application/json'}));
      const link=document.createElement('a');link.href=url;link.download='kindle-pairing.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),30000);
      this._notice='配对文件已下载，10 分钟内放入 Kindle 的 nativeha 文件夹，再打开面板即可。';this._updateStatus();
    }catch(error){this._error=error.message||'生成配对文件失败';this._updateStatus();}
  }
}
customElements.define('kindle-panel-editor',KindlePanelEditor);

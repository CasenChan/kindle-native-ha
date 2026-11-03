// Editor styles. Colors come from the active HA theme so light and dark themes both work.
const EDITOR_CSS = `
:host{
  --kp-bg:var(--primary-background-color,#f3f4f6);--kp-surface:var(--card-background-color,#fff);
  --kp-surface-2:var(--secondary-background-color,#f6f7f9);--kp-border:var(--divider-color,#e2e5e9);
  --kp-text:var(--primary-text-color,#1b2127);--kp-text-2:var(--secondary-text-color,#56616c);
  --kp-text-3:var(--disabled-text-color,#8b95a0);--kp-primary:var(--primary-color,#0a7cd8);
  --kp-ok:var(--success-color,#25915a);--kp-warn:var(--warning-color,#b7791f);--kp-danger:var(--error-color,#cf3f3f);
  --kp-soft:color-mix(in srgb,var(--kp-primary) 10%,transparent);--kp-line:color-mix(in srgb,var(--kp-primary) 40%,transparent);
  --kp-strong:color-mix(in srgb,var(--kp-text) 22%,transparent);--kp-fill:color-mix(in srgb,var(--kp-text) 6%,transparent);
  display:block;height:100%;background:var(--kp-bg);color:var(--kp-text);
  font:14px/1.5 var(--paper-font-body1_-_font-family,Roboto),"Noto Sans CJK SC","PingFang SC","Microsoft YaHei",sans-serif;
  -webkit-font-smoothing:antialiased
}
*{box-sizing:border-box}
button,input,select{font:inherit;color:inherit}
button{cursor:pointer}
button:disabled{cursor:default;opacity:.45}
:focus-visible{outline:2px solid var(--kp-primary);outline-offset:2px}
svg{display:block}
.app{display:flex;flex-direction:column;height:100%;min-height:0}

/* top bar */
.topbar{flex:none;height:56px;display:flex;align-items:center;gap:10px;padding:0 16px 0 20px;background:var(--app-header-background-color,var(--kp-surface));color:var(--app-header-text-color,var(--kp-text));border-bottom:1px solid var(--kp-border)}
.menu-btn{display:none;width:40px;height:40px;border:0;background:none;border-radius:50%;place-items:center;margin-left:-8px;color:inherit}
.menu-btn svg{width:24px;height:24px}
.brand{font-size:18px;font-weight:600;white-space:nowrap}
.spacer{flex:1}
.notice{font-size:13px;color:var(--kp-text-2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
.notice.dirty{color:var(--kp-warn)}
.notice.dirty::before{content:"";display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--kp-warn);margin-right:6px;vertical-align:1px}
.notice.error{color:var(--kp-danger)}
.chip{display:inline-flex;align-items:center;gap:7px;height:32px;padding:0 12px;border-radius:16px;background:var(--kp-surface-2);border:1px solid var(--kp-border);font-size:13px;color:var(--kp-text-2);white-space:nowrap}
.dot{width:8px;height:8px;border-radius:50%;background:var(--kp-ok);flex:none}
.dot.off{background:var(--kp-text-3)}
.btn{height:36px;padding:0 16px;border-radius:18px;border:1px solid var(--kp-strong);background:var(--kp-surface);font-weight:500;display:inline-flex;align-items:center;justify-content:center;gap:6px;white-space:nowrap}
.btn svg{width:18px;height:18px}
.btn.text{border-color:transparent;background:none;color:var(--kp-text-2)}
.btn.primary{background:var(--kp-primary);border-color:var(--kp-primary);color:var(--text-primary-color,#fff)}
.btn.small{height:30px;padding:0 12px;font-size:13px}
.btn.danger{color:var(--kp-danger)}
.btn.block{width:100%}
.icon-btn{width:32px;height:32px;border:0;background:none;border-radius:8px;display:grid;place-items:center;color:var(--kp-text-2)}
.icon-btn:hover{background:var(--kp-fill)}
.icon-btn svg{width:18px;height:18px}

/* workspace */
.workspace{flex:1;min-height:0;display:grid;grid-template-columns:300px minmax(0,1fr) 352px}
.pane{background:var(--kp-surface);overflow:auto;min-height:0}
.pane.left{border-right:1px solid var(--kp-border)}
.pane.right{border-left:1px solid var(--kp-border)}
.pages{display:flex;gap:6px;flex-wrap:wrap;padding:14px 14px 6px}
.page-chip{height:30px;padding:0 12px;border-radius:15px;border:1px solid var(--kp-border);background:var(--kp-surface);font-size:13px;color:var(--kp-text-2);display:inline-flex;align-items:center;gap:6px}
.page-chip.on{background:var(--kp-text);color:var(--kp-surface);border-color:var(--kp-text);font-weight:600}
.page-chip svg{width:14px;height:14px}
.section-head{display:flex;align-items:center;gap:6px;padding:12px 10px 4px 20px;cursor:pointer}
.section-head .name{font-size:12px;font-weight:600;color:var(--kp-text-3);letter-spacing:.4px;flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.section-head.sel .name{color:var(--kp-primary)}
.section-head small{font-size:12px;color:var(--kp-text-3)}
.tile-list{padding:0 10px;min-height:8px;border-radius:10px}
.tile-list.drop{background:var(--kp-soft)}
.row{display:grid;grid-template-columns:14px 36px minmax(0,1fr) auto;align-items:center;gap:10px;padding:7px 10px;border-radius:10px;border:1px solid transparent;margin-bottom:2px;cursor:pointer}
.row:hover{background:var(--kp-fill)}
.row.sel{background:var(--kp-soft);border-color:var(--kp-line)}
.grip{color:var(--kp-text-3);cursor:grab}
.grip svg{width:14px;height:14px}
.ico{width:36px;height:36px;border-radius:10px;background:var(--kp-fill);display:grid;place-items:center;color:var(--kp-text);flex:none}
.ico svg{width:20px;height:20px}
.row.sel .ico{background:var(--kp-surface);color:var(--kp-primary)}
.row .name{font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mono{font-size:12px;color:var(--kp-text-3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-family:"Roboto Mono",ui-monospace,monospace}
.row .state{font-size:12px;color:var(--kp-text-2);text-align:right;white-space:nowrap;max-width:84px;overflow:hidden;text-overflow:ellipsis}
.row .state.on{color:var(--kp-ok)}
.row .state.off{color:var(--kp-text-3)}
.add-row{margin:4px 10px 4px;width:calc(100% - 20px);height:34px;border-radius:9px;border:1.5px dashed var(--kp-strong);background:none;color:var(--kp-text-2);display:flex;align-items:center;justify-content:center;gap:6px;font-size:13px}
.add-row svg{width:16px;height:16px}
.list-foot{padding:10px 10px 24px}
.empty{padding:6px 20px;font-size:12px;color:var(--kp-text-3)}

/* stage */
.stage{position:relative;min-height:0;overflow:hidden;background:var(--kp-surface-2);background-image:radial-gradient(var(--kp-border) 1px,transparent 1px);background-size:18px 18px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px;padding:44px 16px 16px}
.stage-top{position:absolute;top:12px;left:16px;right:16px;display:flex;justify-content:space-between;align-items:center;gap:12px;font-size:12px;color:var(--kp-text-3)}
.bezel{background:#202325;border-radius:28px;padding:20px 18px 38px;box-shadow:0 30px 60px -24px rgba(0,0,0,.45),0 0 0 1px rgba(255,255,255,.08);position:relative;flex:none}
.bezel::after{content:"kindle";position:absolute;bottom:12px;left:0;right:0;text-align:center;color:#6d7276;font-size:11px;letter-spacing:3px}
.crop{position:relative;overflow:hidden;border-radius:2px;background:#fff}
.overlay{position:absolute;inset:0}
.hot{position:absolute;border-radius:10px;cursor:pointer;touch-action:none}
.hot:hover{box-shadow:0 0 0 2px var(--kp-line)}
.hot.sel{box-shadow:0 0 0 3px var(--kp-primary),0 0 0 7px var(--kp-soft)}
.hot .resize{position:absolute;right:-7px;bottom:-7px;width:16px;height:16px;border-radius:5px;background:var(--kp-primary);border:2px solid #fff;cursor:nwse-resize;display:none}
.hot.sel .resize{display:block}
.ghost{position:absolute;border:2px dashed var(--kp-primary);background:color-mix(in srgb,var(--kp-primary) 14%,transparent);border-radius:10px;pointer-events:none}
.cell{position:absolute;border:1px dashed color-mix(in srgb,var(--kp-primary) 35%,transparent);border-radius:6px;pointer-events:none}
.section-hot{position:absolute;cursor:pointer;border-radius:6px}
.section-hot:hover{background:color-mix(in srgb,var(--kp-primary) 8%,transparent)}
.pager{display:flex;align-items:center;gap:10px;color:var(--kp-text-2);font-size:13px}
.pager .pg{width:30px;height:30px;border-radius:50%;border:1px solid var(--kp-border);background:var(--kp-surface);display:grid;place-items:center}
.pager .pg svg{width:16px;height:16px}
.stage-hint{font-size:12px;color:var(--kp-text-3);text-align:center}
.stage-error{position:absolute;left:50%;transform:translateX(-50%);bottom:56px;max-width:80%;background:var(--kp-danger);color:#fff;padding:8px 14px;border-radius:10px;font-size:13px;box-shadow:0 6px 18px rgba(0,0,0,.2)}

/* inspector */
.tabs{display:flex;gap:4px;padding:8px 12px 0;border-bottom:1px solid var(--kp-border);position:sticky;top:0;background:var(--kp-surface);z-index:1}
.tabs button{border:0;background:none;height:42px;padding:0 12px;color:var(--kp-text-2);font-weight:500;border-bottom:2px solid transparent;margin-bottom:-1px}
.tabs button.on{color:var(--kp-primary);border-color:var(--kp-primary)}
.section{padding:18px 20px;border-bottom:1px solid var(--kp-border)}
.section:last-child{border-bottom:0}
.section h3{margin:0 0 14px;font-size:13px;font-weight:600;color:var(--kp-text-2);letter-spacing:.3px}
.head-card{display:flex;align-items:center;gap:12px}
.head-card .ico{width:44px;height:44px;border-radius:12px;background:var(--kp-soft);color:var(--kp-primary)}
.head-card .ico svg{width:24px;height:24px}
.head-card b{display:block;font-size:16px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.head-card small{color:var(--kp-text-3);font-size:12px}
.kind{display:inline-block;font-size:11px;font-weight:600;padding:2px 8px;border-radius:10px;background:var(--kp-soft);color:var(--kp-primary);margin-left:6px;vertical-align:2px}
.field{margin-bottom:16px}
.field:last-child{margin-bottom:0}
.field>label,.field>.label{display:block;font-size:12px;font-weight:500;color:var(--kp-text-2);margin-bottom:6px}
.input{width:100%;height:40px;border:1px solid var(--kp-strong);border-radius:9px;background:var(--kp-surface);padding:0 12px;outline:none}
.input:focus{border-color:var(--kp-primary);box-shadow:0 0 0 3px var(--kp-soft)}
.input.invalid{border-color:var(--kp-danger)}
select.input{padding-right:8px}
.picker{display:flex;align-items:center;gap:10px;width:100%;min-height:52px;border:1px solid var(--kp-strong);border-radius:9px;background:var(--kp-surface);padding:6px 8px 6px 8px;text-align:left}
.picker .t{flex:1;min-width:0}
.picker .t b{display:block;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.picker .change{font-size:13px;color:var(--kp-primary);font-weight:500;padding:6px 8px}
.seg{display:grid;grid-auto-flow:column;grid-auto-columns:1fr;background:var(--kp-fill);border-radius:9px;padding:3px;gap:3px}
.seg button{border:0;background:none;height:34px;border-radius:7px;color:var(--kp-text-2);font-size:13px;white-space:nowrap;padding:0 4px}
.seg button.on{background:var(--kp-surface);color:var(--kp-text);font-weight:600;box-shadow:0 1px 2px rgba(0,0,0,.12)}
.stepper{display:flex;align-items:center;border:1px solid var(--kp-strong);border-radius:9px;height:40px;overflow:hidden}
.stepper button{width:40px;height:100%;border:0;background:none;display:grid;place-items:center;color:var(--kp-text-2)}
.stepper button svg{width:16px;height:16px}
.stepper span{flex:1;text-align:center;font-weight:600}
.hint{font-size:12px;color:var(--kp-text-3);margin-top:6px;line-height:1.6}
.hint.error{color:var(--kp-danger)}
.icons{display:grid;grid-template-columns:repeat(6,1fr);gap:6px}
.icons button{aspect-ratio:1;border:1px solid var(--kp-border);border-radius:9px;background:var(--kp-surface);display:grid;place-items:center;color:var(--kp-text-2);padding:0}
.icons button svg{width:22px;height:22px}
.icons button.on{border-color:var(--kp-primary);background:var(--kp-soft);color:var(--kp-primary)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.radio-card{display:flex;gap:12px;padding:12px;border:1px solid var(--kp-border);border-radius:10px;margin-bottom:8px;width:100%;text-align:left;background:var(--kp-surface)}
.radio-card.on{border-color:var(--kp-line);background:var(--kp-soft)}
.radio-card .r{width:18px;height:18px;border-radius:50%;border:2px solid var(--kp-strong);flex:none;margin-top:2px}
.radio-card.on .r{border:5px solid var(--kp-primary)}
.radio-card b{display:block;font-weight:500}
.radio-card small{color:var(--kp-text-3);font-size:12px}
.switch-row{display:flex;align-items:center;justify-content:space-between;gap:12px;width:100%;border:0;background:none;padding:0;text-align:left}
.toggle{width:40px;height:22px;border-radius:11px;background:var(--kp-strong);position:relative;flex:none;transition:background .15s}
.toggle::after{content:"";position:absolute;top:3px;left:3px;width:16px;height:16px;border-radius:50%;background:#fff;transition:left .15s}
.toggle.on{background:var(--kp-primary)}
.toggle.on::after{left:21px}
.actions-row{display:flex;gap:8px;flex-wrap:wrap}
.meter{height:6px;border-radius:3px;background:var(--kp-fill);overflow:hidden;margin-top:8px}
.meter i{display:block;height:100%;background:var(--kp-primary)}
.meter.full i{background:var(--kp-warn)}

/* devices */
.device{border:1px solid var(--kp-border);border-radius:12px;padding:14px;margin-bottom:10px}
.device.preview{border-color:var(--kp-line)}
.device .top{display:flex;align-items:center;gap:12px}
.device .kico{width:30px;height:40px;border-radius:5px;border:2px solid var(--kp-text);position:relative;flex:none}
.device .kico::after{content:"";position:absolute;inset:3px 3px 7px;border-radius:2px;background:var(--kp-fill)}
.device.offline .kico{border-color:var(--kp-text-3)}
.device b{display:block;font-weight:600}
.device small{font-size:12px;color:var(--kp-text-3)}
.device .meta{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:14px 0 12px}
.device .meta div{background:var(--kp-surface-2);border-radius:8px;padding:8px 10px;min-width:0}
.device .meta span{display:block;font-size:11px;color:var(--kp-text-3)}
.device .meta strong{font-size:13px;font-weight:600;white-space:nowrap}
.device .meta strong.warn{color:var(--kp-warn)}
.device .acts{display:flex;justify-content:flex-end;gap:8px}
.pair-card{border-radius:12px;padding:16px;background:var(--kp-surface-2);border:1px solid var(--kp-border)}
.pair-card ol{margin:10px 0 14px;padding-left:20px;color:var(--kp-text-2);font-size:13px;line-height:1.9}
.code{font-family:"Roboto Mono",ui-monospace,monospace;font-size:12px;background:var(--kp-fill);padding:2px 6px;border-radius:5px}
.demo-note{background:color-mix(in srgb,var(--kp-warn) 14%,transparent);color:var(--kp-warn);padding:8px 20px;font-size:12px}

/* entity picker */
.scrim{position:fixed;inset:0;background:rgba(10,14,18,.45);display:grid;place-items:center;z-index:10;padding:16px}
.dialog{width:600px;max-width:100%;max-height:min(720px,86vh);background:var(--kp-surface);border-radius:18px;box-shadow:0 30px 80px rgba(0,0,0,.3);display:flex;flex-direction:column;overflow:hidden}
.dialog .dh{display:flex;justify-content:space-between;align-items:center;padding:16px 16px 4px 20px}
.dialog .dh h2{margin:0;font-size:17px}
.search{margin:12px 20px 0;display:flex;align-items:center;gap:10px;height:44px;border:1.5px solid var(--kp-strong);border-radius:11px;padding:0 12px}
.search:focus-within{border-color:var(--kp-primary);box-shadow:0 0 0 3px var(--kp-soft)}
.search svg{width:20px;height:20px;color:var(--kp-text-3);flex:none}
.search input{flex:1;border:0;outline:none;background:none;height:100%;min-width:0}
.filters{display:flex;gap:8px;padding:12px 20px;flex-wrap:wrap}
.filters button{height:30px;border-radius:15px;border:1px solid var(--kp-border);background:var(--kp-surface);padding:0 12px;font-size:13px;color:var(--kp-text-2)}
.filters button.on{background:var(--kp-text);color:var(--kp-surface);border-color:var(--kp-text)}
.filters button i{font-style:normal;opacity:.6;margin-left:4px}
.results{overflow:auto;border-top:1px solid var(--kp-border);padding:6px 10px 10px;flex:1;min-height:120px}
.results .gl{padding:10px 10px 4px;font-size:12px;color:var(--kp-text-3);font-weight:600}
.res{display:grid;grid-template-columns:36px minmax(0,1fr) auto;gap:12px;align-items:center;padding:8px 10px;border-radius:10px;width:100%;border:0;background:none;text-align:left}
.res:hover,.res.hl{background:var(--kp-soft)}
.res b{display:block;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.res mark{background:none;color:var(--kp-primary);font-weight:700}
.res .v{font-size:13px;color:var(--kp-text-2);text-align:right;max-width:140px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.res .v small{display:block;font-size:11px;color:var(--kp-text-3)}
.res.added{opacity:.6}
.dialog .df{display:flex;justify-content:space-between;align-items:center;padding:12px 20px;border-top:1px solid var(--kp-border);font-size:12px;color:var(--kp-text-3)}

/* narrow / mobile */
.mtabs{display:none}
:host([narrow]) .menu-btn{display:grid}
:host([narrow]) .topbar{padding:0 8px 0 12px}
:host([narrow]) .hide-narrow{display:none}
:host([narrow]) .mtabs{display:flex;flex:none;background:var(--kp-surface);border-bottom:1px solid var(--kp-border);padding:0 8px}
:host([narrow]) .mtabs button{flex:1;border:0;background:none;height:44px;color:var(--kp-text-2);font-weight:500;border-bottom:2px solid transparent}
:host([narrow]) .mtabs button.on{color:var(--kp-primary);border-color:var(--kp-primary)}
:host([narrow]) .workspace{display:block;overflow:auto}
:host([narrow]) .pane{border:0;overflow:visible}
:host([narrow]) .workspace>*{display:none}
:host([narrow]) .workspace>.show{display:block}
:host([narrow]) .workspace>.stage.show{display:flex;min-height:420px;padding-top:20px}
:host([narrow]) .stage-top{display:none}
:host([narrow]) .tabs{display:none}
:host([narrow]) .dialog{max-height:92vh}
`;

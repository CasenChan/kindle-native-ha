// Paints one rendered page (server display list) as HTML: the same ops the Kindle paints natively.
const gray = value => `rgb(${value},${value},${value})`;
const ICON_COLORS = {k: '#000', w: '#fff', g: 'rgb(180,180,180)'};

const iconSvg = (name, stroke = 'currentColor', width = 2) =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="${stroke}" stroke-width="${width}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ICONS.sensor}</svg>`;

function paintPage(page, screen, tokens = {}) {
  const parts = [];
  for (const op of page.ops) {
    if (op.t === 'r') {
      const fill = op.k === 'backlight' && tokens.backlight ? 0 : op.f;
      const style = [`left:${op.x}px`, `top:${op.y}px`, `width:${op.w}px`, `height:${op.h}px`,
        fill != null ? `background:${gray(fill)}` : '', op.b ? `border:${op.b}px solid ${gray(op.c ?? 0)}` : '',
        op.r ? `border-radius:${op.r}px` : ''].filter(Boolean).join(';');
      parts.push(`<div class="op" style="${style}"></div>`);
    } else if (op.t === 'x') {
      let value = op.k ? tokens[op.k] ?? '' : op.v;
      let color = op.c ?? 0, bold = op.b;
      if (op.k === 'status' && tokens.statusError) { color = 0; bold = true; }
      const align = op.a || 'l';
      const box = align === 'r' ? `right:${screen.width - op.x}px;text-align:right${op.w ? `;max-width:${op.w}px` : ''}`
        : align === 'c' ? `left:${op.x - op.w / 2}px;width:${op.w}px;text-align:center`
        : `left:${op.x}px${op.w ? `;max-width:${op.w}px` : ''}`;
      const unit = op.u ? `<small style="font-size:${Math.round(op.s * 0.5)}px;font-weight:400;margin-left:${Math.max(3, Math.round(op.s * 0.12))}px">${escapeHtml(op.u)}</small>` : '';
      parts.push(`<span class="op text" style="${box};top:${op.y}px;font-size:${op.s}px;color:${gray(color)};font-weight:${bold ? 700 : 400}">${escapeHtml(value)}${unit}</span>`);
    } else if (op.t === 'i') {
      let color = op.c;
      if (op.k === 'backlight' && tokens.backlight) color = 'w';
      if (op.k === 'wifi' && tokens.offline) color = 'g';
      parts.push(`<span class="op" style="left:${op.x}px;top:${op.y}px;width:${op.s}px;height:${op.s}px">${iconSvg(op.n, ICON_COLORS[color] || '#000')}</span>`);
    }
  }
  return parts.join('');
}

const PAINTER_CSS = `
  .kindle-screen{position:relative;overflow:hidden;background:#fff;color:#000;font-family:"Noto Sans CJK SC","Source Han Sans SC","PingFang SC","Microsoft YaHei",sans-serif;line-height:1.2;transform-origin:top left}
  .kindle-screen .op{position:absolute;box-sizing:border-box}
  .kindle-screen .op svg{display:block;width:100%;height:100%}
  .kindle-screen .text{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
`;

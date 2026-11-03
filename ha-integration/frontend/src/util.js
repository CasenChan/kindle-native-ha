// Shared helpers. Kind/icon rules mirror protocol.py so new cards look right before the server answers.
const clone = value => JSON.parse(JSON.stringify(value));
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch]));
const uid = prefix => `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
const clamp = (value, low, high) => Math.max(low, Math.min(high, value));

const TOGGLE_DOMAINS = ['switch', 'light', 'fan', 'input_boolean', 'humidifier'];
const ACTION_DOMAINS = ['scene', 'script', 'button', 'input_button'];
const domainOf = entityId => entityId.split('.')[0];
const kindOf = entityId => {
  const domain = domainOf(entityId);
  return TOGGLE_DOMAINS.includes(domain) ? 'toggle' : domain === 'climate' ? 'climate'
    : ACTION_DOMAINS.includes(domain) ? 'action' : 'sensor';
};
const KIND_NAMES = {toggle: '开关', climate: '空调', action: '场景/按钮', sensor: '状态'};
const ICON_BY_CLASS = {temperature: 'temperature', humidity: 'humidity', door: 'door', garage_door: 'door', window: 'window',
  opening: 'door', lock: 'lock', motion: 'motion', occupancy: 'motion', presence: 'motion', battery: 'battery',
  power: 'bolt', energy: 'bolt', curtain: 'curtain', blind: 'curtain', shade: 'curtain', tv: 'tv', outlet: 'plug'};
const ICON_BY_DOMAIN = {light: 'bulb', switch: 'plug', fan: 'fan', climate: 'thermostat', scene: 'scene', script: 'scene',
  button: 'power', input_button: 'power', lock: 'lock', cover: 'curtain', media_player: 'tv', humidifier: 'humidity',
  input_boolean: 'power', person: 'home'};
const defaultIcon = (entityId, deviceClass) => ICON_BY_CLASS[deviceClass] || ICON_BY_DOMAIN[domainOf(entityId)] || 'sensor';
const ICON_NAMES = {bulb: '灯泡', thermostat: '空调', temperature: '温度', humidity: '湿度', power: '电源', fan: '风扇',
  home: '房屋', scene: '场景', plug: '插座', sensor: '传感器', door: '门', window: '窗', lock: '锁', curtain: '窗帘',
  tv: '电视', motion: '人体', battery: '电池', bolt: '电量'};
const DOMAIN_NAMES = {light: '灯光', switch: '开关', fan: '风扇', climate: '空调', scene: '场景', script: '脚本',
  button: '按钮', input_button: '按钮', input_boolean: '辅助开关', humidifier: '加湿器', sensor: '传感器',
  binary_sensor: '二元传感器', lock: '门锁', cover: '窗帘/门', media_player: '媒体', person: '人员',
  device_tracker: '位置', vacuum: '扫地机', weather: '天气', sun: '太阳'};

const UI_ICONS = {
  menu: "<path d='M4 6h16M4 12h16M4 18h16'/>", plus: "<path d='M12 5v14M5 12h14'/>", minus: "<path d='M5 12h14'/>",
  grip: "<circle cx='9' cy='6' r='1'/><circle cx='15' cy='6' r='1'/><circle cx='9' cy='12' r='1'/><circle cx='15' cy='12' r='1'/><circle cx='9' cy='18' r='1'/><circle cx='15' cy='18' r='1'/>",
  left: "<path d='m15 6-6 6 6 6'/>", right: "<path d='m9 6 6 6-6 6'/>", up: "<path d='m6 15 6-6 6 6'/>", down: "<path d='m6 9 6 6 6-6'/>",
  trash: "<path d='M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3'/>", search: "<circle cx='11' cy='11' r='7'/><path d='m20 20-4-4'/>",
  x: "<path d='M6 6l12 12M18 6 6 18'/>", sync: "<path d='M4 12a8 8 0 0 1 14-5.3L20 9M20 4v5h-5M20 12a8 8 0 0 1-14 5.3L4 15M4 20v-5h5'/>",
  undo: "<path d='M9 14 4 9l5-5'/><path d='M4 9h11a5 5 0 0 1 0 10h-3'/>", file: "<path d='M14 3H6v18h12V7Z'/><path d='M14 3v4h4M12 11v6M9 14l3 3 3-3'/>",
  gear: "<circle cx='12' cy='12' r='3'/><path d='M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z'/>",
  folder: "<path d='M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z'/>",
  page: "<rect x='5' y='3' width='14' height='18' rx='2'/><path d='M9 7h6M9 11h6'/>",
};
const ui = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${UI_ICONS[name]}</svg>`;

const ago = seconds => {
  if (!seconds) return '从未同步';
  const age = Math.max(0, Date.now() / 1000 - seconds);
  if (age < 60) return `${Math.round(age)} 秒前`;
  if (age < 3600) return `${Math.round(age / 60)} 分钟前`;
  if (age < 86400) return `${Math.round(age / 3600)} 小时前`;
  return `${Math.round(age / 86400)} 天前`;
};
const WEEKDAYS = ['日', '一', '二', '三', '四', '五', '六'];
const kindleStatus = (date = new Date()) =>
  `${date.getMonth() + 1}月${date.getDate()}日 周${WEEKDAYS[date.getDay()]} · ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')} 已更新`;

const fs = require('fs');
const races = require('./_race_data.js');

const file = 'C:/Users/admin/Desktop/2026_trail_races.html';
let html = fs.readFileSync(file, 'utf-8');

// 生成JSON形式的JS数组（保持引号）
function toJS(race) {
  const parts = [];
  parts.push(`name:${JSON.stringify(race.name)}`);
  parts.push(`date:${JSON.stringify(race.date)}`);
  if (race.endDate) parts.push(`endDate:${JSON.stringify(race.endDate)}`);
  parts.push(`province:${JSON.stringify(race.province)}`);
  parts.push(`city:${JSON.stringify(race.city)}`);
  // distances
  const distArr = race.distances.map(d => {
    if (typeof d === 'object') {
      const o = [`d:${JSON.stringify(d.d)}`];
      if (d.climb) o.push(`climb:${JSON.stringify(d.climb)}`);
      if (d.time) o.push(`time:${JSON.stringify(d.time)}`);
      return `{${o.join(',')}}`;
    }
    return JSON.stringify(d);
  });
  parts.push(`distances:[${distArr.join(',')}]`);
  parts.push(`tags:[${(race.tags||[]).map(t=>`"${t}"`).join(',')}]`);
  parts.push(`status:${JSON.stringify(race.status)}`);
  if (race.link) parts.push(`link:${JSON.stringify(race.link)}`);
  if (race.wechat) parts.push(`wechat:${JSON.stringify(race.wechat)}`);
  return `    { ${parts.join(', ')} }`;
}

const jsLines = races.map(toJS).join(',\n');
const newArray = `const races = [\n${jsLines}\n];`;

// 替换 const races = [...] 到 ];
const startMarker = 'const races = [';
const startIdx = html.indexOf(startMarker);
const endIdx = html.indexOf('];', startIdx) + 2;
if (startIdx === -1) { console.log('找不到races数组'); process.exit(1); }

html = html.slice(0, startIdx) + newArray + html.slice(endIdx);
fs.writeFileSync(file, html, 'utf-8');
console.log('已替换races数组，共 ' + races.length + ' 场赛事');

// 验证语法
const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
try { new Function(scriptMatch[1]); console.log('✓ JS语法OK'); }
catch(e){ console.log('✗ 语法错误:', e.message); }

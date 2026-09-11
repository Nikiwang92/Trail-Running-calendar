// scripts/daily_update.js
// 每日自动跑一遍：
//   1. 取当天日期
//   2. 批量重算 _race_data.js 的 status 字段（endDate||date < today → past）
//   3. 把更新后的 races 数组写回 _race_data.js（保留注释）
//   4. 同步刷新 index.html：const today、races 数组、页脚"更新时间"
//   5. 校验 index.html 内嵌脚本语法

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname);
const DATA_FILE = path.join(ROOT, '_race_data.js');
const HTML_FILE = path.join(ROOT, 'index.html');

// 1. 基准日期（取本地当天）
const now = new Date();
const todayStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
const todayDate = new Date(todayStr);
console.log(`[daily] 基准日期: ${todayStr}`);

// 2. 加载并重算 status
delete require.cache[require.resolve(DATA_FILE)];
const races = require(DATA_FILE);

let updated = 0;
races.forEach(r => {
    // cancelled 由 merge_all.py 依"连续 14 天未抓到"判定，这里不覆盖
    if (r.status === 'cancelled') return;
    const endDate = new Date(r.endDate || r.date);
    const newStatus = endDate < todayDate ? 'past' : 'upcoming';
    if (r.status !== newStatus) {
        console.log(`  ${r.name} (${r.date}${r.endDate ? '~' + r.endDate : ''}): ${r.status} → ${newStatus}`);
        r.status = newStatus;
        updated++;
    }
});
console.log(`[daily] 共 ${races.length} 场，更新 ${updated} 场状态`);

// 3. 序列化单条赛事为 JS 字面量
function serializeRace(race, indent) {
    const parts = [];
    parts.push(`name:${JSON.stringify(race.name == null ? '' : String(race.name))}`);
    parts.push(`date:${JSON.stringify(race.date == null ? '' : String(race.date))}`);
    if (race.endDate) parts.push(`endDate:${JSON.stringify(race.endDate)}`);
    parts.push(`province:${JSON.stringify(race.province == null ? '' : String(race.province))}`);
    parts.push(`city:${JSON.stringify(race.city == null ? '' : String(race.city))}`);
    const distArr = (race.distances || []).map(d => {
        if (typeof d === 'object') {
            const o = [`d:${JSON.stringify(d.d)}`];
            if (d.climb) o.push(`climb:${JSON.stringify(d.climb)}`);
            if (d.time) o.push(`time:${JSON.stringify(d.time)}`);
            return `{${o.join(',')}}`;
        }
        return JSON.stringify(d);
    });
    parts.push(`distances:[${distArr.join(',')}]`);
    parts.push(`tags:[${(race.tags || []).map(t => `"${t}"`).join(',')}]`);
    parts.push(`status:${JSON.stringify(race.status)}`);
    if (race.link) parts.push(`link:${JSON.stringify(race.link)}`);
    if (race.wechat) parts.push(`wechat:${JSON.stringify(race.wechat)}`);
    if (race.official) parts.push(`official:${JSON.stringify(race.official)}`);
    return `${indent}{ ${parts.join(', ')} }`;
}

// 4. 写回 _race_data.js（保留前后注释）
let dataSrc = fs.readFileSync(DATA_FILE, 'utf-8');
const dataStartMarker = 'module.exports = [';
const dataStartIdx = dataSrc.indexOf(dataStartMarker);
if (dataStartIdx === -1) {
    console.error('[daily] ✗ _race_data.js 找不到 module.exports');
    process.exit(1);
}
const dataEndIdx = dataSrc.indexOf('];', dataStartIdx);
const dataPrefix = dataSrc.slice(0, dataStartIdx + dataStartMarker.length);
const dataSuffix = dataSrc.slice(dataEndIdx);
const newDataArr = '\n' + races.map(r => serializeRace(r, '  ')).join(',\n') + '\n';
fs.writeFileSync(DATA_FILE, dataPrefix + newDataArr + dataSuffix, 'utf-8');
console.log(`[daily] ✓ _race_data.js 已更新`);

// 5. 更新 index.html
let html = fs.readFileSync(HTML_FILE, 'utf-8');

// 5a. const today
const todayRegex = /const today = new Date\('\d{4}-\d{2}-\d{2}'\)/;
if (!todayRegex.test(html)) {
    console.error('[daily] ✗ index.html 找不到 const today');
    process.exit(1);
}
html = html.replace(todayRegex, `const today = new Date('${todayStr}')`);
console.log(`[daily] ✓ const today = ${todayStr}`);

// 5b. races 数组：template/shim 模式跳过；嵌入模式才替换
// 检测 "const races = module" → 跳过（shim 模式）
if (html.includes('const races = module')) {
    console.log('[daily] (skip) template/shim 模式（const races = module.exports）');
} else {
    const racesStartMarker = 'const races = [';
    const racesStartIdx = html.indexOf(racesStartMarker);
    if (racesStartIdx === -1) {
        console.log('[daily] (skip) index.html 无 const races');
    } else {
        const afterMarker = html.substring(racesStartIdx + racesStartMarker.length, racesStartIdx + racesStartMarker.length + 50);
        if (afterMarker.trimStart().startsWith(']')) {
            console.log('[daily] (skip) const races = [] 空数组');
        } else {
            const racesEndIdx = html.indexOf('];', racesStartIdx) + 2;
            const htmlPrefix = html.slice(0, racesStartIdx + racesStartMarker.length);
            const htmlSuffix = html.slice(racesEndIdx);
            const newHtmlArr = '\n' + races.map(r => serializeRace(r, '    ')).join(',\n') + '\n];';
            html = htmlPrefix + newHtmlArr + htmlSuffix;
            console.log(`[daily] ✓ races 数组已重新生成 (${races.length} 场)`);
        }
    }
}

// 5c. 页脚"更新时间：YYYY年M月D日"
const cnDate = `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日`;
const footerRegex = /更新时间：\d{4}年\d{1,2}月\d{1,2}日/;
if (footerRegex.test(html)) {
    html = html.replace(footerRegex, `更新时间：${cnDate}`);
    console.log(`[daily] ✓ 页脚更新时间 = ${cnDate}`);
}

fs.writeFileSync(HTML_FILE, html, 'utf-8');

// 6. 校验 HTML 内嵌脚本语法
try {
    const scriptMatch = fs.readFileSync(HTML_FILE, 'utf-8').match(/<script>([\s\S]*?)<\/script>/);
    new Function(scriptMatch[1]);
    console.log('[daily] ✓ index.html JS 语法 OK');
} catch (e) {
    console.error('[daily] ✗ 语法错误:', e.message);
    process.exit(1);
}

console.log('[daily] 完成');

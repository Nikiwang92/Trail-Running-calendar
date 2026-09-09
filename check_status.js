const fs = require('fs');
const races = require('./_race_data.js');

const today = new Date('2026-09-08');

function getRaceStatus(race) {
    const endDate = race.endDate ? new Date(race.endDate) : new Date(race.date);
    return endDate < today ? 'past' : 'upcoming';
}

let pastCount = 0;
let upcomingCount = 0;
const mismatches = [];

races.forEach(race => {
    const computedStatus = getRaceStatus(race);
    const actualStatus = race.status;
    if (computedStatus !== actualStatus) {
        mismatches.push({
            name: race.name,
            date: race.date,
            endDate: race.endDate,
            computed: computedStatus,
            actual: actualStatus
        });
    }
    if (computedStatus === 'past') pastCount++;
    else upcomingCount++;
});

console.log(`总计 ${races.length} 场赛事`);
console.log(`根据今天 ${today.toISOString().split('T')[0]} 计算：`);
console.log(`  已结束: ${pastCount}`);
console.log(`  未开始: ${upcomingCount}`);
console.log(`\n状态不匹配的赛事：${mismatches.length}`);
mismatches.forEach(m => {
    console.log(`  "${m.name}" (${m.date}${m.endDate ? '~'+m.endDate : ''}): 当前 "${m.actual}" → 应改为 "${m.computed}"`);
});

// 检查是否有8月22日、23日的赛事
const augustRaces = races.filter(r => {
    const d = new Date(r.date);
    return d.getFullYear() === 2026 && d.getMonth() === 7; // 月份0-indexed，7 = 8月
});
console.log(`\n8月份的赛事 (${augustRaces.length} 场):`);
augustRaces.forEach(r => {
    const status = getRaceStatus(r);
    console.log(`  ${r.date}: ${r.name} (${status})`);
});
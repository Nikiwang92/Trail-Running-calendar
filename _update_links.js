const fs = require('fs');
const file = 'C:/Users/admin/Desktop/2026_trail_races.html';
let html = fs.readFileSync(file, 'utf-8');

const links = {
  "2026凯乐石广州100越野赛": "https://www.letoursport.com/events?mid=75253",
  "2026安踏冠军腾冲高黎贡超级山径赛": "https://mgucn.saihuitong.com/",
  "2026第七届四姑娘山云间花径越野跑暨越野黄金联赛中国系列赛总决赛": "https://www.utms.com.cn/event?id=785343",
  "深行·2026第二届越西大凉山超级越野跑": "https://www.utms.com.cn/event?id=850785",
  "2026凯乐石贡嘎100冰川极限挑战赛": "https://reg.zuicool.com/33836",
  "越野东海——2026舟山群岛穿越之旅暨黄金联赛": "https://zuicool.com/event/88921",
  "2026凯乐石松花湖东北100跑山赛": "https://moganshan.saihuitong.com/events?mid=74255",
  "2026云丘山越野赛 by UTMB": "https://mount-yun.utmb.world/",
  "2026厦门（同安）越野赛 by UTMB": "https://xiamen.utmb.world/zh-Hans",
  "Ultra-Trail Shudao by UTMB（大蜀道100越野赛）": "https://shudao.utmb.world/zh-Hans",
  "2026司马台100长城越野赛": "https://zuicool.com/event/95428",
  "漓江越野跑": "https://zuicool.com/event/14689",
  "2026从化一百越野赛": "https://reg.zuicool.com/54950",
  "2026莫干山越野赛 by UTMB": "https://mogan.utmb.world/zh-Hans/",
  "2026京东大境门古长城越野赛 by UTMB": "https://dajingmen.utmb.world/zh-Hans/",
  "ACG 2026崇礼168超级越野赛": "https://sport.luojiweiye.com/web/new_website/?website_id=9&id=522",
  "2026中国移动老牛湾黄河大峡谷100公里越野赛": "https://lnwyys.xempower.cn/",
  "2026北京大学山地越野赛暨首届高校邀请赛": "https://pku-ultra-running.com/",
  "2026凯乐石莫干山跑山赛": "https://zuicool.com/event/89494",
  "2026奥尼捷·衢州·灵鹫山168古道越野赛": "https://zuicool.com/event/49464",
  "柴古唐斯·括苍山越野赛": "https://tsaigu.com/",
  "2026宁海越野挑战赛": "https://ninghai100.com/",
  "户外特工·2026第十届武功山越野赛": "https://zuicool.com/event/14342",
  "澜跑·2026巴松措超级越野赛": "https://zuicool.com/event/28732",
  "2026「玲珑100」·酷爱临安中秋奔月越野赛": "https://zuicool.com/event/40614",
  "2026金山岭长城越野赛·黄金联赛世界系列赛": "https://zuicool.com/event/47245",
  "2026中国山地越野挑战赛（石城站）暨红石100石城温泉越野赛": "https://zuicool.com/events?type=trail-run",
  "2026中岳嵩山越野赛": "https://zuicool.com/events?type=trail-run",
  "2026中岳嵩山越野赛（秋季）": "https://zuicool.com/events?type=trail-run",
  "2026蚝运乳山越野挑战赛": "https://zuicool.com/events?type=trail-run",
  "诺诗兰·2026神仙居越野挑战赛": "https://zuicool.com/events?type=trail-run",
  "黄山西宏秋季越野赛": "https://zuicool.com/events?type=trail-run",
  "2026澜跑无锡宜兴阳羡100越野": "https://zuicool.com/events?type=trail-run",
  "张三丰故里·邵武古道越野赛": "https://zuicool.com/events?type=trail-run",
  "2026亚太越野跑锦标赛": "https://zuicool.com/events?type=trail-run",
  "2026 FUGA深圳100跑山赛": "https://www.letoursport.com/events?mid=71522",
};

const lines = html.split('\n');
let updated = 0;
const outLines = lines.map(line => {
  if (!/^\s*\{ name:/.test(line)) return line;
  const nameMatch = line.match(/name: \"([^\"]+)\"/);
  if (!nameMatch) return line;
  const name = nameMatch[1];
  const link = links[name];
  if (!link) return line;

  let newLine;
  if (/link:/.test(line)) {
    // 已有 link，替换
    newLine = line.replace(/link: \"[^\"]*\"/, `link: "${link}"`);
  } else {
    // 无 link：在 status 字段之后、行尾 } 之前插入
    // 处理行尾是否有逗号
    const m = line.match(/^(.*)(\}),?\s*$/);
    if (m) {
      newLine = m[1] + ', link: "' + link + '" ' + m[2] + (m[0].trimEnd().endsWith(',') ? ',' : '');
    } else {
      return line;
    }
  }
  updated++;
  return newLine;
});

html = outLines.join('\n');
fs.writeFileSync(file, html, 'utf-8');
console.log('更新/添加了 ' + updated + ' 场赛事的链接');

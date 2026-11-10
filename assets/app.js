const FKEY = "jp-snow-favs";
const FIELD_KEY = "jp-snow-cards";
const FIELD_DEFS = [
  ["depth", "積雪"],
  ["d24", "24 小時新雪"],
  ["d48", "48 小時新雪"],
  ["temp", "氣溫"],
  ["forecast", "未來 3 日預報"],
  ["size", "雪道規模"],
  ["price", "一日券價格"],
];
const SORTS = new Set(["depth", "d24", "d48", "fc3", "name", "size", "price_asc", "price_desc"]);
const WEEK = ["日", "一", "二", "三", "四", "五", "六"];

const state = { q: "", region: "all", sort: "depth", id: null };
let resorts = [];
let cond = {};
let updated = "";
let obsTime = "";
let regions = [];
const favs = loadFavs();
let fields = loadFields();

const qInput = document.querySelector("#q");
const sortSel = document.querySelector("#sort");
const regionBox = document.querySelector("#regions");
const listEl = document.querySelector("#list");
const detailEl = document.querySelector("#detail");
const countEl = document.querySelector("#count");
const seasonEl = document.querySelector("#season");
const colophon = document.querySelector("#colophon");

qInput.addEventListener("input", () => {
  state.q = qInput.value;
  writeHash(true);
});
sortSel.addEventListener("change", () => {
  state.sort = sortSel.value;
  writeHash(false);
});
window.addEventListener("hashchange", applyHash);

function loadFavs() {
  try {
    const raw = JSON.parse(localStorage.getItem(FKEY) || "[]");
    return new Set(Array.isArray(raw) ? raw : []);
  } catch {
    return new Set();
  }
}
function saveFavs() {
  localStorage.setItem(FKEY, JSON.stringify([...favs]));
}
function defaultFields() {
  return Object.fromEntries(FIELD_DEFS.map(([id]) => [id, true]));
}
function loadFields() {
  const base = defaultFields();
  try {
    const raw = JSON.parse(localStorage.getItem(FIELD_KEY) || "null");
    if (!raw || typeof raw !== "object") return base;
    for (const [id] of FIELD_DEFS) {
      if (typeof raw[id] === "boolean") base[id] = raw[id];
    }
  } catch {
    return base;
  }
  return base;
}
function saveFields() {
  localStorage.setItem(FIELD_KEY, JSON.stringify(fields));
}
function showField(id) {
  return fields[id] !== false;
}

function fold(value) {
  return (value || "")
    .normalize("NFKC")
    .toLowerCase()
    .replace(/[\u30a1-\u30f6]/g, (ch) => String.fromCharCode(ch.charCodeAt(0) - 0x60))
    .replace(/[\s\u3000・･·\-.．,，/／_＿]+/g, "");
}

function tokyoParts() {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "numeric",
    day: "numeric",
  }).formatToParts(new Date());
  const get = (type) => Number(parts.find((part) => part.type === type).value);
  return { y: get("year"), m: get("month"), d: get("day") };
}

function seasonCopy() {
  const { m, d } = tokyoParts();
  if (m >= 5 && m <= 10) {
    return ["非雪季", "目前不是雪季，多數雪場沒有營業。下面多半是模式估計，很多地方會接近 0。"];
  }
  if (m === 11 || (m === 12 && d < 15)) {
    return ["雪季還沒到", "多數雪場要到 12 月中旬才開放，北海道有些 11 月下旬就會開。下面是積雪和降雪預報，不代表已經在營業。"];
  }
  if (m === 4) {
    return ["雪季尾聲", "不少雪場已經結束營業。數字是積雪和預報，不代表還開著。"];
  }
  return null;
}

function cm(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  const n = Math.round(Number(value) * 10) / 10;
  if (Object.is(n, -0) || n === 0) return "0";
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}
function tempText(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  const n = Math.round(Number(value) * 10) / 10;
  if (n === 0) return "0°";
  const body = Number.isInteger(n) ? String(n) : n.toFixed(1);
  return body + "°";
}
function kindText(kind) {
  return kind === "obs" ? "實測" : "估計";
}
function wxText(code) {
  if (code == null) return "";
  if (code === 0) return "晴";
  if (code <= 3) return "多雲";
  if (code <= 49) return "霧";
  if (code <= 67) return "雨";
  if (code <= 77) return "雪";
  if (code <= 82) return "陣雨";
  if (code <= 86) return "陣雪";
  return "雷雨";
}
function dayLabel(iso, today) {
  if (iso === today) return "今天";
  const [y, m, d] = iso.split("-").map(Number);
  const wd = new Date(y, m - 1, d).getDay();
  return `${m}/${d} 週${WEEK[wd]}`;
}
function formatStamp(iso) {
  if (!iso) return "";
  const [date, time] = iso.split("T");
  if (!date) return iso;
  const [y, m, d] = date.split("-");
  const hm = (time || "").slice(0, 5);
  return `${y}/${m}/${d} ${hm}（日本時間）`;
}

function readHash() {
  const raw = (location.hash || "#/").replace(/^#/, "");
  const qIdx = raw.indexOf("?");
  const path = qIdx >= 0 ? raw.slice(0, qIdx) : raw;
  const params = new URLSearchParams(qIdx >= 0 ? raw.slice(qIdx + 1) : "");
  const match = path.match(/^\/r\/([^/]+)$/);
  state.id = match ? decodeURIComponent(match[1]) : null;
  state.q = params.get("q") || "";
  state.region = params.get("region") || "all";
  state.sort = params.get("sort") || "depth";
  if (!SORTS.has(state.sort)) state.sort = "depth";
}
function writeHash(replace) {
  const params = new URLSearchParams();
  if (state.q) params.set("q", state.q);
  if (state.region && state.region !== "all") params.set("region", state.region);
  if (state.sort && state.sort !== "depth") params.set("sort", state.sort);
  const qs = params.toString();
  const path = state.id ? `/r/${encodeURIComponent(state.id)}` : "/";
  const next = "#" + path + (qs ? `?${qs}` : "");
  if (location.hash === next || (next === "#/" && (location.hash === "" || location.hash === "#/"))) {
    render();
    return;
  }
  if (replace) location.replace(next);
  else location.hash = next;
}
function applyHash() {
  readHash();
  syncControls();
  render();
}
function syncControls() {
  if (document.activeElement !== qInput && qInput.value !== state.q) qInput.value = state.q;
  if (sortSel.value !== state.sort) sortSel.value = state.sort;
  for (const button of regionBox.querySelectorAll("button")) {
    button.setAttribute("aria-selected", button.dataset.region === state.region ? "true" : "false");
  }
}

function regionName(id) {
  return regions.find((item) => item.id === id)?.zh || "";
}
function matches(resort) {
  if (state.region !== "all" && resort.region !== state.region) return false;
  const q = fold(state.q);
  if (!q) return true;
  return resort._q.includes(q);
}
function metric(resort, key) {
  const row = cond[resort.id] || {};
  if (key === "name") return resort.zh;
  const value = row[key];
  return typeof value === "number" ? value : -1;
}
function sizeKm(resort) {
  const km = resort.size && resort.size.piste_km;
  return typeof km === "number" ? km : null;
}
function priceYen(resort) {
  const yen = resort.ticket && resort.ticket.jpy;
  return typeof yen === "number" ? yen : null;
}
function bySort(a, b) {
  const name = a.zh.localeCompare(b.zh, "zh-Hant");
  if (state.sort === "name") return name;
  if (state.sort === "size" || state.sort === "price_asc" || state.sort === "price_desc") {
    const av = state.sort === "size" ? sizeKm(a) : priceYen(a);
    const bv = state.sort === "size" ? sizeKm(b) : priceYen(b);
    if (av == null && bv == null) return name;
    if (av == null) return 1;
    if (bv == null) return -1;
    const sign = state.sort === "price_asc" ? 1 : -1;
    return (av - bv) * sign || name;
  }
  return metric(b, state.sort) - metric(a, state.sort) || name;
}
function yenText(value) {
  return "¥" + Number(value).toLocaleString("zh-Hant");
}
function sizeLine(resort) {
  const size = resort.size;
  if (!size || size.piste_km == null) return "未知";
  const km = Number.isInteger(size.piste_km) ? String(size.piste_km) : String(size.piste_km);
  const bits = [`${km} km`];
  if (size.courses) bits.push(`${size.courses} 條`);
  if (size.lifts) bits.push(`纜車 ${size.lifts}`);
  return bits.join(" · ");
}
function priceLine(resort) {
  const ticket = resort.ticket;
  if (!ticket || ticket.jpy == null) return "未知";
  return `${yenText(ticket.jpy)}（${ticket.season}）`;
}

function card(resort) {
  const row = cond[resort.id] || {};
  const article = document.createElement("article");
  article.className = "card" + (resort.id === state.id ? " active" : "");
  article.dataset.id = resort.id;
  const fav = document.createElement("button");
  fav.type = "button";
  fav.className = "fav" + (favs.has(resort.id) ? " on" : "");
  fav.textContent = favs.has(resort.id) ? "★" : "☆";
  fav.setAttribute("aria-pressed", favs.has(resort.id) ? "true" : "false");
  fav.setAttribute("aria-label", (favs.has(resort.id) ? "取消收藏 " : "收藏 ") + resort.zh);
  fav.addEventListener("click", () => {
    if (favs.has(resort.id)) favs.delete(resort.id);
    else favs.add(resort.id);
    saveFavs();
    render();
  });
  const link = document.createElement("a");
  link.className = "main";
  link.href = hrefFor({ ...state, id: resort.id });
  const title = document.createElement("h2");
  title.textContent = resort.zh;
  const sub = document.createElement("p");
  sub.className = "sub";
  sub.textContent = [resort.pref, resort.ja].filter(Boolean).join(" · ");
  link.append(title, sub);
  const stats = document.createElement("div");
  stats.className = "stats";
  if (showField("depth")) stats.append(stat(cm(row.depth), "cm", `積雪 · ${kindText(row.depth_kind || "est")}`, row.depth));
  if (showField("d24")) stats.append(stat(cm(row.d24), "cm", row.d24_kind === "obs" ? "24 小時 · 實測" : "24 小時", row.d24, true));
  if (showField("temp")) stats.append(stat(tempText(row.temp), "", row.temp_kind === "obs" ? "氣溫 · 實測" : "氣溫", row.temp));
  if (stats.childElementCount) link.append(stats);
  const extraBits = [];
  if (showField("d48")) extraBits.push(`48 小時 ${cm(row.d48)} cm`);
  if (showField("forecast")) extraBits.push(`未來 3 日 ${cm(row.fc3)} cm`);
  if (extraBits.length) {
    const extra = document.createElement("p");
    extra.className = "extra";
    extra.textContent = extraBits.join(" · ");
    link.append(extra);
  }
  if (showField("size")) link.append(metaLine("雪道", sizeLine(resort)));
  if (showField("price")) link.append(metaLine("一日券", priceLine(resort)));
  article.append(link, fav);
  return article;
}
function metaLine(label, value) {
  const p = document.createElement("p");
  p.className = "meta";
  const strong = document.createElement("b");
  strong.textContent = label + " ";
  p.append(strong, document.createTextNode(value));
  return p;
}
function stat(value, unit, label, raw, hotSnow) {
  const node = document.createElement("div");
  const hot = hotSnow && Number(raw) >= 5;
  const zero = Number(raw) === 0;
  node.className = "stat" + (hot ? " hot" : "") + (zero ? " zero" : "");
  const strong = document.createElement("b");
  strong.textContent = unit ? `${value} ${unit}` : value;
  const span = document.createElement("span");
  span.textContent = label;
  node.append(strong, span);
  return node;
}

function hrefFor(next) {
  const params = new URLSearchParams();
  if (next.q) params.set("q", next.q);
  if (next.region && next.region !== "all") params.set("region", next.region);
  if (next.sort && next.sort !== "depth") params.set("sort", next.sort);
  const qs = params.toString();
  const path = next.id ? `/r/${encodeURIComponent(next.id)}` : "/";
  return "#" + path + (qs ? `?${qs}` : "");
}

function renderList(visible) {
  listEl.replaceChildren();
  const favRows = visible.filter((resort) => favs.has(resort.id));
  const rest = visible.filter((resort) => !favs.has(resort.id));
  if (!visible.length) {
    const p = document.createElement("p");
    p.className = "empty";
    p.textContent = "找不到符合的雪場。換個關鍵字，或把地區改回全部。";
    listEl.append(p);
    return;
  }
  if (favRows.length) {
    const label = document.createElement("p");
    label.className = "group-label";
    label.textContent = "收藏";
    listEl.append(label);
    for (const resort of favRows) listEl.append(card(resort));
  }
  if (rest.length) {
    if (favRows.length) {
      const label = document.createElement("p");
      label.className = "group-label";
      label.textContent = "全部結果";
      listEl.append(label);
    }
    for (const resort of rest) listEl.append(card(resort));
  }
}

function renderDetail() {
  const resort = resorts.find((item) => item.id === state.id);
  const wide = window.matchMedia("(min-width: 960px)").matches;
  detailEl.classList.toggle("open", Boolean(resort) && !wide);
  detailEl.replaceChildren();
  if (!resort) {
    if (!wide) return;
    const box = document.createElement("div");
    box.className = "detail-empty";
    const p = document.createElement("p");
    p.textContent = "選一個雪場，看積雪、新雪和未來幾天的降雪。";
    const top = [...resorts].sort((a, b) => (cond[b.id]?.depth || 0) - (cond[a.id]?.depth || 0))[0];
    if (top) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = `看積雪最多的${top.zh}`;
      button.addEventListener("click", () => {
        state.id = top.id;
        writeHash(false);
      });
      box.append(p, button);
    } else {
      box.append(p);
    }
    detailEl.append(box);
    document.title = "日本雪場｜積雪與降雪預報";
    return;
  }

  const row = cond[resort.id] || {};
  const today = (row.fc && row.fc[0] && row.fc[0][0]) || "";
  const wrap = document.createElement("article");
  wrap.className = "detail";
  const back = document.createElement("button");
  back.type = "button";
  back.className = "back";
  back.textContent = "← 返回列表";
  back.addEventListener("click", () => {
    state.id = null;
    writeHash(false);
  });

  const h1 = document.createElement("h1");
  h1.textContent = resort.zh;
  const names = document.createElement("p");
  names.className = "names";
  const region = regionName(resort.region);
  const place = region && region !== resort.pref ? `${resort.pref} · ${region}` : resort.pref;
  names.textContent = [resort.ja, resort.en, place].filter(Boolean).join(" · ");

  const hero = document.createElement("div");
  hero.className = "hero";
  const depth = document.createElement("div");
  depth.className = "depth";
  depth.append(document.createTextNode(cm(row.depth)));
  const unit = document.createElement("small");
  unit.textContent = "cm";
  depth.append(unit);
  const badge = document.createElement("span");
  badge.className = "kind " + (row.depth_kind === "obs" ? "obs" : "est");
  badge.textContent = kindText(row.depth_kind || "est");
  const explain = document.createElement("p");
  explain.className = "explain";
  explain.textContent = depthExplain(row);
  hero.append(depth, badge, explain);

  const grid = document.createElement("div");
  grid.className = "grid";
  grid.append(
    cell(`${cm(row.d24)} cm`, `24 小時新雪 · ${kindText(row.d24_kind)}`),
    cell(`${cm(row.d48)} cm`, `48 小時新雪 · ${kindText(row.d48_kind)}`),
    cell(tempText(row.temp), `氣溫 · ${kindText(row.temp_kind)}`),
    cell(wxText(row.wx) || "—", "現在天氣")
  );

  wrap.append(back, h1, names, hero, grid, factsBox(resort));
  if (resort.note) {
    const note = document.createElement("p");
    note.className = "note";
    note.textContent = resort.note;
    wrap.append(note);
  }
  if (row.obs) wrap.append(obsBox(row));
  wrap.append(forecastBlock(row, today));

  const actions = document.createElement("div");
  actions.className = "actions";
  const fav = document.createElement("button");
  fav.type = "button";
  fav.textContent = favs.has(resort.id) ? "★ 已收藏" : "☆ 收藏";
  fav.addEventListener("click", () => {
    if (favs.has(resort.id)) favs.delete(resort.id);
    else favs.add(resort.id);
    saveFavs();
    render();
  });
  const share = document.createElement("button");
  share.type = "button";
  share.textContent = "分享";
  share.addEventListener("click", () => shareResort(resort));
  actions.append(fav, share);
  const links = resort.links || {};
  if (links.status) actions.append(extLink(links.status, "纜車即時運行狀態"));
  if (links.ticket) actions.append(extLink(links.ticket, "纜車票價"));
  if (resort.web) {
    const site = document.createElement("a");
    site.href = resort.web;
    site.target = "_blank";
    site.rel = "noopener";
    site.textContent = "官方網站";
    actions.append(site);
  }
  const map = document.createElement("a");
  map.href = `https://www.openstreetmap.org/?mlat=${resort.lat}&mlon=${resort.lon}#map=13/${resort.lat}/${resort.lon}`;
  map.target = "_blank";
  map.rel = "noopener";
  map.textContent = "在地圖上打開";
  actions.append(map);
  wrap.append(actions);

  const foot = document.createElement("p");
  foot.className = "extra";
  foot.textContent = updated ? `雪況更新於 ${formatStamp(updated)}` : "";
  wrap.append(foot);
  detailEl.append(wrap);
  if (!wide) detailEl.scrollTop = 0;
  document.title = `${resort.zh}｜日本雪場`;
}

function factsBox(resort) {
  const box = document.createElement("div");
  box.className = "obs-box";
  const h2 = document.createElement("h2");
  h2.textContent = "雪道與一日券";
  const size = document.createElement("p");
  size.textContent = `雪道規模：${sizeLine(resort)}`;
  const sizeNote = document.createElement("p");
  sizeNote.className = "extra";
  sizeNote.textContent = resort.size
    ? `${resort.size.note} 統計日 ${resort.size.as_of}。`
    : "OpenStreetMap 還沒畫到足夠的雪道，所以是未知。";
  const price = document.createElement("p");
  price.textContent = resort.ticket
    ? `一日券：${yenText(resort.ticket.jpy)}，${resort.ticket.season}。`
    : "一日券：未知。";
  box.append(h2, size, sizeNote, price);
  if (resort.ticket) {
    const note = document.createElement("p");
    note.className = "extra";
    const bits = [`查閱日 ${resort.ticket.as_of}`];
    if (resort.ticket.note) bits.push(resort.ticket.note);
    note.append(document.createTextNode(bits.join("。") + "。來源："));
    note.append(extLink(resort.ticket.source, "官網頁面"));
    box.append(note);
  }
  return box;
}
function extLink(href, text) {
  const a = document.createElement("a");
  a.href = href;
  a.target = "_blank";
  a.rel = "noopener";
  a.textContent = text;
  return a;
}
function cell(value, label) {
  const node = document.createElement("div");
  node.className = "cell";
  const strong = document.createElement("b");
  strong.textContent = value;
  const span = document.createElement("span");
  span.textContent = label;
  node.append(strong, span);
  return node;
}
function depthExplain(row) {
  const ele = row.ele != null ? `格點標高約 ${row.ele} 公尺。` : "";
  if (row.depth_kind === "obs" && row.obs) {
    return `氣象廳測站「${row.obs.zh}」的積雪實測，直線距離 ${row.obs.dist} 公里、測站標高 ${row.obs.ele} 公尺。${ele}`;
  }
  let text = `Open-Meteo 天氣模式的估計，不是實測。${ele}`;
  if (row.model_depth != null && row.depth_kind === "obs" && row.model_depth !== row.depth) {
    text += `同一地點的模式估計是 ${row.model_depth} cm。`;
  }
  return text;
}
function obsBox(row) {
  const obs = row.obs;
  const box = document.createElement("div");
  box.className = "obs-box";
  const h2 = document.createElement("h2");
  h2.textContent = "鄰近的氣象廳測站";
  const p = document.createElement("p");
  const bits = [`${obs.zh}（${obs.ja}）`, `直線 ${obs.dist} 公里`, `標高 ${obs.ele} 公尺`];
  let body = bits.join("，") + "。";
  if (obs.depth == null) {
    body += "這個時段沒有積雪實測。積雪觀測通常要到雪季才會恢復，所以現在的積雪用模式估計。";
  } else if (row.depth_kind !== "obs") {
    body += `測站積雪 ${obs.depth} cm。距離或標高差比較大，列表上的數字仍用模式估計。`;
  } else {
    body += `積雪實測 ${obs.depth} cm。`;
  }
  if (obs.d24 != null) body += ` 24 小時新雪實測 ${cm(obs.d24)} cm。`;
  if (obs.temp != null) body += ` 測站氣溫 ${tempText(obs.temp)}，那是測站高度，不一定等於雪場。`;
  if (obs.time) body += ` 觀測時間 ${formatStamp(obs.time)}。`;
  p.textContent = body;
  box.append(h2, p);
  return box;
}
function forecastBlock(row, today) {
  const section = document.createElement("section");
  section.className = "forecast";
  const h2 = document.createElement("h2");
  h2.textContent = "未來幾天的降雪（估計）";
  const days = document.createElement("div");
  days.className = "days";
  const fc = row.fc || [];
  const max = Math.max(5, ...fc.map((day) => day[1] || 0));
  for (const day of fc) {
    const node = document.createElement("div");
    node.className = "day";
    const bar = document.createElement("div");
    bar.className = "bar" + ((day[1] || 0) > 0 ? " on" : "");
    bar.style.height = Math.max(4, Math.round(((day[1] || 0) / max) * 64)) + "px";
    const strong = document.createElement("strong");
    strong.textContent = `${cm(day[1])} cm`;
    const when = document.createElement("em");
    when.textContent = dayLabel(day[0], today);
    const range = document.createElement("small");
    range.textContent = `${tempText(day[3]).replace("°", "")}–${tempText(day[2])} ${wxText(day[4])}`.trim();
    node.append(bar, strong, when, range);
    days.append(node);
  }
  if (!fc.length) {
    const p = document.createElement("p");
    p.textContent = "這幾天的預報暫時沒有。";
    section.append(h2, p);
    return section;
  }
  section.append(h2, days);
  return section;
}

async function shareResort(resort) {
  const url = new URL(hrefFor(state), location.href).href;
  const payload = { title: `${resort.zh}｜日本雪場`, text: `${resort.zh}的積雪`, url };
  if (navigator.share) {
    try {
      await navigator.share(payload);
      return;
    } catch (error) {
      if (error && error.name === "AbortError") return;
    }
  }
  try {
    await navigator.clipboard.writeText(url);
  } catch {
    const box = document.createElement("textarea");
    box.value = url;
    document.body.append(box);
    box.select();
    document.execCommand("copy");
    box.remove();
  }
  toast("已複製連結");
}
let toastTimer = 0;
function toast(message) {
  let node = document.querySelector(".toast");
  if (!node) {
    node = document.createElement("div");
    node.className = "toast";
    document.body.append(node);
  }
  node.textContent = message;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.remove(), 1800);
}

function render() {
  const visible = resorts.filter(matches).sort(bySort);
  countEl.textContent = resorts.length ? `顯示 ${visible.length} 座` : "正在讀取雪況…";
  renderList(visible);
  renderDetail();
}

function renderChrome() {
  regionBox.replaceChildren();
  const all = document.createElement("button");
  all.type = "button";
  all.dataset.region = "all";
  all.textContent = "全部";
  all.setAttribute("role", "tab");
  regionBox.append(all);
  for (const region of regions) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.region = region.id;
    button.textContent = region.zh;
    button.setAttribute("role", "tab");
    regionBox.append(button);
  }
  regionBox.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    state.region = button.dataset.region;
    writeHash(false);
  });
  const season = seasonCopy();
  if (season) {
    seasonEl.hidden = false;
    seasonEl.replaceChildren();
    const strong = document.createElement("strong");
    strong.textContent = season[0];
    seasonEl.append(strong, document.createTextNode(season[1]));
  } else {
    seasonEl.hidden = true;
  }
  colophon.replaceChildren();
  const p1 = document.createElement("p");
  p1.textContent = updated ? `雪況更新於 ${formatStamp(updated)}。` : "";
  const p2 = document.createElement("p");
  p2.append(
    document.createTextNode("積雪若標示實測，是氣象廳 AMeDAS 鄰近測站的觀測，並依距離與標高篩過；其餘積雪、新雪和預報是 "),
    link("https://open-meteo.com/", "Open-Meteo"),
    document.createTextNode(" 天氣模式的估計（CC BY 4.0）。雪場位置 © "),
    link("https://www.openstreetmap.org/copyright", "OpenStreetMap"),
    document.createTextNode(" 貢獻者。雪道長度是同一份地圖裡 downhill 雪道的加總。一日券只收錄從雪場官網讀到的成人價，並寫上適用期間。測站資料來源："),
    link("https://www.jma.go.jp/bosai/amedas/", "氣象廳"),
    document.createTextNode("，內容有整理，不是原始畫面。這不是正式預報，出發前請再跟雪場確認。")
  );
  colophon.append(p1, p2);
}
function link(href, text) {
  const a = document.createElement("a");
  a.href = href;
  a.target = "_blank";
  a.rel = "noopener";
  a.textContent = text;
  return a;
}

async function main() {
  readHash();
  try {
    const [resortRes, condRes] = await Promise.all([
      fetch("data/resorts.json", { cache: "no-cache" }),
      fetch("data/conditions.json", { cache: "no-cache" }),
    ]);
    if (!resortRes.ok || !condRes.ok) throw new Error("bad status");
    const resortJson = await resortRes.json();
    const condJson = await condRes.json();
    regions = resortJson.regions || [];
    resorts = resortJson.resorts || [];
    cond = condJson.resorts || {};
    updated = condJson.updated || "";
    obsTime = condJson.obs_time || "";
    for (const resort of resorts) {
      const region = regionName(resort.region);
      resort._q = fold([resort.zh, resort.ja, resort.en, resort.pref, region, resort.roma, ...(resort.aliases || [])].join(" "));
    }
  } catch {
    countEl.textContent = "雪況暫時讀不到。";
    listEl.textContent = "請稍後再整理頁面。";
    return;
  }
  renderChrome();
  bindSettings();
  syncControls();
  render();
}

function bindSettings() {
  const panel = document.querySelector("#settings");
  const fieldsBox = document.querySelector("#settings-fields");
  const paint = () => {
    fieldsBox.replaceChildren();
    for (const [id, label] of FIELD_DEFS) {
      const row = document.createElement("label");
      row.className = "field";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.checked = showField(id);
      input.addEventListener("change", () => {
        fields[id] = input.checked;
        saveFields();
        render();
      });
      row.append(input, document.createTextNode(label));
      fieldsBox.append(row);
    }
  };
  paint();
  document.querySelector("#settings-open").addEventListener("click", () => {
    panel.hidden = false;
  });
  document.querySelector("#settings-close").addEventListener("click", () => {
    panel.hidden = true;
  });
  document.querySelector("#settings-reset").addEventListener("click", () => {
    fields = defaultFields();
    saveFields();
    paint();
    render();
  });
  panel.addEventListener("click", (event) => {
    if (event.target === panel) panel.hidden = true;
  });
}

main();

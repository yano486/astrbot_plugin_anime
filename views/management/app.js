const bridge = window.AstrBotPluginView;
const $ = (selector) => document.querySelector(selector);
const state = { items: [], targets: [], subscriptions: new Map(), sources: {} };

function currentSeason() {
  const now = new Date();
  const month = Math.floor((now.getMonth()) / 3) * 3 + 1;
  return `${now.getFullYear()}-${String(month).padStart(2, "0")}`;
}

function seasonOptions() {
  const select = $("#season");
  const current = currentSeason();
  const [year, month] = current.split("-").map(Number);
  const months = [1, 4, 7, 10];
  const index = months.indexOf(month);
  const prev = index === 0 ? `${year - 1}-10` : `${year}-${String(months[index - 1]).padStart(2, "0")}`;
  const next = index === 3 ? `${year + 1}-01` : `${year}-${String(months[index + 1]).padStart(2, "0")}`;
  [[prev, "上一季度"], [current, "本季度"], [next, "下一季度"]].forEach(([value, label]) => {
    const option = document.createElement("option"); option.value = value; option.textContent = `${label} · ${value}`; select.append(option);
  });
  select.value = current;
}

function safe(value = "") { return String(value).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c])); }

function firstTime(item) {
  if (!item.schedules?.length) return "时间待定";
  const s = item.schedules[0];
  const totalBeijingMinutes = s.hour * 60 + s.minute - 60;
  const normalized = ((totalBeijingMinutes % (24 * 60)) + (24 * 60)) % (24 * 60);
  const dayShift = Math.floor(totalBeijingMinutes / (24 * 60));
  const bjHour = Math.floor(normalized / 60);
  const bjMinute = normalized % 60;
  const day = ((s.weekday - 1 + dayShift) % 7) + 1;
  const japanClock = String(s.raw_time || `${s.hour}:${String(s.minute).padStart(2,"0")}`).replace(/~/g, "").trim();
  return `日本 周${"一二三四五六日"[s.weekday - 1]} ${japanClock} → 北京 周${"一二三四五六日"[day - 1]} ${String(bjHour).padStart(2,"0")}:${String(bjMinute).padStart(2,"0")}`;
}

function sourceChoices() {
  const select = $("#source");
  const old = select.value;
  select.innerHTML = '<option value="">所有来源</option>';
  [...new Set(state.items.flatMap(item => item.sources || []))].sort().forEach(source => {
    const option = document.createElement("option"); option.value = source; option.textContent = source; select.append(option);
  });
  select.value = old;
}

function renderSources() {
  const container = $("#source-status"); container.replaceChildren();
  Object.entries(state.sources || {}).forEach(([name, result]) => {
    const chip = document.createElement("span");
    chip.className = `source-chip ${result.status === "error" ? "error" : ""}`;
    chip.textContent = `${name} ${result.status === "error" ? "失效" : `${result.count || 0} 条`}`;
    chip.title = result.error || result.source_url || ""; container.append(chip);
  });
}

function render() {
  const q = $("#query").value.trim().toLowerCase();
  const region = $("#region").value, type = $("#type").value, weekday = Number($("#weekday").value), role = $("#role").value, source = $("#source").value;
  const items = state.items.filter(item => {
    if (region === "jp" && item.region !== "jp") return false;
    if (region === "mixed" && item.region !== "mixed") return false;
    if (region === "unknown" && !["unknown", "mixed"].includes(item.region)) return false;
    if (type && item.item_type !== type) return false;
    if (weekday && !(item.schedules || []).some(s => s.weekday === weekday)) return false;
    if (role && item.season_role !== role) return false;
    if (source && !(item.sources || []).includes(source)) return false;
    if (q && !`${item.title} ${item.title_cn} ${(item.aliases || []).join(" ")} ${(item.genres || []).join(" ")}`.toLowerCase().includes(q)) return false;
    return true;
  });
  $("#count").textContent = `${items.length} 部`;
  const catalog = $("#catalog"); catalog.replaceChildren();
  if (!items.length) { catalog.innerHTML = '<div class="empty">当前筛选没有作品。可以检查来源状态或尝试放宽筛选条件。</div>'; return; }
  items.forEach(item => {
    const selected = state.subscriptions.get(item.key) || { enabled: false, lead_minutes: 0, on_time: true };
    const card = document.createElement("article"); card.className = `anime-card ${selected.enabled ? "subscribed" : ""}`;
    const cover = item.cover_url ? `<img class="cover" loading="lazy" src="${safe(item.cover_url)}" alt="">` : '<div class="cover cover-empty">番</div>';
    const role = item.season_role === "new" ? '<i class="badge badge-new">新作</i>' : item.season_role === "continuing" ? '<i class="badge badge-cont">续播</i>' : "";
    const conflict = item.data_status === "conflict" ? '<div class="meta warning">来源时间冲突，提醒已暂停</div>' : item.data_status === "time_unknown" ? '<div class="meta warning">暂无可靠播出时间</div>' : "";
    card.innerHTML = `${cover}<div class="card-main"><div class="card-top">${role}<i class="badge badge-cont">${safe(item.item_type || "类型待确认")}</i><i class="badge">${safe(item.region === "jp" ? "日本" : item.region === "mixed" ? "地区混合" : "地区待确认")}</i></div><h3>${safe(item.title_cn || item.title)}</h3><div class="original">${safe(item.title)}</div><div class="air-time">${safe(firstTime(item))}</div><div class="meta">${safe((item.genres || []).slice(0,4).join(" · "))}</div><div class="meta">来源：${safe((item.sources || []).join("、") || "尚无排期来源")}</div>${conflict}<div class="reminder-controls"><label>提前</label><input class="lead" type="number" min="0" max="1440" step="5" value="${Number(selected.lead_minutes) || 0}"><span>分钟</span><label><input class="on-time" type="checkbox" ${selected.on_time ? "checked" : ""}> 准点提醒</label></div></div><input class="card-check" type="checkbox" ${selected.enabled ? "checked" : ""} aria-label="订阅 ${safe(item.title_cn || item.title)}">`;
    const checkbox = card.querySelector(".card-check");
    checkbox.addEventListener("change", () => { const old = state.subscriptions.get(item.key) || {}; state.subscriptions.set(item.key, {...old, enabled: checkbox.checked, lead_minutes: Number(card.querySelector(".lead").value) || 0, on_time: card.querySelector(".on-time").checked}); card.classList.toggle("subscribed", checkbox.checked); });
    card.querySelector(".lead").addEventListener("change", e => { const old = state.subscriptions.get(item.key) || {}; state.subscriptions.set(item.key, {...old, lead_minutes: Math.max(0, Math.min(1440, Number(e.target.value) || 0)), enabled: checkbox.checked, on_time: card.querySelector(".on-time").checked}); });
    card.querySelector(".on-time").addEventListener("change", e => { const old = state.subscriptions.get(item.key) || {}; state.subscriptions.set(item.key, {...old, on_time: e.target.checked, enabled: checkbox.checked, lead_minutes: Number(card.querySelector(".lead").value) || 0}); });
    catalog.append(card);
  });
}

async function loadItems() {
  $("#refresh-status").textContent = "正在读取作品目录…";
  const result = await bridge.apiGet("items", { season: $("#season").value });
  state.items = result.items || []; sourceChoices(); render();
  $("#refresh-status").textContent = `已载入 ${result.count || 0} 部 · ${result.updated_at || "尚未刷新"}`;
}

async function loadStatus() {
  const data = await bridge.apiGet("status");
  state.sources = data.sources || {}; renderSources();
  if (data.updated_at) $("#refresh-status").textContent = `数据更新于 ${new Date(data.updated_at).toLocaleString()}`;
}

async function loadTargets() {
  const data = await bridge.apiGet("targets"); state.targets = data.targets || [];
  const select = $("#target"); select.innerHTML = '<option value="">选择已绑定的群或会话</option>';
  state.targets.filter(target => target.enabled).forEach(target => { const option = document.createElement("option"); option.value = target.target_id; option.textContent = target.display_name || target.target_id; select.append(option); });
  const list = $("#whitelist-list"); list.replaceChildren();
  state.targets.filter(target => target.enabled).forEach(target => {
    const label = document.createElement("label"); label.className = "whitelist-target";
    label.innerHTML = `<input type="checkbox" data-target="${safe(target.target_id)}" ${target.whitelisted ? "checked" : ""}> ${safe(target.display_name || target.target_id)}${target.subscribed ? " · 自动推送已启用" : ""}`;
    list.append(label);
  });
}

async function loadSubscriptions() {
  const targetId = $("#target").value; if (!targetId) { $("#save-status").textContent = "请先选择推送目标"; return; }
  const data = await bridge.apiGet("subscriptions", { target_id: targetId });
  state.subscriptions = new Map((data.subscriptions || []).map(sub => [sub.anime_key, sub])); render();
  $("#save-status").textContent = "已读取该目标订阅";
}

async function saveSubscriptions() {
  const targetId = $("#target").value; if (!targetId) { $("#save-status").textContent = "请先选择推送目标"; return; }
  const subscriptions = [...state.subscriptions.entries()].filter(([,sub]) => sub.enabled).map(([anime_key,sub]) => ({anime_key, enabled: true, lead_minutes: Number(sub.lead_minutes) || 0, on_time: Boolean(sub.on_time)}));
  const result = await bridge.apiPost("subscriptions", {target_id: targetId, subscriptions});
  await loadTargets();
  $("#save-status").textContent = `已保存 ${result.saved} 部订阅`;
}

async function saveWhitelist() {
  const targets = [...document.querySelectorAll(".whitelist-target input")].map(input => ({target_id: input.dataset.target, allowed: input.checked}));
  const result = await bridge.apiPost("targets/whitelist", {targets});
  await loadTargets();
  $("#save-status").textContent = `白名单已更新 ${result.updated} 个目标`;
}

async function refreshAll() {
  $("#refresh").disabled = true; $("#refresh-status").textContent = "正在刷新多个来源…";
  try { await bridge.apiPost("refresh", {season: $("#season").value}); await loadStatus(); await loadItems(); $("#save-status").textContent = "刷新完成"; }
  catch (error) { $("#refresh-status").textContent = `刷新失败：${error.message}`; }
  finally { $("#refresh").disabled = false; }
}

async function init() {
  try {
    await bridge.ready(); seasonOptions();
    for (const id of ["query", "region", "type", "weekday", "role", "source"]) $("#" + id).addEventListener(id === "query" ? "input" : "change", render);
    $("#season").addEventListener("change", loadItems);
    $("#refresh").addEventListener("click", refreshAll);
    $("#load-subs").addEventListener("click", loadSubscriptions);
    $("#save-subs").addEventListener("click", saveSubscriptions);
    $("#save-whitelist").addEventListener("click", saveWhitelist);
    await Promise.all([loadStatus(), loadTargets(), loadItems()]);
  } catch (error) { $("#catalog").innerHTML = `<div class="error">管理页面载入失败：${safe(error.message)}</div>`; }
}

init();

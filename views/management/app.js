const bridge = window.AstrBotPluginView;
const $ = (selector) => document.querySelector(selector);
const state = { items: [], targets: [], subscriptions: new Map(), subscriptionsTarget: "", sources: {}, movieSources: {} };

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

function safeHttpUrl(value = "") {
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) ? safe(url.href) : "";
  } catch { return ""; }
}

function isMovie(item) { return ["movie", "ova"].includes(item.item_type); }

function movieReleaseValue(item) {
  if (item.release_at) return item.release_at.slice(0, 16);
  return item.release_date ? `${item.release_date.slice(0, 10)}T00:00` : "";
}

function movieYears() {
  const years = new Set(state.items.filter(isMovie).map(item => item.release_date?.slice(0, 4)).filter(Boolean));
  const currentYear = new Date().getFullYear();
  years.add(String(currentYear));
  if (new Date().getMonth() === 11) years.add(String(currentYear + 1));
  const select = $("#movie-year");
  const old = select.value || String(currentYear);
  select.innerHTML = '<option value="all">全部年份</option>';
  [...years].sort().forEach(year => {
    const option = document.createElement("option"); option.value = year; option.textContent = `${year} 年上映`; select.append(option);
  });
  select.value = years.has(old) ? old : String(currentYear);
}

function firstTime(item) {
  if (!item.schedules?.length) return "时间待定";
  const s = item.schedules[0];
  const totalBeijingMinutes = s.hour * 60 + s.minute - 60;
  const normalized = ((totalBeijingMinutes % (24 * 60)) + (24 * 60)) % (24 * 60);
  const dayShift = Math.floor(totalBeijingMinutes / (24 * 60));
  const bjHour = Math.floor(normalized / 60);
  const bjMinute = normalized % 60;
  const day = (((s.weekday - 1 + dayShift) % 7) + 7) % 7 + 1;
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
  const sources = {...(state.sources || {})};
  Object.entries(state.movieSources || {}).forEach(([name, result]) => { sources[`剧场版/OVA · ${name}`] = result; });
  Object.entries(sources).forEach(([name, result]) => {
    const chip = document.createElement("span");
    chip.className = `source-chip ${result.status === "error" || result.error ? "error" : ""}`;
    chip.textContent = `${name} ${result.status === "error" ? "失效" : result.error ? "部分失败" : `${result.count || 0} 条`}`;
    chip.title = result.error || result.source_url || ""; container.append(chip);
  });
}

function render() {
  const q = $("#query").value.trim().toLowerCase();
  const region = $("#region").value, type = $("#type").value, weekday = Number($("#weekday").value), role = $("#role").value, source = $("#source").value, movieYear = $("#movie-year").value;
  const items = state.items.filter(item => {
    const movie = isMovie(item);
    if (region === "jp" && item.region !== "jp") return false;
    if (region === "mixed" && item.region !== "mixed") return false;
    if (region === "unknown" && !["unknown", "mixed"].includes(item.region)) return false;
    if (type && item.item_type !== type) return false;
    if (weekday && !movie && !(item.schedules || []).some(s => s.weekday === weekday)) return false;
    if (role && !movie && item.season_role !== role) return false;
    if (movieYear !== "all" && movie && item.release_date?.slice(0, 4) !== movieYear) return false;
    if (source && !(item.sources || []).includes(source)) return false;
    if (q && !`${item.title} ${item.title_cn} ${(item.aliases || []).join(" ")} ${(item.genres || []).join(" ")}`.toLowerCase().includes(q)) return false;
    return true;
  });
  $("#count").textContent = `${items.length} 部`;
  const catalog = $("#catalog"); catalog.replaceChildren();
  if (!items.length) { catalog.innerHTML = '<div class="empty">当前筛选没有作品。可以检查来源状态或尝试放宽筛选条件。</div>'; return; }
  items.forEach(item => {
    const movie = isMovie(item);
    const selected = state.subscriptions.get(item.key) || { enabled: false, lead_minutes: movie ? 30 : 0, on_time: !movie };
    const card = document.createElement("article"); card.className = `anime-card ${selected.enabled ? "subscribed" : ""}`;
    const imageUrl = safeHttpUrl(item.cover_url);
    const detailUrl = safeHttpUrl(item.detail_url || (item.bangumi_id ? `https://bgm.tv/subject/${item.bangumi_id}` : ""));
    const image = imageUrl ? `<img class="cover" loading="lazy" src="${imageUrl}" alt="">` : '<div class="cover cover-empty">番</div>';
    const cover = detailUrl ? `<a class="cover-link" href="${detailUrl}" target="_blank" rel="noopener noreferrer" aria-label="在 Bangumi 打开 ${safe(item.title_cn || item.title)}">${image}</a>` : image;
    const role = item.season_role === "new" ? '<i class="badge badge-new">新作</i>' : item.season_role === "continuing" ? '<i class="badge badge-cont">续播</i>' : "";
    const note = item.schedule_note ? `<div class="meta warning">${safe(item.schedule_note)}</div>` : item.data_status === "time_unknown" && !movie ? '<div class="meta warning">暂无可靠播出时间，暂不发送时间提醒</div>' : "";
    const timing = movie
      ? `<div class="movie-release"><label>上映时间（北京时间）</label><input class="release-at" type="datetime-local" value="${safe(movieReleaseValue(item))}"><small>自动提醒默认提前 30 分钟；来源仅有日期时以 00:00 为锚点，可在此补充具体时间。</small><div class="release-actions"><button class="button button-quiet save-release" type="button">保存上映时间</button><button class="button button-quiet reset-release" type="button">恢复来源日期</button></div></div>`
      : `<div class="reminder-controls"><label>提前</label><input class="lead" type="number" min="0" max="1440" step="5" value="${Number(selected.lead_minutes) || 0}"><span>分钟</span><label><input class="on-time" type="checkbox" ${selected.on_time ? "checked" : ""}> 准点提醒</label></div>`;
    const displayTime = movie ? `上映日期：${safe(item.release_date || "待确认")}` : safe(firstTime(item));
    card.innerHTML = `${cover}<div class="card-main"><div class="card-top">${role}<i class="badge badge-cont">${safe(item.item_type || "类型待确认")}</i><i class="badge">${safe(item.region === "jp" ? "日本" : item.region === "mixed" ? "地区混合" : "地区待确认")}</i></div><h3>${safe(item.title_cn || item.title)}</h3><div class="original">${safe(item.title)}</div><div class="air-time">${displayTime}</div><div class="meta">${safe((item.genres || []).slice(0,4).join(" · "))}</div><div class="meta">来源：${safe((item.sources || []).join("、") || "尚无排期来源")}</div>${note}${timing}</div><input class="card-check" type="checkbox" ${selected.enabled ? "checked" : ""} aria-label="订阅 ${safe(item.title_cn || item.title)}">`;
    const checkbox = card.querySelector(".card-check");
    const updateSelected = () => {
      const old = state.subscriptions.get(item.key) || {};
      const lead = movie ? 30 : Number(card.querySelector(".lead").value) || 0;
      const onTime = movie ? false : card.querySelector(".on-time").checked;
      state.subscriptions.set(item.key, {...old, enabled: checkbox.checked, lead_minutes: lead, on_time: onTime});
      card.classList.toggle("subscribed", checkbox.checked);
    };
    checkbox.addEventListener("change", updateSelected);
    if (movie) {
      card.querySelector(".save-release").addEventListener("click", () => saveMovieRelease(item, card));
      card.querySelector(".reset-release").addEventListener("click", () => resetMovieRelease(item, card));
    } else {
      card.querySelector(".lead").addEventListener("change", e => { const old = state.subscriptions.get(item.key) || {}; state.subscriptions.set(item.key, {...old, lead_minutes: Math.max(0, Math.min(1440, Number(e.target.value) || 0)), enabled: checkbox.checked, on_time: card.querySelector(".on-time").checked}); });
      card.querySelector(".on-time").addEventListener("change", e => { const old = state.subscriptions.get(item.key) || {}; state.subscriptions.set(item.key, {...old, on_time: e.target.checked, enabled: checkbox.checked, lead_minutes: Number(card.querySelector(".lead").value) || 0}); });
    }
    card.addEventListener("click", event => {
      if (event.target.closest("a, input, button, select, label")) return;
      checkbox.checked = !checkbox.checked;
      updateSelected();
    });
    catalog.append(card);
  });
}

function showView(view) {
  const catalog = view === "catalog";
  $("#catalog-view").hidden = !catalog;
  $("#settings-view").hidden = catalog;
  $("#show-catalog").classList.toggle("active", catalog);
  $("#show-settings").classList.toggle("active", !catalog);
}

async function saveMovieRelease(item, card) {
  const input = card.querySelector(".release-at");
  try {
    const result = await bridge.apiPost("movie-release", {anime_key: item.key, release_at: input.value});
    item.release_at = result.release_at;
    card.querySelector(".save-release").textContent = "已保存";
  } catch (error) {
    card.querySelector(".save-release").textContent = `保存失败：${error.message}`;
  }
}

async function resetMovieRelease(item, card) {
  try {
    await bridge.apiPost("movie-release", {anime_key: item.key, release_at: ""});
    item.release_at = "";
    card.querySelector(".release-at").value = movieReleaseValue(item);
    card.querySelector(".reset-release").textContent = "已恢复";
  } catch (error) {
    card.querySelector(".reset-release").textContent = `恢复失败：${error.message}`;
  }
}

async function loadItems() {
  $("#refresh-status").textContent = "正在读取作品目录…";
  const result = await bridge.apiGet("items", { season: $("#season").value });
  state.items = result.items || []; movieYears(); sourceChoices(); render();
  $("#refresh-status").textContent = `已载入 ${result.count || 0} 部 · ${result.updated_at || "尚未刷新"}`;
}

async function loadStatus() {
  const data = await bridge.apiGet("status");
  state.sources = data.sources || {}; state.movieSources = data.movie_sources || {}; renderSources();
  $("#remote-webui-status").textContent = data.remote_webui_enabled
    ? `${data.remote_webui_url} · 已启动`
    : "未启动。请在 AstrBot 插件配置中启用远程 WebUI，并设置至少 12 个字符的访问口令。";
  if (data.updated_at) $("#refresh-status").textContent = `数据更新于 ${new Date(data.updated_at).toLocaleString()}`;
}

async function loadTargets() {
  const data = await bridge.apiGet("targets"); state.targets = data.targets || [];
  const select = $("#target"); const selectedTarget = select.value; select.innerHTML = '<option value="">选择已绑定的群或会话</option>';
  state.targets.filter(target => target.enabled).forEach(target => { const option = document.createElement("option"); option.value = target.target_id; option.textContent = target.display_name || target.target_id; select.append(option); });
  if (state.targets.some(target => target.enabled && target.target_id === selectedTarget)) select.value = selectedTarget;
  const testSelect = $("#test-target"); const oldTestTarget = testSelect.value;
  testSelect.innerHTML = '<option value="">选择推送目标</option>';
  state.targets.filter(target => target.enabled).forEach(target => { const option = document.createElement("option"); option.value = target.target_id; option.textContent = target.display_name || target.target_id; testSelect.append(option); });
  if (state.targets.some(target => target.enabled && target.target_id === oldTestTarget)) testSelect.value = oldTestTarget;
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
  if ($("#target").value !== targetId) return;
  state.subscriptionsTarget = targetId;
  state.subscriptions = new Map((data.subscriptions || []).map(sub => [sub.anime_key, sub])); render();
  $("#save-status").textContent = "已读取该目标订阅";
}

async function saveSubscriptions() {
  const targetId = $("#target").value; if (!targetId) { $("#save-status").textContent = "请先选择推送目标"; return; }
  if (state.subscriptionsTarget !== targetId) { $("#save-status").textContent = "请先读取当前目标订阅，避免覆盖其他群聊"; return; }
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

async function sendTestPush() {
  const targetId = $("#test-target").value;
  if (!targetId) { $("#test-push-status").textContent = "请先选择已绑定的推送目标。"; return; }
  $("#test-push").disabled = true;
  $("#test-push-status").textContent = "正在发送…";
  try {
    await bridge.apiPost("test-push", {target_id: targetId});
    $("#test-push-status").textContent = "测试消息已发送。";
  } catch (error) {
    $("#test-push-status").textContent = `发送失败：${error.message}`;
  } finally {
    $("#test-push").disabled = false;
  }
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
    for (const id of ["query", "region", "type", "weekday", "role", "movie-year", "source"]) $("#" + id).addEventListener(id === "query" ? "input" : "change", render);
    $("#season").addEventListener("change", loadItems);
    $("#refresh").addEventListener("click", refreshAll);
    $("#load-subs").addEventListener("click", loadSubscriptions);
    $("#save-subs").addEventListener("click", saveSubscriptions);
    $("#save-whitelist").addEventListener("click", saveWhitelist);
    $("#test-push").addEventListener("click", sendTestPush);
    $("#show-catalog").addEventListener("click", () => showView("catalog"));
    $("#show-settings").addEventListener("click", () => showView("settings"));
    await Promise.all([loadStatus(), loadTargets(), loadItems()]);
  } catch (error) { $("#catalog").innerHTML = `<div class="error">管理页面载入失败：${safe(error.message)}</div>`; }
}

init();

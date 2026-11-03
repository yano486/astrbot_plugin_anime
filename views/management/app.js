const bridge = window.AstrBotPluginView;
const $ = (selector) => document.querySelector(selector);
const state = { items: [], targets: [], subscriptions: new Map(), subscriptionsTarget: "", sources: {}, movieSources: {}, preferences: { schedule_source: "earliest", display_timezone: "Asia/Shanghai" }, periodMode: "", periodSelections: { season: "", year: "" } };

function currentSeason(now = new Date()) {
  const month = Math.floor((now.getMonth()) / 3) * 3 + 1;
  return `${now.getFullYear()}-${String(month).padStart(2, "0")}`;
}

function seasonPeriodOptions(now = new Date()) {
  const [year, month] = currentSeason(now).split("-").map(Number);
  const index = [1, 4, 7, 10].indexOf(month);
  return [-1, 0, 1].map(offset => {
    const absolute = year * 4 + index + offset;
    const optionYear = Math.floor(absolute / 4);
    const optionMonth = [1, 4, 7, 10][((absolute % 4) + 4) % 4];
    const value = `${optionYear}-${String(optionMonth).padStart(2, "0")}`;
    return { value, label: value };
  });
}

function catalogPeriodMode(type) {
  return type === "tv" || type === "web" ? "season" : "year";
}

function periodOptions(type, items = state.items, now = new Date()) {
  if (catalogPeriodMode(type) === "season") return seasonPeriodOptions(now);
  const years = new Set();
  for (const item of items || []) {
    if (type && item.item_type !== type) continue;
    const rawYear = isMovie(item) ? item.release_date?.slice(0, 4) : item.season?.slice(0, 4);
    if (/^\d{4}$/.test(rawYear || "")) years.add(rawYear);
  }
  years.add(String(now.getFullYear()));
  if (now.getMonth() === 11) years.add(String(now.getFullYear() + 1));
  return [...years].sort().map(year => ({ value: year, label: `${year} 年` }));
}

function matchesCatalogPeriod(item, type, period) {
  if (!period) return true;
  if (catalogPeriodMode(type) === "season") return !isMovie(item) && item.season === period;
  const year = isMovie(item) ? item.release_date?.slice(0, 4) : item.season?.slice(0, 4);
  return year === period;
}

function configurePeriodControl() {
  const select = $("#period");
  if (!select) return;
  if (state.periodMode && select.value) state.periodSelections[state.periodMode] = select.value;
  const type = $("#type").value;
  const mode = catalogPeriodMode(type);
  const options = periodOptions(type);
  const defaultValue = mode === "season" ? currentSeason() : String(new Date().getFullYear());
  const remembered = state.periodSelections[mode];
  const value = options.some(option => option.value === remembered) ? remembered
    : options.some(option => option.value === defaultValue) ? defaultValue
      : (options[options.length - 1]?.value || "");
  select.replaceChildren();
  options.forEach(valueOption => {
    const option = document.createElement("option");
    option.value = valueOption.value;
    option.textContent = valueOption.label;
    select.append(option);
  });
  select.value = value;
  state.periodMode = mode;
  state.periodSelections[mode] = value;
  $("#period-label").textContent = mode === "season" ? "季度" : "上映年份";
  window.AnimeControls?.refresh(select);
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
  const value = item.release_at || item.release_date || "";
  return /^\d{4}-\d{2}-\d{2}/.test(value) ? value.slice(0, 10) : "";
}

function firstTime(item, timezone = state.preferences.display_timezone) {
  if (!item.schedules?.length) return "时间待定";
  const s = item.schedules[0];
  const offset = timezone === "Asia/Shanghai" ? -60 : 0;
  const total = s.hour * 60 + s.minute + offset;
  const dayShift = Math.floor(total / (24 * 60));
  const clock = ((total % (24 * 60)) + (24 * 60)) % (24 * 60);
  const day = (((s.weekday - 1 + dayShift) % 7) + 7) % 7;
  const zoneName = timezone === "Asia/Shanghai" ? "北京" : "日本";
  const sourceName = timezone === "Asia/Shanghai" ? "日本" : "北京";
  const sourceOffset = timezone === "Asia/Shanghai" ? 0 : -60;
  const sourceTotal = s.hour * 60 + s.minute + sourceOffset;
  const sourceShift = Math.floor(sourceTotal / (24 * 60));
  const sourceClock = ((sourceTotal % (24 * 60)) + (24 * 60)) % (24 * 60);
  const sourceDay = (((s.weekday - 1 + sourceShift) % 7) + 7) % 7;
  return `${zoneName} 周${"一二三四五六日"[day]} ${String(Math.floor(clock / 60)).padStart(2,"0")}:${String(clock % 60).padStart(2,"0")} → ${sourceName} 周${"一二三四五六日"[sourceDay]} ${String(Math.floor(sourceClock / 60)).padStart(2,"0")}:${String(sourceClock % 60).padStart(2,"0")}`;
}

function sourceChoices() {
  const select = $("#source");
  const old = select.value;
  select.innerHTML = '<option value="">所有来源</option>';
  const sources = new Set(["yuc", ...Object.keys(state.sources || {}), ...state.items.flatMap(item => item.sources || [])]);
  [...sources].sort().forEach(source => {
    const option = document.createElement("option"); option.value = source; option.textContent = source; select.append(option);
  });
  select.value = old;
  window.AnimeControls?.refresh(select);
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
  const region = $("#region").value, type = $("#type").value, weekday = Number($("#weekday").value), role = $("#role").value, source = $("#source").value, period = $("#period").value;
  const items = state.items.filter(item => {
    const movie = isMovie(item);
    if (region === "jp" && item.region !== "jp") return false;
    if (region === "mixed" && item.region !== "mixed") return false;
    if (region === "unknown" && !["unknown", "mixed"].includes(item.region)) return false;
    if (type && item.item_type !== type) return false;
    if (weekday && !movie && !(item.schedules || []).some(s => s.weekday === weekday)) return false;
    if (role && !movie && item.season_role !== role) return false;
    if (!matchesCatalogPeriod(item, type, period)) return false;
    if (source && !(item.sources || []).includes(source)) return false;
    if (q && !`${item.title} ${item.title_cn} ${(item.aliases || []).join(" ")} ${(item.genres || []).join(" ")}`.toLowerCase().includes(q)) return false;
    return true;
  });
  $("#count").textContent = `${items.length} 部`;
  const catalog = $("#catalog"); catalog.replaceChildren();
  if (!items.length) { catalog.innerHTML = '<div class="empty">当前筛选没有作品。可以检查来源状态或尝试放宽筛选条件。</div>'; return; }
  items.forEach(item => {
    const movie = isMovie(item);
    const selected = state.subscriptions.get(item.key) || { enabled: false, lead_minutes: movie ? 0 : 15, on_time: true };
    const card = document.createElement("article"); card.className = `anime-card ${selected.enabled ? "subscribed" : ""}`;
    const imageUrl = safeHttpUrl(item.cover_url);
    const detailUrl = safeHttpUrl(item.detail_url || (item.bangumi_id ? `https://bgm.tv/subject/${item.bangumi_id}` : ""));
    const image = imageUrl ? `<img class="cover" loading="lazy" src="${imageUrl}" alt="">` : '<div class="cover cover-empty">番</div>';
    const cover = detailUrl ? `<a class="cover-link" href="${detailUrl}" target="_blank" rel="noopener noreferrer" aria-label="在 Bangumi 打开 ${safe(item.title_cn || item.title)}">${image}</a>` : image;
    const role = item.season_role === "new" ? '<i class="badge badge-new">新作</i>' : item.season_role === "continuing" ? '<i class="badge badge-cont">续播</i>' : "";
    const note = item.schedule_note ? `<div class="meta warning">${safe(item.schedule_note)}</div>` : item.data_status === "time_unknown" && !movie ? '<div class="meta warning">暂无可靠播出时间，暂不发送时间提醒</div>' : "";
    const timing = movie
      ? `<div class="movie-release"><label>上映日期</label><div class="date-field"><input class="release-at" type="hidden" value="${safe(movieReleaseValue(item))}"></div><small>OVA 与剧场版仅按日期触发提醒，不使用 TV 的提前分钟设置。</small><div class="release-actions"><button class="button button-quiet save-release" type="button">保存上映日期</button><button class="button button-quiet reset-release" type="button">恢复来源日期</button></div></div>`
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
  window.AnimeControls?.enhanceAll(catalog);
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
    window.AnimeControls?.refreshDate(input);
    card.querySelector(".save-release").textContent = "已保存";
  } catch (error) {
    card.querySelector(".save-release").textContent = `保存失败：${error.message}`;
  }
}

async function resetMovieRelease(item, card) {
  try {
    await bridge.apiPost("movie-release", {anime_key: item.key, release_at: ""});
    item.release_at = "";
    const input = card.querySelector(".release-at");
    input.value = movieReleaseValue(item);
    window.AnimeControls?.refreshDate(input);
    card.querySelector(".reset-release").textContent = "已恢复";
  } catch (error) {
    card.querySelector(".reset-release").textContent = `恢复失败：${error.message}`;
  }
}

async function loadItems(refreshYear = false) {
  const requestedMode = state.periodMode;
  const requestedPeriod = $("#period").value;
  $("#refresh-status").textContent = requestedMode === "year" && refreshYear ? `正在读取 ${requestedPeriod} 年多个季度…` : "正在读取作品目录…";
  if (requestedMode === "year" && refreshYear) {
    await bridge.apiPost("refresh", {season: requestedPeriod});
    if (requestedMode !== state.periodMode || requestedPeriod !== $("#period").value) return;
    await loadStatus();
  }
  const season = requestedMode === "season" ? requestedPeriod : "all";
  const result = await bridge.apiGet("items", { season });
  if (requestedMode !== state.periodMode || requestedPeriod !== $("#period").value) return;
  state.items = result.items || [];
  configurePeriodControl();
  sourceChoices(); render();
  const itemSelect = $("#test-item");
  if (itemSelect) {
    const oldItem = itemSelect.value;
    itemSelect.innerHTML = '<option value="">选择动画</option>';
    state.items.filter(item => item.item_type === "tv" || item.item_type === "web").forEach(item => {
      const option = document.createElement("option"); option.value = item.key; option.textContent = item.title_cn || item.title; itemSelect.append(option);
    });
    if (state.items.some(item => item.key === oldItem)) itemSelect.value = oldItem;
    window.AnimeControls?.refresh(itemSelect);
  }
  $("#refresh-status").textContent = `已载入 ${result.count || 0} 部 · ${result.updated_at || "尚未刷新"}`;
}

async function loadStatus() {
  const data = await bridge.apiGet("status");
  state.preferences = {...state.preferences, ...(data.preferences || {})};
  applyPreferences();
  state.sources = data.sources || {}; state.movieSources = data.movie_sources || {}; renderSources();
  sourceChoices();
  $("#logout").hidden = !data.remote_webui_password_enabled;
  $("#remote-webui-status").textContent = data.remote_webui_enabled
    ? `${data.remote_webui_url} · ${data.remote_webui_password_enabled ? "密码保护已开启" : "未设置密码，局域网内可直接访问"}`
    : "未启动。请检查 AstrBot 插件中的远程 WebUI 开关、监听地址、端口及登录密码设置。";
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
  window.AnimeControls?.refresh(select);
  window.AnimeControls?.refresh(testSelect);
  const itemSelect = $("#test-item"); const oldItem = itemSelect.value;
  itemSelect.innerHTML = '<option value="">选择动画</option>';
  state.items.filter(item => item.item_type === "tv" || item.item_type === "web").forEach(item => {
    const option = document.createElement("option"); option.value = item.key; option.textContent = item.title_cn || item.title; itemSelect.append(option);
  });
  if (state.items.some(item => item.key === oldItem)) itemSelect.value = oldItem;
  window.AnimeControls?.refresh(itemSelect);
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
    await bridge.apiPost("test-push", {target_id: targetId, kind: "message"});
    $("#test-push-status").textContent = "测试消息已发送。";
  } catch (error) {
    $("#test-push-status").textContent = `发送失败：${error.message}`;
  } finally {
    $("#test-push").disabled = false;
  }
}

async function sendCardTest(kind) {
  const targetId = $("#test-target").value;
  if (!targetId) { $("#test-push-status").textContent = "请先选择推送目标。"; return; }
  const payload = {target_id: targetId, kind};
  if (kind === "update_card") {
    payload.anime_key = $("#test-item").value;
    if (!payload.anime_key) { $("#test-push-status").textContent = "请先选择要测试的动画。"; return; }
  }
  $("#test-push-status").textContent = "正在生成并发送图片卡片…";
  try {
    await bridge.apiPost("test-push", payload);
    $("#test-push-status").textContent = "图片卡片已发送。";
  } catch (error) {
    $("#test-push-status").textContent = `卡片发送失败：${error.message}`;
  }
}

async function addUmoTarget() {
  const input = $("#umo-target");
  try {
    const result = await bridge.apiPost("targets/umo", {umo: input.value.trim()});
    await loadTargets();
    $("#test-target").value = result.target_id;
    input.value = "";
    $("#test-push-status").textContent = "会话已添加到白名单，可直接用于推送测试。";
  } catch (error) {
    $("#test-push-status").textContent = `UMO 添加失败：${error.message}`;
  }
}

function applyPreferences() {
  $("#schedule-source").value = state.preferences.schedule_source;
  $("#display-timezone").value = state.preferences.display_timezone;
  window.AnimeControls?.refresh($("#schedule-source"));
  window.AnimeControls?.refresh($("#display-timezone"));
  render();
}

async function savePreferences() {
  const values = {schedule_source: $("#schedule-source").value, display_timezone: $("#display-timezone").value};
  try {
    const result = await bridge.apiPost("preferences", values);
    state.preferences = result.preferences;
    applyPreferences();
    $("#save-status").textContent = "排期与时区设置已保存。刷新番表后应用新的排期来源。";
  } catch (error) {
    $("#save-status").textContent = `设置保存失败：${error.message}`;
  }
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  window.localStorage.setItem("anime-management-theme", theme);
  const button = $("#toggle-theme");
  button.textContent = theme === "dark" ? "切换亮色" : "切换暗色";
  button.setAttribute("aria-pressed", String(theme === "dark"));
}

async function logout() {
  await bridge.apiPost("logout", {});
  window.location.replace("/");
}

async function refreshAll() {
  $("#refresh").disabled = true; $("#refresh-status").textContent = "正在刷新多个来源…";
  try {
    await bridge.apiPost("refresh", {season: $("#period").value});
    await loadStatus();
    await loadItems();
    $("#save-status").textContent = "刷新完成";
  }
  catch (error) { $("#refresh-status").textContent = `刷新失败：${error.message}`; }
  finally { $("#refresh").disabled = false; }
}

async function init() {
  try {
    await bridge.ready();
    configurePeriodControl();
    window.AnimeControls?.enhanceAll();
    setTheme(window.localStorage.getItem("anime-management-theme") === "dark" ? "dark" : "light");
    for (const id of ["query", "region", "weekday", "role", "source"]) $("#" + id).addEventListener(id === "query" ? "input" : "change", render);
    $("#type").addEventListener("change", () => { configurePeriodControl(); loadItems(state.periodMode === "year"); });
    $("#period").addEventListener("change", () => {
      state.periodSelections[state.periodMode] = $("#period").value;
      loadItems(state.periodMode === "year");
    });
    $("#refresh").addEventListener("click", refreshAll);
    $("#load-subs").addEventListener("click", loadSubscriptions);
    $("#save-subs").addEventListener("click", saveSubscriptions);
    $("#save-whitelist").addEventListener("click", saveWhitelist);
    $("#test-push").addEventListener("click", sendTestPush);
    $("#test-reminder-card").addEventListener("click", () => sendCardTest("reminder_card"));
    $("#test-update-card").addEventListener("click", () => sendCardTest("update_card"));
    $("#add-umo").addEventListener("click", addUmoTarget);
    $("#save-preferences").addEventListener("click", savePreferences);
    $("#toggle-theme").addEventListener("click", () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
    $("#logout").addEventListener("click", logout);
    $("#show-catalog").addEventListener("click", () => showView("catalog"));
    $("#show-settings").addEventListener("click", () => showView("settings"));
    await Promise.all([loadStatus(), loadTargets(), loadItems(state.periodMode === "year")]);
  } catch (error) { $("#catalog").innerHTML = `<div class="error">管理页面载入失败：${safe(error.message)}</div>`; }
}

init();

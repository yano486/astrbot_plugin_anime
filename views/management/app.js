const bridge = window.AstrBotPluginView;
const $ = (selector) => document.querySelector(selector);
const state = { items: [], targets: [], subscriptions: new Map(), subscriptionsTarget: "", showSubscribedOnly: false, weekday: "", sources: {}, movieSources: {}, templateDefinitions: [], preferences: { schedule_source: "earliest", display_timezone: "Asia/Shanghai", exclude_r18: false, push_mode: "text", message_templates: {} }, periodMode: "", periodSelections: { season: "", broadcast: "", year: "" } };
const templateSelections = new Map();
let testItemsRequest = 0;

function currentSeason(now = new Date()) {
  const month = Math.floor((now.getMonth()) / 3) * 3 + 1;
  return `${now.getFullYear()}-${String(month).padStart(2, "0")}`;
}

function seasonPeriodOptions(now = new Date()) {
  const year = now.getFullYear();
  const months = [1, 4, 7, 10];
  const current = Math.floor(now.getMonth() / 3) * 3 + 1;
  return [current, ...months.filter(month => month !== current)].map(month => ({
    value: `${year}-${String(month).padStart(2, "0")}`,
    label: periodLabel("season", `${year}-${String(month).padStart(2, "0")}`),
  }));
}

function catalogPeriodMode(type) {
  if (type === "tv" || type === "web") return "season";
  if (type === "preview") return "preview";
  if (!type) return "broadcast";
  return "year";
}

function nextSeason(now = new Date()) {
  const month = Math.floor(now.getMonth() / 3) * 3 + 1;
  const year = now.getFullYear() + (month === 10 ? 1 : 0);
  const nextMonth = month === 10 ? 1 : month + 3;
  return `${year}-${String(nextMonth).padStart(2, "0")}`;
}

function allYearSeasons(now = new Date()) {
  const year = now.getFullYear();
  const current = currentSeason(now);
  const values = ["01", "04", "07", "10"].map(month => `${year}-${month}`);
  return [current, ...values.filter(value => value !== current)];
}

function periodLabel(type, value) {
  const match = /^(\d{4})-(01|04|07|10)$/.exec(value || "");
  if (match) return ({"01": "冬 · 1月", "04": "春 · 4月", "07": "夏 · 7月", "10": "秋 · 10月"})[match[2]];
  if (value?.endsWith("-h1")) return "上半年";
  if (value?.endsWith("-h2")) return "下半年";
  if (value?.endsWith("-all")) return "全年";
  return /^\d{4}$/.test(value || "") ? `${value} 年` : value || "";
}

function broadcastPeriodOptions(now = new Date()) {
  const year = now.getFullYear();
  const current = currentSeason(now);
  const seasons = seasonPeriodOptions(now).map(option => ({...option, label: periodLabel("broadcast", option.value)}));
  return [...seasons, {value: `${year}-h1`, label: "上半年"}, {value: `${year}-h2`, label: "下半年"}, {value: `${year}-all`, label: "全年"}]
    .sort((a, b) => (a.value === current ? -1 : b.value === current ? 1 : 0));
}

function periodOptions(type, items = state.items, now = new Date()) {
  const mode = catalogPeriodMode(type);
  if (mode === "season") return seasonPeriodOptions(now);
  if (mode === "preview") return [{value: nextSeason(now), label: periodLabel("season", nextSeason(now))}];
  if (mode === "broadcast") return broadcastPeriodOptions(now);
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

function periodsForSelection(type, period) {
  const mode = catalogPeriodMode(type);
  if (mode === "season") return period ? [period] : [];
  if (mode === "preview") return period ? [period] : [];
  if (mode !== "broadcast") return [];
  if (/^\d{4}-(01|04|07|10)$/.test(period || "")) return [period];
  const match = /^(\d{4})-(h1|h2|all)$/.exec(period || "");
  if (!match) return [];
  const months = match[2] === "h1" ? ["01", "04"] : match[2] === "h2" ? ["07", "10"] : ["01", "04", "07", "10"];
  return months.map(month => `${match[1]}-${month}`);
}

function matchesCatalogPeriod(item, type, period) {
  if (!period) return true;
  const mode = catalogPeriodMode(type);
  if (mode === "season") return !isMovie(item) && item.season === period;
  if (mode === "preview") return !isMovie(item) && item.season === period;
  if (mode === "broadcast") {
    const periods = periodsForSelection(type, period);
    if (isMovie(item)) {
      const release = item.release_date || "";
      return periods.some(value => release.startsWith(value));
    }
    return periods.includes(item.season);
  }
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
  const defaultValue = mode === "year" ? String(new Date().getFullYear()) : mode === "preview" ? nextSeason() : currentSeason();
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
  $("#period-label").textContent = mode === "season" || mode === "preview" ? "季度" : mode === "broadcast" ? "播出时间" : "上映年份";
  updateFilterVisibility(type);
  window.AnimeControls?.refresh(select);
}

function updateFilterVisibility(type) {
  const movie = ["ova", "movie"].includes(type);
  const preview = type === "preview";
  $("#query").disabled = preview;
  $("#weekday-filter").hidden = movie || preview;
  $("#query").value = preview ? "" : $("#query").value;
  updatePreviewHint(type);
  syncWeekdayButtons();
}

function updatePreviewHint(type) {
  $("#preview-hint").hidden = type !== "preview";
}

function safe(value = "") { return String(value).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c])); }

function syncWeekdayButtons() {
  document.querySelectorAll("#weekday-buttons [data-weekday]").forEach(button => {
    const active = button.dataset.weekday === state.weekday;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
}

function setStatus(message, kind = "") {
  const notice = $("#save-status");
  const text = notice.querySelector?.(".status-inline-text");
  if (text) text.textContent = message;
  else notice.textContent = message;
  notice.className = `status-inline ${kind}`.trim();
  notice.hidden = !message;
}

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
    chip.textContent = `${name} ${result.status === "error" ? "失败" : result.status === "empty" ? "暂无数据" : result.error ? "部分" : `${result.count || 0} 条`}`;
    chip.title = result.error || result.source_url || ""; container.append(chip);
  });
}

function sourceFailureNotice() {
  const sourceEntries = Object.entries({...state.sources, ...Object.fromEntries(Object.entries(state.movieSources || {}).map(([name, value]) => [`剧场版/OVA · ${name}`, value]))});
  const failures = sourceEntries
    .filter(([, result]) => result.status === "error" || result.error)
    .map(([name, result]) => {
      const error = String(result.error || "");
      if (/429|限流/i.test(error)) return `${name} 暂时限流`;
      if (/timeout|超时/i.test(error)) return `${name} 响应超时`;
      if (/HTTP/i.test(error)) return `${name} 返回网络错误`;
      return `${name} 未完整返回`;
    });
  if (failures.length) return `部分来源未完成：${failures.join("、")}，已保留可用结果`;
  const empty = sourceEntries.filter(([, result]) => result.status === "empty").map(([name]) => `${name}暂无数据`);
  return empty.length ? `已获取番组；${empty.join("、")}` : "";
}

function visibleCatalogItems() {
  if (!state.showSubscribedOnly) return state.items;
  return state.items.filter(item => state.subscriptions.get(item.key)?.enabled === true);
}

function matchesCatalogType(itemType, selectedType) {
  return !selectedType || selectedType === "preview" || itemType === selectedType;
}

function matchesAdaptationType(item, selectedType) {
  return !selectedType || adaptationTypes(item).includes(selectedType);
}

function adaptationTypes(item) {
  const saved = item.adaptation_types || [];
  if (saved.length) return saved;
  const categories = [];
  for (const tag of item.genres || []) {
    const value = String(tag).normalize("NFKC").toLowerCase().replace(/\s+/g, "");
    if (/(原创|原創|オリジナルアニメ|オリジナル作品)/.test(value) && !categories.includes("original")) categories.push("original");
    if (/(轻小说改|輕小說改|小说改|小說改|轻改|小說原作|小说原作|轻小说原作|輕小說原作|原作小说|原作小說|文学改|文學改|文学原作|文學原作)/.test(value) && !categories.includes("novel")) categories.push("novel");
    if (/(漫画改|漫畫改|漫改|漫画原作|漫畫原作|原作漫画|原作漫畫|コミック原作)/.test(value) && !categories.includes("manga")) categories.push("manga");
    if (/(游戏改|遊戲改|游戏原作|遊戲原作|原作游戏|原作遊戲|ゲーム原作|游戏改编|遊戲改編)/.test(value) && !categories.includes("game")) categories.push("game");
  }
  return categories;
}

function adaptationLabel(value) {
  return ({novel: "小说改", manga: "漫画改", game: "游戏改", original: "原创"})[value] || "";
}

function syncSubscriptionButton() {
  const button = $("#load-subs");
  if (!button) return;
  button.textContent = state.showSubscribedOnly ? "显示全部" : "读取订阅";
  button.setAttribute("aria-pressed", String(state.showSubscribedOnly));
}

function render() {
  const q = $("#query").value.trim().toLowerCase();
  const region = $("#region").value, type = $("#type").value, weekday = ["preview", "ova", "movie"].includes(type) ? 0 : Number(state.weekday), adaptationType = $("#adaptation-type").value, source = $("#source").value, period = $("#period").value;
  const items = visibleCatalogItems().filter(item => {
    const movie = isMovie(item);
    if (region === "jp" && item.region !== "jp") return false;
    if (region === "mixed" && item.region !== "mixed") return false;
    if (region === "unknown" && !["unknown", "mixed"].includes(item.region)) return false;
    if (!matchesCatalogType(item.item_type, type)) return false;
    if (weekday && !movie && !(item.schedules || []).some(s => s.weekday === weekday)) return false;
    if (!matchesAdaptationType(item, adaptationType)) return false;
    if (!matchesCatalogPeriod(item, type, period)) return false;
    if (source && !(item.sources || []).includes(source)) return false;
    if (q && !`${item.title} ${item.title_cn} ${(item.aliases || []).join(" ")} ${(item.genres || []).join(" ")}`.toLowerCase().includes(q)) return false;
    return true;
  });
  const itemOrder = {tv: 0, web: 1, ova: 2, movie: 3};
  items.sort((left, right) => (itemOrder[left.item_type] ?? 9) - (itemOrder[right.item_type] ?? 9));
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
    const adaptationBadges = adaptationTypes(item).map(value => `<i class="badge badge-adaptation">${adaptationLabel(value)}</i>`).join("");
    const note = item.schedule_note ? `<div class="meta warning">${safe(item.schedule_note)}</div>` : item.data_status === "time_unknown" && !movie ? '<div class="meta warning">暂无可靠播出时间，暂不发送时间提醒</div>' : "";
    const timing = movie
      ? `<div class="movie-release"><label>上映日期</label><div class="date-field"><input class="release-at" type="hidden" value="${safe(movieReleaseValue(item))}"></div><small>OVA 与剧场版仅按日期触发提醒，不使用 TV 的提前分钟设置。</small><div class="release-actions"><button class="button button-quiet save-release" type="button">保存上映日期</button><button class="button button-quiet reset-release" type="button">恢复来源日期</button></div></div>`
      : `<div class="reminder-controls"><label>提前</label><input class="lead" type="number" min="0" max="1440" step="5" value="${Number(selected.lead_minutes) || 0}"><span>分钟</span><label><input class="on-time" type="checkbox" ${selected.on_time ? "checked" : ""}> 准点提醒</label></div>`;
    const displayTime = movie ? `上映日期：${safe(item.release_date || "待确认")}` : safe(firstTime(item));
    card.innerHTML = `${cover}<div class="card-main"><div class="card-top">${role}${adaptationBadges}<i class="badge badge-cont">${safe(item.item_type || "类型待确认")}</i><i class="badge">${safe(item.region === "jp" ? "日本" : item.region === "mixed" ? "地区混合" : "地区待确认")}</i></div><h3>${safe(item.title_cn || item.title)}</h3><div class="original">${safe(item.title)}</div><div class="air-time">${displayTime}</div><div class="meta">${safe((item.genres || []).slice(0,4).join(" · "))}</div><div class="meta">来源：${safe((item.sources || []).join("、") || "尚无排期来源")}</div>${note}${timing}</div><input class="card-check" type="checkbox" ${selected.enabled ? "checked" : ""} aria-label="订阅 ${safe(item.title_cn || item.title)}">`;
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
  const settings = view === "settings";
  $("#catalog-view").hidden = !catalog;
  $("#settings-view").hidden = !settings;
  $("#messages-view").hidden = view !== "messages";
  $("#show-catalog").classList.toggle("active", catalog);
  $("#show-settings").classList.toggle("active", settings);
  $("#show-messages").classList.toggle("active", view === "messages");
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

async function loadItems(shouldRefresh = false, fullYear = false) {
  const requestedMode = state.periodMode;
  const requestedPeriod = $("#period").value;
  const requestedType = $("#type").value;
  const requestedPeriods = fullYear && !requestedType ? allYearSeasons() : periodsForSelection(requestedType, requestedPeriod);
  $("#refresh-status").textContent = shouldRefresh ? "正在获取多个来源…" : "正在获取作品目录…";
  if (shouldRefresh) {
    const refreshBody = requestedPeriods.length ? {seasons: requestedPeriods} : {season: requestedPeriod};
    await bridge.apiPost("refresh", refreshBody);
    if (requestedMode !== state.periodMode || requestedPeriod !== $("#period").value) return;
    await loadStatus();
  }
  const queryPeriods = requestedPeriods.length ? requestedPeriods : ["all"];
  const results = await Promise.all(queryPeriods.map(season => bridge.apiGet("items", { season })));
  if (requestedMode !== state.periodMode || requestedPeriod !== $("#period").value) return;
  const byKey = new Map();
  results.flatMap(result => result.items || []).forEach(item => byKey.set(item.key, item));
  const result = {items: [...byKey.values()], count: byKey.size, updated_at: results.map(value => value.updated_at).filter(Boolean).sort().at(-1) || ""};
  state.items = result.items;
  configurePeriodControl();
  sourceChoices(); render();
  $("#refresh-status").textContent = `已载入 ${result.count || 0} 部 · ${result.updated_at || "尚未获取"}`;
}

async function loadStatus() {
  const data = await bridge.apiGet("status");
  state.preferences = {...state.preferences, ...(data.preferences || {})};
  state.templateDefinitions = data.template_definitions || state.templateDefinitions;
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
  const list = $("#whitelist-list"); list.replaceChildren();
  state.targets.filter(target => target.enabled).forEach(target => {
    const label = document.createElement("label"); label.className = "whitelist-target";
    label.innerHTML = `<input type="checkbox" data-target="${safe(target.target_id)}" ${target.whitelisted ? "checked" : ""}> <span>${safe(target.display_name || target.target_id)}${target.subscribed ? " · 自动推送已启用" : ""}</span><button class="button button-quiet remove-whitelist" type="button" title="移出白名单">移除</button>`;
    label.addEventListener("click", event => {
      if (event.target.closest?.(".remove-whitelist")) removeWhitelist(event);
    });
    list.append(label);
  });
  await loadTestItems();
}

async function loadTestItems() {
  const requestId = ++testItemsRequest;
  const targetId = $("#test-target").value;
  const select = $("#test-item");
  const previous = select.value;
  select.innerHTML = '<option value="">选择订阅动画</option>';
  select.disabled = true;
  window.AnimeControls?.refresh(select);
  if (!targetId) return;
  const target = state.targets.find(target => target.target_id === targetId);
  if (target && !target.subscribed) {
    $("#test-push-status").textContent = "订阅群没有订阅，请先开启订阅。";
    return;
  }
  try {
    const [subscriptions, catalog] = await Promise.all([
      bridge.apiGet("subscriptions", {target_id: targetId}),
      bridge.apiGet("items", {season: "all"}),
    ]);
    if (requestId !== testItemsRequest || $("#test-target").value !== targetId) return;
    const keys = new Set((subscriptions.subscriptions || []).filter(sub => sub.enabled).map(sub => sub.anime_key));
    const items = (catalog.items || []).filter(item => keys.has(item.key));
    items.forEach(item => {
      const option = document.createElement("option");
      option.value = item.key;
      option.textContent = item.title_cn || item.title;
      select.append(option);
    });
    if (items.some(item => item.key === previous)) select.value = previous;
    select.disabled = !items.length;
    window.AnimeControls?.refresh(select);
    $("#test-push-status").textContent = items.length ? "已读取该目标订阅，可选择动画测试。" : "未添加动画推送，请先勾选动画并保存订阅。";
  } catch (error) {
    if (requestId !== testItemsRequest || $("#test-target").value !== targetId) return;
    $("#test-push-status").textContent = `读取测试订阅失败：${error.message}`;
  }
}

function removeWhitelist(event) {
  event.preventDefault();
  event.stopPropagation();
  const label = event.target.closest?.(".whitelist-target");
  const checkbox = label?.querySelector("input[type=checkbox]");
  if (!checkbox) return;
  checkbox.checked = false;
  saveWhitelist();
}

async function loadSubscriptions() {
  const targetId = $("#target").value; if (!targetId) { setStatus("请先选择推送目标", "notice-error"); return; }
  if (state.showSubscribedOnly && state.subscriptionsTarget === targetId) {
    state.showSubscribedOnly = false;
    syncSubscriptionButton();
    render();
    setStatus("已显示全部动画", "notice-success");
    return;
  }
  const data = await bridge.apiGet("subscriptions", { target_id: targetId });
  if ($("#target").value !== targetId) return;
  state.subscriptionsTarget = targetId;
  state.subscriptions = new Map((data.subscriptions || []).map(sub => [sub.anime_key, sub]));
  state.showSubscribedOnly = true;
  syncSubscriptionButton();
  render();
  setStatus("已读取该目标订阅", "notice-success");
}

async function saveSubscriptions() {
  const targetId = $("#target").value; if (!targetId) { setStatus("请先选择推送目标", "notice-error"); return; }
  if (state.subscriptionsTarget !== targetId) { setStatus("请先读取当前目标订阅，避免覆盖其他群聊", "notice-error"); return; }
  const subscriptions = [...state.subscriptions.entries()].filter(([,sub]) => sub.enabled).map(([anime_key,sub]) => ({anime_key, enabled: true, lead_minutes: Number(sub.lead_minutes) || 0, on_time: Boolean(sub.on_time)}));
  const result = await bridge.apiPost("subscriptions", {target_id: targetId, subscriptions});
  await loadTargets();
  setStatus(`已保存 ${result.saved} 部订阅`, "notice-success");
}

async function saveWhitelist() {
  const targets = [...document.querySelectorAll(".whitelist-target input")].map(input => ({target_id: input.dataset.target, allowed: input.checked}));
  const result = await bridge.apiPost("targets/whitelist", {targets});
  await loadTargets();
  setStatus(`白名单已更新 ${result.updated} 个目标`, "notice-success");
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
  const target = state.targets.find(target => target.target_id === targetId);
  if (target && !target.subscribed) { $("#test-push-status").textContent = "订阅群没有订阅，请先开启订阅。"; return; }
  payload.anime_key = $("#test-item").value;
  if ($("#test-item").disabled) { $("#test-push-status").textContent = "未添加动画推送，请先勾选动画并保存订阅。"; return; }
  if (!payload.anime_key) { $("#test-push-status").textContent = "请选择要测试的订阅动画。"; return; }
  $("#test-push-status").textContent = "正在生成并发送图片卡片…";
  try {
    await bridge.apiPost("test-push", payload);
    $("#test-push-status").textContent = "图片卡片已发送。";
  } catch (error) {
    $("#test-push-status").textContent = `卡片发送失败：${error.message}`;
  }
}

async function sendTableTest(kind) {
  const targetId = $("#test-target").value;
  if (!targetId) { $("#test-push-status").textContent = "请先选择推送目标。"; return; }
  $("#test-push-status").textContent = "正在生成并发送订阅番组图片…";
  try {
    await bridge.apiPost("test-push", {target_id: targetId, kind: kind === "daily" ? "daily_table" : "weekly_table"});
    $("#test-push-status").textContent = `${kind === "daily" ? "每日" : "每周"}番组图片已发送。`;
  } catch (error) {
    $("#test-push-status").textContent = `番组图片发送失败：${error.message}`;
  }
}

async function addUmoTarget() {
  const input = $("#umo-target");
  try {
    const result = await bridge.apiPost("targets/umo", {umo: input.value.trim()});
    await loadTargets();
    $("#test-target").value = result.target_id;
    window.AnimeControls?.refresh($("#test-target"));
    await loadTestItems();
    input.value = "";
    $("#test-push-status").textContent = "会话已添加到白名单，可直接用于推送测试。";
  } catch (error) {
    $("#test-push-status").textContent = `UMO 添加失败：${error.message}`;
  }
}

function applyPreferences() {
  $("#schedule-source").value = state.preferences.schedule_source;
  $("#display-timezone").value = state.preferences.display_timezone;
  $("#exclude-r18").value = String(Boolean(state.preferences.exclude_r18));
  $("#push-mode").value = state.preferences.push_mode || "text";
  $("#card-style").value = state.preferences.card_style || "info";
  $("#card-theme").value = state.preferences.card_theme || "dark";
  $("#daily-table-enabled").value = String(Boolean(state.preferences.daily_table_enabled));
  $("#daily-table-time").value = state.preferences.daily_table_time || "00:00";
  $("#weekly-table-enabled").value = String(Boolean(state.preferences.weekly_table_enabled));
  $("#weekly-table-time").value = state.preferences.weekly_table_time || "00:00";
  renderTemplateEditors();
  window.AnimeControls?.refresh($("#schedule-source"));
  window.AnimeControls?.refresh($("#display-timezone"));
  window.AnimeControls?.refresh($("#exclude-r18"));
  window.AnimeControls?.refresh($("#push-mode"));
  window.AnimeControls?.refresh($("#card-style"));
  window.AnimeControls?.refresh($("#card-theme"));
  window.AnimeControls?.refresh($("#daily-table-enabled"));
  window.AnimeControls?.refresh($("#weekly-table-enabled"));
  render();
}

function renderTemplateEditors() {
  const container = $("#message-templates");
  if (!container) return;
  const templates = state.preferences.message_templates || {};
  container.innerHTML = state.templateDefinitions.map(definition => `
    <details class="message-template-card">
      <summary><strong>${safe(definition.label)}</strong><button class="button button-quiet reset-template" type="button" data-template-key="${safe(definition.key)}">恢复默认</button></summary>
      <small class="template-description">${safe(definition.description)}</small>
      <textarea data-template-key="${safe(definition.key)}" rows="4" aria-label="${safe(definition.label)}">${safe(templates[definition.key] ?? definition.default)}</textarea>
      <div class="template-variables"><span>变量：</span>${(definition.variables || []).map(value => {
        const description = definition.variable_descriptions?.[value] || value;
        return `<button class="variable-chip" type="button" data-template-key="${safe(definition.key)}" data-variable="{${safe(value)}}" title="${safe(description)}">{${safe(value)}}</button>`;
      }).join("") || "无"}</div>
    </details>`).join("");
  container.querySelectorAll?.(".reset-template").forEach(button => button.addEventListener("click", event => {
    event.preventDefault();
    const definition = state.templateDefinitions.find(value => value.key === button.dataset.templateKey);
    const textarea = container.querySelector(`textarea[data-template-key="${CSS.escape(button.dataset.templateKey)}"]`);
    if (definition && textarea) textarea.value = definition.default;
  }));
  container.querySelectorAll?.("summary").forEach(summary => summary.addEventListener("click", event => {
    if (event.target.closest?.(".reset-template")) event.preventDefault();
  }));
  container.querySelectorAll?.("textarea[data-template-key]").forEach(textarea => {
    const templateKey = textarea.dataset.templateKey;
    ["click", "input", "keyup", "select", "blur"].forEach(eventName => {
      textarea.addEventListener(eventName, () => rememberTemplateSelection(templateKey, textarea));
    });
  });
  container.querySelectorAll?.(".variable-chip").forEach(button => button.addEventListener("click", () => {
    insertTemplateVariable(button.dataset.templateKey, button.dataset.variable);
  }));
}

function rememberTemplateSelection(templateKey, textarea) {
  if (!textarea || !Number.isInteger(textarea.selectionStart) || !Number.isInteger(textarea.selectionEnd)) return;
  const length = String(textarea.value || "").length;
  const start = Math.max(0, Math.min(length, textarea.selectionStart));
  const end = Math.max(start, Math.min(length, textarea.selectionEnd));
  templateSelections.set(templateKey, {start, end});
}

function insertTemplateVariable(templateKey, variable) {
  const textarea = $("#message-templates")?.querySelector?.(`textarea[data-template-key="${CSS.escape(templateKey)}"]`);
  if (!textarea) return;
  const focused = document.activeElement === textarea;
  const current = focused && Number.isInteger(textarea.selectionStart) && Number.isInteger(textarea.selectionEnd)
    ? {start: textarea.selectionStart, end: textarea.selectionEnd}
    : templateSelections.get(templateKey);
  const length = textarea.value.length;
  const start = current ? Math.max(0, Math.min(length, current.start)) : length;
  const end = current ? Math.max(start, Math.min(length, current.end)) : start;
  textarea.value = textarea.value.slice(0, start) + variable + textarea.value.slice(end);
  textarea.focus();
  const cursor = start + variable.length;
  textarea.setSelectionRange(cursor, cursor);
  templateSelections.set(templateKey, {start: cursor, end: cursor});
}

function collectTemplateValues() {
  const values = {};
  $("#message-templates")?.querySelectorAll?.("textarea[data-template-key]").forEach(textarea => {
    values[textarea.dataset.templateKey] = textarea.value;
  });
  return values;
}

async function savePreferences() {
  const values = {
    schedule_source: $("#schedule-source").value,
    display_timezone: $("#display-timezone").value,
    exclude_r18: $("#exclude-r18").value === "true",
    push_mode: $("#push-mode").value,
    card_style: $("#card-style").value,
    card_theme: $("#card-theme").value,
    daily_table_enabled: $("#daily-table-enabled").value === "true",
    daily_table_time: $("#daily-table-time").value.trim(),
    weekly_table_enabled: $("#weekly-table-enabled").value === "true",
    weekly_table_time: $("#weekly-table-time").value.trim(),
  };
  try {
    const result = await bridge.apiPost("preferences", values);
    state.preferences = result.preferences;
    applyPreferences();
    setStatus("设置已保存。获取番组后应用新的排期来源。", "notice-success");
  } catch (error) {
    setStatus(`设置保存失败：${error.message}`, "notice-error");
  }
}

async function saveMessageTemplates() {
  try {
    const result = await bridge.apiPost("preferences", {message_templates: collectTemplateValues()});
    state.preferences = result.preferences;
    renderTemplateEditors();
    setStatus("消息文本已保存。", "notice-success");
  } catch (error) {
    setStatus(`消息文本保存失败：${error.message}`, "notice-error");
  }
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  try { window.localStorage?.setItem("anime-management-theme", theme); } catch {}
  const button = $("#toggle-theme");
  button.textContent = theme === "dark" ? "切换亮色" : "切换暗色";
  button.setAttribute("aria-pressed", String(theme === "dark"));
}

function storedTheme() {
  try { return window.localStorage?.getItem("anime-management-theme") || ""; } catch { return ""; }
}

async function logout() {
  await bridge.apiPost("logout", {});
  window.location.replace("/");
}

async function refreshAll() {
  const button = $("#refresh");
  button.disabled = true;
  button.textContent = "正在获取…";
  try {
    await loadItems(true, true);
    setStatus(sourceFailureNotice() || "已获取最新番组", "notice-success");
  }
  catch (error) {
    setStatus(`获取失败：${naturalError(error)}`, "notice-error");
  }
  finally {
    button.disabled = false;
    button.textContent = "获取番组";
  }
}

async function loadPreviewAfterTypeChange() {
  const type = $("#type").value;
  configurePeriodControl();
  try {
    await loadItems(type === "preview");
    if (type === "preview") setStatus(sourceFailureNotice() || "已获取新番抢先看", "notice-success");
  } catch (error) {
    setStatus(`获取失败：${naturalError(error)}`, "notice-error");
  }
}

function naturalError(error) {
  const message = String(error?.message || error || "未知错误");
  if (/429|限流|too many/i.test(message)) return "来源暂时限流，请稍后再获取";
  if (/timeout|timed out|超时/i.test(message)) return "来源响应超时，已保留已有数据";
  if (/network|connect|连接|DNS/i.test(message)) return "网络连接失败，已保留已有数据";
  return message;
}

async function init() {
  try {
    await bridge.ready();
    configurePeriodControl();
    window.AnimeControls?.enhanceAll();
    setTheme(storedTheme() === "dark" ? "dark" : "light");
    for (const id of ["query", "region", "adaptation-type", "source"]) $("#" + id).addEventListener(id === "query" ? "input" : "change", render);
    document.querySelectorAll("#weekday-buttons [data-weekday]").forEach(button => button.addEventListener("click", () => {
      state.weekday = button.dataset.weekday || "";
      syncWeekdayButtons();
      render();
    }));
    $("#target").addEventListener("change", () => { state.showSubscribedOnly = false; syncSubscriptionButton(); });
    $("#type").addEventListener("change", loadPreviewAfterTypeChange);
    $("#period").addEventListener("change", () => {
      state.periodSelections[state.periodMode] = $("#period").value;
      loadItems(false);
    });
    $("#refresh").addEventListener("click", refreshAll);
    $("#load-subs").addEventListener("click", loadSubscriptions);
    $("#save-subs").addEventListener("click", saveSubscriptions);
    $("#save-whitelist").addEventListener("click", saveWhitelist);
    $("#test-push").addEventListener("click", sendTestPush);
    $("#test-target").addEventListener("change", loadTestItems);
    $("#test-reminder-card").addEventListener("click", () => sendCardTest("reminder_card"));
    $("#test-update-card").addEventListener("click", () => sendCardTest("update_card"));
    $("#test-daily-table").addEventListener("click", () => sendTableTest("daily"));
    $("#test-weekly-table").addEventListener("click", () => sendTableTest("weekly"));
    $("#add-umo").addEventListener("click", addUmoTarget);
    $("#save-preferences").addEventListener("click", savePreferences);
    $("#toggle-theme").addEventListener("click", () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
    syncSubscriptionButton();
    $("#logout").addEventListener("click", logout);
    $("#show-catalog").addEventListener("click", () => showView("catalog"));
    $("#show-settings").addEventListener("click", () => showView("settings"));
    $("#show-messages").addEventListener("click", () => showView("messages"));
    $("#save-message-templates").addEventListener("click", saveMessageTemplates);
    await Promise.all([loadStatus(), loadTargets(), loadItems(false)]);
  } catch (error) { $("#catalog").innerHTML = `<div class="error">管理页面载入失败：${safe(error.message)}</div>`; }
}

init();

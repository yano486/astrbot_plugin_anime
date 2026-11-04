(() => {
  const selectControls = new WeakMap();
  const dateControls = new WeakMap();
  const openControls = new Set();
  let controlId = 0;

  function emitChange(element) {
    const EventClass = element.ownerDocument.defaultView?.Event || Event;
    element.dispatchEvent(new EventClass("change", { bubbles: true }));
  }

  function closeControl(control, restoreFocus = false) {
    control.popup.hidden = true;
    control.trigger.setAttribute("aria-expanded", "false");
    openControls.delete(control);
    if (restoreFocus) control.trigger.focus();
  }

  function closeOthers(keep = null) {
    for (const control of openControls) {
      if (control !== keep) closeControl(control);
    }
  }

  function positionPopover(control) {
    const view = control.source.ownerDocument.defaultView;
    const triggerRect = control.trigger.getBoundingClientRect();
    const popupRect = control.popup.getBoundingClientRect();
    const popupHeight = popupRect.height || control.popup.scrollHeight || 240;
    const popupWidth = popupRect.width || control.popup.scrollWidth || triggerRect.width;
    const below = view.innerHeight - triggerRect.bottom;
    const above = triggerRect.top;
    control.popup.dataset.placement = below < popupHeight + 8 && above > below ? "top" : "bottom";
    control.popup.dataset.align = triggerRect.right + popupWidth > view.innerWidth - 12 ? "right" : "left";
  }

  function setOpen(control, open) {
    if (!open) return closeControl(control);
    closeOthers(control);
    control.popup.hidden = false;
    positionPopover(control);
    control.trigger.setAttribute("aria-expanded", "true");
    openControls.add(control);
    const options = [...control.popup.querySelectorAll("[role=option]")];
    const selected = options[control.source.selectedIndex] || options.find(option => !option.disabled);
    selected?.focus();
  }

  function refreshSelect(source) {
    const control = selectControls.get(source);
    if (!control) return;
    control.popup.replaceChildren();
    [...source.options].forEach((option, index) => {
      const item = source.ownerDocument.createElement("button");
      item.type = "button";
      item.className = "select-option";
      item.setAttribute("role", "option");
      item.setAttribute("aria-selected", String(index === source.selectedIndex));
      item.disabled = option.disabled;
      item.dataset.index = String(index);
      item.textContent = option.textContent;
      item.addEventListener("click", () => {
        if (item.disabled) return;
        source.selectedIndex = index;
        emitChange(source);
        closeControl(control, true);
      });
      control.popup.append(item);
    });
    const selected = source.options[source.selectedIndex];
    control.trigger.textContent = selected?.textContent || source.getAttribute("data-placeholder") || "请选择";
    control.trigger.disabled = source.disabled || source.options.length === 0;
    control.trigger.setAttribute("aria-label", source.getAttribute("aria-label") || control.trigger.textContent);
  }

  function enhanceSelect(source) {
    if (selectControls.has(source)) {
      refreshSelect(source);
      return selectControls.get(source);
    }
    if (!source.parentNode) return null;
    const doc = source.ownerDocument;
    const wrapper = doc.createElement("div");
    wrapper.className = "select-control";
    const trigger = doc.createElement("button");
    trigger.type = "button";
    trigger.className = "select-trigger";
    trigger.setAttribute("aria-haspopup", "listbox");
    trigger.setAttribute("aria-expanded", "false");
    const popup = doc.createElement("div");
    popup.className = "select-popover";
    popup.id = `anime-select-${++controlId}`;
    popup.setAttribute("role", "listbox");
    popup.hidden = true;
    trigger.setAttribute("aria-controls", popup.id);
    const control = { source, wrapper, trigger, popup };

    source.parentNode.insertBefore(wrapper, source);
    wrapper.append(source, trigger, popup);
    source.classList.add("select-source");
    source.tabIndex = -1;
    source.setAttribute("aria-hidden", "true");
    selectControls.set(source, control);

    trigger.addEventListener("click", () => setOpen(control, popup.hidden));
    trigger.addEventListener("keydown", event => {
      if (["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) {
        event.preventDefault();
        setOpen(control, true);
      }
    });
    popup.addEventListener("keydown", event => {
      const options = [...popup.querySelectorAll("[role=option]")].filter(option => !option.disabled);
      const current = options.indexOf(doc.activeElement);
      let next = current;
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        doc.activeElement?.click();
        return;
      }
      if (event.key === "ArrowDown") next = Math.min(options.length - 1, current + 1);
      else if (event.key === "ArrowUp") next = Math.max(0, current - 1);
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = options.length - 1;
      else if (event.key === "Escape") {
        event.preventDefault();
        closeControl(control, true);
        return;
      } else return;
      event.preventDefault();
      options[next]?.focus();
    });
    source.addEventListener("change", () => refreshSelect(source));
    refreshSelect(source);
    return control;
  }

  function dateParts(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || "");
    return match ? { year: Number(match[1]), month: Number(match[2]) - 1, day: Number(match[3]) } : null;
  }

  function dateValue(date) {
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  }

  function closeDate(control, restoreFocus = false) {
    control.popup.hidden = true;
    control.trigger.setAttribute("aria-expanded", "false");
    openControls.delete(control);
    if (restoreFocus) control.trigger.focus();
  }

  function renderCalendar(control) {
    const { source, popup } = control;
    const doc = source.ownerDocument;
    popup.replaceChildren();
    const header = doc.createElement("div");
    header.className = "date-calendar-header";
    const previous = doc.createElement("button");
    previous.type = "button";
    previous.className = "date-month-step";
    previous.setAttribute("aria-label", "上个月");
    previous.textContent = "‹";
    const title = doc.createElement("strong");
    title.textContent = `${control.monthCursor.getFullYear()}年${control.monthCursor.getMonth() + 1}月`;
    const next = doc.createElement("button");
    next.type = "button";
    next.className = "date-month-step";
    next.setAttribute("aria-label", "下个月");
    next.textContent = "›";
    header.append(previous, title, next);
    popup.append(header);

    const weekdayRow = doc.createElement("div");
    weekdayRow.className = "date-weekdays";
    for (const day of ["一", "二", "三", "四", "五", "六", "日"]) {
      const label = doc.createElement("span");
      label.textContent = day;
      weekdayRow.append(label);
    }
    popup.append(weekdayRow);

    const selected = dateParts(source.value);
    const first = new Date(control.monthCursor.getFullYear(), control.monthCursor.getMonth(), 1);
    const start = new Date(first.getFullYear(), first.getMonth(), 1 - ((first.getDay() + 6) % 7));
    const grid = doc.createElement("div");
    grid.className = "date-days";
    for (let index = 0; index < 42; index += 1) {
      const day = new Date(start.getFullYear(), start.getMonth(), start.getDate() + index);
      const button = doc.createElement("button");
      button.type = "button";
      button.className = "date-day";
      button.textContent = String(day.getDate());
      button.setAttribute("aria-label", dateValue(day));
      button.setAttribute("aria-pressed", String(Boolean(selected && selected.year === day.getFullYear() && selected.month === day.getMonth() && selected.day === day.getDate())));
      if (day.getMonth() !== control.monthCursor.getMonth()) button.classList.add("outside-month");
      button.addEventListener("click", () => {
        source.value = dateValue(day);
        refreshDate(source);
        emitChange(source);
        closeDate(control);
        control.trigger.focus();
      });
      grid.append(button);
    }
    popup.append(grid);
    previous.addEventListener("click", () => {
      control.monthCursor = new Date(control.monthCursor.getFullYear(), control.monthCursor.getMonth() - 1, 1);
      renderCalendar(control);
      positionPopover(control);
    });
    next.addEventListener("click", () => {
      control.monthCursor = new Date(control.monthCursor.getFullYear(), control.monthCursor.getMonth() + 1, 1);
      renderCalendar(control);
      positionPopover(control);
    });
  }

  function refreshDate(source) {
    const control = dateControls.get(source);
    if (!control) return;
    const date = dateParts(source.value);
    control.value.textContent = date
      ? `${date.year} / ${String(date.month + 1).padStart(2, "0")} / ${String(date.day).padStart(2, "0")}`
      : "选择上映日期";
    control.trigger.setAttribute("aria-label", date ? `上映日期 ${source.value}，更改日期` : "选择上映日期");
    control.trigger.setAttribute("aria-expanded", String(!control.popup.hidden));
  }

  function enhanceDate(source) {
    if (dateControls.has(source)) {
      refreshDate(source);
      return dateControls.get(source);
    }
    if (!source.parentNode) return null;
    const doc = source.ownerDocument;
    const wrapper = doc.createElement("div");
    wrapper.className = "date-control";
    const trigger = doc.createElement("button");
    trigger.type = "button";
    trigger.className = "date-trigger";
    trigger.setAttribute("aria-haspopup", "dialog");
    trigger.setAttribute("aria-expanded", "false");
    const value = doc.createElement("span");
    value.className = "date-value";
    const icon = doc.createElement("span");
    icon.className = "date-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = "▦";
    trigger.append(value, icon);
    const popup = doc.createElement("div");
    popup.className = "date-popover";
    popup.setAttribute("role", "dialog");
    popup.setAttribute("aria-label", "选择上映日期");
    popup.hidden = true;
    const current = dateParts(source.value) || { year: new Date().getFullYear(), month: new Date().getMonth() };
    const control = { source, wrapper, trigger, value, popup, monthCursor: new Date(current.year, current.month, 1) };
    source.parentNode.insertBefore(wrapper, source);
    wrapper.append(source, trigger, popup);
    source.classList.add("date-source");
    source.tabIndex = -1;
    source.setAttribute("aria-hidden", "true");
    dateControls.set(source, control);
    trigger.addEventListener("click", () => {
      if (!popup.hidden) {
        closeDate(control);
        return;
      }
      closeOthers(control);
      const selected = dateParts(source.value);
      if (selected) control.monthCursor = new Date(selected.year, selected.month, 1);
      renderCalendar(control);
      popup.hidden = false;
      positionPopover(control);
      trigger.setAttribute("aria-expanded", "true");
      openControls.add(control);
    });
    trigger.addEventListener("keydown", event => {
      if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        trigger.click();
      }
      if (event.key === "Escape") closeDate(control);
    });
    source.addEventListener("change", () => refreshDate(source));
    popup.addEventListener("keydown", event => {
      const active = doc.activeElement;
      if (!active.classList.contains("date-day")) return;
      if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) {
        event.preventDefault();
        const delta = event.key === "ArrowLeft" ? -1 : event.key === "ArrowRight" ? 1 : event.key === "ArrowUp" ? -7 : 7;
        const date = dateParts(active.getAttribute("aria-label"));
        if (!date) return;
        const target = dateValue(new Date(date.year, date.month, date.day + delta));
        popup.querySelector(`[aria-label="${target}"]`)?.focus();
      } else if (event.key === "Escape") {
        event.preventDefault();
        closeDate(control, true);
      }
    });
    refreshDate(source);
    return control;
  }

  function enhanceAll(root = document) {
    root.querySelectorAll("select").forEach(enhanceSelect);
    root.querySelectorAll("input.release-at").forEach(enhanceDate);
    document.documentElement.classList.add("controls-ready");
  }

  document.addEventListener("pointerdown", event => {
    for (const control of openControls) {
      if (!control.wrapper.contains(event.target) && !control.popup.contains(event.target)) {
        if (dateControls.has(control.source)) closeDate(control);
        else closeControl(control);
      }
    }
  });

  document.addEventListener("keydown", event => {
    if (event.key !== "Escape") return;
    for (const control of openControls) {
      if (dateControls.has(control.source)) closeDate(control, true);
      else closeControl(control, true);
    }
  });

  window.AnimeControls = {
    enhanceAll,
    refresh: refreshSelect,
    refreshDate,
  };
})();

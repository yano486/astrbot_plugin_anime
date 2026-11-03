(() => {
  if (window.AstrBotPluginView) return;

  async function request(path, options = {}) {
    const response = await fetch(`/api/${path}`, {
      credentials: "same-origin",
      headers: options.body ? { "Content-Type": "application/json" } : {},
      ...options,
    });
    const value = await response.json().catch(() => ({}));
    if (response.status === 401 && path !== "login") window.location.replace("/");
    if (!response.ok) throw new Error(value.error || `HTTP ${response.status}`);
    return value;
  }

  window.AstrBotPluginView = {
    ready: async () => {},
    apiGet: (path, params = {}) => {
      const query = new URLSearchParams(params);
      const suffix = query.toString();
      return request(`${path}${suffix ? `?${suffix}` : ""}`);
    },
    apiPost: (path, body) => request(path, { method: "POST", body: JSON.stringify(body) }),
  };
})();

const form = document.querySelector("#login-form");
const password = document.querySelector("#password");
const button = document.querySelector("#login-button");
const error = document.querySelector("#login-error");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  error.hidden = true;
  button.disabled = true;
  button.textContent = "正在验证…";
  try {
    const response = await fetch("/api/login", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: password.value }),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || "登录失败，请重试。");
    window.location.replace("/");
  } catch (reason) {
    error.textContent = reason.message;
    error.hidden = false;
    password.select();
  } finally {
    button.disabled = false;
    button.textContent = "登录";
  }
});

const TOKEN = "farmdss_token";
const API_BASE = String(import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

export function getToken() {
  return localStorage.getItem(TOKEN);
}

export function setToken(token) {
  localStorage.setItem(TOKEN, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN);
}

export async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body && !(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text };
  }
  if (!res.ok) {
    const detail = data?.detail;
    const msg = typeof detail === "string" ? detail : Array.isArray(detail) ? detail[0]?.msg : res.statusText;
    const err = new Error(msg || "Request failed");
    err.status = res.status;
    throw err;
  }
  return data;
}

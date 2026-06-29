const API_BASE = "http://127.0.0.1:8000";

async function request(path: string, options?: RequestInit) {
  const res = await fetch(`${API_BASE}${path}`, options);

  if (!res.ok) {
    throw new Error(`Request failed: ${res.status}`);
  }

  return res.json();
}

export async function getPending() {
  return request("/permissions/pending");
}

export async function approveCommand(cmd: string) {
  return request(`/permissions/approve?cmd=${encodeURIComponent(cmd)}`, {
    method: "POST",
  });
}

export async function denyCommand(cmd: string) {
  return request(`/permissions/deny?cmd=${encodeURIComponent(cmd)}`, {
    method: "POST",
  });
}

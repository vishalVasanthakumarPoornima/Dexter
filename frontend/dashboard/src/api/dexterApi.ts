const API_BASE = "http://127.0.0.1:8000";

async function request(path: string, options?: RequestInit) {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status}`);
  }
  return res.json();
}

export async function getStatus() {
  return request("/status");
}

export async function chat(message: string) {
  return request("/chat", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({message}),
  });
}

export async function getTools() {
  return request("/tools/list");
}

export async function auditTools() {
  return request("/tools/audit");
}

export async function getAllowedCommands() {
  return request("/tools/allowed-commands");
}

export async function searchFiles(query: string, root = "project") {
  return request(
    `/tools/search?query=${encodeURIComponent(query)}&root=${encodeURIComponent(root)}`,
  );
}

export async function readFile(path: string) {
  return request(`/tools/read-file?path=${encodeURIComponent(path)}`);
}

export async function getLogs() {
  return request("/logs");
}

export async function runTerminal(command: string) {
  return request(`/tools/terminal?command=${encodeURIComponent(command)}`);
}

export async function getDocuments() {
  return request("/documents");
}

export async function uploadDocument(file: File, kind = "resume") {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(
    `${API_BASE}/documents/upload?kind=${encodeURIComponent(kind)}`,
    {
      method: "POST",
      body: formData,
    },
  );

  if (!res.ok) {
    throw new Error(`Document upload failed: ${res.status}`);
  }

  return res.json();
}

export async function transcribeSpeech(audioBlob: Blob) {
  const formData = new FormData();
  formData.append("file", audioBlob, "dexter-dictation.webm");

  const res = await fetch(`${API_BASE}/speech/transcribe`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    throw new Error(`Speech transcription failed: ${res.status}`);
  }

  return res.json();
}

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
const ACCESS = "sl_access";
const REFRESH = "sl_refresh";

export const tokens = {
  get access() { return typeof window === "undefined" ? null : localStorage.getItem(ACCESS); },
  get refresh() { return typeof window === "undefined" ? null : localStorage.getItem(REFRESH); },
  set(access, refresh) {
    localStorage.setItem(ACCESS, access);
    if (refresh) localStorage.setItem(REFRESH, refresh);
  },
  clear() { localStorage.removeItem(ACCESS); localStorage.removeItem(REFRESH); },
};

export class ApiError extends Error {
  constructor(message, status, data) { super(message); this.status = status; this.data = data; }
}

function flatten(data) {
  if (!data) return "Une erreur est survenue.";
  if (typeof data === "string") return data;
  if (data.detail) return String(data.detail);
  return Object.entries(data)
    .map(([key, value]) => {
      const text = Array.isArray(value)
        ? value.map((v) => (typeof v === "object" ? flatten(v) : v)).join(" ")
        : typeof value === "object" ? flatten(value) : value;
      return key === "non_field_errors" ? text : `${key} : ${text}`;
    })
    .join(" — ");
}

let refreshing = null;
function refreshAccess() {
  if (!tokens.refresh) return Promise.resolve(false);
  refreshing ??= fetch(`${BASE}/auth/refresh/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh: tokens.refresh }),
  })
    .then(async (res) => {
      if (!res.ok) throw new Error("refresh failed");
      const data = await res.json();
      tokens.set(data.access, data.refresh);
      return true;
    })
    .catch(() => { tokens.clear(); return false; })
    .finally(() => { refreshing = null; });
  return refreshing;
}

async function request(path, { method = "GET", body, form, retry = true } = {}) {
  const headers = {};
  if (tokens.access) headers.Authorization = `Bearer ${tokens.access}`;
  let payload;
  if (form) payload = form;
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }

  let res;
  try {
    res = await fetch(`${BASE}${path}`, { method, headers, body: payload });
  } catch {
    throw new ApiError("Impossible de joindre le serveur. Vérifiez que le backend est lancé.", 0);
  }
  if (res.status === 401 && retry && tokens.refresh && (await refreshAccess())) {
    return request(path, { method, body, form, retry: false });
  }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(flatten(data), res.status, data);
  return data;
}

/** multipart upload with progress (fetch cannot report upload progress). */
export function upload(path, form, onProgress, retry = true) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${BASE}${path}`);
    if (tokens.access) xhr.setRequestHeader("Authorization", `Bearer ${tokens.access}`);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(Math.round((100 * e.loaded) / e.total));
    xhr.onerror = () => reject(new ApiError("Impossible de joindre le serveur. Vérifiez que le backend est lancé.", 0));
    xhr.onload = async () => {
      if (xhr.status === 401 && retry && tokens.refresh && (await refreshAccess())) {
        return resolve(upload(path, form, onProgress, false));
      }
      let data = null;
      try { data = JSON.parse(xhr.responseText); } catch {}
      if (xhr.status >= 200 && xhr.status < 300) resolve(data);
      else reject(new ApiError(flatten(data), xhr.status, data));
    };
    xhr.send(form);
  });
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: "POST", body }),
  patch: (path, body) => request(path, { method: "PATCH", body }),
  del: (path) => request(path, { method: "DELETE" }),
  form: (path, form, method = "POST") => request(path, { method, form }),
  upload,
};

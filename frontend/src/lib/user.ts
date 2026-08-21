const USER_KEY = "kpss_user_id";
const DEVICE_KEY = "tilko_device_id";

export function getUserId(): string {
  if (typeof window === "undefined") return "local";
  const existing = window.localStorage.getItem(USER_KEY);
  if (existing) return existing;
  const created = `aday-${crypto.randomUUID().slice(0, 8)}`;
  window.localStorage.setItem(USER_KEY, created);
  return created;
}

export function setUserId(userId: string) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(USER_KEY, userId);
}

export function clearUserId() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(USER_KEY);
}

export function getDeviceId(): string {
  if (typeof window === "undefined") return "device-local";
  const existing = window.localStorage.getItem(DEVICE_KEY);
  if (existing) return existing;
  const created = crypto.randomUUID();
  window.localStorage.setItem(DEVICE_KEY, created);
  return created;
}

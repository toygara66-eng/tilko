import { existsSync, mkdirSync, readFileSync, renameSync, rmSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const apiDir = join(root, "src", "app", "api");
const stashRoot = join(root, ".android-stash");
const stashDir = join(stashRoot, "api");
const envLocal = join(root, ".env.local");
const envLocalStash = join(stashRoot, "env.local");
const envProduction = join(root, ".env.production");

function readApiBase() {
  if (!existsSync(envProduction)) {
    return "https://tilko-api.onrender.com";
  }
  const text = readFileSync(envProduction, "utf8");
  const match = text.match(/^\s*NEXT_PUBLIC_API_BASE\s*=\s*(.+)\s*$/m);
  const value = (match?.[1] || "").trim().replace(/^["']|["']$/g, "");
  return value || "https://tilko-api.onrender.com";
}

function run(cmd, args, extraEnv = {}) {
  const result = spawnSync(cmd, args, {
    cwd: root,
    stdio: "inherit",
    shell: true,
    env: { ...process.env, ...extraEnv },
  });
  if ((result.status ?? 1) !== 0) {
    process.exit(result.status ?? 1);
  }
}

let movedApi = false;
let movedEnvLocal = false;
try {
  // Capacitor static export: Route Handlers desteklenmez — app dışına taşı.
  if (existsSync(apiDir)) {
    mkdirSync(stashRoot, { recursive: true });
    if (existsSync(stashDir)) {
      rmSync(stashDir, { recursive: true, force: true });
    }
    renameSync(apiDir, stashDir);
    movedApi = true;
  }
  const old = join(root, "src", "app", ".api-stashed");
  if (existsSync(old)) {
    rmSync(old, { recursive: true, force: true });
  }

  // .env.local (127.0.0.1) production APK’ya gömülmesin.
  if (existsSync(envLocal)) {
    mkdirSync(stashRoot, { recursive: true });
    if (existsSync(envLocalStash)) {
      rmSync(envLocalStash, { force: true });
    }
    renameSync(envLocal, envLocalStash);
    movedEnvLocal = true;
  }

  const apiBase = readApiBase();
  if (!/^https:\/\//i.test(apiBase)) {
    console.error(`Android build reddedildi: API HTTPS olmalı → ${apiBase}`);
    process.exit(1);
  }
  console.log(`Android build API: ${apiBase}`);

  run("npx", ["next", "build"], {
    NEXT_PUBLIC_API_BASE: apiBase,
  });
  run("npx", ["cap", "sync", "android"]);
} finally {
  if (movedApi && existsSync(stashDir)) {
    renameSync(stashDir, apiDir);
  }
  if (movedEnvLocal && existsSync(envLocalStash)) {
    renameSync(envLocalStash, envLocal);
  }
}

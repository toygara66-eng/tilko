import { existsSync, mkdirSync, renameSync, rmSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const apiDir = join(root, "src", "app", "api");
const stashRoot = join(root, ".android-stash");
const stashDir = join(stashRoot, "api");

function run(cmd, args) {
  const result = spawnSync(cmd, args, {
    cwd: root,
    stdio: "inherit",
    shell: true,
    env: process.env,
  });
  if ((result.status ?? 1) !== 0) {
    process.exit(result.status ?? 1);
  }
}

let moved = false;
try {
  // Capacitor static export: Route Handlers desteklenmez — app dışına taşı.
  if (existsSync(apiDir)) {
    mkdirSync(stashRoot, { recursive: true });
    if (existsSync(stashDir)) {
      rmSync(stashDir, { recursive: true, force: true });
    }
    renameSync(apiDir, stashDir);
    moved = true;
  }
  const old = join(root, "src", "app", ".api-stashed");
  if (existsSync(old)) {
    rmSync(old, { recursive: true, force: true });
  }
  run("npx", ["next", "build"]);
  run("npx", ["cap", "sync", "android"]);
} finally {
  if (moved && existsSync(stashDir)) {
    renameSync(stashDir, apiDir);
  }
}

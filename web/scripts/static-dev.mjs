import { spawn } from "node:child_process";
import { existsSync, watch } from "node:fs";
import { resolve } from "node:path";

const projectRoot = process.cwd();
const astroCli = resolve(projectRoot, "node_modules/astro/astro.js");
const sourcePaths = ["src", "public", "astro.config.mjs", "package.json"];
const previewArgs = process.argv.slice(2);

let buildProcess;
let previewProcess;
let rebuildQueued = false;
let rebuildTimer;
let stopping = false;
const watchers = [];

function startPreview() {
  if (previewProcess) return;

  previewProcess = spawn(process.execPath, [astroCli, "preview", ...previewArgs], {
    cwd: projectRoot,
    stdio: "inherit",
  });
}

function build() {
  buildProcess = spawn(process.execPath, [astroCli, "build"], {
    cwd: projectRoot,
    stdio: "inherit",
  });

  buildProcess.on("exit", (code) => {
    buildProcess = undefined;
    if (code === 0) startPreview();
    if (rebuildQueued && !stopping) {
      rebuildQueued = false;
      build();
    }
  });
}

function requestRebuild() {
  clearTimeout(rebuildTimer);
  rebuildTimer = setTimeout(() => {
    if (buildProcess) {
      rebuildQueued = true;
      return;
    }
    build();
  }, 150);
}

for (const path of sourcePaths) {
  const absolutePath = resolve(projectRoot, path);
  if (existsSync(absolutePath)) watchers.push(watch(absolutePath, { recursive: true }, requestRebuild));
}

function stop() {
  stopping = true;
  clearTimeout(rebuildTimer);
  watchers.forEach((watcher) => watcher.close());
  buildProcess?.kill();
  previewProcess?.kill();
  setTimeout(() => process.exit(0), 100).unref();
}

process.on("SIGINT", stop);
process.on("SIGTERM", stop);

build();

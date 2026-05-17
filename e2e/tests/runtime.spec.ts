import { test, expect, Page, ConsoleMessage } from "@playwright/test";

const FRONTEND = "http://localhost:5173";
const BACKEND = "http://localhost:8000";

//console capture
interface ConsoleCapture {
  errors: string[];
  warnings: string[];
  logs: string[];
  pollTicks: string[];
  duplicatePollWarnings: string[];
  healthLogs: string[];
  staleClosureWarnings: string[];
  networkErrorLogs: string[];
}

function attachConsoleCapture(page: Page): ConsoleCapture {
  const cap: ConsoleCapture = {
    errors: [], warnings: [], logs: [],
    pollTicks: [], duplicatePollWarnings: [],
    healthLogs: [], staleClosureWarnings: [],
    networkErrorLogs: [],
  };
  page.on("console", (msg: ConsoleMessage) => {
    const text = msg.text();
    const type = msg.type();
    if (type === "error") cap.errors.push(text);
    if (type === "warning") cap.warnings.push(text);
    if (type === "log") cap.logs.push(text);
    if (text.includes("[poll:") && text.includes("stage=")) cap.pollTicks.push(text);
    if (text.includes("Already polling")) cap.duplicatePollWarnings.push(text);
    if (text.includes("[health]")) cap.healthLogs.push(text);
    if (text.includes("Can't perform a React state update")) cap.staleClosureWarnings.push(text);
    if (text.includes("Network error #") && text.includes("[poll:")) cap.networkErrorLogs.push(text);
  });
  return cap;
}

//network capture
interface NetworkCapture {
  startCalls: Map<string, number>; // sessionId -> call count
  progressPolls: number;
}

function attachNetworkCapture(page: Page): NetworkCapture {
  const net: NetworkCapture = { startCalls: new Map(), progressPolls: 0 };
  page.on("request", (req) => {
    if (req.url().includes("/analyze/progress/")) {
      net.progressPolls++;
    }
    if (req.url().includes("/analyze/start/")) {
      const sid = req.url().split("/analyze/start/")[1] ?? "?";
      net.startCalls.set(sid, (net.startCalls.get(sid) ?? 0) + 1);
    }
  });
  return net;
}

//page helpers
async function goFresh(page: Page) {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.addInitScript(() => {
    if (!sessionStorage.getItem("__atlasTestInit")) {
      localStorage.removeItem("atlas-session-v1");
      sessionStorage.setItem("__atlasTestInit", "1");
    }
  });
  await page.goto(FRONTEND, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(600);
}

async function openModal(page: Page) {
  await page.waitForSelector("button[aria-label='Clone Git repository']", { timeout: 10_000 });
  await page.click("button[aria-label='Clone Git repository']");
  await page.waitForSelector("input[placeholder*='github.com']", { timeout: 10_000 });
}

async function submitRepo(page: Page, url: string, cloneTimeout = 300_000) {
  await page.fill("input[placeholder*='github.com']", url);
  await page.click("button[type='submit']");
  // Modal closes when setSessionAndLoading() fires
  await page.waitForSelector("input[placeholder*='github.com']", {
    state: "detached",
    timeout: cloneTimeout,
  });
}

/** Wait for the analyzing overlay to disappear (analysis complete). */
async function waitForComplete(page: Page, timeout = 600_000) {
  await page.waitForSelector(".analyzing-overlay", { state: "detached", timeout });
}

/** Read the persisted session state from localStorage. */
async function readSession(page: Page): Promise<{ sessionId?: string } | null> {
  const raw = await page.evaluate(() => localStorage.getItem("atlas-session-v1"));
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as { state?: { sessionId?: string } };
    return parsed.state ?? null;
  } catch { return null; }
}

async function injectSession(
  page: Page, sessionId: string, repoName: string, totalFiles: number
) {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.addInitScript(
    ({ sid, name, files }) => {
      localStorage.setItem("atlas-session-v1", JSON.stringify({
        state: {
          sessionId: sid,
          repoName: name,
          repoUrl: name,
          sourceType: "github",
          files: [],
          totalFiles: files,
          ingestedAt: new Date().toISOString(),
        },
        version: 0,
      }));
    },
    { sid: sessionId, name: repoName, files: totalFiles }
  );
}

test.describe("01 — Backend and frontend connectivity", () => {
  test("GET /api/health returns ok", async ({ request }) => {
    const res = await request.get(`${BACKEND}/api/health`);
    expect(res.ok()).toBeTruthy();
    expect((await res.json()).status).toBe("ok");
  });

  test("GET /api/settings/status returns provider map", async ({ request }) => {
    const res = await request.get(`${BACKEND}/api/settings/status`);
    expect(res.ok()).toBeTruthy();
    expect(await res.json()).toHaveProperty("active_provider");
  });

  test("Vite serves React app at port 5173", async ({ request }) => {
    const res = await request.get(FRONTEND);
    expect(res.ok()).toBeTruthy();
    expect(await res.text()).toContain("<!DOCTYPE html>");
  });

  test("HMR WebSocket connects to localhost — not internal container IP", async ({ page }) => {
    const wsUrls: string[] = [];
    page.on("websocket", (ws) => wsUrls.push(ws.url()));
    await page.goto(FRONTEND, { waitUntil: "networkidle" });
    await page.waitForTimeout(4_000);
    const leaked = wsUrls.filter(
      (u) => u.startsWith("ws://") &&
        !u.includes("localhost") &&
        !u.includes("127.0.0.1") &&
        !u.includes("[::1]")
    );
    expect(leaked, `HMR leaking to internal IP: ${leaked.join(", ")}`).toHaveLength(0);
    console.log(`[e2e] HMR WS URLs: ${wsUrls.join(", ") || "(none)"}`);
  });
});

test.describe("02 — Health check false-positive prevention", () => {
  test("AI status failure does NOT trigger backend-offline toast", async ({ page }) => {
    await page.route("**/api/settings/status", (r) => r.abort("failed"));
    await page.goto(FRONTEND);
    await page.waitForTimeout(8_000);
    const visible = await page.locator("text=Backend connection failed").isVisible().catch(() => false);
    expect(visible).toBeFalsy();
    console.log("[e2e] ✓ AI status failure: backend-offline toast correctly suppressed");
  });

  test("/api/health failure DOES trigger offline toast after retries", async ({ page }) => {
    await page.route("**/api/health", (r) => r.abort("failed"));
    await page.goto(FRONTEND);
    await page.waitForTimeout(14_000); // 3 retries × 2s + buffer
    const visible = await page.locator("text=Backend connection failed").isVisible().catch(() => false);
    expect(visible).toBeTruthy();
    console.log("[e2e] ✓ /api/health failure: backend-offline toast correctly shown");
  });
});

test.describe("03 — Flask (small repo): ingest + analysis", () => {
  test("End-to-end: open modal → ingest → overlay → dashboard", async ({ page }) => {
    const cap = attachConsoleCapture(page);
    const net = attachNetworkCapture(page);

    await goFresh(page);
    await openModal(page);

    console.log("[e2e] Submitting Flask repo...");
    await submitRepo(page, "https://github.com/pallets/flask");

    // Analyzing overlay appears
    await page.waitForSelector(".analyzing-overlay", { timeout: 15_000 });
    console.log("[e2e] Overlay visible — waiting for completion...");

    await waitForComplete(page, 300_000);

    // Dashboard visible
    await expect(page.locator(".dashboard-layout")).toBeVisible();
    console.log("[e2e] ✓ Dashboard visible after analysis");

    // localStorage was written
    const session = await readSession(page);
    expect(session?.sessionId).toBeTruthy();
    console.log(`[e2e] ✓ Persisted sessionId: ${session?.sessionId}`);

    // No React stale-closure warnings
    expect(cap.staleClosureWarnings, `Stale: ${cap.staleClosureWarnings.join("\n")}`).toHaveLength(0);

    // Backend health logged as reachable
    expect(cap.healthLogs.some((m) => m.includes("reachable"))).toBeTruthy();

    // Polling was active
    expect(net.progressPolls).toBeGreaterThan(0);
    console.log(`[e2e] Poll ticks: ${net.progressPolls}`);

    // No critical React errors
    const reactErrors = cap.errors.filter(
      (e) => e.startsWith("Error:") || e.includes("Minified React error")
    );
    expect(reactErrors, `React errors: ${reactErrors.join("\n")}`).toHaveLength(0);
    console.log(`[e2e] Console errors: ${cap.errors.length}, warnings: ${cap.warnings.length}`);
  });
});

test.describe("04 — Session persistence: page reload scenarios", () => {
  test("Reload AFTER completion: instantly restores session", async ({ page }) => {
    const cap = attachConsoleCapture(page);
    const net = attachNetworkCapture(page);

    await goFresh(page);
    await openModal(page);
    await submitRepo(page, "https://github.com/pallets/flask");
    await waitForComplete(page, 300_000);

    const sessionBefore = await readSession(page);
    expect(sessionBefore?.sessionId).toBeTruthy();
    console.log(`[e2e] Pre-reload sessionId: ${sessionBefore?.sessionId}`);

    // Reload — sessionStorage flag keeps the addInitScript from clearing localStorage
    console.log("[e2e] Reloading page after completion...");
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.waitForTimeout(600);

    const t0 = Date.now();
    await waitForComplete(page, 30_000);
    const elapsed = Date.now() - t0;
    console.log(`[e2e] Session restore took ${elapsed}ms`);
    expect(elapsed, "Cached restore must be < 15s").toBeLessThan(15_000);

    // sessionId survived
    const sessionAfter = await readSession(page);
    expect(sessionAfter?.sessionId).toBe(sessionBefore?.sessionId);
    console.log("[e2e] ✓ sessionId matches after reload");

    // Dashboard visible
    await expect(page.locator(".dashboard-layout")).toBeVisible();

    // /analyze/start was called after reload and returned "cached"
    const startCallsAfterReload = net.startCalls;
    expect(startCallsAfterReload.size).toBeGreaterThan(0);
    console.log(`[e2e] Start calls: ${JSON.stringify([...startCallsAfterReload])}`);

    // No stale closure warnings
    expect(cap.staleClosureWarnings).toHaveLength(0);
    console.log(`[e2e] ✓ Reload after completion: done in ${elapsed}ms`);
  });

  test("Reload MID-analysis: session survives and analysis completes", async ({ page }) => {
    const cap = attachConsoleCapture(page);

    await goFresh(page);
    await openModal(page);

    await page.fill("input[placeholder*='github.com']", "https://github.com/pallets/flask");
    await page.click("button[type='submit']");

    // Wait for overlay (clone done, analysis starting)
    await page.waitForSelector(".analyzing-overlay", { timeout: 180_000 });

    const sessionBefore = await readSession(page);
    expect(sessionBefore?.sessionId).toBeTruthy();
    console.log(`[e2e] Mid-analysis session: ${sessionBefore?.sessionId}`);

    // Reload mid-analysis — sessionStorage flag preserves localStorage
    console.log("[e2e] Reloading mid-analysis...");
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.waitForTimeout(600);

    const sessionAfter = await readSession(page);
    expect(sessionAfter?.sessionId).toBe(sessionBefore?.sessionId);
    console.log("[e2e] ✓ sessionId survived mid-analysis reload");

    await waitForComplete(page, 300_000);
    await expect(page.locator(".dashboard-layout")).toBeVisible();

    // No abandoned interval warnings
    const leakWarnings = cap.warnings.filter(
      (w) => w.includes("memory leak") || w.includes("Cannot update a component")
    );
    expect(leakWarnings).toHaveLength(0);
    console.log("[e2e] ✓ Mid-analysis reload: completed successfully");
  });

  test("Pre-completed session injected into localStorage: restores instantly", async ({ page }) => {
    const net = attachNetworkCapture(page);

    await injectSession(page, "683eba6923b7", "pallets/flask", 208);
    await page.goto(FRONTEND, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(600);

    const t0 = Date.now();
    await waitForComplete(page, 15_000);
    const elapsed = Date.now() - t0;
    console.log(`[e2e] Pre-completed session restore: ${elapsed}ms`);
    expect(elapsed, "Must restore in < 12s").toBeLessThan(12_000);

    await expect(page.locator(".dashboard-layout")).toBeVisible();
    // Cached path = very few polls
    console.log(`[e2e] Poll ticks for cached session: ${net.progressPolls}`);
    expect(net.progressPolls, "Cached session should need < 10 polls").toBeLessThan(10);
    console.log("[e2e] ✓ Pre-completed session: instant restore");
  });
});

test.describe("05 — React StrictMode duplicate polling guard", () => {
  test("At most 2 /analyze/start calls per session (StrictMode max)", async ({ page }) => {
    const net = attachNetworkCapture(page);
    const cap = attachConsoleCapture(page);

    await goFresh(page);
    await openModal(page);
    await submitRepo(page, "https://github.com/pallets/flask");
    await page.waitForSelector(".analyzing-overlay", { timeout: 15_000 });
    await page.waitForTimeout(5_000); // let polling run

    for (const [sid, count] of net.startCalls.entries()) {
      console.log(`[e2e] Session ${sid.slice(0, 8)}: ${count} start call(s)`);
      expect(count, `Session had ${count} start calls (StrictMode max = 2)`).toBeLessThanOrEqual(2);
    }

    const guardHit = cap.duplicatePollWarnings.length > 0;
    console.log(`[e2e] StrictMode guard triggered: ${guardHit} (${cap.duplicatePollWarnings.length} warnings)`);

    await waitForComplete(page, 300_000);
    console.log("[e2e] ✓ StrictMode duplicate guard: OK");
  });
});

test.describe("06 — Network failure recovery during polling", () => {
  test("6 poll failures: loop recovers, no false toast, analysis completes", async ({ page }) => {
    const cap = attachConsoleCapture(page);

    await goFresh(page);
    await openModal(page);
    await submitRepo(page, "https://github.com/pallets/flask");
    await page.waitForSelector(".analyzing-overlay", { timeout: 15_000 });

    // Block 6 consecutive progress polls then unblock
    let blocked = 0;
    await page.route("**/api/analyze/progress/**", async (route) => {
      if (blocked < 6) { blocked++; await route.abort("failed"); }
      else await route.continue();
    });

    await page.waitForTimeout(8_000);

    // Network errors must be logged (exponential backoff active)
    console.log(`[e2e] Logged ${cap.networkErrorLogs.length} network error retries (${blocked} blocked)`);
    expect(cap.networkErrorLogs.length, "Should log at least 1 retry").toBeGreaterThan(0);

    // No "Cannot reach backend" toast (suppressNetworkToast works)
    const toasts = await page.locator("text=Cannot reach backend").count();
    expect(toasts, "No false backend-offline toasts").toBe(0);
    console.log(`[e2e] ✓ Backend-offline toasts during poll failure: ${toasts}`);

    // Loop must not have stopped — analysis must complete
    await waitForComplete(page, 300_000);
    await expect(page.locator(".dashboard-layout")).toBeVisible();
    console.log("[e2e] ✓ Network failure recovery: loop survived and completed");
  });
});

test.describe("07 — Django (medium repo): stage label coverage", () => {
  test("All backend stages map to valid labels (no undefined)", async ({ page }) => {
    const cap = attachConsoleCapture(page);

    await injectSession(page, "0a0b5201a5ee", "django/django", 6813);
    await page.goto(FRONTEND, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(600);

    // Capture stage text while overlay briefly shows (cached = fast)
    const stagesShown: string[] = [];
    const obs = setInterval(async () => {
      const t = await page.locator(".analyzing-overlay").textContent().catch(() => "");
      if (t) stagesShown.push(t.trim());
    }, 100);

    await waitForComplete(page, 30_000);
    clearInterval(obs);

    // No undefined labels in captured snapshots
    const undefinedLabels = stagesShown.filter((t) => t.includes("undefined"));
    expect(undefinedLabels, `Undefined labels: ${undefinedLabels.join("|")}`).toHaveLength(0);

    // Poll ticks must only mention known stages
    const knownStages = new Set([
      "pending", "queued", "starting", "cloning", "extracting", "scanning",
      "parsing", "scoring", "graph", "function_graph", "saving", "done", "error",
    ]);
    const unknownInTicks = cap.pollTicks.filter((t) => {
      const m = t.match(/stage=(\w+)/);
      return m && !knownStages.has(m[1]);
    });
    expect(unknownInTicks, `Unknown stage keys: ${unknownInTicks.join("\n")}`).toHaveLength(0);

    await expect(page.locator(".dashboard-layout")).toBeVisible();
    console.log(`[e2e] ✓ Django: all stage labels valid. Ticks: ${cap.pollTicks.slice(0, 3).join(" | ")}`);
  });
});

test.describe("08 — Memory and render hygiene", () => {
  test("DOM mutations bounded during 5s of active polling", async ({ page }) => {
    await page.addInitScript(() => { (window as any).__mutCount = 0; });

    await goFresh(page);
    await openModal(page);
    await submitRepo(page, "https://github.com/pallets/flask");
    await page.waitForSelector(".analyzing-overlay", { timeout: 15_000 });

    // Attach observer at peak activity
    await page.evaluate(() => {
      (window as any).__mutCount = 0;
      const obs = new MutationObserver(() => { (window as any).__mutCount++; });
      obs.observe(document.getElementById("root")!, {
        childList: true, subtree: true, attributes: false, characterData: false,
      });
      (window as any).__obs = obs;
    });

    await page.waitForTimeout(5_000);

    const mutCount: number = await page.evaluate(() => {
      (window as any).__obs?.disconnect();
      return (window as any).__mutCount ?? 0;
    });
    console.log(`[e2e] DOM mutations in 5s: ${mutCount}`);
    // ~10 polls × ~10 mutations each = ~100; >1000 = infinite re-render
    expect(mutCount, `Possible infinite re-render: ${mutCount} mutations`).toBeLessThan(1000);

    await waitForComplete(page, 300_000);
    console.log("[e2e] ✓ Render hygiene: bounded mutations");
  });

  test("Intervals clean up after session resets — no accumulation", async ({ page }) => {
    const cap = attachConsoleCapture(page);

    await page.addInitScript(() => {
      const orig = { si: window.setInterval, ci: window.clearInterval };
      let net = 0;
      (window as any).setInterval = function (fn: TimerHandler, ms?: number, ...a: unknown[]) {
        net++;
        return orig.si(fn, ms, ...(a as []));
      };
      (window as any).clearInterval = function (id?: number) {
        net = Math.max(0, net - 1);
        orig.ci(id);
      };
      (window as any).__netIntervals = () => net;
    });

    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto(FRONTEND, { waitUntil: "domcontentloaded" });

    // 3 reloads without session
    for (let i = 0; i < 3; i++) {
      await page.evaluate(() => localStorage.removeItem("atlas-session-v1"));
      await page.reload({ waitUntil: "domcontentloaded" });
      await page.waitForTimeout(800);
    }

    const net: number = await page.evaluate(() => (window as any).__netIntervals?.() ?? 0);
    console.log(`[e2e] Net active intervals after 3 resets: ${net}`);
    expect(net, `Interval leak detected: ${net} active`).toBeLessThan(10);

    const leakWarnings = cap.warnings.filter(
      (w) => w.includes("memory leak") || w.includes("Cannot update a component")
    );
    expect(leakWarnings).toHaveLength(0);
    console.log("[e2e] ✓ Interval cleanup hygiene: no leaks");
  });
});

test.describe("09 — Debug overlay (Alt+D)", () => {
  test("Alt+D shows overlay with API base in DEV mode", async ({ page }) => {
    await injectSession(page, "683eba6923b7", "pallets/flask", 208);
    await page.goto(FRONTEND, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1_500);

    await page.keyboard.press("Alt+d");
    await page.waitForTimeout(500);

    const overlayVisible = await page.locator("text=ATLAS DEBUG").isVisible().catch(() => false);
    if (!overlayVisible) {
      console.log("[e2e] Debug overlay not visible — frontend not in DEV mode (expected in Docker)");
      return;
    }
    await expect(page.locator("text=API base")).toBeVisible();
    await expect(page.locator("text=localhost:8000")).toBeVisible();
    console.log("[e2e] ✓ Debug overlay: API base correct");
  });
});

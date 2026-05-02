interface ProfilerEntry {
  readonly timestamp: number;
  readonly durationMs: number;
}

export interface ProfilerStats {
  readonly callsPerSec: number;
  readonly avgMs: number;
  readonly lastCallCount: number;
}

export interface Profiler {
  measure<T>(fn: () => T): T;
  getStats(): ProfilerStats;
  reset(): void;
  /** For array-returning functions: record the result length so getStats().lastCallCount reflects it. */
  setLastResultCount(n: number): void;
}

const WINDOW_MS = 1000;

function createProfilerDev(_name: string): Profiler {
  const buffer: ProfilerEntry[] = [];
  let lastResultCount = 0;

  function pruneWindow(now: number): void {
    const cutoff = now - WINDOW_MS;
    let i = 0;
    while (i < buffer.length && (buffer[i] as ProfilerEntry).timestamp < cutoff) i++;
    if (i > 0) buffer.splice(0, i);
  }

  return {
    measure<T>(fn: () => T): T {
      const start = performance.now();
      const result = fn();
      const end = performance.now();
      pruneWindow(end);
      buffer.push({ timestamp: end, durationMs: end - start });
      return result;
    },

    getStats(): ProfilerStats {
      const now = performance.now();
      pruneWindow(now);
      const count = buffer.length;
      const avgMs =
        count > 0
          ? buffer.reduce((sum, e) => sum + e.durationMs, 0) / count
          : 0;
      return { callsPerSec: count, avgMs, lastCallCount: lastResultCount };
    },

    reset(): void {
      buffer.length = 0;
      lastResultCount = 0;
    },

    setLastResultCount(n: number): void {
      lastResultCount = n;
    },
  };
}

const noopProfiler: Profiler = {
  measure<T>(fn: () => T): T {
    return fn();
  },
  getStats(): ProfilerStats {
    return { callsPerSec: 0, avgMs: 0, lastCallCount: 0 };
  },
  reset(): void {},
  setLastResultCount(_n: number): void {},
};

export function createProfiler(name: string): Profiler {
  return import.meta.env.DEV ? createProfilerDev(name) : noopProfiler;
}

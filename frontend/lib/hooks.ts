"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { ApiError, configError } from "./api";

export interface ApiState<T> {
  data: T | null; // last good data (kept while refetching)
  error: ApiError | null;
  loading: boolean;
  refetch: () => void;
}

interface Settled<T> {
  token: string;
  data: T | null;
  error: ApiError | null;
}

/**
 * Fetches on mount and whenever `key` changes. Aborts on unmount / key change.
 * Pass fetcher=null to skip. `key` must encode every input of the fetcher.
 */
export function useApi<T>(
  key: string,
  fetcher: ((signal: AbortSignal) => Promise<T>) | null,
): ApiState<T> {
  const [nonce, setNonce] = useState(0);
  const [settled, setSettled] = useState<Settled<T>>({ token: "", data: null, error: null });
  const fnRef = useRef(fetcher);
  useEffect(() => {
    fnRef.current = fetcher;
  });
  const token = `${key}#${nonce}`;
  const active = fetcher !== null;

  useEffect(() => {
    const fn = fnRef.current;
    if (!fn) return;
    const ctl = new AbortController();
    fn(ctl.signal)
      .then((data) => setSettled({ token, data, error: null }))
      .catch((e: unknown) => {
        if ((e as Error).name === "AbortError") return;
        const err = e instanceof ApiError ? e : new ApiError((e as Error).message ?? "Unknown error", 0);
        setSettled((s) => ({ token, data: s.data, error: err }));
      });
    return () => ctl.abort();
  }, [token, active]);

  const refetch = useCallback(() => setNonce((n) => n + 1), []);
  const loading = active && settled.token !== token;
  return {
    data: settled.data,
    error: loading ? null : settled.error,
    loading,
    refetch,
  };
}

export { configError };

/** Debounce a changing value (used for text search boxes). */
export function useDebounced<T>(value: T, ms = 350): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

/** localStorage wrapped in try/catch (private windows, blocked storage). */
export function readStore(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}
export function writeStore(key: string, value: string | null) {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    /* storage unavailable: ignore */
  }
}

const listeners = new Set<() => void>();

/** localStorage-backed string, SSR-safe (null on the server / first paint), shared across components. */
export function useStoredString(key: string): [string | null, (v: string | null) => void] {
  const value = useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      window.addEventListener("storage", cb);
      return () => {
        listeners.delete(cb);
        window.removeEventListener("storage", cb);
      };
    },
    () => readStore(key),
    () => null,
  );
  const set = useCallback(
    (v: string | null) => {
      writeStore(key, v);
      listeners.forEach((l) => l());
    },
    [key],
  );
  return [value, set];
}

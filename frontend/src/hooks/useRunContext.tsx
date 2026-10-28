import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { api } from "../api/client";
import type { RunIndexEntry } from "../types/api";

interface RunContextValue {
  runs: RunIndexEntry[];
  activeRunId: string | null;
  selectedRunId: string | null;
  effectiveRunId: string | null;
  loading: boolean;
  error: string | null;
  selectRun: (runId: string | null) => void;
  refreshRuns: () => Promise<RunIndexEntry[]>;
}

const STORAGE_KEY = "yottaflex.selected-run";

const RunContext = createContext<RunContextValue | null>(null);

export function RunProvider({ children }: { children: ReactNode }) {
  const [runs, setRuns] = useState<RunIndexEntry[]>([]);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(() => {
    try {
      return window.localStorage.getItem(STORAGE_KEY);
    } catch {
      return null;
    }
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refreshRuns = useCallback(async () => {
    try {
      const payload = await api.runs();
      setRuns(payload.runs);
      setActiveRunId(payload.active_run_id);
      setError(null);
      setSelectedRunId((current) => {
        if (current && !payload.runs.some((run) => run.run_id === current)) {
          return payload.active_run_id;
        }
        return current;
      });
      return payload.runs;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load runs.");
      return [];
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshRuns();
  }, [refreshRuns]);

  const selectRun = useCallback((runId: string | null) => {
    setSelectedRunId(runId);
    try {
      if (runId) window.localStorage.setItem(STORAGE_KEY, runId);
      else window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Storage may be disabled; selection still works for the session.
    }
  }, []);

  const effectiveRunId = selectedRunId ?? activeRunId;

  const value = useMemo<RunContextValue>(
    () => ({
      runs,
      activeRunId,
      selectedRunId,
      effectiveRunId,
      loading,
      error,
      selectRun,
      refreshRuns,
    }),
    [runs, activeRunId, selectedRunId, effectiveRunId, loading, error, selectRun, refreshRuns],
  );

  return <RunContext.Provider value={value}>{children}</RunContext.Provider>;
}

export function useRunContext() {
  const context = useContext(RunContext);
  if (!context) throw new Error("useRunContext must be used within RunProvider.");
  return context;
}

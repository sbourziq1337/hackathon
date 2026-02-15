import { useState, useEffect, useCallback, useMemo } from "react";
import { fetchCases, subscribeToCases, computePlaceSeverities, hospitals, DEMO_CASES, sortCasesBySeverity, assignCasesToHospitals } from "@/data/api";
import type { EmergencyCase, PlaceSeverity } from "@/data/api";

/** Merge demo cases with API cases by id; real cases override or get added. */
function mergeWithDemoCases(apiCases: EmergencyCase[]): EmergencyCase[] {
  const byId = new Map<string, EmergencyCase>(DEMO_CASES.map((c) => [c.id, c]));
  for (const c of apiCases) {
    byId.set(c.id, c);
  }
  return sortCasesBySeverity([...byId.values()]);
}

/**
 * Hook that shows 5 demo cases (2 critical, 1 severe, 1 moderate, 1 mild) and merges
 * live cases from the backend API / Telegram bot. SSE adds or updates cases in real time.
 */
export function useLiveCases() {
  const [cases, setCases] = useState<EmergencyCase[]>(DEMO_CASES);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchCases();
      setCases(mergeWithDemoCases(data));
    } catch {
      // keep demo cases on error
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Initial fetch (merges API cases with demo cases)
    refresh();

    // Poll every 10s as fallback
    const interval = setInterval(refresh, 10_000);

    // SSE: when a new call comes from Telegram bot, add or update the case
    const unsub = subscribeToCases((newCase) => {
      setCases((prev) => {
        const byId = new Map(prev.map((c) => [c.id, c]));
        byId.set(newCase.id, newCase);
        return sortCasesBySeverity([...byId.values()]);
      });
    });

    return () => {
      clearInterval(interval);
      unsub();
    };
  }, [refresh]);

  const placeSeverities: PlaceSeverity[] = computePlaceSeverities(cases);

  /** Cases with assignedHospital set (nearest hospital with capacity + required services). */
  const casesWithAssignments = useMemo(
    () => assignCasesToHospitals(cases, hospitals),
    [cases, hospitals]
  );

  return { cases: casesWithAssignments, hospitals, placeSeverities, loading, refresh };
}

import { useState, useCallback } from "react";
import { severityConfig, type SeverityLevel, type EmergencyCase } from "@/data/api";
import { useLiveCases } from "@/hooks/useLiveCases";
import CaseCard from "@/components/CaseCard";
import CaseDetailModal from "@/components/CaseDetailModal";
import MapView from "@/components/MapView";
import { Activity, Loader2 } from "lucide-react";

const Index = () => {
  const { cases, hospitals, loading } = useLiveCases();
  const [selectedCase, setSelectedCase] = useState<EmergencyCase | null>(null);

  const handleCaseClick = useCallback((c: EmergencyCase) => {
    setSelectedCase(c);
  }, []);

  const countBySeverity = (sev: SeverityLevel) => cases.filter(c => c.severity === sev).length;

  return (
    <div className="h-screen flex flex-col">
      {/* Header stats */}
      <div className="border-b border-border bg-card px-6 py-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-3">
            <Activity className="w-5 h-5 text-primary" />
            <h1 className="text-lg font-bold text-foreground">Live Emergency Cases</h1>
            <span className="text-xs font-mono text-muted-foreground bg-secondary px-2 py-0.5 rounded">
              {loading ? "..." : cases.length} ACTIVE
            </span>
          </div>
          <p className="text-[10px] text-muted-foreground max-w-xl text-right">
            Victims are matched to the <strong className="text-foreground/90">nearest hospital with available capacity and required care</strong> (e.g. cardiology, trauma). If that hospital is full, the next nearest with capacity is suggested.
          </p>
          <div className="flex items-center gap-4">
            {(["critical", "severe", "moderate", "mild"] as SeverityLevel[]).map((s) => (
              <div key={s} className="flex items-center gap-1.5">
                <span className={`${severityConfig[s].className} w-5 h-5 rounded flex items-center justify-center text-[10px]`}>
                  {countBySeverity(s)}
                </span>
                <span className="text-[10px] text-muted-foreground uppercase">{s}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Cases list */}
        <div className="w-80 flex-shrink-0 border-r border-border overflow-auto p-3 space-y-2 bg-surface-overlay">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin text-primary" />
            </div>
          ) : cases.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground text-sm">
              No cases yet. Send a message to the Telegram bot to create one.
            </div>
          ) : (
            cases.map((c) => (
              <CaseCard key={c.id} caseData={c} hospitals={hospitals} onClick={handleCaseClick} />
            ))
          )}
        </div>

        {/* Map */}
        <div className="flex-1">
          <MapView cases={cases} hospitals={hospitals} onCaseClick={handleCaseClick} />
        </div>
      </div>

      <CaseDetailModal
        caseData={selectedCase}
        assignedHospital={selectedCase ? hospitals.find((h) => h.name === selectedCase.assignedHospital) ?? null : null}
        hospitals={hospitals}
        onClose={() => setSelectedCase(null)}
      />
    </div>
  );
};

export default Index;

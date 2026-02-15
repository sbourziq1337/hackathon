import { EmergencyCase, Hospital, severityConfig } from "@/data/api";
import { getDangerColor, VICTIM_COLORS } from "@/lib/dangerColors";
import { AlertTriangle, Building2, Clock } from "lucide-react";

interface CriticalCasesBoxProps {
  cases: EmergencyCase[];
  hospitals: Hospital[];
  onCaseClick: (c: EmergencyCase) => void;
}

const severityOrder = { critical: 0, severe: 1, moderate: 2, mild: 3 };

function formatTimeAgo(iso: string): string {
  const d = new Date(iso);
  const mins = Math.floor((Date.now() - d.getTime()) / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

interface HospitalCriticalSummary {
  hospital: Hospital;
  criticalCount: number;
  totalVictims: number;
  dangerVictims: number; // for color (matches map: max region victims)
  worstCase: EmergencyCase;
  grade: keyof typeof severityOrder;
}

const CriticalCasesBox = ({ cases, hospitals, onCaseClick }: CriticalCasesBoxProps) => {
  const byHospital = new Map<string, EmergencyCase[]>();
  for (const c of cases) {
    if (!c.assignedHospital) continue;
    const list = byHospital.get(c.assignedHospital) ?? [];
    list.push(c);
    byHospital.set(c.assignedHospital, list);
  }

  // Region victim counts (same as map) for consistent coloring
  const victimsByPlace = new Map<string, number>();
  cases.forEach((c) => {
    const v = victimsByPlace.get(c.placeName) ?? 0;
    victimsByPlace.set(c.placeName, v + c.numberOfPatients);
  });

  const summaries: HospitalCriticalSummary[] = hospitals
    .map((hospital) => {
      const hospitalCases = byHospital.get(hospital.name) ?? [];
      const criticalCases = hospitalCases.filter((c) => c.severity === "critical");
      const totalVictims = hospitalCases.reduce((sum, c) => sum + c.numberOfPatients, 0);
      // Danger = max region victim count (matches map: hospital + area + victims same color)
      const maxRegionVictims = Math.max(
        0,
        ...hospitalCases.map((c) => victimsByPlace.get(c.placeName) ?? 0)
      );
      const dangerVictims = maxRegionVictims > 0 ? maxRegionVictims : totalVictims;
      if (hospitalCases.length === 0) return null;

      const sorted = [...hospitalCases].sort(
        (a, b) =>
          severityOrder[a.severity] - severityOrder[b.severity] ||
          new Date(a.timeOfReport).getTime() - new Date(b.timeOfReport).getTime()
      );
      const worstCase = sorted[0];

      return {
        hospital,
        criticalCount: criticalCases.length,
        totalVictims,
        dangerVictims,
        worstCase,
        grade: worstCase.severity,
      };
    })
    .filter((s): s is HospitalCriticalSummary => s !== null);

  summaries.sort(
    (a, b) =>
      b.criticalCount - a.criticalCount ||
      b.dangerVictims - a.dangerVictims ||
      severityOrder[a.grade] - severityOrder[b.grade] ||
      new Date(a.worstCase.timeOfReport).getTime() - new Date(b.worstCase.timeOfReport).getTime()
  );

  const topHospitals = summaries.slice(0, 5);
  if (topHospitals.length === 0) return null;

  return (
    <div className="absolute top-4 right-4 w-64 bg-card/95 backdrop-blur border border-border rounded-lg shadow-lg z-[1000] overflow-hidden">
      <div className="px-3 py-2 bg-destructive/20 border-b border-border flex items-center gap-2">
        <AlertTriangle className="w-4 h-4 text-destructive flex-shrink-0" />
        <span className="text-xs font-bold text-foreground">Hospitals – Most Critical</span>
      </div>
      <div className="max-h-56 overflow-auto">
        {topHospitals.map(({ hospital, criticalCount, totalVictims, dangerVictims, worstCase, grade }) => {
          const sev = severityConfig[grade];
          const dangerKey = getDangerColor(dangerVictims);
          const dangerColor = VICTIM_COLORS[dangerKey].stroke;
          return (
            <button
              key={hospital.id}
              onClick={() => onCaseClick(worstCase)}
              className="w-full text-left px-3 py-2.5 hover:bg-secondary/50 transition-colors border-b border-border last:border-b-0 flex items-start gap-2"
            >
              <div
                className="w-1 h-12 rounded-full flex-shrink-0"
                style={{ backgroundColor: dangerColor }}
                title={`${totalVictims} victim${totalVictims !== 1 ? "s" : ""} · ${dangerKey} danger`}
              />
              <div className="flex items-start gap-2 min-w-0 flex-1">
                <Building2 className="w-4 h-4 text-primary flex-shrink-0 mt-0.5" />
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-semibold text-foreground truncate">{hospital.name}</div>
                  <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                    <span className={`${sev.className} px-1.5 py-0.5 rounded text-[10px] uppercase`}>
                      {sev.emoji} {sev.label}
                    </span>
                    <span className="text-[10px] text-muted-foreground">
                      <strong>{criticalCount}</strong> critical · <strong>{totalVictims}</strong> victim{totalVictims !== 1 ? "s" : ""}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground mt-1">
                    <Clock className="w-3 h-3 flex-shrink-0" />
                    {formatTimeAgo(worstCase.timeOfReport)} · {worstCase.placeName}
                  </div>
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};

export default CriticalCasesBox;

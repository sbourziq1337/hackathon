import { EmergencyCase, Hospital, severityConfig } from "@/data/api";
import { estimateAmbulanceEtaMinutes } from "@/lib/geo";
import { Clock, MapPin, Ambulance, Phone, Users, Building2, Hash } from "lucide-react";

const ambulanceLabel: Record<string, string> = {
  dispatched: "Dispatched",
  en_route: "En Route",
  on_scene: "On Scene",
  pending: "Pending",
};

interface CaseCardProps {
  caseData: EmergencyCase;
  hospitals: Hospital[];
  onClick: (c: EmergencyCase) => void;
  compact?: boolean;
}

const CaseCard = ({ caseData, hospitals, onClick }: CaseCardProps) => {
  const sev = severityConfig[caseData.severity];
  const time = new Date(caseData.timeOfReport);
  const minutesAgo = Math.floor((Date.now() - time.getTime()) / 60000);

  const assignedHospital = caseData.assignedHospital
    ? hospitals.find((h) => h.name === caseData.assignedHospital)
    : null;
  const etaMinutes =
    assignedHospital && caseData.ambulanceStatus !== "on_scene"
      ? estimateAmbulanceEtaMinutes(
          caseData.latitude,
          caseData.longitude,
          assignedHospital.latitude,
          assignedHospital.longitude
        )
      : null;

  return (
    <button
      onClick={() => onClick(caseData)}
      className={`w-full text-left card-glow rounded-lg bg-card p-3 transition-all hover:bg-secondary/50 ${
        caseData.severity === "critical" ? "pulse-critical" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <span className={`${sev.className} px-2 py-0.5 rounded text-[10px] uppercase tracking-wider`}>
          {sev.emoji} {sev.label}
        </span>
        <span className="text-[10px] font-mono text-muted-foreground flex items-center gap-1">
          <Clock className="w-3 h-3" />
          {minutesAgo}m ago
        </span>
      </div>

      <div className="space-y-1.5">
        <div className="flex items-center gap-1.5 text-xs text-foreground">
          <Hash className="w-3 h-3 text-primary flex-shrink-0" />
          <span className="truncate font-mono font-medium">{caseData.id}</span>
        </div>
        <div className="flex items-center gap-1.5 text-xs text-foreground">
          <MapPin className="w-3 h-3 text-primary flex-shrink-0" />
          <span className="truncate font-medium">{caseData.placeName}</span>
        </div>
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Phone className="w-3 h-3 flex-shrink-0" />
          {caseData.callerPhone}
        </div>
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Users className="w-3 h-3 flex-shrink-0" />
          {caseData.numberOfPatients} patient{caseData.numberOfPatients > 1 ? 's' : ''}
        </div>
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Building2 className="w-3 h-3 flex-shrink-0" />
          {caseData.assignedHospital ? (
            <>
              <span className="truncate">{caseData.assignedHospital}</span>
              {assignedHospital && (
                <span className="text-[10px] font-mono text-muted-foreground/80">
                  · {assignedHospital.emergencyBeds.available}/{assignedHospital.emergencyBeds.total} beds
                </span>
              )}
            </>
          ) : (
            "—"
          )}
        </div>
        <div className="flex items-center gap-1.5 text-xs">
          <Ambulance className="w-3 h-3 flex-shrink-0" />
          <span
            className={`${
              caseData.ambulanceStatus === "pending"
                ? "text-severity-severe"
                : caseData.ambulanceStatus === "on_scene"
                  ? "text-severity-mild"
                  : "text-primary"
            }`}
          >
            {caseData.ambulanceStatus === "on_scene"
              ? ambulanceLabel.on_scene
              : caseData.ambulanceStatus === "pending"
                ? ambulanceLabel.pending
                : etaMinutes != null
                  ? `${ambulanceLabel[caseData.ambulanceStatus]} · ~${etaMinutes} min`
                  : ambulanceLabel[caseData.ambulanceStatus]}
          </span>
        </div>
      </div>

      <div className="mt-2 pt-2 border-t border-border">
        <span className="text-[10px] font-mono text-muted-foreground">{caseData.id}</span>
      </div>
    </button>
  );
};

export default CaseCard;

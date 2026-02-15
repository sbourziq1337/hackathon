import * as React from "react";
import { EmergencyCase, severityConfig, getRequiredServicesForCase, findBackupHospital, type Hospital } from "@/data/api";
import { X, MapPin, Clock, User, Stethoscope, Brain, Wind, Bone, Heart, Gauge, Hash, Ambulance, Building2, Phone, Users, Bed, AlertTriangle } from "lucide-react";

const SERVICE_LABELS: Record<string, string> = {
  traumaUnit: "Trauma",
  cardiology: "Cardiology",
  pediatrics: "Pediatrics",
  neurosurgery: "Neurosurgery",
  radiology: "Radiology",
  laboratory: "Laboratory",
  pharmacy: "Pharmacy",
  burnUnit: "Burn unit",
  orthopedics: "Orthopedics",
  ophthalmology: "Ophthalmology",
};

const ambulanceLabel: Record<string, string> = {
  dispatched: "Dispatched",
  en_route: "En Route",
  on_scene: "On Scene",
  pending: "Pending",
};

type DetailRowProps = {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  valueClass?: string;
};
const DetailRow = ({ icon: Icon, label, value, valueClass }: DetailRowProps) => (
  <div className="flex items-start gap-3 py-2 border-b border-border/50 last:border-0">
    <Icon className="w-4 h-4 text-primary flex-shrink-0 mt-0.5" />
    <div className="flex-1 min-w-0">
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground block">{label}</span>
      <span className={`text-sm font-medium ${valueClass || "text-foreground"}`}>{value}</span>
    </div>
  </div>
);

const CaseDetailModal = ({
  caseData,
  assignedHospital,
  hospitals = [],
  onClose,
}: {
  caseData: EmergencyCase | null;
  assignedHospital: Hospital | null;
  hospitals?: Hospital[];
  onClose: () => void;
}) => {
  if (!caseData) return null;
  const sev = severityConfig[caseData.severity];
  const time = new Date(caseData.timeOfReport);
  const requiredServices = getRequiredServicesForCase(caseData);
  const requiredLabels = requiredServices.map((k) => SERVICE_LABELS[k] ?? k);

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-background/80 backdrop-blur-sm" onClick={onClose}>
      <div
        className="bg-card border border-border rounded-lg w-full max-w-md max-h-[85vh] overflow-auto shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 bg-card border-b border-border p-4 flex items-center justify-between z-10">
          <div className="flex items-center gap-3">
            <span className={`${sev.className} px-2.5 py-1 rounded text-xs uppercase tracking-wider`}>
              {sev.emoji} {sev.label}
            </span>
            <span className="text-xs font-mono text-muted-foreground">{caseData.id}</span>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-secondary rounded-md transition-colors">
            <X className="w-4 h-4 text-muted-foreground" />
          </button>
        </div>

        <div className="p-4 space-y-0">
          {/* Shared info */}
          <div className="mb-2">
            <span className="text-[10px] uppercase tracking-wider text-primary font-semibold">Call Information</span>
          </div>
          <DetailRow icon={Phone} label="Caller Phone" value={caseData.callerPhone} />
          <DetailRow icon={Hash} label="Case ID" value={caseData.id} />
          <DetailRow icon={Clock} label="Time of Report" value={time.toLocaleString()} />
          <DetailRow icon={MapPin} label="Location" value={`${caseData.placeName} (${caseData.latitude.toFixed(4)}, ${caseData.longitude.toFixed(4)})`} />
          <DetailRow icon={Users} label="Number of Patients" value={`${caseData.patients.length}`} />
          <DetailRow icon={Ambulance} label="Ambulance Status" value={ambulanceLabel[caseData.ambulanceStatus] || caseData.ambulanceStatus} />
          <DetailRow icon={Building2} label="Assigned Hospital" value={caseData.assignedHospital || "Not yet assigned"} />

          {requiredLabels.length > 0 && (
            <div className="pt-2">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground block mb-1">Required services (from symptoms)</span>
              <div className="flex flex-wrap gap-1.5">
                {requiredLabels.map((l) => (
                  <span key={l} className="px-2 py-0.5 rounded text-xs bg-primary/10 text-primary">
                    {l}
                  </span>
                ))}
              </div>
            </div>
          )}

          {assignedHospital && (
            <div className="mt-3 pt-3 border-t border-border">
              <span className="text-[10px] uppercase tracking-wider text-primary font-semibold block mb-2">Recommended hospital (nearest with capacity &amp; required services)</span>
              <div className="text-sm font-semibold text-foreground">{assignedHospital.name}</div>
              {assignedHospital.emergencyBeds.available <= 0 ? (
                <div className="flex items-center gap-2 mt-2 px-2.5 py-1.5 rounded-md bg-severity-critical/15 border border-severity-critical/30 text-severity-critical text-xs">
                  <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
                  At capacity — confirm availability before dispatch
                </div>
              ) : null}
              <div className="flex items-center gap-2 mt-1.5 text-xs text-muted-foreground">
                <Bed className="w-3.5 h-3.5" />
                <span>Emergency: {assignedHospital.emergencyBeds.available}/{assignedHospital.emergencyBeds.total} beds</span>
                <span>·</span>
                <span>ICU: {assignedHospital.icuBeds.available}/{assignedHospital.icuBeds.total}</span>
              </div>
              <div className="flex flex-wrap gap-1 mt-2">
                {(["traumaUnit", "cardiology", "pediatrics", "neurosurgery", "orthopedics", "burnUnit", "ophthalmology"] as const).filter((k) => assignedHospital[k]).map((k) => (
                  <span key={k} className="px-2 py-0.5 rounded text-[10px] bg-severity-mild/10 text-severity-mild">
                    {SERVICE_LABELS[k]}
                  </span>
                ))}
              </div>
              {assignedHospital.emergencyBeds.available <= 0 && (() => {
                const backup = findBackupHospital(
                  caseData.latitude, caseData.longitude,
                  hospitals,
                  assignedHospital.name,
                  caseData.numberOfPatients,
                  getRequiredServicesForCase(caseData)
                );
                return backup ? (
                  <div className="mt-3 pt-3 border-t border-border/50">
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground block mb-1">Next nearest with capacity</span>
                    <div className="text-sm font-medium text-foreground">{backup.name}</div>
                    <div className="text-xs text-muted-foreground mt-0.5">Emergency: {backup.emergencyBeds.available}/{backup.emergencyBeds.total} beds</div>
                  </div>
                ) : null;
              })()}
            </div>
          )}

          {/* Per-patient info */}
          {caseData.patients.map((patient, idx) => {
            const pSev = severityConfig[patient.severity];
            return (
              <div key={idx} className="mt-4 pt-3 border-t border-border">
                <div className="flex items-center gap-2 mb-2">
                  <User className="w-4 h-4 text-primary" />
                  <span className="text-xs font-semibold text-foreground">Patient {idx + 1}</span>
                  <span className={`${pSev.className} px-2 py-0.5 rounded text-[10px] uppercase tracking-wider`}>
                    {pSev.emoji} {pSev.label}
                  </span>
                </div>
                <div className="pl-1">
                  <DetailRow icon={User} label="Age" value={`${patient.patientAge} years`} />
                  <DetailRow icon={Stethoscope} label="Signs & Symptoms" value={patient.signsAndSymptoms.join(", ")} />
                  <DetailRow icon={Brain} label="Level of Consciousness" value={patient.levelOfConsciousness} />
                  <DetailRow icon={Wind} label="Breathing Status" value={patient.breathingStatus} />
                  <DetailRow icon={Bone} label="Trauma History" value={patient.traumaHistory} />
                  <DetailRow icon={Heart} label="Chronic Diseases" value={patient.knownChronicDiseases.join(", ")} />
                  <DetailRow
                    icon={Gauge}
                    label="Pain Score"
                    value={`${patient.painScore}/10`}
                    valueClass={patient.painScore >= 8 ? "text-severity-critical" : patient.painScore >= 5 ? "text-severity-severe" : "text-foreground"}
                  />
                  <DetailRow icon={Hash} label="Severity" value={pSev.label} />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default CaseDetailModal;

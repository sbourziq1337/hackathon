import { Link } from "react-router-dom";
import {
  hospitals,
  sortHospitalsByPreparedness,
  getTotalAvailableBeds,
  getRequiredServicesForCase,
  computeOccupancyPercentage,
  getOccupiedLevelFromPercentage,
  getEffectiveServiceAvailability,
  type Hospital,
  type EmergencyOccupiedLevel,
  type HospitalServiceKey,
} from "@/data/api";
import { useLiveCases } from "@/hooks/useLiveCases";
import {
  Building2,
  Bed,
  Heart,
  Brain,
  Baby,
  Bone,
  AlertTriangle,
  Scan,
  FlaskConical,
  Pill,
  Flame,
  Eye,
  Activity,
  MapPin,
  Phone,
  AlertCircle,
  ChevronRight,
} from "lucide-react";

const OCCUPIED_LEVEL_LABELS: Record<EmergencyOccupiedLevel, string> = {
  critical: "75–100% occupied",
  high: "50–74% occupied",
  moderate: "25–49% occupied",
  low: "0–24% occupied",
};

const serviceConfig: { key: HospitalServiceKey; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { key: "traumaUnit", label: "Trauma", icon: Bone },
  { key: "cardiology", label: "Cardiology", icon: Heart },
  { key: "pediatrics", label: "Pediatrics", icon: Baby },
  { key: "neurosurgery", label: "Neuro", icon: Brain },
  { key: "radiology", label: "Radiology", icon: Scan },
  { key: "laboratory", label: "Lab", icon: FlaskConical },
  { key: "pharmacy", label: "Pharmacy", icon: Pill },
  { key: "burnUnit", label: "Burn", icon: Flame },
  { key: "orthopedics", label: "Ortho", icon: Activity },
  { key: "ophthalmology", label: "Ophthal", icon: Eye },
];

const Hospitals = () => {
  const { cases } = useLiveCases();
  const sorted = sortHospitalsByPreparedness(hospitals);
  const criticalCases = cases.filter((c) => c.severity === "critical");

  return (
    <div className="h-screen flex flex-col">
      {/* Header */}
      <div className="border-b border-border bg-card px-6 py-3 flex-shrink-0">
        <div className="flex items-center gap-3">
          <Building2 className="w-5 h-5 text-primary" />
          <h1 className="text-lg font-bold text-foreground">Hospital Availability</h1>
          <span className="text-xs font-mono text-muted-foreground bg-secondary px-2 py-0.5 rounded">
            MARRAKECH–SAFI
          </span>
        </div>
        {/* Dispatch guide: occupancy from emergency, ICU, pediatrics, lab, pharmacy */}
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-severity-mild" />
            Low (0–24% occupied) — most prepared
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-severity-moderate" />
            Moderate (25–49%)
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-severity-severe" />
            High (50–74%)
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-severity-critical" />
            Critical (75–100%) — avoid for new cases
          </span>
          <Link
            to="/"
            className="ml-auto flex items-center gap-1 text-primary hover:underline"
          >
            View all cases on map
            <ChevronRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-6">
        {/* Critical cases → recommended hospital (for quick dispatch) */}
        {criticalCases.length > 0 && (
          <section className="mb-6">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground mb-1">
              <AlertCircle className="w-4 h-4 text-severity-critical" />
              Critical cases — recommended hospital (capacity + required services)
            </h2>
            <p className="text-[10px] text-muted-foreground mb-3">When the nearest is full, the next nearest with capacity and required care is suggested in the case detail.</p>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
              {criticalCases.map((c) => (
                <div
                  key={c.id}
                  className="rounded-lg bg-card border border-border p-3 flex flex-col gap-2"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <span className="text-[10px] font-mono text-muted-foreground block">{c.id}</span>
                      <span className="text-sm font-mono font-medium text-foreground truncate block">
                        {c.id}
                      </span>
                      <span className="text-xs text-muted-foreground flex items-center gap-1 mt-0.5">
                        <MapPin className="w-3 h-3 flex-shrink-0" />
                        {c.placeName}
                      </span>
                      <span className="text-xs text-muted-foreground flex items-center gap-1">
                        <Phone className="w-3 h-3 flex-shrink-0" />
                        {c.callerPhone}
                      </span>
                    </div>
                    <Link
                      to="/"
                      className="flex-shrink-0 text-[10px] text-primary hover:underline flex items-center gap-0.5"
                    >
                      Map
                      <ChevronRight className="w-3 h-3" />
                    </Link>
                  </div>
                  <div className="mt-1 pt-2 border-t border-border/50">
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground block mb-1">
                      Required services
                    </span>
                    <div className="flex flex-wrap gap-1">
                      {getRequiredServicesForCase(c).map((k) => {
                        const config = serviceConfig.find((s) => s.key === k);
                        const Label = config?.icon ?? Building2;
                        return (
                          <span
                            key={k}
                            className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] bg-primary/10 text-primary"
                          >
                            <Label className="w-3 h-3" />
                            {config?.label ?? k}
                          </span>
                        );
                      })}
                      {getRequiredServicesForCase(c).length === 0 && (
                        <span className="text-[10px] text-muted-foreground">General emergency</span>
                      )}
                    </div>
                    <div className="mt-2 flex items-center gap-1.5 text-sm font-semibold text-foreground">
                      <Building2 className="w-3.5 h-3.5 text-primary" />
                      {c.assignedHospital ?? "— Not assigned"}
                    </div>
                    {c.assignedHospital && (
                      <p className="text-[10px] text-muted-foreground mt-0.5">
                        Nearest with capacity and required services
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Hospital cards — sorted by most prepared first (total available beds) */}
        <section>
          <h2 className="text-sm font-semibold text-foreground mb-3">All hospitals (most prepared first)</h2>
          <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
            {sorted.map((h) => {
              const occupancyPct = computeOccupancyPercentage(h);
              const level = getOccupiedLevelFromPercentage(occupancyPct);
              const totalAvailable = getTotalAvailableBeds(h);
              const isCritical = level === "critical";

              return (
                <div
                  key={h.id}
                  className={`rounded-lg bg-card border p-5 transition-shadow hover:shadow-lg ${
                    level === "critical" ? "border-severity-critical/50" : level === "high" ? "border-severity-severe/30" : "border-border"
                  }`}
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="min-w-0">
                      <h3 className="font-semibold text-foreground text-sm truncate">{h.name}</h3>
                      <p className="text-xs text-muted-foreground font-mono mt-0.5">
                        {h.latitude.toFixed(4)}, {h.longitude.toFixed(4)}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      {isCritical && (
                        <span className="severity-badge-critical px-2 py-0.5 rounded text-[10px] flex items-center gap-1">
                          <AlertTriangle className="w-3 h-3" /> CRITICAL
                        </span>
                      )}
                      <span className="text-[10px] font-mono text-muted-foreground">
                        {totalAvailable} total available
                      </span>
                    </div>
                  </div>

                  {/* Occupancy level bar — width = occupancy % (from emergency, ICU, pediatrics, lab, pharmacy) */}
                  <div className="mb-4">
                    <div className="flex justify-between text-[10px] mb-1">
                      <span className="text-muted-foreground uppercase tracking-wider">Occupancy level</span>
                      <span
                        className={`font-mono font-bold ${
                          level === "critical"
                            ? "text-severity-critical"
                            : level === "high"
                              ? "text-severity-severe"
                              : level === "moderate"
                                ? "text-severity-moderate"
                                : "text-severity-mild"
                        }`}
                      >
                        {occupancyPct}%
                      </span>
                    </div>
                    <div className="h-2.5 rounded-full bg-secondary overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all ${
                          level === "critical"
                            ? "bg-severity-critical"
                            : level === "high"
                              ? "bg-severity-severe"
                              : level === "moderate"
                                ? "bg-severity-moderate"
                                : "bg-severity-mild"
                        }`}
                        style={{ width: `${Math.min(100, occupancyPct)}%` }}
                      />
                    </div>
                    <p className="text-[10px] text-muted-foreground mt-1">{OCCUPIED_LEVEL_LABELS[level]}</p>
                  </div>

                  {/* Beds: Emergency, ICU, Pediatrics, Lab, Pharmacy (counts only) */}
                  <div className="grid grid-cols-2 gap-3 mb-4">
                    <div className="bg-secondary/50 rounded-md p-2.5">
                      <div className="flex items-center gap-1.5 mb-1">
                        <Bed className="w-3 h-3 text-primary" />
                        <span className="text-[10px] text-muted-foreground uppercase">Emergency</span>
                      </div>
                      <span className="text-lg font-semibold text-foreground">
                        {h.emergencyBeds.available}
                        <span className="text-muted-foreground text-xs font-normal"> / {h.emergencyBeds.total}</span>
                      </span>
                    </div>
                    <div className="bg-secondary/50 rounded-md p-2.5">
                      <div className="flex items-center gap-1.5 mb-1">
                        <Bed className="w-3 h-3 text-severity-critical" />
                        <span className="text-[10px] text-muted-foreground uppercase">ICU</span>
                      </div>
                      <span className="text-lg font-semibold text-foreground">
                        {h.icuBeds.available}
                        <span className="text-muted-foreground text-xs font-normal"> / {h.icuBeds.total}</span>
                      </span>
                    </div>
                    <div className="bg-secondary/50 rounded-md p-2.5">
                      <div className="flex items-center gap-1.5 mb-1">
                        <Baby className="w-3 h-3 text-primary" />
                        <span className="text-[10px] text-muted-foreground uppercase">Pediatrics</span>
                      </div>
                      <span className="text-lg font-semibold text-foreground">
                        {h.pediatricsBeds.available}
                        <span className="text-muted-foreground text-xs font-normal"> / {h.pediatricsBeds.total}</span>
                      </span>
                    </div>
                    <div className="bg-secondary/50 rounded-md p-2.5">
                      <div className="flex items-center gap-1.5 mb-1">
                        <FlaskConical className="w-3 h-3 text-primary" />
                        <span className="text-[10px] text-muted-foreground uppercase">Lab</span>
                      </div>
                      <span className="text-lg font-semibold text-foreground">{h.labAvailable}</span>
                      <span className="text-[10px] text-muted-foreground block">slots</span>
                    </div>
                    <div className="bg-secondary/50 rounded-md p-2.5 col-span-2">
                      <div className="flex items-center gap-1.5 mb-1">
                        <Pill className="w-3 h-3 text-primary" />
                        <span className="text-[10px] text-muted-foreground uppercase">Pharmacy</span>
                      </div>
                      <span className="text-lg font-semibold text-foreground">{h.pharmacyAvailable}</span>
                      <span className="text-[10px] text-muted-foreground block">slots</span>
                    </div>
                  </div>

                  {/* Services: effective availability depends on occupancy — high occupancy → more red, low → more green */}
                  <div>
                    <span className="text-[10px] text-muted-foreground uppercase tracking-wider block mb-2">
                      Services (green = available, red = unavailable or overloaded)
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {serviceConfig.map((s) => {
                        const effectiveAvailable = getEffectiveServiceAvailability(h, occupancyPct)[s.key];
                        return (
                          <span
                            key={s.key}
                            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium ${
                              effectiveAvailable
                                ? "bg-severity-mild/15 text-severity-mild border border-severity-mild/30"
                                : "bg-severity-critical/15 text-severity-critical border border-severity-critical/30"
                            }`}
                          >
                            <s.icon className="w-3 h-3" />
                            {s.label}
                          </span>
                        );
                      })}
                    </div>
                  </div>

                  <Link
                    to="/"
                    className="mt-4 pt-3 border-t border-border flex items-center justify-center gap-1 text-xs text-primary hover:underline"
                  >
                    <MapPin className="w-3.5 h-3.5" />
                    View on map
                  </Link>
                </div>
              );
            })}
          </div>
        </section>
      </div>
    </div>
  );
};

export default Hospitals;

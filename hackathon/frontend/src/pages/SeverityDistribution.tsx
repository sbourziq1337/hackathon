import { severityConfig, type SeverityLevel } from "@/data/api";
import { useLiveCases } from "@/hooks/useLiveCases";
import { BarChart3, AlertTriangle, Clock, MapPin, Loader2, PieChart } from "lucide-react";

const SEVERITY_ORDER: SeverityLevel[] = ["critical", "severe", "moderate", "mild"];

const SeverityDistribution = () => {
  const { placeSeverities, loading } = useLiveCases();

  const sorted = [...placeSeverities].sort((a, b) => {
    if (a.isAlertZone && !b.isAlertZone) return -1;
    if (!a.isAlertZone && b.isAlertZone) return 1;
    return b.critical - a.critical || b.severe - a.severe || b.totalActiveCases - a.totalActiveCases;
  });

  return (
    <div className="h-screen flex flex-col">
      <div className="border-b border-border bg-card px-6 py-3">
        <div className="flex items-center gap-3">
          <BarChart3 className="w-5 h-5 text-primary" />
          <h1 className="text-lg font-bold text-foreground">Severity Distribution</h1>
          <span className="text-xs font-mono text-muted-foreground bg-secondary px-2 py-0.5 rounded">
            BY PLACE
          </span>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-6">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-24 text-muted-foreground">
            <Loader2 className="w-10 h-10 animate-spin text-primary mb-4" />
            <p className="text-sm">Loading cases…</p>
          </div>
        ) : sorted.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-muted-foreground">
            <PieChart className="w-12 h-12 mb-4 opacity-50" />
            <p className="text-sm font-medium text-foreground">No cases yet</p>
            <p className="text-xs mt-1">Severity distribution will appear when emergency cases are reported.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
            {sorted.map((place) => {
              const total = place.totalActiveCases || 1;
              const sumCounts = place.critical + place.severe + place.moderate + place.mild;
              return (
                <div
                  key={place.placeName}
                  className={`card-glow rounded-lg bg-card p-5 ${
                    place.isAlertZone ? "border-severity-critical/40" : ""
                  }`}
                >
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex items-center gap-2 min-w-0">
                      <MapPin className="w-4 h-4 text-primary flex-shrink-0" />
                      <h3 className="font-semibold text-foreground text-sm truncate" title={place.placeName}>
                        {place.placeName}
                      </h3>
                    </div>
                    {place.isAlertZone && (
                      <span className="severity-badge-critical px-2 py-0.5 rounded text-[10px] flex items-center gap-1 flex-shrink-0">
                        <AlertTriangle className="w-3 h-3" /> ALERT
                      </span>
                    )}
                  </div>

                  {/* Severity bars — percentages from counts; bar width uses same ratio so they sum to 100% */}
                  <div className="space-y-2.5 mb-4">
                    {SEVERITY_ORDER.map((s) => {
                      const count = place[s];
                      const pct = total > 0 ? (count / total) * 100 : 0;
                      return (
                        <div key={s} className="flex items-center gap-3">
                          <span className="text-[10px] w-16 text-muted-foreground uppercase tracking-wider flex-shrink-0">
                            {severityConfig[s].emoji} {s}
                          </span>
                          <div className="flex-1 min-w-0 h-3.5 rounded-full bg-secondary overflow-hidden">
                            <div
                              className="h-full rounded-full transition-all min-w-0"
                              style={{
                                width: `${Math.min(100, pct)}%`,
                                backgroundColor: severityConfig[s].color,
                              }}
                            />
                          </div>
                          <span className="text-xs font-mono text-foreground w-6 text-right flex-shrink-0">{count}</span>
                          <span className="text-[10px] font-mono text-muted-foreground w-9 text-right flex-shrink-0">
                            {pct.toFixed(1)}%
                          </span>
                        </div>
                      );
                    })}
                  </div>

                  {/* Total check: sum of severity counts should equal total */}
                  <div className="flex items-center justify-between pt-3 border-t border-border">
                    <div className="flex items-center gap-4">
                      <div>
                        <span className="text-[10px] text-muted-foreground uppercase block">Total cases</span>
                        <span className="stat-value text-base">{sumCounts}</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <Clock className="w-3 h-3 text-muted-foreground flex-shrink-0" />
                        <div>
                          <span className="text-[10px] text-muted-foreground uppercase block">Avg response</span>
                          <span
                            className={`stat-value text-base ${
                              place.avgResponseTimeMinutes > 15
                                ? "text-severity-critical"
                                : place.avgResponseTimeMinutes > 10
                                  ? "text-severity-severe"
                                  : "text-severity-mild"
                            }`}
                          >
                            {place.avgResponseTimeMinutes}m
                          </span>
                        </div>
                      </div>
                    </div>
                    <span className="text-[10px] font-mono text-muted-foreground flex-shrink-0">
                      {place.latitude.toFixed(2)}°N {Math.abs(place.longitude).toFixed(2)}°W
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default SeverityDistribution;

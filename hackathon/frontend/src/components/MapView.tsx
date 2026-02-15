import { useEffect, useRef, useCallback } from "react";
import { useTheme } from "next-themes";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { EmergencyCase, Hospital, severityConfig, type SeverityLevel } from "@/data/api";
import { getDangerColor, VICTIM_COLORS, type DangerColorKey } from "@/lib/dangerColors";

interface MapViewProps {
  cases: EmergencyCase[];
  hospitals: Hospital[];
  onCaseClick: (c: EmergencyCase) => void;
}

interface PlaceGroup {
  placeName: string;
  lat: number;
  lng: number;
  cases: EmergencyCase[];
  totalVictims: number;
}

function groupCasesByPlace(cases: EmergencyCase[]): PlaceGroup[] {
  const byPlace = new Map<string, EmergencyCase[]>();
  for (const c of cases) {
    const list = byPlace.get(c.placeName) ?? [];
    list.push(c);
    byPlace.set(c.placeName, list);
  }
  return Array.from(byPlace.entries()).map(([placeName, caseList]) => {
    const totalVictims = caseList.reduce((sum, c) => sum + c.numberOfPatients, 0);
    const lat = caseList.reduce((s, c) => s + c.latitude, 0) / caseList.length;
    const lng = caseList.reduce((s, c) => s + c.longitude, 0) / caseList.length;
    return { placeName, lat, lng, cases: caseList, totalVictims };
  });
}

function haversineKm(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLng = ((lng2 - lng1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLng / 2) * Math.sin(dLng / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

function findNearestHospital(lat: number, lng: number, hospitals: Hospital[]): Hospital | null {
  if (hospitals.length === 0) return null;
  let nearest = hospitals[0];
  let minDist = haversineKm(lat, lng, nearest.latitude, nearest.longitude);
  for (let i = 1; i < hospitals.length; i++) {
    const d = haversineKm(lat, lng, hospitals[i].latitude, hospitals[i].longitude);
    if (d < minDist) {
      minDist = d;
      nearest = hospitals[i];
    }
  }
  return nearest;
}

// Hospital color = worst danger among regions that assign cases to it (same as victims in that area)
function getHospitalColor(hospital: Hospital, placeGroups: PlaceGroup[]): DangerColorKey {
  let maxVictims = 0;
  for (const g of placeGroups) {
    const assignsToThis = g.cases.some((c) => c.assignedHospital === hospital.name);
    if (assignsToThis && g.totalVictims > maxVictims) maxVictims = g.totalVictims;
  }
  if (maxVictims > 0) return getDangerColor(maxVictims);
  let nearestGroup: PlaceGroup | null = null;
  let minDist = Infinity;
  for (const g of placeGroups) {
    const d = haversineKm(hospital.latitude, hospital.longitude, g.lat, g.lng);
    if (d < minDist) {
      minDist = d;
      nearestGroup = g;
    }
  }
  return nearestGroup ? getDangerColor(nearestGroup.totalVictims) : "green";
}

function createHospitalIcon(colorKey: DangerColorKey) {
  const { stroke } = VICTIM_COLORS[colorKey];
  return L.divIcon({
    className: "hospital-marker",
    html: `<div style="
      width:14px;height:14px;
      background:${stroke};
      border:2px solid ${stroke}cc;
      border-radius:2px;
      box-shadow:0 0 10px ${stroke}66;
    "></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  });
}

/** Victim marker colored by severity (red / orange / yellow / green). */
function createCaseIconBySeverity(severityColor: string) {
  return L.divIcon({
    className: "case-marker",
    html: `<div style="
      width:14px;height:14px;border-radius:50%;
      background:${severityColor};
      border:2px solid white;
      box-shadow:0 0 10px ${severityColor}, 0 0 20px ${severityColor}99;
    "></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  });
}

const DARK_TILES = "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";
const LIGHT_GRAY_TILES = "https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png";

const MapView = ({ cases, hospitals, onCaseClick }: MapViewProps) => {
  const mapRef = useRef<L.Map | null>(null);
  const tileLayerRef = useRef<L.TileLayer | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const { resolvedTheme } = useTheme();
  /** Fit bounds only once so user zoom/pan is not overwritten on every data update. */
  const initialFitDoneRef = useRef(false);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = L.map(containerRef.current, {
      center: [31.6295, -7.9811],
      zoom: 9,
      zoomControl: false,
      attributionControl: false,
    });

    L.control.zoom({ position: "bottomright" }).addTo(map);

    const isLight = resolvedTheme === "light";
    const tileLayer = L.tileLayer(isLight ? LIGHT_GRAY_TILES : DARK_TILES, {
      maxZoom: 19,
    }).addTo(map);
    tileLayerRef.current = tileLayer;
    mapRef.current = map;
    initialFitDoneRef.current = false;

    return () => {
      map.remove();
      mapRef.current = null;
      tileLayerRef.current = null;
      initialFitDoneRef.current = false;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const currentLayer = tileLayerRef.current;
    if (!map || !currentLayer || resolvedTheme === undefined) return;
    const isLight = resolvedTheme === "light";
    const url = isLight ? LIGHT_GRAY_TILES : DARK_TILES;
    map.removeLayer(currentLayer);
    const newLayer = L.tileLayer(url, { maxZoom: 19 }).addTo(map);
    tileLayerRef.current = newLayer;
  }, [resolvedTheme]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const overlayGroup = L.featureGroup();
    map.addLayer(overlayGroup);

    const placeGroups = groupCasesByPlace(cases);

    // Fit bounds only once when we first have data; never again so zoom/pan stays as the user left it
    const allPoints: [number, number][] = [
      ...cases.map((c) => [c.latitude, c.longitude] as [number, number]),
      ...hospitals.map((h) => [h.latitude, h.longitude] as [number, number]),
    ];
    if (allPoints.length > 0 && !initialFitDoneRef.current) {
      const bounds = L.latLngBounds(allPoints.map(([lat, lng]) => L.latLng(lat, lng)));
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 13 });
      initialFitDoneRef.current = true;
    }

    // Draw lines from each place group to its assigned hospital (assignment is done in useLiveCases with services + capacity)
    const severityOrder: Record<SeverityLevel, number> = { critical: 0, severe: 1, moderate: 2, mild: 3 };

    const isLightMap = resolvedTheme === "light";
    const distanceLabelColor = isLightMap ? "#1f2937" : "white";
    const distanceLabelShadow = isLightMap ? "0 1px 3px rgba(0,0,0,0.2)" : "0 2px 6px rgba(0,0,0,0.4)";

    placeGroups.forEach((group) => {
      const assignedHospitalName = group.cases[0]?.assignedHospital ?? null;
      if (!assignedHospitalName) return;
      const assignedHospital = hospitals.find((h) => h.name === assignedHospitalName);
      if (!assignedHospital) return;

      const worstSeverity: SeverityLevel = group.cases.reduce(
        (worst, c) => (severityOrder[c.severity] < severityOrder[worst] ? c.severity : worst),
        "mild" as SeverityLevel
      );
      const stroke = severityConfig[worstSeverity].color;
      const distKm = haversineKm(group.lat, group.lng, assignedHospital.latitude, assignedHospital.longitude);

      const line = L.polyline(
        [
          [group.lat, group.lng],
          [assignedHospital.latitude, assignedHospital.longitude],
        ],
        { color: stroke, weight: 2.5, opacity: 0.8, dashArray: "8, 6" }
      );

      const midLat = (group.lat + assignedHospital.latitude) / 2;
      const midLng = (group.lng + assignedHospital.longitude) / 2;
      const distLabel = L.marker([midLat, midLng], {
        icon: L.divIcon({
          className: "distance-label",
          html: `<div style="
            background:${stroke}dd;
            color:${distanceLabelColor};
            font-size:10px;
            font-weight:700;
            font-family:Inter,system-ui,sans-serif;
            padding:2px 6px;
            border-radius:4px;
            white-space:nowrap;
            box-shadow:${distanceLabelShadow};
          ">${distKm.toFixed(1)} km</div>`,
          iconSize: [60, 20],
          iconAnchor: [30, 10],
        }),
        interactive: false,
      });

      line.bindPopup(
        `<div style="font-family:Inter,sans-serif;min-width:220px;">
          <div style="font-size:13px;font-weight:700;margin-bottom:8px;">📍 ${group.placeName} → 🏥 ${assignedHospital.name}</div>
          <div style="font-size:12px;margin-bottom:4px;"><strong>${group.totalVictims}</strong> victim${group.totalVictims !== 1 ? "s" : ""}</div>
          <div style="font-size:11px;color:#94a3b8;margin-top:6px;"><strong>Distance:</strong> ${distKm.toFixed(1)} km</div>
          <div style="font-size:11px;color:#94a3b8;"><strong>Emergency beds:</strong> ${assignedHospital.emergencyBeds.available}/${assignedHospital.emergencyBeds.total}</div>
        </div>`
      );

      overlayGroup.addLayer(line);
      overlayGroup.addLayer(distLabel);
    });

    // 2. Hospital markers – colored by region danger
    hospitals.forEach((h) => {
      const colorKey = getHospitalColor(h, placeGroups);
      const marker = L.marker([h.latitude, h.longitude], { icon: createHospitalIcon(colorKey) });
      marker.bindPopup(
        `<div style="font-family:Inter,sans-serif;min-width:180px;">
          <div style="font-size:12px;font-weight:700;margin-bottom:4px;">🏥 ${h.name}</div>
          <div style="font-size:11px;color:#94a3b8;">Emergency: ${h.emergencyBeds.available}/${h.emergencyBeds.total} beds</div>
          <div style="font-size:11px;color:#94a3b8;">ICU: ${h.icuBeds.available}/${h.icuBeds.total} beds</div>
        </div>`
      );
      overlayGroup.addLayer(marker);
    });

    // 3. Case markers (victim locations) – colored by severity (red / orange / yellow / green)
    cases.forEach((c) => {
      const severityColor = severityConfig[c.severity].color;
      const marker = L.marker([c.latitude, c.longitude], { icon: createCaseIconBySeverity(severityColor) });
      const sev = severityConfig[c.severity];
      const hospitalInfo = c.assignedHospital ?? "None assigned";
      marker.bindPopup(
        `<div style="font-family:Inter,sans-serif;min-width:200px;">
          <div style="font-size:11px;font-weight:700;margin-bottom:6px;">${sev.emoji} ${sev.label.toUpperCase()}</div>
          <div style="font-size:12px;font-weight:600;margin-bottom:4px;">${c.placeName}</div>
          <div style="font-size:11px;margin-bottom:2px;"><strong>${c.numberOfPatients}</strong> victim${c.numberOfPatients !== 1 ? "s" : ""}</div>
          <div style="font-size:11px;color:#94a3b8;margin-top:4px;"><strong>Hospital:</strong> ${hospitalInfo}</div>
          <div style="font-size:10px;color:#64748b;margin-top:4px;">${c.id}</div>
        </div>`
      );
      marker.on("click", () => onCaseClick(c));
      overlayGroup.addLayer(marker);
    });

    return () => {
      map.removeLayer(overlayGroup);
    };
  }, [cases, hospitals, onCaseClick, resolvedTheme]);

  const handleFitBounds = useCallback(() => {
    const map = mapRef.current;
    if (!map) return;
    const allPoints: [number, number][] = [
      ...cases.map((c) => [c.latitude, c.longitude] as [number, number]),
      ...hospitals.map((h) => [h.latitude, h.longitude] as [number, number]),
    ];
    if (allPoints.length > 0) {
      const bounds = L.latLngBounds(allPoints.map(([lat, lng]) => L.latLng(lat, lng)));
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 13 });
    }
  }, [cases, hospitals]);

  return (
    <div className="relative w-full h-full">
      <div ref={containerRef} className="w-full h-full rounded-lg" />
      <button
        type="button"
        onClick={handleFitBounds}
        className="absolute top-4 right-4 z-[1000] rounded-lg border border-border bg-card/95 backdrop-blur px-2.5 py-1.5 text-[10px] font-medium text-foreground shadow hover:bg-secondary/80 transition-colors"
        title="Fit map to show all cases and hospitals"
      >
        Fit view
      </button>
      <div className="absolute bottom-4 left-4 bg-card/95 backdrop-blur border border-border rounded-lg px-3 py-2 shadow-lg z-[1000]">
        <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">
          Severity (victims)
        </div>
        <div className="flex flex-wrap gap-3 text-xs">
          <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-severity-critical" />Critical</span>
          <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-severity-severe" />Severe</span>
          <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-severity-moderate" />Moderate</span>
          <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-full bg-severity-mild" />Mild</span>
        </div>
        <div className="mt-2 pt-2 border-t border-border text-[10px] text-muted-foreground">
          ● Victim (by severity) &nbsp;■ Hospital &nbsp;┄ Line to recommended hospital (capacity + services)
        </div>
      </div>
    </div>
  );
};

export default MapView;

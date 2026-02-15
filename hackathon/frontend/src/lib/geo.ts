/**
 * Haversine distance in km between two lat/lng points.
 */
export function haversineKm(
  lat1: number,
  lng1: number,
  lat2: number,
  lng2: number
): number {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLng = ((lng2 - lng1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLng / 2) *
      Math.sin(dLng / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

/** Average ambulance speed (km/h) for urban/suburban roads. */
const AMBULANCE_SPEED_KMH = 45;

/**
 * Estimated minutes for ambulance to travel from victim to hospital.
 */
export function estimateAmbulanceEtaMinutes(
  victimLat: number,
  victimLng: number,
  hospitalLat: number,
  hospitalLng: number
): number {
  const km = haversineKm(victimLat, victimLng, hospitalLat, hospitalLng);
  const hours = km / AMBULANCE_SPEED_KMH;
  return Math.max(1, Math.round(hours * 60));
}

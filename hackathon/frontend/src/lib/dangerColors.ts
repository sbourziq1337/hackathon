// Danger level colors (red = most critical, green = least)
export const VICTIM_COLORS: Record<string, { fill: string; stroke: string }> = {
  red: { fill: "rgba(239, 68, 68, 0.45)", stroke: "#ef4444" },
  orange: { fill: "rgba(249, 115, 22, 0.45)", stroke: "#f97316" },
  yellow: { fill: "rgba(234, 179, 8, 0.45)", stroke: "#eab308" },
  green: { fill: "rgba(34, 197, 94, 0.45)", stroke: "#22c55e" },
};

export type DangerColorKey = keyof typeof VICTIM_COLORS;

export function getDangerColor(totalVictims: number): DangerColorKey {
  if (totalVictims >= 9) return "red";
  if (totalVictims >= 6) return "orange";
  if (totalVictims >= 3) return "yellow";
  return "green";
}

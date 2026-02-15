export type SeverityLevel = 'critical' | 'severe' | 'moderate' | 'mild';

export interface Patient {
  patientAge: number;
  signsAndSymptoms: string[];
  severity: SeverityLevel;
  levelOfConsciousness: string;
  breathingStatus: string;
  traumaHistory: string;
  knownChronicDiseases: string[];
  painScore: number;
}

export interface EmergencyCase {
  id: string;
  timeOfReport: string;
  latitude: number;
  longitude: number;
  placeName: string;
  callerPhone: string;
  patients: Patient[];
  // convenience: overall severity is the worst among patients
  severity: SeverityLevel;
  // legacy compat fields (from first patient)
  numberOfPatients: number;
  patientAge: number;
  signsAndSymptoms: string[];
  levelOfConsciousness: string;
  breathingStatus: string;
  traumaHistory: string;
  knownChronicDiseases: string[];
  painScore: number;
  ambulanceStatus: 'dispatched' | 'en_route' | 'on_scene' | 'pending';
  assignedHospital: string | null;
}

export interface Hospital {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  emergencyBeds: { available: number; total: number };
  icuBeds: { available: number; total: number };
  pediatricsBeds: { available: number; total: number };
  labAvailable: number;
  pharmacyAvailable: number;
  traumaUnit: boolean;
  cardiology: boolean;
  pediatrics: boolean;
  neurosurgery: boolean;
  radiology: boolean;
  laboratory: boolean;
  pharmacy: boolean;
  burnUnit: boolean;
  orthopedics: boolean;
  ophthalmology: boolean;
}

export interface PlaceSeverity {
  placeName: string;
  latitude: number;
  longitude: number;
  totalActiveCases: number;
  critical: number;
  severe: number;
  moderate: number;
  mild: number;
  avgResponseTimeMinutes: number;
  isAlertZone: boolean;
}

const places = [
  { name: "Jemaa el-Fnaa", lat: 31.6258, lng: -7.9891 },
  { name: "Gueliz", lat: 31.6345, lng: -8.0083 },
  { name: "Oukaimeden", lat: 31.2056, lng: -7.8600 },
  { name: "Ijoukak", lat: 31.0500, lng: -8.1500 },
  { name: "Chichaoua", lat: 31.5333, lng: -8.7667 },
  { name: "Essaouira Centre", lat: 31.5085, lng: -9.7595 },
  { name: "Sidi Youssef Ben Ali", lat: 31.6050, lng: -7.9800 },
  { name: "Medina", lat: 31.6295, lng: -7.9811 },
  { name: "Menara", lat: 31.6100, lng: -8.0200 },
  { name: "Tamansourt", lat: 31.6700, lng: -8.1200 },
];

const symptoms = [
  "Chest pain", "Difficulty breathing", "Severe headache", "Loss of consciousness",
  "Abdominal pain", "High fever", "Seizures", "Severe bleeding",
  "Fracture", "Burns", "Stroke symptoms", "Cardiac arrest",
  "Allergic reaction", "Dehydration", "Hypertension crisis", "Diabetic emergency",
];

const consciousness = ["Alert", "Verbal response", "Pain response", "Unresponsive"];
const breathing = ["Normal", "Labored", "Shallow", "Absent", "Rapid"];
const chronicDiseases = ["Diabetes", "Hypertension", "Asthma", "Heart disease", "None"];
const ambulanceStatuses: EmergencyCase['ambulanceStatus'][] = ['dispatched', 'en_route', 'on_scene', 'pending'];
const severities: SeverityLevel[] = ['critical', 'severe', 'moderate', 'mild'];

function randomFrom<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)];
}

function generateCaseId(): string {
  return `MKS-${Date.now().toString(36).toUpperCase().slice(-4)}-${Math.random().toString(36).slice(2, 5).toUpperCase()}`;
}

function generateTime(minutesAgo: number): string {
  const d = new Date(Date.now() - minutesAgo * 60000);
  return d.toISOString();
}

function generatePhone(): string {
  const prefixes = ['+212 6', '+212 7'];
  return `${randomFrom(prefixes)}${Math.floor(10000000 + Math.random() * 90000000).toString().slice(0, 8)}`;
}

const severityOrder: Record<SeverityLevel, number> = { critical: 0, severe: 1, moderate: 2, mild: 3 };

function generatePatient(baseSev: SeverityLevel): Patient {
  const sev = Math.random() > 0.6 ? baseSev : randomFrom(severities);
  const syms = Array.from({ length: 2 + Math.floor(Math.random() * 3) }, () => randomFrom(symptoms));
  return {
    patientAge: 5 + Math.floor(Math.random() * 85),
    signsAndSymptoms: [...new Set(syms)],
    severity: sev,
    levelOfConsciousness: sev === 'critical' ? randomFrom(["Pain response", "Unresponsive"]) : randomFrom(consciousness),
    breathingStatus: sev === 'critical' ? randomFrom(["Absent", "Shallow"]) : randomFrom(breathing),
    traumaHistory: Math.random() > 0.6 ? "Motor vehicle accident" : Math.random() > 0.5 ? "Fall from height" : "None",
    knownChronicDiseases: [randomFrom(chronicDiseases)],
    painScore: sev === 'critical' ? 8 + Math.floor(Math.random() * 3) : Math.floor(Math.random() * 10) + 1,
  };
}

export const mockCases: EmergencyCase[] = Array.from({ length: 24 }, (_, i) => {
  const place = places[i % places.length];
  const baseSev: SeverityLevel = i < 4 ? 'critical' : i < 9 ? 'severe' : i < 16 ? 'moderate' : 'mild';
  const numPatients = baseSev === 'critical' ? (Math.random() > 0.5 ? Math.floor(Math.random() * 3) + 2 : 1) : (Math.random() > 0.7 ? Math.floor(Math.random() * 4) + 2 : 1);
  const patients = Array.from({ length: numPatients }, () => generatePatient(baseSev));
  // overall severity = worst among patients
  const overallSev = patients.reduce((worst, p) => severityOrder[p.severity] < severityOrder[worst] ? p.severity : worst, patients[0].severity);
  const first = patients[0];
  return {
    id: generateCaseId(),
    timeOfReport: generateTime(Math.floor(Math.random() * 120)),
    latitude: place.lat + (Math.random() - 0.5) * 0.02,
    longitude: place.lng + (Math.random() - 0.5) * 0.02,
    placeName: place.name,
    callerPhone: generatePhone(),
    patients,
    severity: overallSev,
    numberOfPatients: numPatients,
    patientAge: first.patientAge,
    signsAndSymptoms: first.signsAndSymptoms,
    levelOfConsciousness: first.levelOfConsciousness,
    breathingStatus: first.breathingStatus,
    traumaHistory: first.traumaHistory,
    knownChronicDiseases: first.knownChronicDiseases,
    painScore: first.painScore,
    ambulanceStatus: randomFrom(ambulanceStatuses),
    assignedHospital: Math.random() > 0.4 ? randomFrom(["CHU Mohammed VI", "Hôpital Ibn Tofail", "Clinique Al Farabi"]) : null,
  };
}).sort((a, b) => severityOrder[a.severity] - severityOrder[b.severity]);

export const mockHospitals: Hospital[] = [
  {
    id: "h1", name: "CHU Mohammed VI", latitude: 31.6340, longitude: -8.0150,
    emergencyBeds: { available: 3, total: 30 }, icuBeds: { available: 1, total: 12 },
    pediatricsBeds: { available: 2, total: 8 }, labAvailable: 4, pharmacyAvailable: 2,
    traumaUnit: true, cardiology: true, pediatrics: true, neurosurgery: true,
    radiology: true, laboratory: true, pharmacy: true, burnUnit: true, orthopedics: true, ophthalmology: true,
  },
  {
    id: "h2", name: "Hôpital Ibn Tofail", latitude: 31.6280, longitude: -7.9920,
    emergencyBeds: { available: 8, total: 25 }, icuBeds: { available: 3, total: 8 },
    pediatricsBeds: { available: 4, total: 10 }, labAvailable: 3, pharmacyAvailable: 2,
    traumaUnit: true, cardiology: true, pediatrics: true, neurosurgery: false,
    radiology: true, laboratory: true, pharmacy: true, burnUnit: false, orthopedics: true, ophthalmology: false,
  },
  {
    id: "h3", name: "Clinique Al Farabi", latitude: 31.6400, longitude: -8.0050,
    emergencyBeds: { available: 5, total: 15 }, icuBeds: { available: 2, total: 5 },
    pediatricsBeds: { available: 0, total: 0 }, labAvailable: 2, pharmacyAvailable: 1,
    traumaUnit: false, cardiology: true, pediatrics: false, neurosurgery: false,
    radiology: true, laboratory: true, pharmacy: true, burnUnit: false, orthopedics: false, ophthalmology: true,
  },
  {
    id: "h4", name: "Hôpital Régional Essaouira", latitude: 31.5100, longitude: -9.7600,
    emergencyBeds: { available: 10, total: 20 }, icuBeds: { available: 4, total: 6 },
    pediatricsBeds: { available: 6, total: 12 }, labAvailable: 5, pharmacyAvailable: 3,
    traumaUnit: true, cardiology: false, pediatrics: true, neurosurgery: false,
    radiology: true, laboratory: true, pharmacy: true, burnUnit: false, orthopedics: true, ophthalmology: false,
  },
  {
    id: "h5", name: "Hôpital Provincial Chichaoua", latitude: 31.5340, longitude: -8.7660,
    emergencyBeds: { available: 12, total: 18 }, icuBeds: { available: 5, total: 5 },
    pediatricsBeds: { available: 5, total: 8 }, labAvailable: 4, pharmacyAvailable: 2,
    traumaUnit: false, cardiology: false, pediatrics: true, neurosurgery: false,
    radiology: false, laboratory: true, pharmacy: true, burnUnit: false, orthopedics: false, ophthalmology: false,
  },
  {
    id: "h6", name: "Clinique Yasmine", latitude: 31.6380, longitude: -7.9950,
    emergencyBeds: { available: 1, total: 10 }, icuBeds: { available: 0, total: 3 },
    pediatricsBeds: { available: 0, total: 0 }, labAvailable: 0, pharmacyAvailable: 1,
    traumaUnit: false, cardiology: true, pediatrics: false, neurosurgery: false,
    radiology: true, laboratory: false, pharmacy: true, burnUnit: false, orthopedics: false, ophthalmology: false,
  },
];

export const mockPlaceSeverities: PlaceSeverity[] = places.map((p) => {
  const casesHere = mockCases.filter(c => c.placeName === p.name);
  const critical = casesHere.filter(c => c.severity === 'critical').length;
  const severe = casesHere.filter(c => c.severity === 'severe').length;
  const moderate = casesHere.filter(c => c.severity === 'moderate').length;
  const mild = casesHere.filter(c => c.severity === 'mild').length;
  const total = casesHere.length;
  const avgResponse = total > 0 ? 4 + Math.floor(Math.random() * 20) : 0;
  const isAlert = critical / Math.max(total, 1) > 0.3 || avgResponse > 18 || total > 4;
  return {
    placeName: p.name,
    latitude: p.lat,
    longitude: p.lng,
    totalActiveCases: total,
    critical, severe, moderate, mild,
    avgResponseTimeMinutes: avgResponse,
    isAlertZone: isAlert,
  };
});

export const severityConfig: Record<SeverityLevel, { label: string; emoji: string; className: string; color: string }> = {
  critical: { label: "Critical", emoji: "🔴", className: "severity-badge-critical", color: "hsl(0 72% 51%)" },
  severe: { label: "Severe", emoji: "🟠", className: "severity-badge-severe", color: "hsl(25 95% 53%)" },
  moderate: { label: "Moderate", emoji: "🟡", className: "severity-badge-moderate", color: "hsl(45 93% 47%)" },
  mild: { label: "Mild", emoji: "🟢", className: "severity-badge-mild", color: "hsl(142 71% 45%)" },
};

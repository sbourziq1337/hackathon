import { NavLink as RouterNavLink, Outlet } from "react-router-dom";
import { useTheme } from "next-themes";
import { Activity, Building2, BarChart3, Mic, AlertTriangle, LogOut, User, Sun, Moon } from "lucide-react";

const navItems = [
  { to: "/", label: "Live Cases", icon: Activity },
  { to: "/hospitals", label: "Hospitals", icon: Building2 },
  { to: "/severity", label: "Distribution", icon: BarChart3 },
  { to: "/voice-triage", label: "Voice Triage", icon: Mic },
];

interface LayoutProps {
  user?: { fullName: string; role: string; organization: string };
  onLogout?: () => void;
}

const Layout = ({ user, onLogout }: LayoutProps) => {
  const { theme, setTheme } = useTheme();

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Sidebar */}
      <aside className="w-64 flex-shrink-0 border-r border-border bg-sidebar flex flex-col">
        <div className="p-5 border-b border-border">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-primary/20 flex items-center justify-center">
              <AlertTriangle className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h1 className="text-sm font-bold text-foreground tracking-tight">2020 AI AGENT</h1>
              <p className="text-[10px] font-mono text-muted-foreground tracking-widest">MARRAKECH–SAFI</p>
            </div>
          </div>
        </div>

        <nav className="flex-1 p-3 space-y-1">
          {navItems.map((item) => (
            <RouterNavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                `nav-link ${isActive ? "nav-link-active" : ""}`
              }
            >
              <item.icon className="w-4 h-4" />
              {item.label}
            </RouterNavLink>
          ))}
        </nav>

        {/* Theme toggle */}
        <div className="p-3 border-t border-border">
          <button
            type="button"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            className="w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-secondary/50 transition-colors"
            title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          >
            {theme === "dark" ? (
              <Sun className="w-4 h-4" />
            ) : (
              <Moon className="w-4 h-4" />
            )}
            {theme === "dark" ? "Light mode" : "Dark mode"}
          </button>
        </div>

        {/* User info + logout */}
        {user && (
          <div className="p-3 border-t border-border">
            <div className="flex items-center gap-2 px-2 py-2">
              <div className="w-7 h-7 rounded-full bg-primary/20 flex items-center justify-center flex-shrink-0">
                <User className="w-3.5 h-3.5 text-primary" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-xs font-semibold text-foreground truncate">{user.fullName}</div>
                <div className="text-[10px] text-muted-foreground truncate">{user.role} · {user.organization}</div>
              </div>
            </div>
            <button
              onClick={onLogout}
              className="w-full mt-1 flex items-center gap-2 px-3 py-2 text-xs text-muted-foreground hover:text-foreground hover:bg-secondary/50 rounded-md transition-colors"
            >
              <LogOut className="w-3.5 h-3.5" />
              Sign Out
            </button>
          </div>
        )}

        <div className="p-4 border-t border-border">
          <div className="flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-severity-mild opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-severity-mild" />
            </span>
            <span className="text-xs font-mono text-muted-foreground">SYSTEM ONLINE</span>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
};

export default Layout;

import { useState } from "react";
import { ThemeProvider } from "next-themes";
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Layout from "@/components/Layout";
import Index from "./pages/Index";
import Hospitals from "./pages/Hospitals";
import SeverityDistribution from "./pages/SeverityDistribution";
import VoiceTriage from "./pages/VoiceTriage";
import NotFound from "./pages/NotFound";
import Login from "./pages/Login";

const queryClient = new QueryClient();

const App = () => {
  const [auth, setAuth] = useState<{ token: string; fullName: string; role: string; organization: string } | null>(() => {
    const saved = sessionStorage.getItem("auth");
    return saved ? JSON.parse(saved) : null;
  });

  const handleLogin = (token: string, user: { fullName: string; role: string; organization: string }) => {
    const data = { token, ...user };
    setAuth(data);
    sessionStorage.setItem("auth", JSON.stringify(data));
  };

  const handleLogout = () => {
    setAuth(null);
    sessionStorage.removeItem("auth");
  };

  if (!auth) {
    return (
      <QueryClientProvider client={queryClient}>
        <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false} storageKey="crisis-theme">
          <TooltipProvider>
            <Toaster />
            <Sonner />
            <Login onLogin={handleLogin} />
          </TooltipProvider>
        </ThemeProvider>
      </QueryClientProvider>
    );
  }

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false} storageKey="crisis-theme">
        <TooltipProvider>
          <Toaster />
          <Sonner />
          <BrowserRouter>
          <Routes>
            <Route element={<Layout user={auth} onLogout={handleLogout} />}>
              <Route path="/" element={<Index />} />
              <Route path="/hospitals" element={<Hospitals />} />
              <Route path="/severity" element={<SeverityDistribution />} />
              <Route path="/voice-triage" element={<VoiceTriage />} />
            </Route>
            <Route path="*" element={<NotFound />} />
          </Routes>
          </BrowserRouter>
        </TooltipProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
};

export default App;

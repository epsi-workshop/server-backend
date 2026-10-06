import { HashRouter, Navigate, Route, Routes } from "react-router-dom";
import { lazy, type ReactNode } from "react";
import { AuthProvider, LiveProvider, ToastProvider, useAuth } from "./store";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import ChangePassword from "./pages/ChangePassword";
import Overview from "./pages/Overview";
import Camera from "./pages/Camera";
import Alerts from "./pages/Alerts";
import type { Role } from "./types";

// Pages chargées à la demande : Recharts (historique) et l'administration pèsent lourd
// et ne servent pas à l'écran principal.
const Sensors = lazy(() => import("./pages/Sensors"));
const Logs = lazy(() => import("./pages/Logs"));
const Admin = lazy(() => import("./pages/Admin"));

function Guard({ min, children }: { min: Role; children: ReactNode }) {
  const { can } = useAuth();
  return can(min) ? <>{children}</> : <Navigate to="/" replace />;
}

function Gate() {
  const { user, loading } = useAuth();
  if (loading) return <div className="login"><p className="empty">Chargement…</p></div>;
  if (!user) return <Login />;
  if (user.mustChangePassword) return <ChangePassword forced />;
  return (
    <LiveProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Overview />} />
          <Route path="camera" element={<Camera />} />
          <Route path="capteurs" element={<Sensors />} />
          <Route path="alertes" element={<Alerts />} />
          <Route path="journaux" element={<Guard min="operateur"><Logs /></Guard>} />
          <Route path="admin" element={<Guard min="admin"><Admin /></Guard>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </LiveProvider>
  );
}

// HashRouter : fonctionne derrière nginx sans réécriture d'URL et dans un fichier HTML autonome.
export default function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <HashRouter><Gate /></HashRouter>
      </AuthProvider>
    </ToastProvider>
  );
}

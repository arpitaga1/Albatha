import { Route, Routes } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import ProtectedRoute from "./components/ProtectedRoute";
import AppShell from "./components/AppShell";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import HistoryPage from "./pages/HistoryPage";
import StartValidationPage from "./pages/StartValidationPage";
import StartNewValidationPage from "./pages/StartNewValidationPage";
import ValidationWizardPage from "./pages/ValidationWizardPage";
import SsccDemoPage from "./pages/SsccDemoPage";

function Protected({ children }: { children: React.ReactNode }) {
  return (
    <ProtectedRoute>
      <AppShell>{children}</AppShell>
    </ProtectedRoute>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<Protected><DashboardPage /></Protected>} />
        <Route path="/dashboard" element={<Protected><DashboardPage /></Protected>} />
        <Route path="/history" element={<Protected><HistoryPage /></Protected>} />
        <Route path="/validate" element={<Protected><StartValidationPage /></Protected>} />
        <Route path="/validate-new" element={<Protected><StartNewValidationPage /></Protected>} />
        <Route path="/validate/:invoiceNumber" element={<Protected><ValidationWizardPage /></Protected>} />
        <Route path="/sscc-demo" element={<Protected><SsccDemoPage /></Protected>} />
      </Routes>
    </AuthProvider>
  );
}

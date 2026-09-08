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

function Protected({ children, navPath }: { children: React.ReactNode; navPath?: string }) {
  return (
    <ProtectedRoute navPath={navPath}>
      <AppShell>{children}</AppShell>
    </ProtectedRoute>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<Protected navPath="/dashboard"><DashboardPage /></Protected>} />
        <Route path="/dashboard" element={<Protected navPath="/dashboard"><DashboardPage /></Protected>} />
        <Route path="/history" element={<Protected navPath="/history"><HistoryPage /></Protected>} />
        <Route path="/validate" element={<Protected navPath="/validate"><StartValidationPage /></Protected>} />
        <Route path="/validate-new" element={<Protected navPath="/validate-new"><StartNewValidationPage /></Protected>} />
        {/* No navPath - reached by drilling into an invoice from Start
            Validation or History, both of which are already gated above. */}
        <Route path="/validate/:invoiceNumber" element={<Protected><ValidationWizardPage /></Protected>} />
        <Route path="/configurations" element={<Protected navPath="/configurations"><SsccDemoPage /></Protected>} />
      </Routes>
    </AuthProvider>
  );
}

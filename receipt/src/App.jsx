import "./App.css";
import "./styles/Theme.css";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import React from "react";
import Registration from "./pages/Registration";
import Dashboard from "./pages/Dashboard";
import { AuthProvider } from "./components/AuthContext";
import ProtectedRoute from "./components/ProtectedRoute";
import PreferencesBar from "./components/PreferencesBar";
import { PageTitleProvider } from "./components/PageTitle";
import AccountRequired from "./components/AccountRequired";
import Scans from "./pages/Scans";
import Statements from "./pages/Statements";
import StatementDetail from "./pages/StatementDetail";
import Accounts from "./pages/Accounts";
import Review from "./pages/Review";
import Transactions from "./pages/Transactions";
import Uploads from "./pages/Uploads";
import UploadDetail from "./pages/UploadDetail";
import Tags from "./pages/Tags"; 
import ExpenseAnalysis from "./pages/ExpenseAnalysis";
import IncomeAnalysis from "./pages/IncomeAnalysis";
import Budgeting from "./pages/Budgeting";
import Subscriptions from "./pages/Subscriptions";
import TimelineTree from "./pages/TimelineTree";
import Settings from "./pages/Settings";

function App() {
  return (
    <AuthProvider>
      <PageTitleProvider>
      <PreferencesBar />
      <div>
        <Routes>
          <Route path="/" element={<Registration />} />
          <Route path="/dashboard" element={<ProtectedRoute><AccountRequired><Dashboard /></AccountRequired></ProtectedRoute>} />
          <Route path="/dashboard/expenses" element={<ProtectedRoute><AccountRequired><ExpenseAnalysis /></AccountRequired></ProtectedRoute>} />
          <Route path="/dashboard/income" element={<ProtectedRoute><AccountRequired><IncomeAnalysis /></AccountRequired></ProtectedRoute>} />
          <Route path="/dashboard/budgeting" element={<ProtectedRoute><AccountRequired><Budgeting /></AccountRequired></ProtectedRoute>} />
          <Route path="/dashboard/subscriptions" element={<ProtectedRoute><AccountRequired><Subscriptions /></AccountRequired></ProtectedRoute>} />
          <Route path="/dashboard/timeline" element={<ProtectedRoute><AccountRequired><TimelineTree /></AccountRequired></ProtectedRoute>} />
          <Route path="/settings" element={<ProtectedRoute><AccountRequired><Settings /></AccountRequired></ProtectedRoute>} />
          <Route path="/statements" element={<ProtectedRoute><AccountRequired><Statements /></AccountRequired></ProtectedRoute>} />
          <Route path="/statements/:id" element={<ProtectedRoute><AccountRequired><StatementDetail /></AccountRequired></ProtectedRoute>} />
          <Route path="/transactions" element={<ProtectedRoute><AccountRequired><Transactions /></AccountRequired></ProtectedRoute>} />
          <Route path="/scans" element={<ProtectedRoute><AccountRequired><Scans /></AccountRequired></ProtectedRoute>} />
          <Route path="/review" element={<ProtectedRoute><AccountRequired><Review /></AccountRequired></ProtectedRoute>} />
          <Route path="/uploads" element={<ProtectedRoute><AccountRequired><Uploads /></AccountRequired></ProtectedRoute>} />
          <Route path="/uploads/:category/:id" element={<ProtectedRoute><AccountRequired><UploadDetail /></AccountRequired></ProtectedRoute>} />
          <Route path="/tags" element={<ProtectedRoute><AccountRequired><Tags /></AccountRequired></ProtectedRoute>} />
          <Route path="/accounts" element={<ProtectedRoute><Accounts /></ProtectedRoute>} />
        </Routes>
      </div>
      </PageTitleProvider>
    </AuthProvider>
  );
}

export default App;

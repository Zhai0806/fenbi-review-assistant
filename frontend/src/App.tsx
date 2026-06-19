import { BrowserRouter, Routes, Route } from "react-router-dom";
import { ConfigProvider, theme } from "antd";
import { useState } from "react";
import AppLayout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import ExamReview from "./pages/ExamReview";
import WrongBank from "./pages/WrongBank";
import Insights from "./pages/Insights";
import AIChat from "./pages/AIChat";
import Notes from "./pages/Notes";
import Shenlun from "./pages/Shenlun";

export default function App() {
  const [dark, setDark] = useState(false);

  return (
    <ConfigProvider
      theme={{
        algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm,
        token: { colorPrimary: "#1a73e8" },
      }}
    >
      <BrowserRouter>
        <AppLayout dark={dark} onToggleDark={() => setDark(!dark)}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/exam/:id" element={<ExamReview />} />
            <Route path="/wrong-bank" element={<WrongBank />} />
            <Route path="/insights" element={<Insights />} />
            <Route path="/chat" element={<AIChat />} />
            <Route path="/notes" element={<Notes />} />
            <Route path="/shenlun" element={<Shenlun />} />
          </Routes>
        </AppLayout>
      </BrowserRouter>
    </ConfigProvider>
  );
}

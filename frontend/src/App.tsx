import { useState } from "react";
import { useSessionStore } from "./store/sessionStore";
import { Dashboard } from "./components/dashboard/Dashboard";
import { IngestModal } from "./components/ingest/IngestModal";
import { SplashScreen } from "./components/SplashScreen";
import { AnimatePresence } from "framer-motion";
import { PerfOverlay } from "./components/PerfOverlay";

function App() {
  const sessionId = useSessionStore((s) => s.sessionId);
  const [showSplash, setShowSplash] = useState(true);

  return (
    <>
      <AnimatePresence mode="wait">
        {showSplash ? (
          <SplashScreen key="splash" onComplete={() => setShowSplash(false)} />
        ) : (
          <div key="app" className="w-full h-full" style={{ animation: "fadeIn 0.5s ease-out" }}>
            <Dashboard />
            {!sessionId && <IngestModal />}
          </div>
        )}
      </AnimatePresence>
      {(import.meta.env.DEV || import.meta.env.VITE_ENABLE_PERF === "true") && <PerfOverlay />}
    </>
  );
}

export default App;

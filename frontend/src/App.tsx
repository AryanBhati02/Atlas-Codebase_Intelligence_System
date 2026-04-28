import { useState } from "react";
import { useSessionStore } from "./store/sessionStore";
import { Dashboard } from "./components/dashboard/Dashboard";
import { IngestModal } from "./components/ingest/IngestModal";
import { SplashScreen } from "./components/SplashScreen";
import { AnimatePresence } from "framer-motion";

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
    </>
  );
}

export default App;

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { GitBranch, UploadCloud, Sparkles, Shield, BarChart3 } from "lucide-react";
import { GitHubInput } from "./GitHubInput";
import { ZipUpload } from "./ZipUpload";
import type { IngestTab } from "../../types";

const FEATURES = [
  { icon: Sparkles, label: "AI-Powered Analysis" },
  { icon: BarChart3, label: "Complexity Scoring" },
  { icon: Shield, label: "Security Scanning" },
];

export function IngestPanel() {
  const [activeTab, setActiveTab] = useState<IngestTab>("github");

  return (
    <div className="flex flex-col items-center justify-center px-4 py-6">
      { }
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.7, ease: [0.22, 0.61, 0.36, 1] }}
        className="text-center mb-10"
      >
        <div className="flex items-center justify-center gap-3 mb-5">
          <div className="relative">
            <motion.div
              className="absolute inset-[-6px] rounded-2xl"
              style={{
                background: "conic-gradient(from 0deg, rgba(124,110,224,0.3), rgba(34,211,238,0.2), rgba(246,196,69,0.2), rgba(124,110,224,0.3))",
                filter: "blur(8px)",
              }}
              animate={{ rotate: 360 }}
              transition={{ duration: 8, repeat: Infinity, ease: "linear" }}
            />
            <div className="relative w-12 h-12 flex items-center justify-center shadow-lg rounded-xl overflow-hidden">
              <img src="/icon.png" alt="Codebase Intelligence Logo" className="w-full h-full object-cover" />
            </div>
          </div>
          <h1 className="text-3xl font-bold tracking-tight" style={{ color: "var(--text-primary)" }}>
            Codebase Intelligence
          </h1>
        </div>
        <p className="text-base max-w-md mx-auto leading-relaxed" style={{ color: "var(--text-tertiary)" }}>
          Transform any repository into an interactive, AI-powered knowledge
          system. Understand unfamiliar code in minutes.
        </p>
        <div className="glow-line w-48 mx-auto mt-4 opacity-50" />
      </motion.div>

      { }
      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5, delay: 0.15, ease: "easeOut" }}
        className="glass-card rounded-2xl w-full max-w-lg glow-purple"
      >
        { }
        <div className="flex" style={{ borderBottom: "1px solid var(--surface-section-border)" }}>
          <TabButton
            active={activeTab === "github"}
            onClick={() => setActiveTab("github")}
            icon={<GitBranch className="w-4 h-4" />}
            label="GitHub URL"
          />
          <TabButton
            active={activeTab === "upload"}
            onClick={() => setActiveTab("upload")}
            icon={<UploadCloud className="w-4 h-4" />}
            label="Upload ZIP"
          />
        </div>

        { }
        <div className="p-6">
          <AnimatePresence mode="wait">
            {activeTab === "github" ? (
              <motion.div
                key="github"
                initial={{ opacity: 0, x: -16 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 16 }}
                transition={{ duration: 0.2 }}
              >
                <GitHubInput />
              </motion.div>
            ) : (
              <motion.div
                key="upload"
                initial={{ opacity: 0, x: 16 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -16 }}
                transition={{ duration: 0.2 }}
              >
                <ZipUpload />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>

      { }
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.4, duration: 0.5 }}
        className="flex gap-3 mt-8 flex-wrap justify-center"
      >
        {FEATURES.map((f, i) => (
          <motion.div
            key={f.label}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5 + i * 0.12, ease: [0.22, 0.61, 0.36, 1] }}
            whileHover={{ scale: 1.04, y: -2 }}
            className="flex items-center gap-2 px-3.5 py-1.5 rounded-full
              bg-dark-800/60 border border-white/5 text-xs text-slate-400
              hover:border-accent-purple/15 hover:text-slate-300
              hover:shadow-[0_0_16px_rgba(124,110,224,0.06)]
              transition-all duration-300 cursor-default"
          >
            <f.icon className="w-3.5 h-3.5 text-accent-purple" />
            {f.label}
          </motion.div>
        ))}
      </motion.div>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`
        relative flex-1 flex items-center justify-center gap-2 py-3.5
        text-sm font-medium transition-colors duration-200
        ${active ? "" : ""}
      `}
      style={{ color: active ? "var(--text-primary)" : "var(--text-muted)" }}
    >
      {icon}
      {label}
      {active && (
        <motion.div
          layoutId="tab-indicator"
          className="absolute bottom-0 left-0 right-0 h-0.5
            bg-gradient-to-r from-accent-purple to-accent-blue"
          transition={{ type: "spring", stiffness: 400, damping: 30 }}
        />
      )}
    </button>
  );
}

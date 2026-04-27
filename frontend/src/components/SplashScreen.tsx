import { motion } from "framer-motion";

export function SplashScreen({ onComplete }: { onComplete: () => void }) {
    return (
        <motion.div
            initial={{ opacity: 1 }}
            exit={{ opacity: 0, scale: 1.05 }}
            transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
            onAnimationComplete={(definition) => {
                if (definition === "exit" || (definition as any)?.opacity === 0) {
                    // Fallback if needed, but AnimatePresence handles unmount
                }
            }}
            className="fixed inset-0 z-[9999] flex flex-col items-center justify-center bg-base"
            style={{ background: "var(--bg-base)" }}
        >
            <div className="relative w-28 h-28 mb-8">
                <motion.div
                    className="absolute inset-[-15px] rounded-3xl opacity-60"
                    style={{
                        background:
                            "conic-gradient(from 0deg, rgba(124,110,224,0.4), rgba(34,211,238,0.3), rgba(246,196,69,0.3), rgba(124,110,224,0.4))",
                        filter: "blur(16px)",
                    }}
                    animate={{ rotate: 360 }}
                    transition={{ duration: 5, repeat: Infinity, ease: "linear" }}
                />
                <motion.div
                    initial={{ scale: 0.8, opacity: 0, y: 20 }}
                    animate={{ scale: 1, opacity: 1, y: 0 }}
                    transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
                    className="relative w-full h-full rounded-2xl flex items-center justify-center overflow-hidden shadow-2xl bg-surface"
                    style={{
                        background: "var(--bg-surface)",
                        border: "1px solid var(--accent-purple-border)",
                        boxShadow: "0 0 40px rgba(124,110,224,0.15)",
                    }}
                >
                    <img
                        src="/icon.png"
                        alt="Logo"
                        className="w-full h-full object-cover"
                    />
                </motion.div>
            </div>

            <motion.h1
                initial={{ y: 20, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                transition={{ duration: 0.8, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
                className="text-3xl font-bold tracking-tight mb-3"
                style={{ color: "var(--text-primary)" }}
            >
                Codebase Intelligence
            </motion.h1>

            <motion.p
                initial={{ y: 15, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                transition={{ duration: 0.8, delay: 0.35, ease: [0.22, 1, 0.36, 1] }}
                className="text-sm font-medium"
                style={{ color: "var(--text-tertiary)" }}
            >
                Initializing Workspace...
            </motion.p>

            <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.5, delay: 0.6 }}
                className="w-56 h-1 mt-8 rounded-full overflow-hidden"
                style={{ background: "var(--border-light)" }}
            >
                <motion.div
                    className="h-full origin-left"
                    style={{ background: "var(--gradient-brand)" }}
                    initial={{ scaleX: 0 }}
                    animate={{ scaleX: 1 }}
                    transition={{ duration: 1.8, delay: 0.6, ease: "easeInOut" }}
                    onAnimationComplete={onComplete}
                />
            </motion.div>
        </motion.div>
    );
}

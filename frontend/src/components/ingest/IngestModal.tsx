import { useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X } from "lucide-react";
import { useAppStore } from "../../store/appStore";
import { IngestPanel } from "./IngestPanel";

export function IngestModal() {
    const { showIngestModal, setShowIngestModal } = useAppStore();

    const handleClose = useCallback(() => {
        setShowIngestModal(false);
    }, [setShowIngestModal]);

    useEffect(() => {
        if (!showIngestModal) return;
        const onKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape") handleClose();
        };
        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [showIngestModal, handleClose]);

    return (
        <AnimatePresence>
            {showIngestModal && (
                <>
                    <motion.div
                        key="ingest-backdrop"
                        className="ingest-modal-backdrop"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        onClick={handleClose}
                    >
                        <motion.div
                            key="ingest-modal"
                            className="ingest-modal"
                            initial={{ opacity: 0, y: 20, scale: 0.96 }}
                            animate={{ opacity: 1, y: 0, scale: 1 }}
                            exit={{ opacity: 0, y: 20, scale: 0.96 }}
                            transition={{ duration: 0.25, ease: [0.22, 0.61, 0.36, 1] }}
                            onClick={(e) => e.stopPropagation()}
                        >
                            <div className="flex items-center justify-end p-2">
                                <button
                                    onClick={handleClose}
                                    className="p-1.5 rounded-lg transition-colors"
                                    style={{
                                        color: "var(--text-tertiary)",
                                        background: "var(--bg-input)",
                                    }}
                                    aria-label="Close modal"
                                    tabIndex={0}
                                >
                                    <X className="w-4 h-4" />
                                </button>
                            </div>
                            <div className="px-6 pb-6">
                                <IngestPanel />
                            </div>
                        </motion.div>
                    </motion.div>
                </>
            )}
        </AnimatePresence>
    );
}

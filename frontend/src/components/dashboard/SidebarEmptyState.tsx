import { motion } from "framer-motion";
import { FolderOpen, GitBranch } from "lucide-react";
import { useAppStore } from "../../store/appStore";

export function SidebarEmptyState() {
    const { setShowIngestModal } = useAppStore();

    const handleOpenFolder = async () => {
        try {
            if ("showDirectoryPicker" in window) {
                await (window as unknown as { showDirectoryPicker: () => Promise<unknown> }).showDirectoryPicker();
            } else {
                setShowIngestModal(true);
            }
        } catch {
            
        }
    };

    return (
        <>
            <div className="panel-header">
                <h2>Explorer</h2>
            </div>

            <div className="flex flex-col items-center justify-center flex-1 p-4 gap-4">
                <motion.div
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ duration: 0.4 }}
                    className="flex items-center gap-2 mb-2"
                >
                    <div className="w-8 h-8 rounded-lg flex items-center justify-center overflow-hidden">
                        <img src="/icon.png" alt="Logo" className="w-full h-full object-cover" />
                    </div>
                </motion.div>

                <p
                    className="text-[10px] text-center leading-relaxed max-w-[180px]"
                    style={{ color: "var(--text-muted)" }}
                >
                    Open a folder or clone a repository to get started
                </p>

                <div className="flex flex-col gap-2 w-full max-w-[200px]">
                    <motion.button
                        onClick={handleOpenFolder}
                        whileHover={{ scale: 1.02 }}
                        whileTap={{ scale: 0.98 }}
                        className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-[11px] font-medium transition-colors duration-200"
                        style={{
                            background: "var(--bg-input)",
                            border: "1px solid var(--border-light)",
                            color: "var(--text-secondary)",
                        }}
                        aria-label="Open local folder"
                        tabIndex={0}
                    >
                        <FolderOpen className="w-3.5 h-3.5" style={{ color: "var(--accent-gold)" }} />
                        Open Folder
                    </motion.button>

                    <motion.button
                        onClick={() => setShowIngestModal(true)}
                        whileHover={{ scale: 1.02 }}
                        whileTap={{ scale: 0.98 }}
                        className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-[11px] font-medium transition-colors duration-200"
                        style={{
                            background: "var(--accent-purple-subtle)",
                            border: "1px solid var(--accent-purple-border)",
                            color: "var(--text-primary)",
                        }}
                        aria-label="Clone Git repository"
                        tabIndex={0}
                    >
                        <GitBranch className="w-3.5 h-3.5" style={{ color: "var(--accent-purple)" }} />
                        Clone Repository
                    </motion.button>
                </div>
            </div>
        </>
    );
}

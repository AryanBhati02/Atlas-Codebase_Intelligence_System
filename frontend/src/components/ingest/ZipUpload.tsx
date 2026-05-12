import { useState, useRef, useCallback } from "react";
import { motion } from "framer-motion";
import { UploadCloud, FileArchive, Loader2, AlertCircle, X } from "lucide-react";
import { ingestZip } from "../../api/ingest";
import { useAppStore } from "../../store/appStore";

const MAX_SIZE_MB = 100;

export function ZipUpload() {
  const [dragActive, setDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { isLoading, error, setLoading, setError, setSession, setShowIngestModal } = useAppStore();

  const validateFile = useCallback((file: File): string | null => {
    if (!file.name.toLowerCase().endsWith(".zip")) {
      return "Only .zip files are accepted.";
    }
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      return `File too large: ${(file.size / 1024 / 1024).toFixed(1)}MB (max ${MAX_SIZE_MB}MB).`;
    }
    return null;
  }, []);

  const handleFile = useCallback(
    (file: File) => {
      const validationError = validateFile(file);
      if (validationError) {
        setError(validationError);
        return;
      }
      setError(null);
      setSelectedFile(file);
    },
    [validateFile, setError]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragActive(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  const handleUpload = async () => {
    if (!selectedFile || isLoading) return;
    setLoading(true);
    setError(null);

    try {
      const data = await ingestZip(selectedFile);
      setLoading(false);
      setSession(data);
      setShowIngestModal(false);
    } catch (err: unknown) {
      if (err && typeof err === "object" && "response" in err) {
        const axiosErr = err as { response?: { data?: { detail?: string } } };
        setError(axiosErr.response?.data?.detail || "Upload failed.");
      } else {
        setError("Network error. Is the backend running on port 8000?");
      }
    }
  };

  return (
    <div className="space-y-4">
      { }
      <div
        id="drop-zone"
        onDragOver={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`
          relative flex flex-col items-center justify-center
          py-10 px-6 rounded-xl border-2 border-dashed cursor-pointer
          transition-all duration-200
          ${dragActive
            ? "drop-zone-active border-accent-purple/60 bg-accent-purple/5"
            : ""
          }
        `}
        style={{
          borderColor: dragActive ? undefined : "var(--surface-input-border)",
          background: dragActive ? undefined : "var(--surface-card-bg)",
        }}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".zip"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFile(file);
          }}
        />

        <motion.div
          animate={{ y: dragActive ? -4 : 0 }}
          transition={{ type: "spring", stiffness: 300 }}
        >
          <UploadCloud
            className={`w-8 h-8 mb-3 transition-colors duration-200 ${dragActive ? "text-accent-purple" : ""
              }`}
            style={{ color: dragActive ? undefined : "var(--text-muted)" }}
          />
        </motion.div>

        <p className="text-sm font-medium" style={{ color: "var(--text-secondary)" }}>
          {dragActive ? "Drop your ZIP file" : "Drag & drop a ZIP file"}
        </p>
        <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
          or click to browse · Max {MAX_SIZE_MB}MB
        </p>
      </div>

      { }
      {selectedFile && (
        <motion.div
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center gap-3 p-3 rounded-xl"
          style={{
            background: "var(--surface-card-bg)",
            border: "1px solid var(--surface-card-border)",
          }}
        >
          <FileArchive className="w-5 h-5 text-accent-purple shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-sm truncate" style={{ color: "var(--text-primary)" }}>{selectedFile.name}</p>
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>
              {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
            </p>
          </div>
          <button
            onClick={(e) => {
              e.stopPropagation();
              setSelectedFile(null);
            }}
            className="p-1 rounded-md hover:bg-white/5 text-slate-500 hover:text-white transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </motion.div>
      )}

      { }
      {error && (
        <motion.div
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-start gap-2 p-3 rounded-lg bg-red-500/8 border border-red-500/15"
        >
          <AlertCircle className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
          <p className="text-xs text-red-300 leading-relaxed">{error}</p>
        </motion.div>
      )}

      { }
      <button
        id="upload-button"
        onClick={handleUpload}
        disabled={!selectedFile || isLoading}
        className="w-full py-3 px-4 rounded-xl text-sm font-semibold
          bg-gradient-to-r from-accent-purple to-accent-violet
          text-white flex items-center justify-center gap-2
          hover:shadow-lg hover:shadow-accent-purple/20
          disabled:opacity-40 disabled:cursor-not-allowed
          transition-all duration-200 active:scale-[0.98]"
      >
        {isLoading ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" />
            Extracting & Analyzing...
          </>
        ) : (
          <>
            <UploadCloud className="w-4 h-4" />
            Upload & Analyze
          </>
        )}
      </button>
    </div>
  );
}

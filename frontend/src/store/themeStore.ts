import { create } from "zustand";

export type ThemeMode = "dark" | "light";

export interface ThemeColors {
    bgBase: string;
    threeBg: string;
    threeFog: string;
    threeGridPrimary: string;
    threeGridSecondary: string;
    threeFloorPlane: string;
    labelColor: string;
    labelDimmed: string;
    labelSelectedColor: string;
    labelSelectedBg: string;
    edgeDefault: [number, number, number];
    edgeDimmed: [number, number, number];
    edgeActive: [number, number, number];
    ambientIntensity: number;
    toolbarBg: string;
    toolbarText: string;
    toolbarHover: string;
    toolbarBorder: string;
    toolbarActiveText: string;
    toolbarActiveBg: string;
    toolbarDropdownBg: string;
    toolbarDropdownText: string;
    toolbarDropdownHover: string;
    toolbarDropdownActiveText: string;
    toolbarDropdownActiveBg: string;
}

const DARK_COLORS: ThemeColors = {
    bgBase: "#050508",
    threeBg: "#010105",
    threeFog: "#010105",
    threeGridPrimary: "#2a1f50",
    threeGridSecondary: "#12102a",
    threeFloorPlane: "#080514",
    labelColor: "#e2e8f0",
    labelDimmed: "#475569",
    labelSelectedColor: "#f6c445",
    labelSelectedBg: "rgba(246,196,69,0.08)",
    edgeDefault: [0.45, 0.38, 0.85],
    edgeDimmed: [0.18, 0.18, 0.22],
    edgeActive: [0.96, 0.77, 0.27],
    ambientIntensity: 0.25,
    toolbarBg: "rgba(0,0,0,0.50)",
    toolbarText: "#64748b",
    toolbarHover: "#e2e8f0",
    toolbarBorder: "rgba(255,255,255,0.04)",
    toolbarActiveText: "#e2e8f0",
    toolbarActiveBg: "rgba(255,255,255,0.06)",
    toolbarDropdownBg: "rgba(0,0,0,0.80)",
    toolbarDropdownText: "#64748b",
    toolbarDropdownHover: "rgba(255,255,255,0.03)",
    toolbarDropdownActiveText: "#e2e8f0",
    toolbarDropdownActiveBg: "rgba(255,255,255,0.06)",
};

const LIGHT_COLORS: ThemeColors = {
    bgBase: "#f6f5f2",
    threeBg: "#e8e6e0",
    threeFog: "#e8e6e0",
    threeGridPrimary: "#c4b8d8",
    threeGridSecondary: "#ddd8ec",
    threeFloorPlane: "#d8d4cc",
    labelColor: "#1f1f1f",
    labelDimmed: "#a0a0a0",
    labelSelectedColor: "#d97706",
    labelSelectedBg: "rgba(217,119,6,0.10)",
    edgeDefault: [0.42, 0.35, 0.78],
    edgeDimmed: [0.72, 0.72, 0.75],
    edgeActive: [0.85, 0.47, 0.02],
    ambientIntensity: 0.6,
    toolbarBg: "rgba(255,255,255,0.80)",
    toolbarText: "#787878",
    toolbarHover: "#1f1f1f",
    toolbarBorder: "rgba(0,0,0,0.08)",
    toolbarActiveText: "#1f1f1f",
    toolbarActiveBg: "rgba(0,0,0,0.06)",
    toolbarDropdownBg: "rgba(255,255,255,0.95)",
    toolbarDropdownText: "#787878",
    toolbarDropdownHover: "rgba(0,0,0,0.04)",
    toolbarDropdownActiveText: "#1f1f1f",
    toolbarDropdownActiveBg: "rgba(0,0,0,0.06)",
};

function getStoredTheme(): ThemeMode {
    try {
        const stored = localStorage.getItem("ci-theme");
        if (stored === "light" || stored === "dark") return stored;
    } catch { }
    return "dark";
}

interface ThemeState {
    theme: ThemeMode;
    colors: ThemeColors;
    toggleTheme: () => void;
    setTheme: (t: ThemeMode) => void;
}

export const useThemeStore = create<ThemeState>((set, get) => ({
    theme: getStoredTheme(),
    colors: getStoredTheme() === "dark" ? DARK_COLORS : LIGHT_COLORS,

    setTheme: (next: ThemeMode) => {
        try { localStorage.setItem("ci-theme", next); } catch { }
        document.documentElement.setAttribute("data-theme", next);
        set({ theme: next, colors: next === "dark" ? DARK_COLORS : LIGHT_COLORS });
        window.dispatchEvent(new CustomEvent("theme-changed", { detail: next }));
    },

    toggleTheme: () => {
        const next = get().theme === "dark" ? "light" : "dark";
        get().setTheme(next);
    },
}));

export function getThemeColors(theme: ThemeMode): ThemeColors {
    return theme === "dark" ? DARK_COLORS : LIGHT_COLORS;
}

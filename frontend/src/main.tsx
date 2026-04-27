import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

const savedTheme = (() => {
  try {
    const t = localStorage.getItem("ci-theme");
    return t === "light" ? "light" : "dark";
  } catch {
    return "dark";
  }
})();
document.documentElement.setAttribute("data-theme", savedTheme);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

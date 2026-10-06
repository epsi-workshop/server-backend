import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/barlow/latin-400.css";
import "@fontsource/barlow/latin-500.css";
import "@fontsource/barlow/latin-600.css";
import "@fontsource/barlow-condensed/latin-500.css";
import "@fontsource/barlow-condensed/latin-600.css";
import "./styles.css";
import { initApi } from "./api";
import App from "./App";

initApi().then(() => {
  createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
});

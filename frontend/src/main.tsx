import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/inter/latin-400.css";
import "@fontsource/inter/latin-500.css";
import "@fontsource/inter/latin-600.css";
import "@fontsource/fraunces/latin-300.css";
import "@fontsource/fraunces/latin-400.css";
import "@fontsource/fraunces/latin-400-italic.css";
import "./theme";
import "./styles.css";
import { initApi } from "./api";
import App from "./App";

initApi().then(() => {
  createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
});

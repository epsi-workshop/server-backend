import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/geist";
import "@fontsource-variable/geist-mono";
import "./theme";
import "./styles.css";
import { initApi } from "./api";
import App from "./App";

initApi().then(() => {
  createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
});

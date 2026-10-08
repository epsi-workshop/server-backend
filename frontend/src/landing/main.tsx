import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/geist";
import "@fontsource-variable/geist-mono";
import "./landing.css";
import Landing from "./Landing";

createRoot(document.getElementById("root")!).render(<StrictMode><Landing /></StrictMode>);

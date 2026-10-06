// Flux caméra simulé (mode démo uniquement, chargé à la demande par la page Caméra).
import { useEffect, useRef } from "react";
import { getMockScene } from "./mock";
import { drawScene } from "./mockScene";

export default function MockFeed() {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const cv = ref.current;
    const ctx = cv?.getContext("2d");
    if (!cv || !ctx) return;
    let raf = 0, last = 0;
    const loop = (t: number) => {
      if (t - last > 90) { drawScene(ctx, cv.width, cv.height, t, getMockScene()); last = t; }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);
  return <canvas ref={ref} width={960} height={540} aria-label="Flux vidéo simulé de la salle serveur" />;
}

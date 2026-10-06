// Image de caméra simulée pour le mode démo : salle serveur, baies, silhouette détectée.

export interface SceneOpts {
  person: boolean;
  personX: number; // 0..1
  confidence: number;
  masked: boolean;
  /** horodatage incrusté (par défaut : maintenant) */
  at?: number;
}

export function drawScene(ctx: CanvasRenderingContext2D, w: number, h: number, t: number, o: SceneOpts) {
  if (o.masked) {
    ctx.fillStyle = "#050607";
    ctx.fillRect(0, 0, w, h);
    overlay(ctx, w, h, o.at);
    return;
  }
  // Fond et sol
  ctx.fillStyle = "#1b252e";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#222e38";
  ctx.fillRect(0, h * 0.72, w, h * 0.28);
  ctx.strokeStyle = "rgba(255,255,255,0.05)";
  ctx.lineWidth = 1;
  for (let i = -6; i <= 6; i++) {
    ctx.beginPath();
    ctx.moveTo(w / 2 + i * w * 0.04, h * 0.72);
    ctx.lineTo(w / 2 + i * w * 0.2, h);
    ctx.stroke();
  }
  // Baies serveur
  const racks = 5;
  for (let r = 0; r < racks; r++) {
    const rw = w * 0.11, rh = h * 0.56;
    const x = w * 0.08 + r * w * 0.175, y = h * 0.16;
    ctx.fillStyle = "#11181e";
    ctx.fillRect(x, y, rw, rh);
    ctx.strokeStyle = "#2f3d49";
    ctx.strokeRect(x + 0.5, y + 0.5, rw - 1, rh - 1);
    for (let u = 0; u < 12; u++) {
      const uy = y + 8 + u * (rh - 16) / 12;
      ctx.fillStyle = "#1c262f";
      ctx.fillRect(x + 5, uy, rw - 10, (rh - 16) / 12 - 3);
      const blink = Math.sin(t / 180 + r * 3.1 + u * 1.7) > 0.2;
      ctx.fillStyle = blink ? (u % 4 === 0 ? "#e0a030" : "#3fbf7f") : "#24313b";
      ctx.fillRect(x + rw - 14, uy + 3, 4, 3);
    }
  }
  // Silhouette
  if (o.person) {
    const px = w * (0.15 + o.personX * 0.7), base = h * 0.9, ph = h * 0.62;
    ctx.fillStyle = "#3a4650";
    ctx.beginPath();
    ctx.arc(px, base - ph + ph * 0.09, ph * 0.08, 0, Math.PI * 2);
    ctx.fill();
    roundRect(ctx, px - ph * 0.13, base - ph + ph * 0.2, ph * 0.26, ph * 0.45, ph * 0.06);
    ctx.fill();
    ctx.fillRect(px - ph * 0.1, base - ph * 0.36, ph * 0.08, ph * 0.36);
    ctx.fillRect(px + ph * 0.02, base - ph * 0.36, ph * 0.08, ph * 0.36);
    // Cadre de détection
    const bx = px - ph * 0.2, by = base - ph - 6, bw = ph * 0.4, bh = ph + 10;
    ctx.strokeStyle = "#ff5a4f";
    ctx.lineWidth = 2;
    ctx.strokeRect(bx, by, bw, bh);
    const label = `personne ${Math.round(o.confidence * 100)} %`;
    ctx.font = "600 13px Barlow, system-ui, sans-serif";
    const tw = ctx.measureText(label).width + 10;
    ctx.fillStyle = "#ff5a4f";
    ctx.fillRect(bx, by - 20, tw, 20);
    ctx.fillStyle = "#fff";
    ctx.fillText(label, bx + 5, by - 6);
  }
  // Bruit de capteur
  for (let i = 0; i < 260; i++) {
    ctx.fillStyle = `rgba(255,255,255,${Math.random() * 0.05})`;
    ctx.fillRect(Math.random() * w, Math.random() * h, 1.5, 1.5);
  }
  overlay(ctx, w, h, o.at);
}

function overlay(ctx: CanvasRenderingContext2D, w: number, h: number, at?: number) {
  const now = new Date(at ?? Date.now());
  const stamp = `CAM-01  ${now.toLocaleDateString("fr-FR")}  ${now.toLocaleTimeString("fr-FR")}`;
  ctx.font = "500 13px Barlow, system-ui, sans-serif";
  ctx.fillStyle = "rgba(0,0,0,0.45)";
  ctx.fillRect(8, h - 28, ctx.measureText(stamp).width + 14, 20);
  ctx.fillStyle = "#e8eef3";
  ctx.fillText(stamp, 15, h - 13);
  void w;
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

export function captureDataUrl(personX: number, confidence: number, at?: number): string | null {
  try {
    const c = document.createElement("canvas");
    c.width = 640;
    c.height = 360;
    const ctx = c.getContext("2d");
    if (!ctx) return null;
    drawScene(ctx, 640, 360, performance.now(), { person: true, personX, confidence, masked: false, at });
    return c.toDataURL("image/jpeg", 0.72);
  } catch {
    return null;
  }
}

import React, { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { autoView, niceTicks, parseChart, parsePlot, sampleFunction, sampleParam, samplePolar } from "./plotSpec.mjs";

/** Fenced languages that are drawn instead of shown as code. */
export const VISUAL_LANGUAGES = new Set(["plot", "desmos", "chart", "mermaid"]);

const COLORS = ["#7c5cff", "#e8590c", "#2f9e44", "#1c7ed6", "#d6336c", "#f08c00", "#12b886", "#868e96"];
const W = 640;
const H = 400;
const M = { left: 44, right: 14, top: 14, bottom: 28 };

const fmt = (v: number) => {
  const a = Math.abs(v);
  if (a !== 0 && (a >= 1e6 || a < 1e-4)) return v.toExponential(1);
  return String(Number(v.toPrecision(6)));
};

type View = { x: [number, number]; y: [number, number] };

/** A Desmos-style graph of functions, polar and parametric curves and points: drag to pan, wheel to zoom. */
function PlotView({ text }: { text: string }) {
  const spec = useMemo(() => parsePlot(text), [text]);
  const initial = useMemo<View>(() => autoView(spec), [spec]);
  const [view, setView] = useState<View>(initial);
  const svgRef = useRef<SVGSVGElement>(null);
  const drag = useRef<{ x: number; y: number; view: View } | null>(null);
  useEffect(() => setView(initial), [initial]);

  const sx = (x: number) => M.left + ((x - view.x[0]) / (view.x[1] - view.x[0])) * (W - M.left - M.right);
  const sy = (y: number) => H - M.bottom - ((y - view.y[0]) / (view.y[1] - view.y[0])) * (H - M.top - M.bottom);

  const paths = useMemo(() => spec.curves.map((curve, index) => {
    let lines: number[][][] = [];
    if (curve.kind === "fn") lines = sampleFunction(curve.f, view.x[0], view.x[1], view.y[0], view.y[1]);
    else if (curve.kind === "param") lines = sampleParam(curve.fx, curve.fy, curve.tRange[0], curve.tRange[1]);
    else if (curve.kind === "polar") lines = samplePolar(curve.r);
    const d = lines.map((line) => line.map((p, i) => `${i ? "L" : "M"}${sx(p[0]).toFixed(1)} ${sy(p[1]).toFixed(1)}`).join("")).join("");
    return { curve, d, color: COLORS[index % COLORS.length] };
  }), [spec, view]);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = svg.getBoundingClientRect();
      const px = ((event.clientX - rect.left) / rect.width) * W;
      const py = ((event.clientY - rect.top) / rect.height) * H;
      const factor = event.deltaY > 0 ? 1.15 : 1 / 1.15;
      setView((v) => {
        const ux = v.x[0] + ((px - M.left) / (W - M.left - M.right)) * (v.x[1] - v.x[0]);
        const uy = v.y[0] + ((H - M.bottom - py) / (H - M.top - M.bottom)) * (v.y[1] - v.y[0]);
        return { x: [ux + (v.x[0] - ux) * factor, ux + (v.x[1] - ux) * factor], y: [uy + (v.y[0] - uy) * factor, uy + (v.y[1] - uy) * factor] };
      });
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, []);

  const xTicks = niceTicks(view.x[0], view.x[1]);
  const yTicks = niceTicks(view.y[0], view.y[1], 6);
  const originX = view.x[0] <= 0 && view.x[1] >= 0 ? sx(0) : null;
  const originY = view.y[0] <= 0 && view.y[1] >= 0 ? sy(0) : null;
  const zoom = (factor: number) => setView((v) => {
    const cx = (v.x[0] + v.x[1]) / 2; const cy = (v.y[0] + v.y[1]) / 2;
    return { x: [cx + (v.x[0] - cx) * factor, cx + (v.x[1] - cx) * factor], y: [cy + (v.y[0] - cy) * factor, cy + (v.y[1] - cy) * factor] };
  });

  return (
    <figure className="core-vis core-plot">
      {spec.title && <figcaption className="core-vis-title">{spec.title}</figcaption>}
      <svg
        ref={svgRef} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={spec.title || "Graph"}
        onPointerDown={(e) => { (e.currentTarget as Element).setPointerCapture(e.pointerId); drag.current = { x: e.clientX, y: e.clientY, view }; }}
        onPointerMove={(e) => {
          const d = drag.current; const rect = svgRef.current?.getBoundingClientRect();
          if (!d || !rect) return;
          const dx = ((e.clientX - d.x) / rect.width) * W * ((d.view.x[1] - d.view.x[0]) / (W - M.left - M.right));
          const dy = ((e.clientY - d.y) / rect.height) * H * ((d.view.y[1] - d.view.y[0]) / (H - M.top - M.bottom));
          setView({ x: [d.view.x[0] - dx, d.view.x[1] - dx], y: [d.view.y[0] + dy, d.view.y[1] + dy] });
        }}
        onPointerUp={() => { drag.current = null; }}
        onDoubleClick={() => setView(initial)}
      >
        <clipPath id="core-plot-clip"><rect x={M.left} y={M.top} width={W - M.left - M.right} height={H - M.top - M.bottom} /></clipPath>
        <g className="core-vis-grid">
          {xTicks.map((t) => <line key={`gx${t}`} x1={sx(t)} x2={sx(t)} y1={M.top} y2={H - M.bottom} />)}
          {yTicks.map((t) => <line key={`gy${t}`} x1={M.left} x2={W - M.right} y1={sy(t)} y2={sy(t)} />)}
        </g>
        <g className="core-vis-axes">
          {originY !== null && <line x1={M.left} x2={W - M.right} y1={originY} y2={originY} />}
          {originX !== null && <line x1={originX} x2={originX} y1={M.top} y2={H - M.bottom} />}
        </g>
        <g className="core-vis-labels">
          {xTicks.map((t) => <text key={`lx${t}`} x={sx(t)} y={H - M.bottom + 16} textAnchor="middle">{fmt(t)}</text>)}
          {yTicks.map((t) => <text key={`ly${t}`} x={M.left - 6} y={sy(t) + 4} textAnchor="end">{fmt(t)}</text>)}
        </g>
        <g clipPath="url(#core-plot-clip)">
          {paths.map(({ curve, d, color }, i) => {
            if (curve.kind === "vline") return <line key={i} x1={sx(curve.x)} x2={sx(curve.x)} y1={M.top} y2={H - M.bottom} stroke={color} strokeWidth={2} />;
            if (curve.kind === "points") return <g key={i} fill={color}>{curve.points.map((p: number[], j: number) => <circle key={j} cx={sx(p[0])} cy={sy(p[1])} r={4} />)}</g>;
            return <path key={i} d={d} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" />;
          })}
        </g>
      </svg>
      <div className="core-vis-legend">
        {paths.map(({ curve, color }, i) => <span key={i}><i style={{ background: color }} />{curve.label}</span>)}
        <span className="core-vis-tools">
          <button type="button" onClick={() => zoom(0.8)} aria-label="Zoom in">+</button>
          <button type="button" onClick={() => zoom(1.25)} aria-label="Zoom out">−</button>
          <button type="button" onClick={() => setView(initial)} aria-label="Reset view">↺</button>
        </span>
      </div>
      {spec.errors.length > 0 && (
        <ul className="core-vis-errors">{spec.errors.map((e) => <li key={e.line}>Line {e.line}: <code>{e.text}</code> — {e.message}</li>)}</ul>
      )}
    </figure>
  );
}

/** Bar, line and pie charts from a small JSON spec. */
function ChartView({ text, fallback }: { text: string; fallback: ReactNode }) {
  const parsed = useMemo(() => parseChart(text), [text]);
  if ("error" in parsed) return <>{fallback}</>;
  const { spec } = parsed;
  const n = spec.labels.length;
  const all = spec.series.flatMap((s) => s.data);
  const lo = Math.min(0, ...all);
  const hi = Math.max(0, ...all) || 1;
  const sy = (v: number) => H - M.bottom - ((v - lo) / (hi - lo || 1)) * (H - M.top - M.bottom);
  const band = (W - M.left - M.right) / n;
  const yTicks = niceTicks(lo, hi, 6);
  const pie = spec.type === "pie";
  const total = pie ? spec.series[0].data.reduce((a, b) => a + b, 0) : 1;
  let angle = -Math.PI / 2;
  return (
    <figure className="core-vis core-chart">
      {spec.title && <figcaption className="core-vis-title">{spec.title}</figcaption>}
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={spec.title || "Chart"}>
        {!pie && (
          <>
            <g className="core-vis-grid">{yTicks.map((t) => <line key={t} x1={M.left} x2={W - M.right} y1={sy(t)} y2={sy(t)} />)}</g>
            <g className="core-vis-labels">
              {yTicks.map((t) => <text key={t} x={M.left - 6} y={sy(t) + 4} textAnchor="end">{fmt(t)}</text>)}
              {spec.labels.map((l, i) => <text key={i} x={M.left + band * (i + 0.5)} y={H - M.bottom + 16} textAnchor="middle">{l.length > 10 ? `${l.slice(0, 9)}…` : l}</text>)}
            </g>
            {spec.type === "bar" && spec.series.map((s, si) => s.data.map((v, i) => {
              const w = (band * 0.8) / spec.series.length;
              return <rect key={`${si}-${i}`} x={M.left + band * i + band * 0.1 + w * si} y={Math.min(sy(v), sy(0))} width={w} height={Math.abs(sy(v) - sy(0))} fill={COLORS[si % COLORS.length]} rx={2}><title>{`${s.name} · ${spec.labels[i]}: ${fmt(v)}`}</title></rect>;
            }))}
            {spec.type === "line" && spec.series.map((s, si) => (
              <g key={si} stroke={COLORS[si % COLORS.length]} fill={COLORS[si % COLORS.length]}>
                <polyline fill="none" strokeWidth={2} points={s.data.map((v, i) => `${M.left + band * (i + 0.5)},${sy(v)}`).join(" ")} />
                {s.data.map((v, i) => <circle key={i} cx={M.left + band * (i + 0.5)} cy={sy(v)} r={3.5} stroke="none"><title>{`${s.name} · ${spec.labels[i]}: ${fmt(v)}`}</title></circle>)}
              </g>
            ))}
          </>
        )}
        {pie && spec.series[0].data.map((v, i) => {
          const a0 = angle; angle += (v / total) * Math.PI * 2;
          const a1 = angle; const cx = W / 2; const cy = H / 2; const r = 150;
          const large = a1 - a0 > Math.PI ? 1 : 0;
          const d = v / total >= 0.9999 ? `M${cx - r} ${cy}a${r} ${r} 0 1 0 ${2 * r} 0a${r} ${r} 0 1 0 ${-2 * r} 0` : `M${cx} ${cy}L${cx + r * Math.cos(a0)} ${cy + r * Math.sin(a0)}A${r} ${r} 0 ${large} 1 ${cx + r * Math.cos(a1)} ${cy + r * Math.sin(a1)}Z`;
          return <path key={i} d={d} fill={COLORS[i % COLORS.length]} stroke="rgb(var(--surface-primary))" strokeWidth={2}><title>{`${spec.labels[i]}: ${fmt(v)} (${Math.round((v / total) * 100)}%)`}</title></path>;
        })}
      </svg>
      <div className="core-vis-legend">
        {(pie ? spec.labels : spec.series.map((s) => s.name)).map((name, i) => <span key={i}><i style={{ background: COLORS[i % COLORS.length] }} />{name}</span>)}
      </div>
    </figure>
  );
}

const isDark = () => document.documentElement.dataset.theme === "dark"
  || (!document.documentElement.dataset.theme && window.matchMedia?.("(prefers-color-scheme: dark)").matches);

/** Flowcharts, sequence diagrams and more. Loaded on demand; until the text is a valid diagram the source stays visible. */
function MermaidView({ text, fallback }: { text: string; fallback: ReactNode }) {
  const id = useId().replace(/[^a-zA-Z0-9]/g, "");
  const [svg, setSvg] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    const timer = setTimeout(async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: isDark() ? "dark" : "neutral", fontFamily: "inherit" });
        await mermaid.parse(text);
        const rendered = await mermaid.render(`mmd${id}`, text);
        if (alive) setSvg(rendered.svg);
      } catch {
        if (alive) setSvg(null);                         // half-streamed or invalid: keep showing the source
      }
    }, 450);
    return () => { alive = false; clearTimeout(timer); };
  }, [text, id]);
  if (!svg) return <>{fallback}</>;
  return <div className="core-vis core-mermaid" role="img" aria-label="Diagram" dangerouslySetInnerHTML={{ __html: svg }} />;
}

/** A fenced block drawn as a graph, chart or diagram, with a switch to the source. */
export function VisualBlock({ language, text, label, done, fallback }: { language: string; text: string; label: string; done: string; fallback: ReactNode }) {
  const [source, setSource] = useState(false);
  const [copied, setCopied] = useState(false);
  const visual = language === "mermaid" ? <MermaidView text={text} fallback={fallback} />
    : language === "chart" ? <ChartView text={text} fallback={fallback} />
      : <PlotView text={text} />;
  return (
    <div className="core-code core-visual">
      <div className="core-code-head">
        <span>{language === "desmos" ? "plot" : language}</span>
        <span className="core-code-actions">
          <button type="button" onClick={() => setSource((v) => !v)}>{source ? "Graph" : "Source"}</button>
          <button type="button" onClick={() => { void navigator.clipboard?.writeText(text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1200); }); }}>{copied ? done : label}</button>
        </span>
      </div>
      {source ? fallback : visual}
    </div>
  );
}

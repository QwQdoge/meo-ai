export class MathError extends Error {}
export const MAX_CURVES: number;
export function compileExpression(source: string, variables?: string[]): (x: number) => number;
export type Curve = { kind: string; label: string; [key: string]: any };
export type PlotSpec = { title: string; xRange: [number, number] | null; yRange: [number, number] | null; curves: Curve[]; errors: { line: number; text: string; message: string }[] };
export function parsePlot(text: string): PlotSpec;
export function sampleFunction(f: (x: number) => number, xmin: number, xmax: number, ymin: number, ymax: number, count?: number): number[][][];
export function sampleParam(fx: (t: number) => number, fy: (t: number) => number, t0: number, t1: number, count?: number): number[][][];
export function samplePolar(r: (t: number) => number, count?: number, a?: number, b?: number): number[][][];
export function autoView(spec: PlotSpec): { x: [number, number]; y: [number, number] };
export function niceTicks(min: number, max: number, target?: number): number[];
export type ChartSpec = { type: 'bar' | 'line' | 'pie'; title: string; labels: string[]; series: { name: string; data: number[] }[] };
export function parseChart(text: string): { spec: ChartSpec } | { error: string };

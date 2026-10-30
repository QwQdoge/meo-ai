// Loaded on demand (see rich.tsx): KaTeX and the Markdown math plugins are only fetched once an answer contains a formula.
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";

export const mathRemark = [remarkMath];
export const mathRehype = [[rehypeKatex, { throwOnError: false, strict: "ignore" }]] as any[];

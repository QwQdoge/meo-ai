import React from "react";

type Spec = Record<string, any>;

/** The generic on / off switch the core attaches to a row or card (`switch: {on, label, action}`). */
export function Switch({ spec, act }: { spec: Spec; act: (a: any) => void }) {
  return (
    <button type="button" role="switch" aria-checked={!!spec.on} aria-label={spec.label} className="core-switch" onClick={() => act(spec.action)}>
      <i />
    </button>
  );
}

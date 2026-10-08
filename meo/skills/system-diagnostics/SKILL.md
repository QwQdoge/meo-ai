---
name: system-diagnostics
description: Diagnose MeoArch symptoms using observed facts and registered read capabilities.
---

1. Ask for the symptom and affected component; inspect available typed capabilities.
2. Use read-only owner APIs or request a diagnostic report from Quick Repair.
3. Separate observed facts from hypotheses. Do not invent journal access.
4. Propose the smallest repair and its verification before requesting a write.
5. Use the repair owner's existing confirmation and Polkit interface.

This skill grants no capabilities. If no maintained API exists, hand off to
Settings or Quick Repair. Never use a shell command as an OS API fallback.

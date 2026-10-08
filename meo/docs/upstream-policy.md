# Upstream divergence policy

Keep upstream `src/`, `data/`, providers, Skills, MCP and history formats intact
unless a tested integration seam needs a patch. Meo-specific files live in
`meo/`. Preserve `COPYING`, attribution, upstream README and Git history.

Current seams:

1. `src/meo_profile.py` + Meson-installed prompt data.
2. `ChatInterface` selects the overlay for `meo:` sessions.
3. `run_llm_with_tools(extra_system_prompts=...)` appends it each inference turn.
4. API SSE carries additive `delta.meo_event` without removing legacy text.

Synchronization: fetch `upstream`, create a review branch from the Meo default
branch, merge a reviewed upstream commit, resolve seams, run native and protocol
checks, then open a PR. Never force-push default or merge untested changes.
Do not automatically merge upstream CI/release changes. Record the new baseline
in the architecture document after review. `master` remains the inherited default
branch so GitHub correctly retains the fork relationship.

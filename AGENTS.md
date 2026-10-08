# Meo AI contributor rules

Preserve Newelle upstream provenance and GPL-3.0 license. Keep product-specific
work under `meo/`; limit `src/` patches to documented integration seams.
Do not delete GTK while the core still imports Gtk/Adw/WebKit.

MeoUI owns shared controls and tokens. Meo.System, Account, SystemTransaction,
OmniStore and repair authorities retain their typed privilege boundaries.
Prompts, Skills and MCP descriptions are never security enforcement.

Inspect status and nearest code/tests before changes. Preserve unrelated work.
For Python changes run `python3 -m compileall -q src` and
`python3 -m unittest discover -s meo/tests -p 'test_*.py' -v`.
For native changes configure/build `meo/` with MeoUI and run CTest offscreen.
Distinguish mock protocol tests, native builds, real agent/provider execution,
and live Plasma integration in reports. No release/tag/signing is implied.

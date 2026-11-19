# Meo AI for Chrome

Lets Meo AI on **chat.meoarch.org** use your own Chrome: open pages, read them, click, type and take
screenshots, in a tab it opens, with your logins. It is off until you turn it on.

## Install (until it is on the Chrome Web Store)

1. Download this folder (`meo/browser-extension` in the meo-ai repository).
2. Open `chrome://extensions`, turn on **Developer mode**, click **Load unpacked** and pick the folder.
3. Click the Meo AI icon in the toolbar and turn on **Allow Meo AI to control this browser**.
4. In Meo AI: Settings → Permissions → Browser control → **My Chrome (extension)**, then reload chat.meoarch.org.

## How it works

- `bridge.js` runs only on `https://chat.meoarch.org/*` and passes messages between the page and the
  extension; the page never gets the extension's APIs.
- `background.js` runs the tools (`browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type`,
  `browser_press_key`, `browser_scroll`, `browser_navigate_back`, `browser_take_screenshot`, `browser_tabs`).
  Tool calls are accepted only from that bridge, and only while control is on.
- Meo works in one tab it opened (or one you picked with `browser_tabs`); `chrome://`, extension pages
  and the Web Store are never touched; it refuses to type into password fields.
- Meo AI's permission levels apply as on the desktop: looking at a page asks nothing, clicking and typing
  follow your approval level.

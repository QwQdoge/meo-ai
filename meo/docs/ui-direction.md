# Meo AI UI direction — Quiet Expressive

Meo AI should feel clearly designed, but never performative. The visual target is **quiet expressive**: strong hierarchy, deliberate shape and spacing, a small amount of tension between compact and open areas, and very little decorative noise.

## Principles

1. **Tension comes from hierarchy, not decoration.** Use differences in scale, density, alignment, and container shape before adding color, gradients, shadows, or motion.
2. **The conversation remains the stable center.** Navigation, cards, confirmations, and model controls must not make the message column jump unnecessarily.
3. **Primary color is an accent, not wallpaper.** Reserve it for current selection, status marks, values, focus, and the most important action.
4. **One expressive move per region.** A selected navigation card, an assistant identity mark, or a compact card grid is enough. Do not stack multiple visual effects in the same region.
5. **Motion is state feedback.** Use MeoUI's existing state/ripple/spring behavior. Avoid ambient animation, looping effects, large transforms, parallax, or attention-seeking entrance motion.
6. **Useful before impressive.** Keyboard navigation, readable line length, stable focus, responsive layout, cancellation, confirmation, and error states are higher priority than visual novelty.

## Layout

- Wide desktop (1280 dp and above): a 248 dp navigation area, bounded conversation, and optional 340 dp response inspector. Each region has its own rounded tonal surface.
- Medium desktop: the inspector opens as a dismissible overlay. Below 1120 dp the navigation collapses to 72 dp; below 760 dp it disappears and essential actions remain in the header.
- Users can drag the two SplitView dividers to resize navigation and details, or hide either panel using its header control. Widths and visibility persist in the native layout settings; the chat always retains a minimum usable width.
- Navigation icons and labels align to the left.
- The empty conversation has a quiet centered introduction, draft shortcuts and composer. Conversation mode moves the composer to the bottom.
- User messages use a compact tonal container. Assistant messages use open text with a small identity mark, copy action and response-details action.
- Conversation and composer share an 840 dp maximum width. Structured result cards sit in the scrollable history, wrapping from three columns to one as space changes.
- The inspector separates response metadata, managed memory, pending resources and AI settings. Its data comes from AgentClient; missing provider fields are omitted.
- Navigation shows the current conversation and searches its messages. Do not invent recent chats, account identity or online devices in place of missing APIs.

## Interaction stability

- Streaming follows the bottom only while the reader is already near the bottom. If the user scrolls upward, new tokens must not drag the viewport back down.
- `Enter` sends, while `Shift+Enter` inserts a new line. IME composition is allowed to consume Enter first so Chinese/Japanese/Korean input is not broken.
- `Ctrl+N` creates a new chat when no request or confirmation is blocking it.
- Presentation cards use `card_id` as stable identity. A repeated ID updates the existing card in place instead of appending duplicates and shifting the shelf.
- Updates to cards retain their identity and place in the grid. They do not force the reader back to the bottom of the conversation.
- Response details retain each answer’s tool trace during the current session so selecting an earlier answer does not show the newest answer’s events.
- Important controls expose stable object names so native UI tests can inspect responsive states without depending on pixel-perfect screenshots.

## AI presentation cards

Cards are **secondary context**, not another chat transcript.

- Up to six cards are retained by the native client.
- Multiple cards share a responsive grid in the scrollable conversation. They must remain readable without covering the composer.
- Cards use a consistent compact width and bounded text. Long detail text is bounded rather than expanding the whole interface.
- `info`, `status`, `metric`, `file`, and `system` share the same visual family. The kind label is metadata, not a loud badge.
- Repeated updates to the same card preserve its position, which is especially important for metrics, media state, build status, and system controls.
- Cards never imply authority. Privileged operations continue through typed tools and explicit confirmation.

## Confirmation

A pending tool decision is visually separated from ordinary cards with a tonal surface and explicit decision buttons. It should be noticeable immediately without looking like an error dialog unless an actual error occurred.

## Model roles

Model-role configuration is a focused modal surface, not a permanent dashboard. Background roles (`title`, `judge`) use quieter outlined cards while primary roles (`reasoning`, `execution`) use filled cards. The model picker uses the MeoUI exposed-dropdown component so keyboard, focus, visual state, and accessibility behavior match the rest of MeoArch.

The UI must make the split between background and primary workloads understandable without implying that a saved preference is already active runtime routing.

## Visual limits

Avoid by default:

- decorative gradients;
- neon/glow effects;
- large saturated backgrounds;
- oversized pill controls everywhere;
- more than one strong accent color in the same surface;
- looping or autonomous animation;
- glass/blur as a dependency for basic legibility;
- dense dashboards around the chat.

The desired result should still look correct with animations disabled and with a neutral Material 3 dynamic color palette.

## Preview and acceptance

`meo-ai --ui-demo --size 1560x940 --screenshot /absolute/output/path.png` renders deterministic sample content without refreshing service metadata. The header labels it as a design preview. The fixtures are not measurements of the current computer or evidence of provider execution. Normal startup shows actual service state and starts with no fabricated messages.

Validate the wide conversation, empty page and narrow breakpoints offscreen, then run native CTest including the local HTTP/SSE fake-AI integration. Offscreen rendering does not establish real Plasma focus, accessibility, IME, scale or compositor behavior.

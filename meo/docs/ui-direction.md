# Meo AI UI direction — Quiet Expressive

Meo AI should feel clearly designed, but never performative. The visual target is **quiet expressive**: strong hierarchy, deliberate shape and spacing, a small amount of tension between compact and open areas, and very little decorative noise.

## Principles

1. **Tension comes from hierarchy, not decoration.** Use differences in scale, density, alignment, and container shape before adding color, gradients, shadows, or motion.
2. **The conversation remains the stable center.** Navigation, cards, confirmations, and model controls must not make the message column jump unnecessarily.
3. **Primary color is an accent, not wallpaper.** Reserve it for current selection, status marks, values, focus, and the most important action.
4. **One expressive move per region.** A selected navigation card, an assistant accent rail, or a compact card shelf is enough. Do not stack multiple visual effects in the same region.
5. **Motion is state feedback.** Use MeoUI's existing state/ripple/spring behavior. Avoid ambient animation, looping effects, large transforms, parallax, or attention-seeking entrance motion.
6. **Useful before impressive.** Keyboard navigation, readable line length, stable focus, responsive layout, cancellation, confirmation, and error states are higher priority than visual novelty.

## Layout

- Wide desktop: 236 dp navigation rail, compact 66 dp top bar, bounded conversation width, composer fixed to the bottom.
- Medium desktop: navigation rail collapses to 78 dp rather than forcing content too narrow.
- Compact window: navigation rail disappears; the top bar keeps only the essential model-role, stop, and new-chat controls.
- Conversation text is visually quieter than cards and actions. User messages use a compact container; assistant messages use open surface plus a thin accent rail.

## AI presentation cards

Cards are **secondary context**, not another chat transcript.

- Up to six cards are retained by the native client.
- Multiple cards live in one horizontal shelf above the composer instead of wrapping into unpredictable rows.
- Cards use a consistent compact width and bounded text. Long detail text is clipped rather than expanding the whole interface.
- `info`, `status`, `metric`, `file`, and `system` share the same visual family. The kind label is metadata, not a loud badge.
- Cards never imply authority. Privileged operations continue through typed tools and explicit confirmation.

## Confirmation

A pending tool decision is visually separated from ordinary cards with a selected outlined surface and a narrow primary accent. It should be noticeable immediately without looking like an error dialog unless an actual error occurred.

## Model roles

Model-role configuration is a focused modal surface, not a permanent dashboard. Role cards are outlined and dense. The UI should make the split between background (`title`, `judge`) and primary (`reasoning`, `execution`) workloads understandable without implying that a saved preference is already active runtime routing.

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
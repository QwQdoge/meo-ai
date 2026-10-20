# Cloud core view contract (v1)

`meo_ai_core::cloud::AppCore` owns all product state. A client:

1. creates the core with platform hooks (`changed()`, `open_url(url)`) and a storage
   implementation, dispatches `{"type":"start"}`;
2. renders `AppCore::view()` (JSON below) whenever `changed()` fires;
3. sends back the `action` object attached to the element the user activated, adding
   only user input fields (`text` for `send`, `value` for `set_setting`).

Clients must not interpret feature IDs; they render component kinds only.

## Root

| Field | Meaning |
| --- | --- |
| `schema` | View schema version (1) |
| `auth.state` | `signed_out` / `signing_in` / `signed_in`; `auth.email` |
| `online` | `false` → show an offline hint; cached data is still shown |
| `navigation[]` | `{id,label,icon,symbol,placement(primary/secondary),selected,action}`; empty when signed out |
| `page` | One of the page kinds below |
| `notice` | `{kind: error/info, text, action}` or `null` |
| `prefs` | Client preferences (e.g. `general.enter_to_send`, `appearance.theme`) |

## Page kinds

- `sign_in`: `title, text, busy, actions[]`
- `conversation`: `title`, `sidebar{title, actions[], items[{id,title,subtitle,selected,action}]}`,
  `messages[{role,text,streaming}]` (text is Markdown), `empty{title,text}|null`,
  `composer{placeholder,busy,sendAction,stopAction,toolbar[control]}`, `consent{title,text,actions[2]}|null`
- `list`: `title, loading?, items[{id,title,subtitle,action?}], empty{title}|null, actions[]`
- `settings`: `title, sections[{id,label,items[control]}]`
- `unavailable`: `title, text, actions[]`

`button` = `{label, style: primary/secondary/danger, action}`.
`control` = `{id,label,kind,binding,value,options[{value,label}],action?,style?}` with
`kind` ∈ `toggle | select | text | info | button`. Changing a control dispatches
`{"type":"set_setting","binding":…,"value":…}`; `button` dispatches its `action`.

## Actions

`start, sign_in, sign_out, auth_callback{url}, navigate{route}, new_conversation,
select_conversation{id}, send{text}, stop, approve_consent, deny_consent,
set_setting{binding,value}, refresh, dismiss_notice`.

> 📚 [MeoArch 主文档 / Master Doc](https://github.com/QwQdoge/MeoArch-os-workspace/blob/main/docs/MEOARCH_MASTER.md)：全部仓库地图、操作手册、Cloudflare 清单、全部文档链接。<!-- meoarch-master -->

# Projects, environments and persistent state

A **project** is where Chat and Work keep their context. Meo API stores its name, description,
instructions, chats and memories (so they follow the account to every device). On top of that, each
**device** can link a project to an **environment**, and a project folder keeps the **goal, to-do
list and notes** between sessions. All of it lives in `core-rs/src/cloud` (`project_env.rs` and
`app.rs`); the clients only draw the project page. For the distinction between conversation-only
Chat and device-bound Work (including the General and Code profiles), see
[Chat, Work and Code product model](chat-work-product-model.md).

## Environment (per device)

| Link | What it does | Stored |
| --- | --- | --- |
| Folder | Work in this project reads, edits and runs commands in this folder (desktop only; the system folder dialog picks it). | This device (`project-envs`), never uploaded |
| GitHub repository | Tells the model which repository the project is about; it reaches issues, pull requests and remote files through the GitHub app (the project page shows whether that app is installed, on and signed in, with the button that fixes it). | This device |

* **Starting Work in a project** (`start_project_work`, the "Work here" / "Start Work" buttons) files
  the new task under the project and opens the folder linked to the selected target device. The user
  must be able to see/confirm the target device; a saved default may preselect it but must not hide it.
  A project task uses that device's linked folder; anything else uses the general Work folder
  (`/workspace`, the composer's folder chip). With the chip, choosing a folder while a project is open
  links it to the project on this device.
* **Online** (no folder, or the web / Android clients): the repository link and the GitHub app are the
  environment. Local folders need the desktop app; the web and Android show that plainly instead of a
  button that cannot work.
* A project folder can be any local folder, a git checkout or not. With a repository linked and an
  **empty** folder, "Clone into folder" runs `git clone https://github.com/<repo>.git .` there (your own
  git credentials; a non-empty folder is refused, nothing is overwritten).

## Goal, to-do and notes: `.agent/` in the project folder

```
<project folder>/
  AGENTS.md        rules for how to work (stays where it is)
  .agent/
    GOAL.md        what the project is for and when it is done
    TODO.md        - [ ] open  - [~] in progress  - [x] done, under ## Now / ## Next / ## Done
    NOTES.md       a short introduction: what is where, how to run and test, decisions
```

Plain Markdown, so it survives restarts, can be edited by hand, committed with the code and read by any
tool. `AGENTS.md` and `.agent/` have different jobs: rules versus state. The core never moves
`AGENTS.md`.

* **Created** only when asked: the project page's "Set up .agent" button, or by the model when a task
  is larger than a small edit (the rules tell it to). Existing files are never overwritten.
* **Read** at the start of every Work turn (fresh from disk, bounded) and added to the prompt as
  "Project state", after the static instructions so prompt caches still hit.
* **Kept up to date by the model** (static rule `PERSISTENT_STATE` in `agent.rs`): update GOAL.md when
  the goal changes; write the plan as TODO items at the start of work with more than two steps; mark
  `[~]` when starting and `[x]` when done and checked, in the same turn; add discovered work; record
  lasting decisions in NOTES.md; never delete a to-do the user wrote; keep files short.
* **Edited by the user** on the project page: the goal text, ticking a to-do (writes `[x]` / `[ ]` into
  the file) and "Add a to-do" (goes under `## Next`). Edits on disk, by hand or by the model, show after
  every tool round or when the project is opened. While Work runs, the details card lists the goal and
  the to-do (in-progress item animated) instead of the model's inline task list.
* Notes and rules are data, never instructions that override the request and never grant permissions.

## Project page

Overview (Start Work, name, description, instructions) · Environment · Goal & to-do · Chats · Memory ·
Danger zone. The page has its own navigation; the app sidebar stays, unlike Settings (`standalone`).

## Not done yet

* The repository link is per device: Meo API has no field for it yet. Folder links cannot sync (paths
  differ between machines), but the repository could move to the project record.
* Goal and to-do for a project that has no folder (they would have to live in Meo API).
* Android cannot pick a folder; it shows the project and its repository only.

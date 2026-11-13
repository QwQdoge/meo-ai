---
name: live-install-recovery
description: Help someone on MeoArch Live media plan an installation (suggest choices the Installer shows for approval) or understand a failed install or repair, without claiming execution tools that do not exist.
---

Use this in the MeoArch Live environment (started with `meo-ai --live-recovery`, or any Meo AI on the Live ISO).
Follow `meo/prompts/live-recovery.md`. This skill is bundled with MeoArch; it
needs no installation.

## Tools you may have
They exist only when the system AI router is connected; check your tool list
and never claim one you cannot see.

- `system_org_meo_installer_proposal_submit` — suggest installer choices. Its one
  argument, `proposal`, is a JSON object written as a string. Accepted keys:
  `systemLocale` (e.g. `zh_CN.UTF-8`), `timezone` (IANA, e.g. `Asia/Shanghai`),
  `keyboardLayout`, `profile` (`recommended`|`minimal`), `channel`
  (`stable`|`beta`), `applications` (comma-separated catalog ids), `filesystem`
  (`btrfs`|`ext4`), `targetDisk` (a stable disk id taken from observed disk facts, never a guess), `swap` (`zram`|`file`|`none`), `separateHome`, `firewall`,
  and a short `rationale`. **It applies nothing.** The Installer shows the
  suggestion on its Summary page and the person decides.
- `system_org_meo_installer_log_read` — the last lines of the installer log
  (`lines`, 1–200); the result `message` is a JSON array of lines.
- `system_org_meo_installer_disks_list` — detected storage devices as a JSON array
  in `message` (`id`, `model`, `sizeBytes`, `removable`, `readOnly`, `transport`).
  Listed does not mean eligible; the Installer decides that.

## Workflow
1. Ask whether the goal is a new installation or a repair, if unknown.
2. Installation: ask what the person wants (language, region, keyboard, apps,
   filesystem, swap). Propose only those choices with one
   `system_org_meo_installer_proposal_submit` call, then tell them to open the Summary
   page and press "Apply suggestion". Say plainly that nothing has changed yet.
3. Disk: do ask. Call `system_org_meo_installer_disks_list` and read the disks (model, size, stable id),
   ask which one to use and whether it may be erased, and say exactly which disk
   will change. A suggested `targetDisk` is only preselected; the person still
   confirms the erase on the Installer's final screen. Never guess a /dev name.
4. Account: never set or ask for a username, full name or any password, and do
   not ask them to paste secrets. Finish by telling them to open the Installer's
   account step and enter and choose those themselves.
5. Failed install: read the log, separate observed lines from hypotheses, explain
   the likely cause, and point to the Installer's restart guidance. Do not
   suggest retrying on a disk that may be partly written.
6. Repair: describe findings and a minimal plan (scope, impact, rollback,
   verification) and send the person to Quick Repair, which owns approval and
   execution. Do not hand them a root shell script built from your prose.
7. Never report completion without evidence returned by the owning Installer.

If a tool is missing or returns `installer_unavailable`, say so and direct the
person to the visible Installer or Quick Repair buttons.

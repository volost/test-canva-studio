# Reference copies

Four files were copied (copy, not move) on **2026-11-21** from the project owner's machine, where the originals stay,
so that this repository is self-contained. They are reading material for the person or model that works on the studio;
no code imports them. The skill (`.claude/skills/test-canva-studio/`) and `DESIGN.md` / `PLAN.md` cite them as
`PLAYBOOK §n`, `SPEC §n`, `BLUEPRINT`.

| File here | Origin (owner's machine) | Origin file's date | What it is |
|---|---|---|---|
| `PLAYBOOK.md` | `/Users/volost/GitRepos/canva/handoff/PLAYBOOK.md` | 2026-11-12 | How a Claude Code session generates a Canva wedding website template from a skeleton: connector behaviour found by running it (§4), the phases of the 2026-11-12 run (§5), restart rule and hard limits (§6), pitfalls. Section 11 lists what that run did NOT establish. |
| `SPEC.md` | `/Users/volost/GitRepos/canva/study/sage-linen/SPEC.md` | 2026-11-21 (translated; original Ukrainian text kept beside it on the owner's machine as `SPEC.uk.md`) | The spec of the first new design, "Sage & Linen": look, asset table, envelope geometry, slot table, wording data, and in §7 the configurability rules for the buyer. |
| `BLUEPRINT.md` | `/Users/volost/GitRepos/canva/study/ivory-lace/BLUEPRINT.md` | 2026-11-21 (translated; original kept as `BLUEPRINT.uk.md`) | The owner's own analysis notes of the purchased reference template (structure, layout principles, type and image roles, frame sizes, interactive parts, verified connector abilities, open points). |
| `../../config/extra_model_paths.example.yaml` | `/Users/volost/GitRepos/canva/pilot/comfy/extra_model_paths.yaml` | 2026-11-11 | ComfyUI's extra model folders file. The machine path inside was replaced with an example path and a comment explaining it. |

The bodies of the three Markdown files are unedited copies, with one exception: one sample e-mail address in `SPEC.md`
(§6 "Wording", a made-up contact for the example couple) was replaced with `hello@example.com`, because the repository
carries no e-mail addresses.

## What is deliberately NOT included

- The seller's materials of the purchased template: its PDF guide, images and any file of the seller's. Their licence
  terms are not known, so they stay on the owner's machine. `BLUEPRINT.md` is the project's own analysis, not the seller's text.
- The rest of the owner's study and pilot folders (`study/`, `pilot/`, `handoff/tools`, `handoff/examples`, element
  outlines, exports, logs). The files above still mention some of them (for example `study/sage-linen/assets/`,
  `pilot/tools/white_to_alpha.py`); those paths exist only on the owner's machine. Code in `app/` and `canva/` was
  ported from some of those scripts (the docstrings say which); the ported versions in this repository are the working ones.

## Reading order for a newcomer

`PLAYBOOK.md` first (it is written for a Claude session working for another person), then `SPEC.md` §7, then `BLUEPRINT.md`
only if you need to understand the Ivory Lace skeleton.

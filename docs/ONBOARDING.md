# Onboarding — your first day on the studio

This is the checklist for a developer who joins the project and continues it in their own Claude Code session.
The full setup reference is [README.md](../README.md); the project rules for Claude are in [CLAUDE.md](../CLAUDE.md).
Work through the steps in order. Each step says what "done" looks like.

The project belongs to the **owner** (the person who invited you). The owner approves every step of the studio's
flow, merges branches and owns the Canva designs. Talk to the owner in their language (Ukrainian); everything in the
repository is in English, and the studio's own interface is in Ukrainian on purpose.

## 1. Accounts and access (before you clone)

- [ ] **GitHub.** Accept the invitation to the private repository `volost/test-canva-studio`.
      Done: you can open https://github.com/volost/test-canva-studio.
- [ ] **Claude.** You need Claude Code (CLI or the Claude desktop app) signed in to your own Claude account.
- [ ] **Canva connector — your own.** Connectors are tied to the Claude account that connects them, so the owner's
      connector does not travel with the repository. In claude.ai open the connector settings, add **Canva** and sign in
      with **your** Canva account. (The exact menu names may differ by app version — this path is unverified.)
      Done: in a Claude Code session, a request such as "list my Canva designs" returns designs from your account.
- [ ] **Canva designs.** Ask the owner to share with your Canva account (Share → add your e-mail → *Can edit*):
      - the test copy `DAHason1g_M` — the development skeleton the studio is built and tested on (PLAN Task 13 uses it);
      - later, the owner's own skeleton when it exists.
      Then let your Claude session make **your own** copy of the test copy and register it as the development
      skeleton: follow [docs/CANVA_TEST_COPY.md](CANVA_TEST_COPY.md). A Canva design cannot be stored in git.
      The purchased original `DAHarqlqips` must **never** be edited. You do not need access to it; if you have it, treat
      it as read-only. The studio refuses it as a target (`forbidden_design_ids` in `config.json`), keep it there.
      Note: when the studio's skill runs `copy-design`, the new copy is created in the Canva account of **whoever's
      connector runs it** — with your connector, template copies land in your account. Agree with the owner where the
      copies should live before the first real run.

## 2. Machine setup

- [ ] Follow README "Requirements" and "Setup" steps 1–6: clone, `config.json` from `config.example.json`,
      ComfyUI model paths, `.git/info/exclude` lines, tests, `./run.sh`.
      Done: the test suite ends with `OK` (about 460 tests), and `./run.sh` prints both addresses
      (`Студія: http://127.0.0.1:8765`, `ComfyUI: http://127.0.0.1:8188`).
- [ ] Open http://127.0.0.1:8765 in a browser. Done: the page «Студія шаблонів» ("Template studio") opens; the lists
      are empty on a fresh clone.
- [ ] Optional: if you want Claude Code to run the server tests inside its sandbox, set
      `sandbox.network.allowLocalBinding: true` in **your own** settings (README "Optional sandbox setting").

## 3. Your first Claude Code session

- [ ] Open Claude Code **in the repo root** (the cloned `test-canva-studio` folder), not in a parent folder. Only then
      are `CLAUDE.md`, the project settings and the `/test-canva-studio` command loaded at start.
- [ ] Paste this as your first message:

      > Read CLAUDE.md, STATUS.md, docs/DECISIONS.md and docs/OPEN_ISSUES.md in full. Then summarise in ten lines:
      > what the studio does, what is done, what is next (PLAN.md Task 13 and Task 14), what is unverified, and the hard
      > rules. Do not change anything yet.

      Done: the summary matches STATUS.md — Tasks 1–12 done, Task 13 (end-to-end run on the test copy) and Task 14
      (spec for the owner's own skeleton) left, then a final review of the whole branch.
- [ ] Check that the command is available: type `/` and look for `test-canva-studio`. It is a manual-only command
      (`disable-model-invocation`), so Claude will never start it on its own.

## 4. How work is done here

- **Branches.** Work on a branch, push it, and ask the owner to merge. Do not push to `main`.
- **Commits.** No `Co-Authored-By` lines and no "Generated with" lines in commits, PRs or docs.
- **Plan and method.** PLAN.md is the plan; tasks run as one implementer agent plus one reviewer agent per task
  (superpowers subagent-driven development). Every decision taken so far, with its reason, is in docs/DECISIONS.md;
  read the relevant part before changing something that looks odd — it is usually there for a reason.
- **Verify, don't assume.** A claim about behaviour needs a run; otherwise write "unverified". Every check in the code
  has a control (a deliberately bad input it must reject) — keep that pattern.
- **Never delete** files, generations, designs or branches without the owner's explicit command. The studio itself never
  deletes; "regenerate" adds a new version.
- **Canva safety.** Canva is written only through a studio job executed by `/test-canva-studio`, only on the template's
  own copy, one writer at a time; never publish a site, submit a form or change account settings.
- **Comments.** Add English comments wherever the next person or model needs them (module purpose, non-obvious
  decisions and why).
- **Out of scope by the owner's decision:** Etsy listings and sales rules, the buyer's PDF guide, and checking the
  Z-Image Turbo licence.

## 5. Your first task

Task 13 — the first end-to-end run on the test copy — is done **together with the owner**, because every step needs
their approval (PLAN.md Task 13, STATUS.md "What to hand to Task 13"). Before it, agree with the owner on:

1. whose Canva account the template copy is created in (section 1 note);
2. the session in which `/test-canva-studio` runs (yours, with your connector);
3. a time when the owner can approve steps in the studio UI.

Task 14 (docs for the owner's own skeleton) is independent and can be done first if the owner prefers.

## 6. If something does not match

If this guide, README, STATUS.md or the code disagree, the code and a live run win. Tell the owner, fix the document on
a branch, and record the reason in docs/DECISIONS.md.

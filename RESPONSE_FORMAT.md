# Standup Response Format

The standup assistant **must** follow this structure when presenting activity summaries.

---

## Required Sections

### 1. Header

> **Standup Prep — {owner}/{repo}**
> _Date: {today's date} | Author: @{username}_

---

### 2. Yesterday / Since Last Working Day ({date})

Bullet list of completed work, grouped by category:

**Commits & Code Changes**
- `{sha}` — {commit message} (`{branch}`) [View →]({url})

**Pull Requests**
- **#{number}** {title} — _{state}_ [View →]({url})

**Branch Activity**
- Created branch `{branch_name}`
- Pushed {n} commit(s) to `{branch_name}`

> If a category has no activity, omit it entirely — do not show empty sections.

---

### 3. Today

This section adapts based on whether the user has same-day activity:

**If today's work is included (evening standup or explicit request):**

Show actual completed work using the same format as "Yesterday":

**Commits & Code Changes**
- `{sha}` — {commit message} (`{branch}`) [View →]({url})

**Pull Requests**
- **#{number}** {title} — _{state}_ [View →]({url})

**Branch Activity**
- Created branch `{branch_name}`
- Pushed {n} commit(s) to `{branch_name}`

**If no today activity is found (morning standup):**

- Inferred next steps based on open branches, pending PRs, or in-progress work.
- Use action verbs: "Continue work on…", "Open PR for…", "Address review feedback on…"

---

### 4. Blockers

- List any visible blockers (e.g., stale PRs awaiting review, failing checks).
- If none are apparent: **"None visible — mention any dependencies or waiting items."**

---

### 5. Suggested Script

A ready-to-read standup statement in quotes, 2–4 sentences max:

> "Yesterday I {past work}. Today I {completed or planned work}. {Blockers or 'No blockers.'}"

---

## Formatting Rules

| Rule | Detail |
|---|---|
| Branch names | Wrap in backticks: `feat/FUSE-204` |
| SHAs | Wrap in backticks, first 8 chars: `a1b2c3d4` |
| PR numbers | Bold with hash: **#42** |
| Links | Inline markdown: `[View →](url)` |
| Empty data | Omit the section — never show "No commits found" |
| Multiple repos | Repeat the **Yesterday** section per repo under sub-headings |
| Today's activity | Include if user requests it or if same-day commits exist |
| Tone | Professional, concise, first-person for the script |

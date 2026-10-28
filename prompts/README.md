# AI Prompt History

This folder documents how AI tools were used while building YottaFlex
Attribution OS. Its purpose is provenance: a reviewer should be able to see
which tool contributed to which kind of work, how that work was integrated, and
what evidence verifies the result.

## Tool roles

| Tool | Documented role |
| --- | --- |
| [Claude](CLAUDE_PROMPTS.md) | User-confirmed contributor for selected React components, reusable UI patterns, interface copy, frontend API request code, and selected backend coding where applicable. |
| [ChatGPT](CHATGPT_PROMPTS.md) | User-confirmed contributor for requirement analysis, implementation planning, coding-prompt generation, UI review prompts, export-audit instructions, and QA checklists. It did not edit repository files. |
| [OpenCode](OPENCODE_PROMPTS.md) | Repository implementation agent used in recorded sessions for code inspection, file edits, running commands, debugging, tests, exports, and browser QA. |

The three roles are complementary. ChatGPT helped turn requirements into
instructions; Claude contributed to selected implementation work; OpenCode
applied, integrated, and verified changes in the repository. No tool is
credited with writing the entire application.

## Files

- [AI_USAGE_LOG.md](AI_USAGE_LOG.md) - consolidated contribution and
  verification table.
- [CLAUDE_PROMPTS.md](CLAUDE_PROMPTS.md) - frontend, reusable-component, API,
  and backend coding contributions.
- [CHATGPT_PROMPTS.md](CHATGPT_PROMPTS.md) - requirement analysis, prompt
  generation, UX review, export-audit, and test-planning prompts.
- [OPENCODE_PROMPTS.md](OPENCODE_PROMPTS.md) - repository inspection,
  implementation, debugging, testing, and browser verification.

## Original prompts versus reconstructed summaries

The repository does not contain complete transcripts for every AI session.
Entries are therefore marked in one of two ways:

- **Actual prompt or excerpt** - text recovered from a recorded session or
  reproduced from a prompt supplied in that session.
- **Reconstructed summary** - a concise description of the task, clearly
  labelled because the exact historical wording is unavailable.

Reconstructed summaries are not presented as verbatim history. They describe
the task and the resulting repository change, not an invented conversation.

Large confidential assessment instructions are intentionally not reproduced.
Only short task-level excerpts and project-specific summaries are included.

## Evidence standard

Claims in these documents are tied to at least one of:

- source files in this repository;
- automated tests under `backend/tests/`;
- API responses or parsed export files;
- commands executed in the repository and their recorded results;
- browser checks documented in the final review material.

Where authorship cannot be proven from a stored transcript, the document says
so. The repository can verify that a feature exists and works; it cannot always
prove which assistant drafted a particular line.

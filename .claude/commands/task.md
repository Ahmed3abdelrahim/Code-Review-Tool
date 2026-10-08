Work on task $ARGUMENTS from docs/Code_Review_IMPLEMENTATION_PLAN.md, following the workflow in CLAUDE.md.

1. Read docs/PROGRESS.md. Confirm every task listed in "Depends on" is ticked. If not, stop and tell
   me which ones are missing.
2. Read only the section for task $ARGUMENTS, any part of Section 5 it references, and the existing
   code it touches.
3. Think hard: design options, edge cases, failure modes, security implications, and how each
   acceptance criterion will be proven.
4. Present the plan: goal; acceptance criteria (numbered); exact test files and test names; files to
   create or change; design choices and trade-offs; risks; open questions. Stop and wait for approval.
5. After approval, write the tests first. Run them and show they fail for the expected reason.
6. Implement. Run `make check` and the task's integration/security/fault tests until green.
7. Report every acceptance criterion as PASS or FAIL with evidence.
8. Update docs/PROGRESS.md (tick the task, short notes) and docs/DECISIONS.md if a decision was made.
9. Give me the list of created and changed files and a Conventional Commit message with the task ID
   as scope. Do not run git; I commit.

Never weaken, skip or delete a test or acceptance criterion to make it pass. If an AC looks wrong or
impossible, stop and explain why.

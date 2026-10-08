Verify the gate for phase $ARGUMENTS. Report only; do not modify any file.

1. Read the "Phase $ARGUMENTS gate" block and Section 9 of docs/Code_Review_IMPLEMENTATION_PLAN.md.
2. Confirm in docs/PROGRESS.md that every task of the phase is ticked.
3. Run `make check-all` and `make verify-p$ARGUMENTS`, and `make eval` if the phase is 3 or later.
4. For each gate criterion, report PASS / FAIL / NEEDS-MANUAL with evidence.
5. List the manual end-to-end steps I must run (from the phase verification task) and what to check.

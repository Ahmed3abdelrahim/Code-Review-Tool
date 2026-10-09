Persist task completion

Adds `POST /tasks/:id/complete`, which marks a task done and stores the completion time. Completing a task that is already done is a no-op, so double clicks in the UI are harmless.

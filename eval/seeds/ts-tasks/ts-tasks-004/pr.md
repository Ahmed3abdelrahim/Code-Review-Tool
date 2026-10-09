Add sort option to task listing

`listTasks` takes an optional `{ sortBy }` (`"createdAt"` by default, or `"dueDate"`), and `GET /projects/:projectId/tasks?sort=dueDate` uses it. Unknown sort values fall back to creation order.

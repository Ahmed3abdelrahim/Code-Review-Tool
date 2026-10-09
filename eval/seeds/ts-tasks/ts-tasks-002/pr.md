Validate new task input

Creating a task now checks the request body: `title` (required, at most 200 characters) and `estimateHours` (required, a number); `dueDate` is optional and must parse as a date. Invalid requests get a 400 listing every problem instead of a database error.

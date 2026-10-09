import type { Task } from "../domain/task";

/** Drops completed tasks from the list and returns it. */
export function removeCompleted(tasks: Task[]): Task[] {
  tasks.forEach((task, index) => {
    if (task.status === "done") {
      tasks.splice(index, 1);
    }
  });
  return tasks;
}

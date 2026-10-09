import type { Task, TaskStatus } from "../domain/task";

export type StatusCounts = Record<TaskStatus, number>;

export function countByStatus(tasks: readonly Task[]): StatusCounts {
  const counts: StatusCounts = { todo: 0, in_progress: 0, done: 0 };
  for (const task of tasks) {
    counts[task.status] += 1;
  }
  return counts;
}

import type { Task } from "../domain/task";

/** Share of the estimate already spent, capped at 1. */
export function progress(task: Task): number {
  return Math.min(task.spentHours / task.estimateHours, 1);
}

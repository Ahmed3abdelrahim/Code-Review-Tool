import type { NewTaskInput, Task } from "../domain/task";
import type { TaskStore } from "../repositories/taskRepository";
import { NotFoundError } from "./errors";

export type TaskSortKey = "createdAt" | "dueDate";

export interface ListTasksOptions {
  /** Defaults to "createdAt" (oldest first). With "dueDate", tasks without one come last. */
  sortBy?: TaskSortKey;
}

function byDueDate(a: Task, b: Task): number {
  const aTime = a.dueDate?.getTime() ?? Number.POSITIVE_INFINITY;
  const bTime = b.dueDate?.getTime() ?? Number.POSITIVE_INFINITY;
  if (aTime !== bTime) {
    return aTime < bTime ? -1 : 1;
  }
  return a.id - b.id;
}

export class TaskService {
  constructor(private readonly tasks: TaskStore) {}

  async getTask(id: number): Promise<Task> {
    const task = await this.tasks.findById(id);
    if (!task) {
      throw new NotFoundError(`task ${id} not found`);
    }
    return task;
  }

  async listTasks(projectId: number, options: ListTasksOptions = {}): Promise<Task[]> {
    const { sortBy = "createdAt" } = options;
    const tasks = await this.tasks.listByProject(projectId);
    return sortBy === "dueDate" ? [...tasks].sort(byDueDate) : tasks;
  }

  createTask(projectId: number, input: NewTaskInput): Promise<Task> {
    return this.tasks.insert(projectId, input);
  }

  async logTime(id: number, hours: number): Promise<Task> {
    const task = await this.getTask(id);
    const updated: Task = { ...task, spentHours: task.spentHours + hours };
    await this.tasks.save(updated);
    return updated;
  }
}

import type { NewTaskInput, Task } from "../domain/task";
import type { TaskStore } from "../repositories/taskRepository";
import { NotFoundError } from "./errors";

export class TaskService {
  constructor(private readonly tasks: TaskStore) {}

  async getTask(id: number): Promise<Task> {
    const task = await this.tasks.findById(id);
    if (!task) {
      throw new NotFoundError(`task ${id} not found`);
    }
    return task;
  }

  listTasks(projectId: number): Promise<Task[]> {
    return this.tasks.listByProject(projectId);
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

import type { NewTaskInput, Task } from "../src/domain/task";
import type { TaskStore } from "../src/repositories/taskRepository";

export function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 1,
    projectId: 10,
    title: "Write release notes",
    status: "todo",
    estimateHours: 4,
    spentHours: 0,
    dueDate: null,
    createdAt: new Date("2025-03-01T09:00:00Z"),
    completedAt: null,
    archived: false,
    ...overrides,
  };
}

export class InMemoryTaskStore implements TaskStore {
  readonly tasks = new Map<number, Task>();

  constructor(tasks: Task[] = []) {
    for (const task of tasks) {
      this.tasks.set(task.id, task);
    }
  }

  async findById(id: number): Promise<Task | null> {
    return this.tasks.get(id) ?? null;
  }

  async listByProject(projectId: number): Promise<Task[]> {
    return [...this.tasks.values()].filter((t) => t.projectId === projectId && !t.archived);
  }

  async insert(projectId: number, input: NewTaskInput): Promise<Task> {
    const task = makeTask({
      id: this.tasks.size + 1,
      projectId,
      title: input.title,
      estimateHours: input.estimateHours,
      dueDate: input.dueDate ?? null,
    });
    this.tasks.set(task.id, task);
    return task;
  }

  async save(task: Task): Promise<void> {
    this.tasks.set(task.id, task);
  }
}

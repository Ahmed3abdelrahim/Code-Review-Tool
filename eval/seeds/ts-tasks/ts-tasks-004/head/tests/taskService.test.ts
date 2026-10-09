import { describe, expect, it } from "vitest";

import { NotFoundError } from "../src/services/errors";
import { TaskService } from "../src/services/taskService";
import { InMemoryTaskStore, makeTask } from "./fakes";

describe("TaskService", () => {
  it("throws NotFoundError for an unknown task", async () => {
    const service = new TaskService(new InMemoryTaskStore());
    await expect(service.getTask(42)).rejects.toBeInstanceOf(NotFoundError);
  });

  it("adds logged time to the task", async () => {
    const store = new InMemoryTaskStore([makeTask({ spentHours: 1.5 })]);
    const updated = await new TaskService(store).logTime(1, 2);
    expect(updated.spentHours).toBe(3.5);
    expect(store.tasks.get(1)?.spentHours).toBe(3.5);
  });

  it("sorts by due date with undated tasks last", async () => {
    const store = new InMemoryTaskStore([
      makeTask({ id: 1, dueDate: null }),
      makeTask({ id: 2, dueDate: new Date("2025-04-10") }),
      makeTask({ id: 3, dueDate: new Date("2025-04-02") }),
    ]);
    const tasks = await new TaskService(store).listTasks(10, { sortBy: "dueDate" });
    expect(tasks.map((t) => t.id)).toEqual([3, 2, 1]);
  });

  it("keeps creation order by default", async () => {
    const store = new InMemoryTaskStore([makeTask({ id: 1 }), makeTask({ id: 2 })]);
    const tasks = await new TaskService(store).listTasks(10);
    expect(tasks.map((t) => t.id)).toEqual([1, 2]);
  });

  it("creates tasks in the given project", async () => {
    const service = new TaskService(new InMemoryTaskStore());
    const task = await service.createTask(10, { title: "Plan sprint", estimateHours: 2 });
    expect(await service.listTasks(10)).toEqual([task]);
  });
});

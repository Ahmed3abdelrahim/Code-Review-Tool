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

  it("marks a task done and records when", async () => {
    const service = new TaskService(new InMemoryTaskStore([makeTask()]));
    const task = await service.completeTask(1);
    expect(task.status).toBe("done");
    expect(task.completedAt).toBeInstanceOf(Date);
  });

  it("leaves an already completed task unchanged", async () => {
    const done = makeTask({ status: "done", completedAt: new Date("2025-03-02T10:00:00Z") });
    const service = new TaskService(new InMemoryTaskStore([done]));
    expect(await service.completeTask(1)).toEqual(done);
  });

  it("creates tasks in the given project", async () => {
    const service = new TaskService(new InMemoryTaskStore());
    const task = await service.createTask(10, { title: "Plan sprint", estimateHours: 2 });
    expect(await service.listTasks(10)).toEqual([task]);
  });
});

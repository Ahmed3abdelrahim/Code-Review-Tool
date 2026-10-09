import { describe, expect, it } from "vitest";

import { countByStatus } from "../src/services/stats";
import { makeTask } from "./fakes";

describe("countByStatus", () => {
  it("counts every status, including those with no tasks", () => {
    const tasks = [
      makeTask({ id: 1, status: "todo" }),
      makeTask({ id: 2, status: "done" }),
      makeTask({ id: 3, status: "todo" }),
    ];
    expect(countByStatus(tasks)).toEqual({ todo: 2, in_progress: 0, done: 1 });
  });

  it("returns zeros for an empty project", () => {
    expect(countByStatus([])).toEqual({ todo: 0, in_progress: 0, done: 0 });
  });
});

import { describe, expect, it } from "vitest";

import { removeCompleted } from "../src/ui/filters";
import { makeTask } from "./fakes";

describe("removeCompleted", () => {
  it("keeps only unfinished tasks", () => {
    const tasks = [
      makeTask({ id: 1, status: "todo" }),
      makeTask({ id: 2, status: "done" }),
      makeTask({ id: 3, status: "in_progress" }),
      makeTask({ id: 4, status: "done" }),
    ];
    expect(removeCompleted(tasks).map((t) => t.id)).toEqual([1, 3]);
  });

  it("returns an empty list unchanged", () => {
    expect(removeCompleted([])).toEqual([]);
  });
});

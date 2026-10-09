import { describe, expect, it } from "vitest";

import { ValidationError } from "../src/services/errors";
import { parseNewTask } from "../src/services/validation";

function problemsOf(body: unknown): string[] {
  try {
    parseNewTask(body);
  } catch (err) {
    if (err instanceof ValidationError) {
      return err.problems;
    }
    throw err;
  }
  return [];
}

describe("parseNewTask", () => {
  it("accepts a complete body and trims the title", () => {
    expect(parseNewTask({ title: "  Fix login  ", estimateHours: 3 })).toEqual({
      title: "Fix login",
      estimateHours: 3,
      dueDate: null,
    });
  });

  it("requires a title and an estimate", () => {
    expect(problemsOf({})).toEqual(["title is required", "estimateHours is required"]);
  });

  it("rejects an estimate that is not a number", () => {
    expect(problemsOf({ title: "Fix login", estimateHours: "three" })).toEqual([
      "estimateHours must be a number",
    ]);
  });

  it("parses the due date", () => {
    const input = parseNewTask({ title: "Ship", estimateHours: 1, dueDate: "2025-04-01" });
    expect(input.dueDate).toEqual(new Date("2025-04-01"));
  });
});

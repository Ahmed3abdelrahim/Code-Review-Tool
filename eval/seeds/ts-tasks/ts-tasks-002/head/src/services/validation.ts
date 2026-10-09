import type { NewTaskInput } from "../domain/task";
import { ValidationError } from "./errors";

const MAX_TITLE_LENGTH = 200;

/** Checks a create-task request body and returns it as a NewTaskInput. */
export function parseNewTask(body: unknown): NewTaskInput {
  const input = (typeof body === "object" && body !== null ? body : {}) as Record<string, unknown>;
  const problems: string[] = [];

  const title = typeof input.title === "string" ? input.title.trim() : "";
  if (title === "") {
    problems.push("title is required");
  } else if (title.length > MAX_TITLE_LENGTH) {
    problems.push(`title must be at most ${MAX_TITLE_LENGTH} characters`);
  }

  const estimateHours = input.estimateHours;
  if (estimateHours == null) {
    problems.push("estimateHours is required");
  } else if (typeof estimateHours !== "number" || Number.isNaN(estimateHours)) {
    problems.push("estimateHours must be a number");
  }

  let dueDate: Date | null = null;
  if (input.dueDate != null) {
    dueDate = new Date(String(input.dueDate));
    if (Number.isNaN(dueDate.getTime())) {
      problems.push("dueDate must be a date");
    }
  }

  if (problems.length > 0) {
    throw new ValidationError(problems);
  }
  return { title, estimateHours: estimateHours as number, dueDate };
}

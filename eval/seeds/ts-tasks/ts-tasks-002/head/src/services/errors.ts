export class NotFoundError extends Error {
  override name = "NotFoundError";
}

export class ValidationError extends Error {
  override name = "ValidationError";

  constructor(readonly problems: string[]) {
    super(problems.join("; "));
  }
}

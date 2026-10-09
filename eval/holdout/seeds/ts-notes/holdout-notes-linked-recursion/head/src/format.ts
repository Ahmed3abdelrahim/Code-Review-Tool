import type { Note } from "./notes";

export function formatTitle(note: Note): string {
  return note.title.trim() || "(untitled)";
}

export function formatDay(date: Date): string {
  return date.toISOString().slice(0, 10);
}

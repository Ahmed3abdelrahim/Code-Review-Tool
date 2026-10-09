import type { Note } from "./notes";

export function formatTitle(note: Note): string {
  return note.title.trim() || "(untitled)";
}

export function formatDay(date: Date): string {
  return date.toISOString().slice(0, 10);
}

export function notesOnDay(notes: Note[], day: string): Note[] {
  const target = new Date(day);
  return notes.filter(
    (n) =>
      n.createdAt.getFullYear() === target.getFullYear() &&
      n.createdAt.getMonth() === target.getMonth() &&
      n.createdAt.getDate() === target.getDate(),
  );
}

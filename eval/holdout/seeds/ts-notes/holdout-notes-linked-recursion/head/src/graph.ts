import type { NoteStore } from "./notes";

export function collectLinked(store: NoteStore, id: string): string[] {
  const note = store.get(id);
  if (!note) {
    return [];
  }
  const result: string[] = [];
  for (const target of note.links) {
    result.push(target, ...collectLinked(store, target));
  }
  return result;
}

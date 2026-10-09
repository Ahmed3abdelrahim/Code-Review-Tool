export interface Note {
  id: string;
  title: string;
  body: string;
  createdAt: Date;
  links: string[];
}

export class NoteStore {
  private readonly notes = new Map<string, Note>();

  add(note: Note): void {
    this.notes.set(note.id, note);
  }

  get(id: string): Note | undefined {
    return this.notes.get(id);
  }

  link(fromId: string, toId: string): void {
    const from = this.notes.get(fromId);
    if (!from) {
      throw new Error(`Unknown note: ${fromId}`);
    }
    if (!this.notes.has(toId)) {
      throw new Error(`Unknown note: ${toId}`);
    }
    from.links.push(toId);
  }

  all(): Note[] {
    return [...this.notes.values()];
  }
}

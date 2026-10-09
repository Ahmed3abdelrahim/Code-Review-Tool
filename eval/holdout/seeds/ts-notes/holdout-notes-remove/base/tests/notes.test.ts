import { describe, expect, it } from "vitest";
import { NoteStore } from "../src/notes";

describe("NoteStore", () => {
  it("links two notes", () => {
    const store = new NoteStore();
    store.add({ id: "a", title: "A", body: "", createdAt: new Date(0), links: [] });
    store.add({ id: "b", title: "B", body: "", createdAt: new Date(0), links: [] });
    store.link("a", "b");
    expect(store.get("a")?.links).toEqual(["b"]);
  });
});

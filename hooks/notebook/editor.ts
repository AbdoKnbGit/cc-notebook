// Size only the viewport. The Input always owns the whole cell and scrolls it.
export function editorRows(bodyRows: number, columns: number) {
  const footer = columns < 24 ? 4 : 2
  return Math.max(2, Math.min(80, bodyRows - footer - 3))
}

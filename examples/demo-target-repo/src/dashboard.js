export function emptyBugListMessage(items) {
  return items.length === 0 ? "No items" : `${items.length} bugs`;
}

export function addBugButtonLabel() {
  return "Add";
}

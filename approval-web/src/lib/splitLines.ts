export function splitLines(value: string) {
  return value
    .split("\n")
    .map(line => line.trim())
    .filter(Boolean);
}

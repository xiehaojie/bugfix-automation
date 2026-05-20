export function compactPath(value?: string) {
  if (!value) return "";
  if (value.length <= 64) return value;
  return `...${value.slice(-61)}`;
}

export function formatBytes(value?: number) {
  if (!value) return "0 B";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

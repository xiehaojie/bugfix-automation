export function Badge({ children, tone = "green" }: { children: string; tone?: "green" | "blue" | "gray" }) {
  return <span className={`badge ${tone}`}>{children || "未填"}</span>;
}

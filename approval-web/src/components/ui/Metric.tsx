export function Metric({ value, label }: { value: number; label: string }) {
  return <div className="metric"><strong>{value}</strong><span>{label}</span></div>;
}

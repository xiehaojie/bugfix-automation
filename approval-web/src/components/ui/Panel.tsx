import type { ReactNode } from "react";

export function Panel({ title, icon, aside, children }: { title: string; icon: ReactNode; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="panel">
      <div className="panelTitle">
        <div>{icon}<h3>{title}</h3></div>
        {aside ? <span className="panelAsideSlot">{aside}</span> : null}
      </div>
      {children}
    </section>
  );
}

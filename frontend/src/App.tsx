const stackItems = ["PostgreSQL", "FastAPI", "React", "Docker Compose"];

export function App() {
  return (
    <main className="workspace-shell">
      <section className="workspace-header">
        <p className="eyebrow">New workspace</p>
        <h1>PUR Leads v2</h1>
      </section>
      <section className="stack-strip" aria-label="Application stack">
        {stackItems.map((item) => (
          <span key={item}>{item}</span>
        ))}
      </section>
    </main>
  );
}

import Link from "next/link";
import { SiteHeader } from "./components/site-header";

const features = [
  {
    id: "chat",
    title: "Chat with Laplace",
    description:
      "Ask about SOPs, articles, meetings, and project decisions. Every answer comes with its sources.",
    action: "Ask a question",
  },
];

export default function Home() {
  return (
    <main className="home" id="home">
      <SiteHeader activePage="home" />

      <section className="hero" aria-labelledby="hero-title">
        <h1 id="hero-title">
          See Clearly.
          <br />
          <span>Laplace.</span>
        </h1>
        <p className="hero-copy">
          Find answers, not documents. Your company&apos;s knowledge, one
          question away.
        </p>
      </section>

      <section className="features" aria-label="Explore Laplace">
        <div className="feature-grid">
          {features.map((feature) => (
            <Link
              className="feature-card"
              href="/chat"
              id={feature.id}
              key={feature.id}
            >
              <span className="card-title">{feature.title}</span>
              <span className="card-description">{feature.description}</span>
              <span className="card-action">
                {feature.action}
                <span className="card-arrow" aria-hidden="true">
                  ↗
                </span>
              </span>
            </Link>
          ))}
        </div>
      </section>

      <footer className="site-footer">
        <a className="footer-brand" href="#home">
          Laplace
        </a>
        <span>A clearer way to work.</span>
        <a className="back-to-top" href="#home">
          Back to top ↑
        </a>
      </footer>
    </main>
  );
}

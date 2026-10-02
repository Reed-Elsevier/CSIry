import Link from "next/link";

type SiteHeaderProps = {
  activePage: "home" | "chat";
};

export function SiteHeader({ activePage }: SiteHeaderProps) {
  return (
    <header className="site-header">
      <Link className="brand" href="/" aria-label="Laplace home">
        <span className="brand-mark" aria-hidden="true">
          <span />
          <span />
          <span />
          <span />
        </span>
        <span>laplace</span>
      </Link>

      <nav className="main-nav" aria-label="Main navigation">
        <Link
          className={`nav-link${activePage === "home" ? " nav-link-active" : ""}`}
          href="/"
          aria-current={activePage === "home" ? "page" : undefined}
        >
          Home
        </Link>
        <Link
          className={`nav-link${activePage === "chat" ? " nav-link-active" : ""}`}
          href="/chat"
          aria-current={activePage === "chat" ? "page" : undefined}
        >
          Chat
        </Link>
      </nav>
    </header>
  );
}

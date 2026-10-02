import { Fragment, type ReactNode } from "react";

// Tiny dependency-free markdown renderer. Supports: headings, bold, italic,
// inline code, code fences, links, ordered/unordered lists, blockquotes and
// horizontal rules. Output is real React elements (no dangerouslySetInnerHTML).

const INLINE =
  /(`[^`]+`|\*\*[^*]+\*\*|\*[^*\s][^*]*\*|\[[^\]]+\]\([^)\s]+\))/g;

const HR = /^\s*([-*_])(\s*\1){2,}\s*$/;
const HEADING = /^(#{1,6})\s+(.*?)\s*#*\s*$/;
const UL = /^\s*[-*+]\s+(.*)$/;
const OL = /^\s*(\d+)[.)]\s+(.*)$/;
const QUOTE = /^\s*>\s?(.*)$/;
const FENCE = /^\s*```/;

function isBlockStart(line: string): boolean {
  return (
    FENCE.test(line) ||
    HR.test(line) ||
    HEADING.test(line) ||
    UL.test(line) ||
    OL.test(line) ||
    QUOTE.test(line)
  );
}

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  return text
    .split(INLINE)
    .filter(Boolean)
    .map((part, i) => {
      const key = `${keyPrefix}-${i}`;

      if (part.length > 2 && part.startsWith("`") && part.endsWith("`")) {
        return <code key={key}>{part.slice(1, -1)}</code>;
      }
      if (part.length > 4 && part.startsWith("**") && part.endsWith("**")) {
        return <strong key={key}>{renderInline(part.slice(2, -2), key)}</strong>;
      }
      if (part.length > 2 && part.startsWith("*") && part.endsWith("*")) {
        return <em key={key}>{renderInline(part.slice(1, -1), key)}</em>;
      }

      const link = part.match(/^\[([^\]]+)\]\(([^)\s]+)\)$/);
      if (link && /^(https?:|mailto:)/i.test(link[2])) {
        return (
          <a key={key} href={link[2]} target="_blank" rel="noopener noreferrer">
            {link[1]}
          </a>
        );
      }

      return <Fragment key={key}>{part}</Fragment>;
    });
}

function renderBlocks(source: string, keyPrefix: string): ReactNode[] {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const out: ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const key = `${keyPrefix}-${out.length}`;

    if (!line.trim()) {
      i++;
      continue;
    }

    // Code fence
    if (FENCE.test(line)) {
      const code: string[] = [];
      i++;
      while (i < lines.length && !FENCE.test(lines[i])) {
        code.push(lines[i]);
        i++;
      }
      i++; // skip closing fence
      out.push(
        <pre key={key}>
          <code>{code.join("\n")}</code>
        </pre>,
      );
      continue;
    }

    // Horizontal rule
    if (HR.test(line)) {
      out.push(<hr key={key} />);
      i++;
      continue;
    }

    // Heading
    const heading = line.match(HEADING);
    if (heading) {
      const Tag = `h${heading[1].length}` as
        | "h1"
        | "h2"
        | "h3"
        | "h4"
        | "h5"
        | "h6";
      out.push(<Tag key={key}>{renderInline(heading[2], key)}</Tag>);
      i++;
      continue;
    }

    // Blockquote (contents are parsed as markdown too)
    if (QUOTE.test(line)) {
      const inner: string[] = [];
      while (i < lines.length && QUOTE.test(lines[i])) {
        inner.push((lines[i].match(QUOTE) as RegExpMatchArray)[1]);
        i++;
      }
      out.push(
        <blockquote key={key}>{renderBlocks(inner.join("\n"), key)}</blockquote>,
      );
      continue;
    }

    // Lists
    if (UL.test(line) || OL.test(line)) {
      const ordered = OL.test(line);
      const re = ordered ? OL : UL;
      const start = ordered ? Number((line.match(OL) as RegExpMatchArray)[1]) : 1;
      const items: string[] = [];

      while (i < lines.length) {
        const m = lines[i].match(re);
        if (m) {
          items.push(m[m.length - 1]);
          i++;
        } else if (
          // wrapped continuation line of the previous item
          lines[i].trim() &&
          /^\s{2,}/.test(lines[i]) &&
          items.length > 0 &&
          !isBlockStart(lines[i])
        ) {
          items[items.length - 1] += " " + lines[i].trim();
          i++;
        } else if (!lines[i].trim() && i + 1 < lines.length && re.test(lines[i + 1])) {
          i++; // blank line between items of the same list
        } else {
          break;
        }
      }

      const listItems = items.map((text, n) => (
        <li key={n}>{renderInline(text, `${key}-${n}`)}</li>
      ));
      out.push(
        ordered ? (
          <ol key={key} start={start}>
            {listItems}
          </ol>
        ) : (
          <ul key={key}>{listItems}</ul>
        ),
      );
      continue;
    }

    // Paragraph
    const paragraph = [line];
    i++;
    while (i < lines.length && lines[i].trim() && !isBlockStart(lines[i])) {
      paragraph.push(lines[i]);
      i++;
    }
    out.push(<p key={key}>{renderInline(paragraph.join(" "), key)}</p>);
  }

  return out;
}

export function Markdown({ content }: { content: string }) {
  return <>{renderBlocks(content, "md")}</>;
}

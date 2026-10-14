import { Fragment } from "react";

/** Minimal, safe markdown for agent answers: **bold**, "- " bullets, paragraphs. No HTML injection. */
function inline(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((p, i) =>
    p.startsWith("**") && p.endsWith("**") ? <strong key={i}>{p.slice(2, -2)}</strong> : <Fragment key={i}>{p}</Fragment>,
  );
}

export function SimpleMarkdown({ text }: { text: string }) {
  const blocks: JSX.Element[] = [];
  let list: string[] = [];
  const flush = () => {
    if (list.length) {
      blocks.push(
        <ul key={`ul-${blocks.length}`} className="ml-4 list-disc space-y-1">
          {list.map((li, i) => (
            <li key={i}>{inline(li)}</li>
          ))}
        </ul>,
      );
      list = [];
    }
  };
  text.split("\n").forEach((line) => {
    if (line.startsWith("- ")) {
      list.push(line.slice(2));
    } else {
      flush();
      if (line.trim()) blocks.push(<p key={`p-${blocks.length}`}>{inline(line)}</p>);
    }
  });
  flush();
  return <div className="space-y-2">{blocks}</div>;
}

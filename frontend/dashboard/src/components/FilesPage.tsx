import { useState } from "react";
import { readFile, searchFiles } from "../api/dexterApi";

export default function FilesPage() {
  const [query, setQuery] = useState("backend");
  const [matches, setMatches] = useState<string[]>([]);
  const [selectedPath, setSelectedPath] = useState("");
  const [content, setContent] = useState("");

  async function handleSearch() {
    const data = await searchFiles(query);
    setMatches(data.matches ?? []);
  }

  async function handleRead(path: string) {
    const data = await readFile(path);
    setSelectedPath(path);

    if (data.ok) {
      setContent(data.content);
    } else {
      setContent(data.error ?? "Unable to read file.");
    }
  }

  return (
    <section className="page-panel">
      <div className="page-header">
        <div>
          <h2>Files & Folders</h2>
          <p>Search project files and inspect contents.</p>
        </div>
      </div>

      <div className="file-page-grid">
        <section className="mini-panel">
          <h3>Search Files</h3>

          <div className="compact-input-row">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              placeholder="Search files..."
            />
            <button onClick={handleSearch}>Search</button>
          </div>

          <div className="file-results">
            {matches.map((match) => (
              <button key={match} onClick={() => handleRead(match)}>
                {match}
              </button>
            ))}
          </div>
        </section>

        <section className="mini-panel file-page-viewer">
          <h3>{selectedPath || "File Viewer"}</h3>
          <pre className="file-page-preview">
            {content || "Select a file to view its contents."}
          </pre>
        </section>
      </div>
    </section>
  );
}
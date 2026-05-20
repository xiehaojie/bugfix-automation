import { Columns, FileCode2, FileMinus2, FilePlus2, Rows3 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

interface DiffViewProps {
  diff: string;
  scrollToFile?: string | null;
  changedFiles?: string[];
  branch?: string;
}

interface FileSegment {
  path: string;
  lines: string[];
}

function splitDiffByFile(diff: string): FileSegment[] {
  const lines = diff.split("\n");
  const segments: FileSegment[] = [];
  let current: FileSegment | null = null;
  for (const line of lines) {
    if (line.startsWith("diff --git")) {
      const m = line.match(/^diff --git a\/(.+?) b\//);
      const path = m?.[1] ?? "(unknown)";
      current = { path, lines: [line] };
      segments.push(current);
    } else if (current) {
      current.lines.push(line);
    } else {
      current = { path: "(header)", lines: [line] };
      segments.push(current);
    }
  }
  return segments.filter(s => s.path !== "(header)" || s.lines.some(l => l.trim()));
}

function classifyLine(line: string): string {
  if (line.startsWith("diff --git")) return "file";
  if (line.startsWith("+++") || line.startsWith("---")) return "fileMeta";
  if (line.startsWith("@@")) return "hunk";
  if (line.startsWith("+")) return "add";
  if (line.startsWith("-")) return "del";
  if (line.startsWith("index ") || line.startsWith("new file") || line.startsWith("deleted file") || line.startsWith("similarity") || line.startsWith("rename ")) return "fileMeta";
  return "ctx";
}

/** Parse @@ -a,b +c,d @@ header into starting line numbers */
function parseHunkHeader(line: string): { oldStart: number; newStart: number } {
  const m = line.match(/@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
  return { oldStart: m ? Number(m[1]) : 1, newStart: m ? Number(m[2]) : 1 };
}

interface NumberedLine {
  kind: "ctx" | "add" | "del" | "hunk" | "file" | "fileMeta";
  text: string;
  oldLine: number | null;
  newLine: number | null;
}

function buildUnifiedNumbered(segmentLines: string[]): NumberedLine[] {
  const result: NumberedLine[] = [];
  let oldLine = 0;
  let newLine = 0;
  for (const raw of segmentLines) {
    const cls = classifyLine(raw) as NumberedLine["kind"];
    if (cls === "hunk") {
      const { oldStart, newStart } = parseHunkHeader(raw);
      oldLine = oldStart;
      newLine = newStart;
      result.push({ kind: "hunk", text: raw, oldLine: null, newLine: null });
    } else if (cls === "del") {
      result.push({ kind: "del", text: raw, oldLine, newLine: null });
      oldLine++;
    } else if (cls === "add") {
      result.push({ kind: "add", text: raw, oldLine: null, newLine });
      newLine++;
    } else if (cls === "ctx") {
      result.push({ kind: "ctx", text: raw, oldLine, newLine });
      oldLine++;
      newLine++;
    } else {
      result.push({ kind: cls, text: raw, oldLine: null, newLine: null });
    }
  }
  return result;
}

interface SideBySideRow {
  left: { kind: "ctx" | "del" | "empty"; text: string; line: number | null };
  right: { kind: "ctx" | "add" | "empty"; text: string; line: number | null };
}

interface Hunk {
  header: string;
  rows: SideBySideRow[];
}

function buildSideBySide(segmentLines: string[]): { hunks: Hunk[] } {
  const hunks: Hunk[] = [];
  let current: Hunk | null = null;
  let dels: { text: string; line: number }[] = [];
  let adds: { text: string; line: number }[] = [];
  let oldLine = 0;
  let newLine = 0;

  const flushPair = () => {
    if (!current) return;
    const max = Math.max(dels.length, adds.length);
    for (let i = 0; i < max; i++) {
      const d = dels[i];
      const a = adds[i];
      current.rows.push({
        left: d ? { kind: "del", text: d.text, line: d.line } : { kind: "empty", text: "", line: null },
        right: a ? { kind: "add", text: a.text, line: a.line } : { kind: "empty", text: "", line: null },
      });
    }
    dels = [];
    adds = [];
  };

  for (const raw of segmentLines) {
    const cls = classifyLine(raw);
    if (cls === "file" || cls === "fileMeta") continue;
    if (cls === "hunk") {
      flushPair();
      const { oldStart, newStart } = parseHunkHeader(raw);
      oldLine = oldStart;
      newLine = newStart;
      current = { header: raw, rows: [] };
      hunks.push(current);
      continue;
    }
    if (!current) continue;
    if (cls === "del") {
      dels.push({ text: raw.slice(1), line: oldLine });
      oldLine++;
    } else if (cls === "add") {
      adds.push({ text: raw.slice(1), line: newLine });
      newLine++;
    } else {
      flushPair();
      const text = raw.startsWith(" ") ? raw.slice(1) : raw;
      current.rows.push({
        left: { kind: "ctx", text, line: oldLine },
        right: { kind: "ctx", text, line: newLine },
      });
      oldLine++;
      newLine++;
    }
  }
  flushPair();
  return { hunks };
}

function basename(path: string): string {
  const parts = path.split("/");
  return parts[parts.length - 1] || path;
}

/** Fetch and display file content for new/deleted files */
function FileContentViewer({ branch, path, isNew }: { branch?: string; path: string; isNew: boolean }) {
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [visible, setVisible] = useState(false);

  const load = async () => {
    if (!branch) { setError("未知分支，无法读取文件"); return; }
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/file-content?branch=${encodeURIComponent(branch)}&path=${encodeURIComponent(path)}`);
      const data = await res.json();
      if (data.ok) {
        setContent(data.content);
        setVisible(true);
      } else {
        setError(data.error ?? "读取失败");
      }
    } catch {
      setError("网络错误");
    } finally {
      setLoading(false);
    }
  };

  if (!visible && !content) {
    return (
      <div className="diffNoContent">
        <div className="diffNoContentInfo">
          {isNew
            ? <><FilePlus2 size={15} className="diffNoContentIcon new" /> 新建文件</>
            : <><FileMinus2 size={15} className="diffNoContentIcon del" /> 文件已删除</>}
        </div>
        <button
          type="button"
          className="diffPreviewBtn"
          onClick={load}
          disabled={loading}
        >
          {loading ? "读取中…" : <><FileCode2 size={13} /> 预览文件内容</>}
        </button>
        {error && <span className="diffPreviewError">{error}</span>}
      </div>
    );
  }

  const lines = (content ?? "").split("\n");
  return (
    <div className="diffFileContentViewer">
      <div className="diffFileContentHeader">
        <span className="diffFileContentLines">{lines.length} 行</span>
        <button type="button" className="diffPreviewBtn ghost" onClick={() => { setVisible(false); setContent(null); }}>收起</button>
      </div>
      <table className="diffTable unified">
        <tbody>
          {lines.map((line, i) => (
            <tr key={i} className={`diffRow ${isNew ? "add" : "del"}`}>
              <td className="diffLineNum old">{isNew ? "" : i + 1}</td>
              <td className="diffLineNum new">{isNew ? i + 1 : ""}</td>
              <td className="diffCode"><pre>{(isNew ? "+" : "-") + line || " "}</pre></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function DiffView({ diff, scrollToFile, changedFiles, branch }: DiffViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  const segments = useMemo(() => {
    const parsed = splitDiffByFile(diff);
    if (!changedFiles?.length) return parsed;
    const diffPaths = new Set(parsed.map(s => s.path));
    for (const file of changedFiles) {
      const alreadyExists = diffPaths.has(file) ||
        [...diffPaths].some(p => p.endsWith(file) || file.endsWith(p));
      if (!alreadyExists) {
        parsed.push({ path: file, lines: [`diff --git a/${file} b/${file}`, "new file mode 100644"] });
      }
    }
    return parsed;
  }, [diff, changedFiles]);

  const [mode, setMode] = useState<"unified" | "split">("split");
  const [activeFile, setActiveFile] = useState<string | null>(null);

  useEffect(() => {
    if (!scrollToFile) return;
    const match = segments.find(s =>
      s.path === scrollToFile || s.path.endsWith(scrollToFile) || scrollToFile.endsWith(s.path)
    );
    if (match) setActiveFile(match.path);
  }, [scrollToFile, segments]);

  useEffect(() => {
    if (activeFile) return;
    const first = segments.find(s => s.path !== "(header)");
    if (first) setActiveFile(first.path);
  }, [segments, activeFile]);

  const fileSegments = segments.filter(s => s.path !== "(header)");

  if (!diff.trim() && !fileSegments.length) return <div className="noDiff">没有当前工作区 diff。</div>;

  const visible = activeFile ? segments.filter(s => s.path === activeFile) : segments;

  return (
    <div className="diffWrap" ref={containerRef}>
      <div className="diffToolbar">
        <div className="diffFileTabs" role="tablist">
          {fileSegments.map(seg => {
            const hasHunks = seg.lines.some(l => l.startsWith("@@"));
            const isNew = seg.lines.some(l => l.startsWith("new file"));
            const isDel = seg.lines.some(l => l.startsWith("deleted file"));
            return (
              <button
                key={seg.path}
                role="tab"
                aria-selected={seg.path === activeFile}
                className={`diffFileTab ${seg.path === activeFile ? "active" : ""}`}
                onClick={() => setActiveFile(seg.path)}
                title={seg.path}
              >
                {basename(seg.path)}
                {isNew && !hasHunks && <span className="diffTabBadge new">新建</span>}
                {isDel && !hasHunks && <span className="diffTabBadge del">删除</span>}
              </button>
            );
          })}
        </div>
        <div className="diffModeSwitch" role="group" aria-label="差异显示模式">
          <button type="button" className={`diffModeBtn ${mode === "split" ? "active" : ""}`} onClick={() => setMode("split")} title="左右对照">
            <Columns size={13} /> 左右
          </button>
          <button type="button" className={`diffModeBtn ${mode === "unified" ? "active" : ""}`} onClick={() => setMode("unified")} title="统一视图">
            <Rows3 size={13} /> 统一
          </button>
        </div>
      </div>
      <div className="diffBody">
        {visible.map(seg => {
          const hasHunks = seg.lines.some(l => l.startsWith("@@"));
          const isNew = seg.lines.some(l => l.startsWith("new file"));
          const isDel = seg.lines.some(l => l.startsWith("deleted file"));
          return (
            <div className="diffFile" key={seg.path} data-file={seg.path}>
              <div className="diffFileHeader">
                {seg.path}
                {isNew && <span className="diffFileBadge new">新建文件</span>}
                {isDel && <span className="diffFileBadge del">已删除</span>}
              </div>
              {hasHunks ? (
                isNew || isDel
                  ? <WholeFileSegment lines={seg.lines} isNew={isNew} />
                  : mode === "unified" ? <UnifiedSegment lines={seg.lines} /> : <SplitSegment lines={seg.lines} />
              ) : (
                <FileContentViewer branch={branch} path={seg.path} isNew={isNew} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function WholeFileSegment({ lines, isNew }: { lines: string[]; isNew: boolean }) {
  const numbered = useMemo(() => buildUnifiedNumbered(lines), [lines]);
  const content = numbered.filter(ln => isNew ? ln.kind === "add" : ln.kind === "del");
  return (
    <table className="diffTable unified">
      <tbody>
        {content.map((ln, i) => (
          <tr key={i} className="diffRow add">
            <td className="diffLineNum old">{isNew ? "" : ln.oldLine ?? ""}</td>
            <td className="diffLineNum new">{isNew ? ln.newLine ?? "" : ""}</td>
            <td className="diffCode"><pre>{ln.text || " "}</pre></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function UnifiedSegment({ lines }: { lines: string[] }) {
  const numbered = useMemo(() => buildUnifiedNumbered(lines), [lines]);
  return (
    <table className="diffTable unified">
      <tbody>
        {numbered.map((ln, i) => (
          <tr key={i} className={`diffRow ${ln.kind}`}>
            <td className="diffLineNum old">{ln.oldLine ?? ""}</td>
            <td className="diffLineNum new">{ln.newLine ?? ""}</td>
            <td className="diffCode"><pre>{ln.text || " "}</pre></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function SplitSegment({ lines }: { lines: string[] }) {
  const { hunks } = useMemo(() => buildSideBySide(lines), [lines]);
  return (
    <div className="diffSplit">
      {hunks.map((hunk, hi) => (
        <div className="splitHunk" key={hi}>
          <div className="splitHunkHeader">{hunk.header}</div>
          <div className="splitGrid">
            <table className="diffTable splitSide left">
              <tbody>
                {hunk.rows.map((row, ri) => (
                  <tr key={ri} className={`diffRow ${row.left.kind}`}>
                    <td className="diffLineNum">{row.left.line ?? ""}</td>
                    <td className="diffCode"><pre>{row.left.text || " "}</pre></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <table className="diffTable splitSide right">
              <tbody>
                {hunk.rows.map((row, ri) => (
                  <tr key={ri} className={`diffRow ${row.right.kind}`}>
                    <td className="diffLineNum">{row.right.line ?? ""}</td>
                    <td className="diffCode"><pre>{row.right.text || " "}</pre></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  );
}

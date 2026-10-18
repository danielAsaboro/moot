// Pretty-print and tokenise Cypher for display. No parsing beyond what the line breaks and highlighting need.

export type TokClass = "kw" | "fn" | "param" | "str" | "label" | "num" | "punct" | "text";
export interface Tok { t: string; c: TokClass }

const KEYWORDS = new Set([
  "MATCH", "OPTIONAL", "WHERE", "RETURN", "WITH", "ORDER", "BY", "CALL", "UNWIND", "YIELD", "AS", "AND", "OR", "XOR", "NOT",
  "IS", "NULL", "DISTINCT", "DESC", "ASC", "LIMIT", "SKIP", "IN", "CASE", "WHEN", "THEN", "ELSE", "END", "CREATE", "MERGE",
  "SET", "DELETE", "DETACH", "REMOVE", "ON", "TRUE", "FALSE", "UNION", "ALL", "STARTS", "ENDS", "CONTAINS", "EXISTS",
]);
// Clauses that start a new line when they appear outside brackets.
const BREAKS = new Set(["MATCH", "OPTIONAL", "WHERE", "RETURN", "WITH", "ORDER", "CALL", "UNWIND", "CREATE", "MERGE", "SET", "DELETE", "DETACH", "REMOVE", "UNION"]);
// A clause keyword that continues the one before it on the same line.
const JOINED: Record<string, string[]> = { MATCH: ["OPTIONAL"], DELETE: ["DETACH"], WITH: ["STARTS", "ENDS"] };

const TOKEN = /('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"|`[^`]*`|\$[A-Za-z_]\w*|[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*|\d+(?:\.\d+)?|\s+|[\s\S])/g;

/** Lines of classified tokens, broken before each top-level clause. WHERE is indented under its MATCH. */
export function formatCypher(src: string): Tok[][] {
  const raw = src.match(TOKEN) ?? [];
  const lines: Tok[][] = [[]];
  let depth = 0;
  let prevWord = "";               // last non-space token, upper-cased
  let labelRun = false;           // inside a run of relationship types: [:A|B|C]
  const cur = () => lines[lines.length - 1];
  const trimEnd = () => { const l = cur(); while (l.length && /^\s+$/.test(l[l.length - 1].t)) l.pop(); };

  for (let i = 0; i < raw.length; i++) {
    const t = raw[i];
    if (/^\s+$/.test(t)) { if (cur().length) cur().push({ t: " ", c: "text" }); continue; }
    const up = t.toUpperCase();
    let c: TokClass = "text";
    if (t[0] === "'" || t[0] === '"') c = "str";
    else if (t[0] === "$") c = "param";
    else if (/^\d/.test(t)) c = "num";
    else if (/^[A-Za-z_`]/.test(t)) {
      let j = i + 1;
      while (j < raw.length && /^\s+$/.test(raw[j])) j++;
      // Labels and relationship types touch their colon (n:Label, [:A|B]); map values have a space after it.
      if (raw[i - 1] === ":" || (raw[i - 1] === "|" && labelRun)) c = "label";
      else if (KEYWORDS.has(up) && !t.includes(".")) c = "kw";
      else if (raw[j] === "(") c = "fn";
    } else c = "punct";

    if (c === "kw" && depth === 0 && BREAKS.has(up) && !JOINED[up]?.includes(prevWord) && cur().length) {
      trimEnd();
      lines.push(up === "WHERE" ? [{ t: "  ", c: "text" }] : []);
    }
    if ("([{".includes(t)) depth++;
    else if (")]}".includes(t)) depth = Math.max(0, depth - 1);
    cur().push({ t, c });
    prevWord = c === "punct" ? t : up;
    labelRun = c === "label" || (labelRun && t === "|");
  }
  trimEnd();
  return lines.filter(l => l.length);
}


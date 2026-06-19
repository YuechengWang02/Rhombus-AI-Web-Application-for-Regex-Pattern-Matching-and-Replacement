import type { GenerateRegexResponse } from "../api/types";

interface Props {
  result: GenerateRegexResponse;
}

/** Shows the LLM-generated regex, its explanation, confidence, and matches. */
export function RegexPreview({ result }: Props) {
  return (
    <div className="card regex-preview">
      <div className="regex-preview__row">
        <span className="label">Pattern</span>
        <code>{result.regex}</code>
        {result.flags && <span className="badge">/{result.flags}</span>}
      </div>
      {result.explanation && <p className="muted">{result.explanation}</p>}
      <p className="muted">
        Confidence: {(result.confidence * 100).toFixed(0)}%
      </p>
      {result.sample_matches.length > 0 ? (
        <div>
          <span className="label">Sample matches</span>
          <ul className="chips">
            {result.sample_matches.map((m, i) => (
              <li key={i} className="chip">
                {m}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="muted">No sample matches found in the column preview.</p>
      )}
    </div>
  );
}

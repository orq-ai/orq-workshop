"""External knowledge base stub: the /search contract orq expects, over four policy docs."""
import json, re
from http.server import BaseHTTPRequestHandler, HTTPServer
from app.refund_agent.config import DATA_DIR

DOCS = {p.stem: p.read_text() for p in sorted((DATA_DIR / "kb").glob("*.md"))}


def search(query: str, top_k: int = 3, threshold: float = 0.0):
    words = {w for w in re.findall(r"[a-z]+", query.lower()) if len(w) > 3}
    scored = []
    for topic, text in DOCS.items():
        score = round(sum(text.lower().count(w) for w in words) / max(1, len(words)), 3)
        if score > threshold:
            scored.append({"id": f"ext_{topic}", "text": text, "metadata": {"topic": topic}, "scores": {"search_score": score}})
    return sorted(scored, key=lambda m: -m["scores"]["search_score"])[:top_k]


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        ok = self.path == "/search"
        out = json.dumps({"matches": search(body.get("query", ""), body.get("top_k", 3), body.get("threshold", 0.0)) if ok else []}).encode()
        self.send_response(200 if ok else 404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("external KB stub on http://127.0.0.1:8765/search")
    HTTPServer(("127.0.0.1", 8765), Handler).serve_forever()

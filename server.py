"""Anek Writes - a tiny local server.

What it does:
  1. Shows the website (the files inside the "public" folder).
  2. When you ask for a topic, it asks Google Gemini to search the web
     and write about it. Your key stays on the server (in .env or in the
     GEMINI_API_KEY environment variable) and is never sent to the web page.

Run it on your computer by double-clicking start.bat.
On Render, the start command is: python server.py
"""
import json
import os
import socket
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
PUBLIC = os.path.join(ROOT, "public")
PORT = int(os.environ.get("PORT", 8000))  # hosts like Render set PORT for us

# How long each piece should be
LENGTHS = {
    "short": "Write ONE paragraph of about 120 words.",
    "medium": "Write about 300 words in 3 or 4 paragraphs. No section headings.",
    "long": "Write about 700 words in 5 to 7 paragraphs, with 3 or 4 section headings.",
}

# This is the "personality" we give the AI
STYLE = """You are the writer behind Anek Writes, a site for students who want writing that is educational but genuinely fun to read.

Research first: use Google Search and base every fact on what you find. Never invent statistics, quotes, names or dates. If sources disagree or you are unsure, say so plainly.

Voice: a smart, witty friend explaining something over chai, NOT a teacher, textbook or news article. Write the way people actually talk: ALWAYS use contractions, so "it's" never "it is", "you're" never "you are", "don't", "that's", "here's". Use simple everyday words, short punchy sentences, the odd sentence fragment. Talk straight to the reader with "you". It's fine to sound a little cheeky, to say "honestly" or "turns out", or to add a quick aside in brackets. Never sound formal, polished or like an essay: no "furthermore", "moreover", "thus", "significant", "various", "numerous", "utilize" or "plays a crucial role". Open with a surprising fact, a tiny story or a vivid image, never a dictionary definition. Include at least one everyday comparison (cricket, street food, phones, school life, and India-relevant where it fits naturally). Humour should come from sharp observation, not forced jokes, slang overload or exclamation marks. Mix short and long sentences, but keep most of them short.

Be frank. Don't sanitise or tiptoe around sensitive topics (sex, drugs, death, religion, politics, crime, war, mental health, controversy). Explain them honestly and directly, like a friend who isn't scared of the subject. No warnings, disclaimers, "consult a professional" lines or moralising unless the topic truly needs a safety fact. Swearing is welcome: drop in real curse words (shit, damn, hell, bloody, bullshit, fuck and so on) where a person would actually say them, for emphasis or humour, maybe a few times in a longer piece and not in every sentence. Never swear at the reader, and never use slurs or attack a group of people.

Sound human, not machine. Real people are specific, a bit opinionated and slightly uneven. So: give one concrete, oddly specific detail (a number you actually found, a place, a name, a tiny scene) instead of general statements. Don't use the "it isn't X, it's Y" or "not just X, but Y" pattern. Don't group things in neat threes. Don't end with a tidy moral, a recap, a call to reflect or a "next time you..." line; stop on a concrete detail or a dry little remark instead. Don't start several sentences the same way. Never use em dashes, semicolons or colons in the writing; use commas and full stops. Don't announce what you're about to say. Don't use "Turns out" more than once. Let one sentence run a little long and one be really short. Avoid sounding balanced about everything; pick an angle and commit to it.

Never use: "In conclusion", "delve", "tapestry", "landscape", "in today's world", "it's important to note", "fascinating", "journey", "unlock", "buckle up", "let's dive in", "dive into". No emoji. No bullet lists. Do not open with a question. Go easy on dashes.

Format: the first line must be exactly `TITLE: ` followed by a short catchy title (max 8 words). Then a blank line, then the writing as plain paragraphs separated by blank lines. If asked for section headings, put each on its own line starting with `## `. No other markdown (no bold, no lists). Do not list sources in the text, they are shown separately."""


def load_env():
    """Read settings from the .env file, then let real environment variables win.
    On a host like Render you set GEMINI_API_KEY there and there is no .env file.
    Read fresh every time so edits work without a restart."""
    env = {}
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip().strip('"').strip("'")
    for name in ("GEMINI_API_KEY", "GEMINI_MODEL"):
        if os.environ.get(name, "").strip():
            env[name] = os.environ[name].strip()
    return env


class SearchUnavailable(Exception):
    """Raised when Google won't allow web search on this key (for example the free plan)."""


# When web search is refused, remember it for a while so we don't waste a request each time
no_search_until = [0]


class ModelBusy(Exception):
    """Raised when a Gemini model is overloaded or too slow right now."""


def write_piece(topic, length):
    """Try live web search first. If that isn't allowed, write without it and say so.
    If a model is busy, move on to the next one."""
    chosen = load_env().get("GEMINI_MODEL", "gemini-3.5-flash-lite")
    models = list(dict.fromkeys([chosen, "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]))
    searched = time.time() >= no_search_until[0]
    for model in models:
        while True:
            try:
                result = ask_gemini(topic, length, searched, model)
                result["searched"] = searched
                return result
            except SearchUnavailable:
                searched = False  # try again with the same model, no search
                no_search_until[0] = time.time() + 600  # don't retry search for 10 minutes
            except ModelBusy:
                break  # try the next model
    raise ValueError("Gemini is very busy right now. Wait a minute and try again.")


def ask_gemini(topic, length, use_search=True, model=None):
    """Send the topic to Gemini (with Google Search switched on) and tidy up the answer."""
    env = load_env()
    api_key = env.get("GEMINI_API_KEY", "")
    if not api_key or api_key == "paste-your-key-here":
        raise ValueError("No Gemini key yet. Open the .env file and paste your key after GEMINI_API_KEY=")
    model = model or env.get("GEMINI_MODEL", "gemini-3.5-flash-lite")

    prompt = "Topic: " + topic + "\n" + LENGTHS[length]
    if not use_search:
        prompt += "\nGoogle Search is not available this time. Write only what you reliably know, and skip specific numbers or dates you are not sure about."
    body = {
        "systemInstruction": {"parts": [{"text": STYLE}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.9},
    }
    if use_search:
        body["tools"] = [{"google_search": {}}]
    url = "https://generativelanguage.googleapis.com/v1beta/models/" + model + ":generateContent"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as err:
        try:
            message = json.load(err).get("error", {}).get("message", "")
        except Exception:
            message = ""
        if err.code in (400, 403) and "key" in message.lower():
            raise ValueError("Google says this key isn't valid. Check the key in your .env file.")
        if err.code == 429 and use_search:
            raise SearchUnavailable()
        if err.code == 429:
            raise ValueError("Too many requests, or the free limit is used up. Wait a minute and try again.")
        if err.code == 404:
            raise ValueError("That Gemini model isn't available for your key. Change GEMINI_MODEL in .env.")
        if err.code in (500, 503):
            raise ModelBusy()
        raise ValueError("Gemini error " + str(err.code) + ": " + (message or "unknown problem"))
    except (TimeoutError, socket.timeout):
        raise ModelBusy()
    except urllib.error.URLError:
        raise ValueError("Couldn't reach Google. Check your internet connection.")

    candidates = data.get("candidates") or []
    if not candidates:
        raise ValueError("Gemini didn't write anything for that topic. Try rewording it.")
    cand = candidates[0]
    parts = cand.get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise ValueError("Gemini came back empty. Try rewording the topic.")

    # First line is "TITLE: ...", the rest is the writing
    title = topic
    lines = text.split("\n")
    if lines[0].upper().startswith("TITLE:"):
        title = lines[0][6:].strip().strip("*\"")
        text = "\n".join(lines[1:]).strip()

    # Collect the web pages Gemini used (remove duplicates)
    sources, seen = [], set()
    chunks = cand.get("groundingMetadata", {}).get("groundingChunks", [])
    for chunk in chunks:
        web = chunk.get("web", {})
        link = web.get("uri")
        if link and link not in seen:
            seen.add(link)
            sources.append({"title": web.get("title") or link, "url": link})

    return {"title": title, "text": text, "sources": sources[:8]}


# Protects your Google key when the site is shared: each visitor gets a few pieces
# every 10 minutes, and the whole site has a daily cap.
VISITOR_LIMIT = 6
DAILY_LIMIT = 200
recent_requests = {}
daily_count = [0, 0]  # [day number, pieces written that day]


def check_visitor_limit(visitor):
    visitor = visitor.split(",")[0].strip()
    now = time.time()
    day = int(now // 86400)
    if daily_count[0] != day:
        daily_count[0], daily_count[1] = day, 0
    if daily_count[1] >= DAILY_LIMIT:
        raise ValueError("Anek Writes has hit its limit for today. Come back tomorrow.")
    times = [t for t in recent_requests.get(visitor, []) if now - t < 600]
    if len(times) >= VISITOR_LIMIT:
        raise ValueError("Easy there, that's a lot of topics. Give it a few minutes and try again.")
    times.append(now)
    recent_requests[visitor] = times
    daily_count[1] += 1


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, payload):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            path = "/index.html"
        full = os.path.abspath(os.path.join(PUBLIC, path.lstrip("/")))
        # Only serve files that really live inside the public folder
        if not full.startswith(PUBLIC + os.sep) or not os.path.isfile(full):
            self.send_error(404)
            return
        kinds = {".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".svg": "image/svg+xml"}
        kind = kinds.get(os.path.splitext(full)[1], "application/octet-stream")
        with open(full, "rb") as f:
            raw = f.read()
        self.send_response(200)
        self.send_header("Content-Type", kind + "; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        if self.path != "/api/write":
            self.send_error(404)
            return
        try:
            size = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(size) or b"{}")
            topic = str(payload.get("topic", "")).strip()[:200]
            length = payload.get("length", "medium")
            if not topic:
                raise ValueError("Type a topic first.")
            if length not in LENGTHS:
                length = "medium"
            check_visitor_limit(self.headers.get("X-Forwarded-For") or self.client_address[0])
            self.send_json(200, write_piece(topic, length))
        except ValueError as err:
            self.send_json(400, {"error": str(err)})
        except Exception as err:
            self.send_json(500, {"error": "Something went wrong: " + str(err)})


if __name__ == "__main__":
    # 0.0.0.0 means "listen on every address", which a host like Render needs
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("Anek Writes is running on port " + str(PORT) + " (locally: http://localhost:" + str(PORT) + ")")
    print("Keep this window open while you use the site. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopped.")

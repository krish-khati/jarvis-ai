# ============================================
# readaloud.py - "Padh ke sunao" ke helper (koi naya library nahi: requests + stdlib HTMLParser)
#   - clean_for_speech: emoji, URL, symbols bolne se pehle hata do
#   - split_sentences / groups: lamba text 6-6 lines ke tukdon mein
#   - fetch_webpage: sirf http/https, public sites, max 3000 characters
# Web page / screen / clipboard ka text UNTRUSTED DATA hai: ye sirf bola jaata hai, AI ko instruction
# ki tarah kabhi nahi jaata (tools seedha DirectReply dete hain).
# ============================================
import ipaddress
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urlparse

MAX_CHARS = 3000        # Web page se itna hi text
LINES_PER_GROUP = 6     # Pehle itni lines bolo, phir "baaki bhi padhun?"
MAX_DOWNLOAD = 1_000_000

_URL = re.compile(r"(?:https?://|www\.)\S+", re.I)
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]")
# Bolne layak: letters (Devanagari matra bhi - \w unhe kaat deta hai), digits, aam punctuation
_SYMBOLS = re.compile(r"[^\w\s.,!?;:'\"()%₹$&\-।ऀ-ॿ]|_")


def clean_for_speech(text):
    """Emoji, URL, markdown/symbols hatao; spaces saaf. Newline (line todne ke liye) bacha ke rakhte hain."""
    text = _URL.sub(" ", text or "")
    text = _EMOJI.sub("", text)
    text = _SYMBOLS.sub(" ", text)
    lines = [" ".join(l.split()) for l in text.splitlines()]
    lines = [l for l in lines if re.search(r"[^\W_]", l)]      # Sirf symbols wali line hata do
    return "\n".join(lines)


def split_sentences(text):
    """Saaf text -> sentences (line ka end bhi sentence ka end)."""
    out = []
    for line in text.splitlines():
        out += [s.strip() for s in re.split(r"(?<=[.!?।])\s+", line) if s.strip()]
    return out


def groups(text, per=LINES_PER_GROUP):
    """Text -> [6 sentences ka tukda, ...] (har tukda ek string)."""
    s = split_sentences(clean_for_speech(text))
    return [" ".join(s[i:i + per]) for i in range(0, len(s), per)]


# --- Web page ---
class _TextExtractor(HTMLParser):
    """Simple text nikalne wala parser: script/style/nav jaise hisse chhod deta hai."""
    SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer", "aside", "form", "template"}
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article", "title"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip, self.title = [], 0, ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        if tag == "title":
            self._in_title = True
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        if tag == "title":
            self._in_title = False
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self.skip:
            self.parts.append(data)


def extract_text(html):
    """HTML -> saaf text (max MAX_CHARS, sentence ke end pe kata hua)."""
    p = _TextExtractor()
    p.feed(html)
    text = "\n".join(l for l in (" ".join(x.split()) for x in "".join(p.parts).splitlines()) if l)
    if p.title.strip() and not text.startswith(p.title.strip()):
        text = p.title.strip() + ".\n" + text
    return cut(text)


def cut(text, limit=MAX_CHARS):
    if len(text) <= limit:
        return text
    head = text[:limit]
    end = max(head.rfind(". "), head.rfind("\n"), head.rfind("।"))
    return head[:end + 1] if end > limit // 2 else head


def _public_host(host):
    """localhost / ghar ke network (private IP) wali sites nahi - sirf public internet."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


def safe_url(url):
    """(ok, url_ya_wajah): sirf http/https + public host."""
    url = (url or "").strip().strip("<>\"'")
    if re.match(r"^www\.", url, re.I):
        url = "https://" + url
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        return False, "sirf http/https link chalta hai"
    if not _public_host(u.hostname):
        return False, "ye address allowed nahi hai"
    return True, url


def fetch_webpage(url):
    """URL ka text (max 3000 characters). Galti pe ValueError(wajah)."""
    import requests
    ok, url = safe_url(url)
    if not ok:
        raise ValueError(url)
    try:
        r = requests.get(url, timeout=8, stream=True, allow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0 JARVIS-reader"})
        final = urlparse(r.url)
        if final.scheme not in ("http", "https") or not _public_host(final.hostname or ""):
            raise ValueError("redirect allowed jagah pe nahi gaya")
        kind = r.headers.get("content-type", "").lower()
        if r.status_code != 200 or not ("html" in kind or "text/plain" in kind):
            raise ValueError("page nahi khula ya text page nahi hai")
        raw = r.raw.read(MAX_DOWNLOAD, decode_content=True)
        r.close()
    except requests.RequestException:
        raise ValueError("page tak pahunch nahi paya")
    html = raw.decode(r.encoding or "utf-8", errors="replace")
    text = cut(html) if "text/plain" in kind else extract_text(html)
    if not text.strip():
        raise ValueError("page mein padhne layak text nahi mila")
    return text

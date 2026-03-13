"""
metadata_parser.py
==================
Purely algorithmic parser that extracts keywords and metadata from Discord
messages, file attachments, GIFs, and URLs.  No LLM is used here.
"""

import re
from collections import Counter
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import discord

# ---------------------------------------------------------------------------
# Stopword list used for keyword filtering
# ---------------------------------------------------------------------------
STOPWORDS: set = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "need", "dare",
    "ought", "used", "i", "me", "my", "we", "our", "you", "your", "he",
    "him", "his", "she", "her", "it", "its", "they", "them", "their",
    "this", "that", "these", "those", "what", "which", "who", "when",
    "where", "why", "how", "all", "each", "both", "few", "more", "most",
    "other", "some", "such", "no", "not", "only", "same", "so", "than",
    "too", "very", "s", "t", "just", "don", "now", "also", "as", "if",
    "up", "out", "about", "into", "through", "during", "before", "after",
    "above", "below", "between", "because", "while", "although", "since",
    "until", "unless", "however", "therefore", "thus", "hence", "still",
    "got", "get", "go", "going", "come", "comes", "came", "make", "made",
    "think", "know", "see", "look", "want", "use", "work", "way", "time",
    "like", "one", "two", "three", "new", "good", "great", "well", "even",
    "back", "take", "put", "set", "give", "tell", "try", "ask", "keep",
    "let", "seem", "feel", "next", "old", "right", "big", "high", "own",
    "last", "long", "little", "every", "say", "said", "hey", "hi", "ok",
    "yeah", "yes", "nah", "lol", "lmao", "omg", "btw", "imo", "irl",
}

# ---------------------------------------------------------------------------
# Known platform → keyword mapping used in URL analysis
# ---------------------------------------------------------------------------
PLATFORM_KEYWORDS: Dict[str, List[str]] = {
    "github.com":        ["code", "open-source", "programming", "github", "repository"],
    "gitlab.com":        ["code", "devops", "gitlab", "repository"],
    "youtube.com":       ["video", "multimedia", "youtube"],
    "youtu.be":          ["video", "multimedia", "youtube"],
    "twitter.com":       ["social-media", "twitter"],
    "x.com":             ["social-media", "twitter"],
    "reddit.com":        ["community", "reddit", "forum"],
    "medium.com":        ["article", "blog", "writing"],
    "dev.to":            ["programming", "blog", "developer"],
    "producthunt.com":   ["startup", "product", "launch"],
    "techcrunch.com":    ["startup", "tech-news", "technology"],
    "arxiv.org":         ["research", "paper", "academic"],
    "figma.com":         ["design", "ui", "figma"],
    "notion.so":         ["productivity", "notes", "notion"],
    "linkedin.com":      ["professional", "networking", "linkedin"],
    "stackoverflow.com": ["programming", "qa", "stackoverflow"],
    "npmjs.com":         ["javascript", "package", "npm"],
    "pypi.org":          ["python", "package", "pypi"],
    "huggingface.co":    ["ai", "machine-learning", "model"],
    "kaggle.com":        ["data-science", "machine-learning", "dataset"],
    "replit.com":        ["code", "cloud-ide", "programming"],
    "vercel.com":        ["deployment", "frontend", "web"],
    "netlify.com":       ["deployment", "frontend", "web"],
    "heroku.com":        ["deployment", "cloud", "hosting"],
    "openai.com":        ["ai", "chatgpt", "llm", "artificial-intelligence"],
    "anthropic.com":     ["ai", "claude", "llm", "artificial-intelligence"],
    "groq.com":          ["ai", "llm", "inference", "artificial-intelligence"],
}

# Code-file extension → friendly language name
LANG_MAP: Dict[str, str] = {
    "py":   "python",  "js":   "javascript", "ts":   "typescript",
    "java": "java",    "cpp":  "cpp",         "c":    "c",
    "go":   "golang",  "rs":   "rust",        "rb":   "ruby",
    "php":  "php",     "html": "web",         "css":  "web",
    "sh":   "shell",   "bash": "shell",       "kt":   "kotlin",
    "swift":"swift",   "dart": "dart",        "lua":  "lua",
}

# Compiled regex constants
_URL_RE   = re.compile(r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[^\s]*)?")
_WORD_RE  = re.compile(r"[^\w\s\'\-]")
_SPLIT_RE = re.compile(r"[-_\s]+")
_CAMEL_RE = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)")

# Technology / industry term patterns (case-insensitive)
_TECH_PATTERNS: List[str] = [
    r"\b(AI|ML|LLM|API|SDK|CLI|UI|UX|SaaS|PaaS|IaaS|IoT|AR|VR|NFT|DAO|DeFi|GPT)\b",
    r"\b(blockchain|cryptocurrency|bitcoin|ethereum|web3|cloud|devops|agile|scrum)\b",
    r"\b(python|javascript|typescript|react|vue|angular|node(?:\.?js)?|django|fastapi|flask)\b",
    r"\b(docker|kubernetes|aws|gcp|azure|terraform|ci/?cd|microservice)\b",
    r"\b(database|sql|nosql|mongodb|postgresql|redis|elasticsearch|supabase)\b",
    r"\b(machine learning|deep learning|neural network|computer vision)\b",
    r"\b(startup|mvp|product.market|revenue|monetize|scale|pivot|launch)\b",
    r"\b(mobile|desktop|platform|automation|open.source)\b",
]


# ---------------------------------------------------------------------------
# Main parser class
# ---------------------------------------------------------------------------
class MetadataParser:
    """
    Algorithm-based parser that extracts keywords and metadata from every
    component of a Discord message: text, attachments, URLs, and embeds.
    No external API or LLM is involved.
    """

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def parse_message(self, message: discord.Message) -> Optional[Dict[str, Any]]:
        """
        Parse a Discord message and return a structured dict with:
          - type        : 'message' | 'file' | 'link'
          - keywords    : deduplicated list of extracted keywords
          - metadata    : nested dict of detailed analysis per component
          - raw_content : first 2,000 chars of the message text

        Returns None if no meaningful content could be extracted.
        """
        all_keywords: List[str] = []
        metadata: Dict[str, Any] = {}
        content_type = "message"

        # ── 1. Text content ──────────────────────────────────────────
        if message.content:
            text_data = self._parse_text(message.content)
            all_keywords.extend(text_data["keywords"])
            metadata["text_analysis"] = text_data

        # ── 2. File / image / GIF attachments ────────────────────────
        if message.attachments:
            att_data = self._parse_attachments(message.attachments)
            all_keywords.extend(att_data.get("keywords", []))
            metadata["attachments"] = att_data
            content_type = "file"

        # ── 3. URLs embedded in the message text ─────────────────────
        urls = _URL_RE.findall(message.content or "")
        if urls:
            link_data = self._parse_links(urls)
            all_keywords.extend(link_data.get("keywords", []))
            metadata["links"] = link_data
            if content_type == "message":
                content_type = "link"

        # ── 4. Discord auto-generated embed previews ──────────────────
        if message.embeds:
            embed_data = self._parse_embeds(message.embeds)
            all_keywords.extend(embed_data.get("keywords", []))
            metadata["embeds"] = embed_data

        deduped = self._deduplicate(all_keywords)

        # Skip if nothing meaningful was found
        if not deduped and not message.attachments:
            return None

        return {
            "type":        content_type,
            "keywords":    deduped,
            "metadata":    metadata,
            "raw_content": (message.content or "")[:2000],
        }

    # ------------------------------------------------------------------
    # Text parsing
    # ------------------------------------------------------------------

    def _parse_text(self, text: str) -> Dict[str, Any]:
        """Extract keywords and metadata from a plain-text string."""
        # Strip Discord mentions, HTML tags, URLs, then non-word chars
        clean = re.sub(r"<[^>]+>", " ", text)
        clean = _URL_RE.sub(" ", clean)
        clean = _WORD_RE.sub(" ", clean)

        words = clean.lower().split()
        meaningful = [
            w.strip("'-") for w in words
            if len(w) > 2 and w not in STOPWORDS and w.isalpha()
        ]

        freq = Counter(meaningful)
        top_keywords = [word for word, _ in freq.most_common(10)]

        hashtags = re.findall(r"#(\w+)", text)
        tech_terms = self._extract_tech_terms(text)

        return {
            "keywords":   top_keywords + hashtags + tech_terms,
            "word_count": len(words),
            "hashtags":   hashtags,
            "tech_terms": tech_terms,
            "char_count": len(text),
        }

    # ------------------------------------------------------------------
    # Attachment parsing
    # ------------------------------------------------------------------

    def _parse_attachments(
        self, attachments: List[discord.Attachment]
    ) -> Dict[str, Any]:
        results: Dict[str, Any] = {"keywords": [], "files": []}
        for att in attachments:
            info = self._analyze_attachment(att)
            results["files"].append(info)
            results["keywords"].extend(info.get("keywords", []))
        return results

    def _analyze_attachment(self, att: discord.Attachment) -> Dict[str, Any]:
        """Derive metadata and keywords from a single attachment — no LLM."""
        filename = att.filename
        filename_lower = filename.lower()
        ext = filename_lower.rsplit(".", 1)[-1] if "." in filename_lower else ""
        content_type = att.content_type or ""

        keywords: List[str] = []

        # Keywords from the filename itself (split on separators)
        stem = filename_lower.rsplit(".", 1)[0]
        name_parts = _SPLIT_RE.split(stem)
        keywords.extend(
            p for p in name_parts if len(p) > 2 and p not in STOPWORDS
        )

        info: Dict[str, Any] = {
            "filename":     filename,
            "extension":    ext,
            "size_bytes":   att.size,
            "size_kb":      round(att.size / 1024, 2),
            "content_type": content_type,
            "url":          att.url,
        }

        # ── Images & GIFs ────────────────────────────────────────────
        if content_type.startswith("image/") or ext in ("jpg", "jpeg", "png",
                                                         "gif", "webp", "bmp",
                                                         "svg", "tiff"):
            is_gif = ext == "gif" or "gif" in content_type
            info["media_type"] = "gif" if is_gif else "image"
            keywords.append("visual-content")
            if is_gif:
                keywords.extend(["animation", "gif"])

            if att.width and att.height:
                info["dimensions"] = f"{att.width}x{att.height}"
                info["aspect_ratio"] = round(att.width / att.height, 2)
                pixels = att.width * att.height
                keywords.append("high-resolution" if pixels > 2_000_000 else "thumbnail")

        # ── Video ─────────────────────────────────────────────────────
        elif content_type.startswith("video/") or ext in ("mp4", "mov", "avi",
                                                           "mkv", "webm"):
            info["media_type"] = "video"
            keywords.extend(["video", "multimedia"])

        # ── Audio ─────────────────────────────────────────────────────
        elif content_type.startswith("audio/") or ext in ("mp3", "wav", "ogg",
                                                           "flac", "aac"):
            info["media_type"] = "audio"
            keywords.extend(["audio", "sound", "music"])

        # ── Documents ─────────────────────────────────────────────────
        elif ext in ("pdf", "doc", "docx", "txt", "md", "rtf", "odt", "pptx",
                     "ppt", "key"):
            info["media_type"] = "document"
            keywords.extend(["document", ext])

        # ── Spreadsheets / Data ───────────────────────────────────────
        elif ext in ("csv", "xlsx", "xls", "ods", "tsv", "parquet"):
            info["media_type"] = "spreadsheet"
            keywords.extend(["data", "spreadsheet", "analytics", "dataset"])

        # ── Code files ────────────────────────────────────────────────
        elif ext in LANG_MAP or ext in ("json", "yaml", "yml", "toml", "xml",
                                        "sql", "graphql"):
            info["media_type"] = "code"
            lang = LANG_MAP.get(ext, ext)
            keywords.extend(["code", "programming", lang])

        # ── Archives ──────────────────────────────────────────────────
        elif ext in ("zip", "tar", "gz", "rar", "7z"):
            info["media_type"] = "archive"
            keywords.extend(["archive", "compressed"])

        info["keywords"] = list(dict.fromkeys(keywords))   # preserve order, deduplicate
        return info

    # ------------------------------------------------------------------
    # URL / link parsing
    # ------------------------------------------------------------------

    def _parse_links(self, urls: List[str]) -> Dict[str, Any]:
        results: Dict[str, Any] = {"keywords": [], "urls": []}
        for url in urls:
            url_info = self._analyze_url(url)
            results["urls"].append(url_info)
            results["keywords"].extend(url_info.get("keywords", []))
        return results

    def _analyze_url(self, url: str) -> Dict[str, Any]:
        """
        Algorithmic URL analysis:
          1. Match against known platform → keyword table.
          2. Split domain parts for generic domains.
          3. Walk path segments, splitting camelCase / kebab-case.
          4. Inspect query-string keys for non-tracking params.
          5. Detect file-type from path extension.
        """
        try:
            parsed = urlparse(url)
        except Exception:
            return {"url": url, "keywords": []}

        keywords: List[str] = []
        domain = parsed.netloc.lower()
        domain_clean = re.sub(r"^www\.", "", domain)

        # ── 1. Known platform detection ───────────────────────────────
        matched = False
        for platform, kws in PLATFORM_KEYWORDS.items():
            if platform in domain_clean:
                keywords.extend(kws)
                matched = True
                break

        if not matched:
            # ── 2. Generic domain keyword extraction ──────────────────
            parts = domain_clean.split(".")
            for part in parts[:-1]:   # skip TLD
                if len(part) > 2 and part not in STOPWORDS:
                    keywords.append(part)

        # ── 3. Path segment analysis ──────────────────────────────────
        path_segments = [s for s in parsed.path.split("/") if s and len(s) > 2]
        for seg in path_segments[:6]:
            sub_words = _SPLIT_RE.split(seg)
            for w in sub_words:
                camel_words = _CAMEL_RE.findall(w)
                for cw in (camel_words if camel_words else [w]):
                    cw_lower = cw.lower()
                    if len(cw_lower) > 2 and cw_lower not in STOPWORDS:
                        keywords.append(cw_lower)

        # ── 4. Query-string key extraction ────────────────────────────
        _tracking = {"utm_source", "utm_medium", "utm_campaign", "utm_content",
                     "utm_term", "ref", "src", "fbclid", "gclid"}
        for key in parse_qs(parsed.query):
            if key.lower() not in _tracking and len(key) > 2:
                keywords.append(key.lower())

        # ── 5. File-type detection from path ──────────────────────────
        path_lower = parsed.path.lower()
        url_type = "website"
        if any(path_lower.endswith(e) for e in (".pdf", ".doc", ".docx")):
            url_type = "document"
            keywords.append("document")
        elif any(path_lower.endswith(e) for e in (".mp4", ".mov", ".avi")):
            url_type = "video"
            keywords.append("video")
        elif any(path_lower.endswith(e) for e in (".jpg", ".png", ".gif", ".webp")):
            url_type = "image"
            keywords.append("image")

        return {
            "url":      url,
            "domain":   domain_clean,
            "path":     parsed.path,
            "url_type": url_type,
            "keywords": list(dict.fromkeys(keywords)),
        }

    # ------------------------------------------------------------------
    # Discord embed parsing
    # ------------------------------------------------------------------

    def _parse_embeds(self, embeds: List[discord.Embed]) -> Dict[str, Any]:
        results: Dict[str, Any] = {"keywords": [], "embeds": []}
        for embed in embeds:
            embed_info: Dict[str, Any] = {}
            text_parts: List[str] = []

            if embed.title:
                embed_info["title"] = embed.title
                text_parts.append(embed.title)

            if embed.description:
                embed_info["description"] = embed.description[:300]
                text_parts.append(embed.description)

            if embed.url:
                embed_info["url"] = embed.url
                url_data = self._analyze_url(embed.url)
                results["keywords"].extend(url_data.get("keywords", []))

            if embed.author and embed.author.name:
                embed_info["author"] = embed.author.name

            if embed.fields:
                embed_info["fields"] = [
                    {"name": f.name, "value": f.value[:100]}
                    for f in embed.fields
                ]
                for f in embed.fields:
                    text_parts.append(f"{f.name} {f.value}")

            if text_parts:
                combined = " ".join(text_parts)
                text_data = self._parse_text(combined)
                results["keywords"].extend(text_data["keywords"])

            results["embeds"].append(embed_info)

        return results

    # ------------------------------------------------------------------
    # Technology-term extraction (regex-based, no LLM)
    # ------------------------------------------------------------------

    def _extract_tech_terms(self, text: str) -> List[str]:
        found: List[str] = []
        for pattern in _TECH_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for m in matches:
                term = m if isinstance(m, str) else m[0]
                found.append(term.lower())
        return list(dict.fromkeys(found))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _deduplicate(keywords: List[str]) -> List[str]:
        """Case-insensitive deduplication, preserving first-seen order."""
        seen: set = set()
        result: List[str] = []
        for kw in keywords:
            kw_lower = kw.lower().strip()
            if kw_lower and kw_lower not in seen and len(kw_lower) > 1:
                seen.add(kw_lower)
                result.append(kw_lower)
        return result

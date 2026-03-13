# IdeaDB 🧠💡

**IdeaDB** is a Discord bot that silently observes your server's conversations, automatically collects and parses every message — including text, files, GIFs, and shared links — extracts meaningful keywords and metadata using a pure-algorithmic pipeline, and uses a Groq-hosted LLM to synthesise all of that context into actionable startup and project ideas on demand.

---

## Table of Contents

1. [Overview](#overview)
2. [How It Works](#how-it-works)
3. [Tech Stack](#tech-stack)
4. [Features](#features)
5. [Bot Commands](#bot-commands)
6. [Project Structure](#project-structure)
7. [Getting Started](#getting-started)
   - [Prerequisites](#prerequisites)
   - [Installation](#installation)
   - [Configuration](#configuration)
   - [Running the Bot](#running-the-bot)
8. [Architecture Deep-Dive](#architecture-deep-dive)
   - [Metadata Parser (Algorithm)](#metadata-parser-algorithm)
   - [Idea Generator (LLM)](#idea-generator-llm)
   - [Database](#database)
9. [Auto-Idea Generation](#auto-idea-generation)
10. [Deployment](#deployment)
11. [Contributing](#contributing)
12. [License](#license)

---

## Overview

Most startup ideas come from the collective brain of a group — scattered across messages, links, files, and random GIFs people share. IdeaDB captures all of that noise automatically and turns it into structured, LLM-generated startup/project concepts.

```
Discord Messages  ──►  MetadataParser  ──►  SQLite DB  ──►  IdeaGenerator (Groq LLM)  ──►  Ideas
                         (algorithm)                            (llama-3.1-8b-instant)
```

- **Everything up to idea generation is purely algorithmic** — no LLM, no API calls, no cost.
- **The LLM is invoked only when you explicitly ask for ideas** (or when the auto-threshold is reached).

---

## How It Works

1. **Collection** — The bot listens to every channel it has access to. For each non-command message it:
   - Parses the text using keyword-frequency analysis and stopword filtering.
   - Extracts tech/industry terms via regex pattern matching.
   - Analyses any attached files/GIFs (file type, dimensions, name tokens, media class).
   - Parses embedded URLs algorithmically (domain classification, path-segment tokenisation, query-key extraction).
   - Reads Discord's auto-generated link-preview embeds for extra title/description keywords.

2. **Storage** — Extracted keywords and metadata are stored in a local SQLite database, keyed by Discord guild ID.

3. **Idea Generation** — When you run `!ideas`, the bot:
   - Pulls the most-recent entries from the DB.
   - Aggregates top keywords by frequency, content-type breakdown, and tech-term mentions.
   - Sends a structured context prompt to the Groq API (`llama-3.1-8b-instant`).
   - Returns the formatted ideas as a Discord embed.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Bot framework | [discord.py](https://discordpy.readthedocs.io/) ≥ 2.3 |
| LLM inference | [Groq API](https://console.groq.com/) — `llama-3.1-8b-instant` |
| LLM client | [groq-python](https://github.com/groq/groq-python) |
| Database | SQLite (via Python's built-in `sqlite3`) |
| HTTP client | [aiohttp](https://docs.aiohttp.org/) |
| Config | [python-dotenv](https://github.com/theskumar/python-dotenv) |
| Runtime | Python 3.11+ |

**No external NLP libraries** are required for the metadata extraction — everything in `metadata_parser.py` is standard-library Python (`re`, `collections.Counter`, `urllib.parse`).

---

## Features

### ✅ Automatic Message Collection
- Runs silently in the background.
- Works across all channels the bot has read access to.
- Ignores bot messages and command invocations.

### ✅ Algorithmic Metadata Extraction
- **Text messages** — stopword-filtered keyword frequency, hashtag detection, tech-term pattern matching.
- **File attachments** — file type classification, filename tokenisation, media-class tagging (image, video, audio, document, code, spreadsheet, archive).
- **Images & GIFs** — dimensions, aspect ratio, resolution category, animation flag.
- **URLs / links** — known-platform recognition (GitHub, YouTube, ProductHunt, HuggingFace, etc.), path-segment tokenisation, camelCase splitting, query-key extraction.
- **Discord embeds** — title, description, and field keyword extraction.

### ✅ LLM-Powered Idea Generation
- Model: `llama-3.1-8b-instant` via Groq.
- Each idea includes: name, one-sentence pitch, problem, target audience, and tech stack suggestion.
- Context is built entirely from aggregated keywords — no raw messages are sent to the LLM.

### ✅ Persistent SQLite Storage
- All collected data survives bot restarts.
- Entries are keyed by guild ID, so multiple servers are fully isolated.

### ✅ Optional Auto-Generation
- Configure `AUTO_IDEA_THRESHOLD` to post ideas automatically after N new entries.
- Results are posted to your designated `IDEA_CHANNEL`.

---

## Bot Commands

| Command | Description | Permission |
|---------|-------------|------------|
| `!ideas [count]` | Generate `count` startup/project ideas (default: 5, max: 10) | Everyone |
| `!keywords` | Show the top 25 keywords collected for this server | Everyone |
| `!stats` | Show total entries, message/file/link breakdown | Everyone |
| `!clear` | Wipe all collected data for this server | Administrator |

### Examples

```
!ideas          → 5 ideas
!ideas 3        → 3 ideas
!keywords       → top keywords ranked by frequency
!stats          → collection stats embed
!clear          → admin-only data wipe
```

---

## Project Structure

```
ideaDB/
├── bot.py               # Discord bot — event handlers & commands
├── metadata_parser.py   # Algorithmic keyword/metadata extractor
├── idea_generator.py    # Groq LLM wrapper (llama-3.1-8b-instant)
├── database.py          # SQLite persistence layer
├── requirements.txt     # Python dependencies
├── .env.example         # Template for environment variables
├── .gitignore           # Excludes .env, *.sqlite, __pycache__, venv, etc.
└── README.md            # This file
```

---

## Getting Started

### Prerequisites

- Python **3.11** or later
- A [Discord bot token](https://discord.com/developers/applications) with the **Message Content** intent enabled
- A [Groq API key](https://console.groq.com)

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/Qrytics/ideaDB.git
cd ideaDB

# 2. Create and activate a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate          # Windows

# 3. Install dependencies
pip install -r requirements.txt
```

### Configuration

Copy the example env file and fill in your credentials:

```bash
cp .env.example .env
```

Open `.env` and set the values:

```dotenv
# Required
DISCORD_TOKEN=your_discord_bot_token_here
GROQ_API_KEY=your_groq_api_key_here

# Optional
IDEA_CHANNEL=idea-generation     # channel name or ID for auto-posts
DB_PATH=ideadb.sqlite            # path for the SQLite database
AUTO_IDEA_THRESHOLD=50           # auto-generate after N new entries (0 = off)
```

> ⚠️ **Never commit your `.env` file.** It is listed in `.gitignore`.

### Discord Bot Setup

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications) and create a new application.
2. Under **Bot**, click *Add Bot*, then copy the token into `DISCORD_TOKEN`.
3. Under **Bot → Privileged Gateway Intents**, enable **Message Content Intent**.
4. Under **OAuth2 → URL Generator**, select scopes: `bot` and permissions: `Read Messages/View Channels`, `Send Messages`, `Embed Links`.
5. Use the generated URL to invite the bot to your server.

### Running the Bot

```bash
python bot.py
```

You should see:
```
✅  IdeaDB is online — logged in as IdeaDB#1234 (id=...)
    Prefix: !   |   DB: ideadb.sqlite
    Auto-idea threshold: disabled
```

---

## Architecture Deep-Dive

### Metadata Parser (Algorithm)

`metadata_parser.py` is a **zero-LLM, zero-external-API** module. It uses only Python standard library plus `discord.py` objects.

#### Text Analysis

1. Strip Discord mention tags, URLs, and special characters.
2. Tokenise into lowercase words.
3. Filter stopwords (180+ common English words) and short tokens.
4. Run `collections.Counter` to rank by frequency → top 10 keywords.
5. Extract `#hashtags` with a simple regex.
6. Run 9 compiled regex patterns against the original text to detect tech/industry terms (AI, ML, API, SaaS, blockchain, framework names, etc.).

#### Attachment Analysis

For each `discord.Attachment`:
- Determine `media_type` from MIME type and file extension.
- Tokenise the filename stem (splitting on `-`, `_`, spaces).
- Add category tags: `visual-content`, `animation`, `gif`, `video`, `audio`, `code`, `document`, `spreadsheet`, `archive`, etc.
- For images: extract pixel dimensions, compute aspect ratio, classify as `high-resolution` or `thumbnail`.
- Map code-file extensions to language names (`py` → `python`, `rs` → `rust`, etc.).

#### URL Analysis

For each URL found in a message:
1. Parse with `urllib.parse.urlparse`.
2. Check against a 20-entry known-platform table (GitHub, YouTube, ProductHunt, HuggingFace, etc.).
3. For unknown domains: split the hostname into parts and keep non-TLD, non-stopword tokens.
4. Walk the first 6 path segments: split on `-`/`_`, then use a camelCase-splitting regex, filter stopwords.
5. Extract non-tracking query-string keys.
6. Detect document/video/image type from the path extension.

#### Embed Analysis

For Discord-generated link previews: extract title, description, and field text, then run them through the text analyser.

---

### Idea Generator (LLM)

`idea_generator.py` calls the **Groq API** with model `llama-3.1-8b-instant`.

The `generate_ideas` coroutine:
1. Calls `_build_context` (pure Python) to aggregate:
   - Top 30 keywords by frequency.
   - Content-type breakdown (messages, files, links).
   - Up to 20 unique tech-terms from raw message text.
   - Up to 10 recent message snippets (≤200 chars each).
2. Constructs a structured prompt asking for `count` ideas in a consistent format.
3. Offloads the blocking Groq call to `asyncio.get_event_loop().run_in_executor` to keep the Discord event loop non-blocking.
4. Returns the LLM's markdown-formatted text.

---

### Database

`database.py` wraps a local SQLite file with a single `entries` table and a handful of helper methods:

| Method | Description |
|--------|-------------|
| `store_entry(...)` | Insert a parsed entry |
| `get_recent_entries(guild_id, limit)` | Fetch latest N entries |
| `get_top_keywords(guild_id, limit)` | Aggregate keyword frequencies |
| `get_stats(guild_id)` | Return per-type entry counts |
| `clear_guild(guild_id)` | Delete all entries for a server |
| `count_entries(guild_id)` | Total entry count for a server |

Indices on `guild_id` and `(guild_id, content_type)` keep queries fast even with tens of thousands of entries.

---

## Auto-Idea Generation

Set `AUTO_IDEA_THRESHOLD=50` (or any positive integer) in your `.env` file.  
After every 50 new collected entries the bot posts 3 auto-generated ideas to the channel named in `IDEA_CHANNEL`.

The counter resets per-guild after each auto-post and is held in memory (it resets on bot restart — by design, to avoid spamming after a restart).

---

## Deployment

### Using a Process Manager (Linux / VPS)

```bash
# Install pm2
npm install -g pm2

# Start the bot
pm2 start bot.py --interpreter python3 --name ideadb

# Auto-start on reboot
pm2 startup && pm2 save
```

### Using systemd

```ini
# /etc/systemd/system/ideadb.service
[Unit]
Description=IdeaDB Discord Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/ideaDB
EnvironmentFile=/opt/ideaDB/.env
ExecStart=/opt/ideaDB/.venv/bin/python bot.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable ideadb
sudo systemctl start ideadb
```

### Using Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "bot.py"]
```

```bash
docker build -t ideadb .
docker run -d --env-file .env --name ideadb ideadb
```

---

## Contributing

Pull requests are welcome! Please:

1. Fork the repository.
2. Create a feature branch: `git checkout -b feature/my-feature`.
3. Commit your changes.
4. Open a Pull Request.

---

## License

MIT License — see [LICENSE](LICENSE) for details.

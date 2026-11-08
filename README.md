# Jarvis: your local voice-controlled assistant

Talk to your PC. Jarvis listens (local Whisper), thinks (Claude or a local Ollama model), acts (apps, files,
browser, screen, shell, coding CLIs, MCP servers) and talks back. Risky actions need your spoken approval.

## Setup (Windows, Python 3.11)

```
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
copy .env.example .env        (then put your ANTHROPIC_API_KEY in .env)
python main.py --check        (shows missing packages / microphone problems)
python tests\smoke_test.py    (offline self-test)
python main.py --text         (try everything by typing first)
python main.py                (voice mode: say "Jarvis, open Spotify")
```

**OmniRoute / any OpenAI-compatible gateway:** set `JARVIS_PROVIDER=omniroute`, then `JARVIS_OPENAI_BASE_URL` (ends in `/v1`), `JARVIS_OPENAI_KEY` and `JARVIS_OPENAI_MODEL` from the OmniRoute dashboard. Pick a model with tool calling.

**Ollama:** set `JARVIS_PROVIDER=ollama` and `JARVIS_OLLAMA_MODEL` to the exact name from `ollama list`. Small local models get a lite toolset automatically (`JARVIS_LITE`).

Fully local: install Ollama, `ollama pull qwen2.5:7b`, set `JARVIS_PROVIDER=ollama` in `.env`.
(For screen vision locally also `ollama pull llava`.)

## Talking to it

- Wake mode (default): say "Jarvis, <command>". Follow-ups work for 25 s without repeating the name.
- `--mode hotkey`: press F9, then speak. `--mode always`: every sentence is a command.
- "Go to sleep" returns to wake-word waiting. "Goodbye Jarvis" quits.
- Approvals: Jarvis asks out loud. Answer "yes", "no" or "always" (always = skip asking for that tool this session;
  never offered for shell, delete, write, move, power or coding agents).

Examples: "open Chrome and search for cheap flights to Goa", "play lo-fi beats on YouTube", "set volume to 30",
"find my resume in documents", "what's on my screen", "click the Send button", "remind me in 20 minutes to stretch",
"every weekday at 8:30 give me a briefing", "ask Claude Code to add tests in my project folder",
"remember that my TCS joining location is Pune".

## Features

| Area | Tools |
|---|---|
| Apps | open_app (Start Menu + Store apps), close_app, list_running_apps |
| Files | list/read/search files, search_in_files, open, create folder, write, move, delete (Recycle Bin) |
| Browser | open, search, read, links, click, type, press, scroll, back, youtube_play (own persistent profile) |
| Screen | look_at_screen, locate_on_screen, click_element, click_screen, scroll, screenshot |
| System | volume, mute, media keys, clipboard, type text, shortcuts, status, lock, shutdown/restart |
| Web | web_search, fetch_url |
| Shell | run_command (always asks, dangerous patterns blocked) |
| Coding agents | run_coding_agent for Claude Code, Codex, Gemini CLI, OpenCode (window or headless) |
| Memory | remember / recall / forget, injected into every conversation |
| Schedule | reminders and recurring routines (routines run unattended, approval-needing tools are skipped) |
| Extend | drop `.py` files into `plugins/`; MCP servers via `mcp_servers.json` (see the example file) |

## Extras

- `python main.py --gui`: live transcript window with Allow / Always / Deny buttons, a Stop-talking button and a typing box.
- Press **F8** (`JARVIS_STOP_KEY`) any time to cut Jarvis off mid-sentence.
- `python main.py --voices` lists voices. Set `JARVIS_TTS_VOICE=<part of name>` to choose one.
- Neural wake word: `pip install openwakeword`, set `JARVIS_LISTEN_MODE=neural`, then say "hey Jarvis". Low CPU, no mishearing of the name.
- `python main.py --install-startup` starts Jarvis (window mode) when Windows starts. `--remove-startup` undoes it.
- UI Automation tools (`ui_list_controls`, `ui_click`, `ui_type`) click real buttons and menus by name. More reliable than screenshots.

## Iron-Man style HUD and a better voice

`python main.py --hud` runs voice mode and opens a full-screen HUD in your browser (press F11): a glowing orb that
pulses while Jarvis listens, spins amber while thinking, and ripples while speaking, with your words and Jarvis's
replies typing out live. For a natural British male voice: `pip install edge-tts pygame`, then set
`JARVIS_TTS_ENGINE=edge` in `.env` (optional `JARVIS_EDGE_VOICE=en-GB-RyanNeural`). Needs internet, falls back to the
built-in voice offline.

## Languages: English, Hindi, Hinglish

Set `JARVIS_LANGUAGE=auto` (or `hi`) and `JARVIS_WHISPER_MODEL=small` in `.env`. Jarvis switches to the multilingual
speech model, understands Hindi and Hinglish, accepts "haan / nahi / hamesha" for approvals, answers in your language,
and with `JARVIS_TTS_ENGINE=edge` speaks Hindi replies in a Hindi voice. "जार्विस" works as a wake word.

## Only you can command it (owner check)

`python main.py --enroll-face` (5 camera shots), then `JARVIS_AUTH=face` in `.env`. Jarvis checks your face when a
session starts (valid for `JARVIS_AUTH_TTL` seconds). Needs `pip install opencv-python`. Voice ID is also available
(`--enroll-voice`, `JARVIS_AUTH=voice|either|both`) but needs `resemblyzer`, which needs torch. If a check can't run,
Jarvis refuses. This is a convenience lock: a photo or a recording can fool it, so don't treat it as real security.

## Control it from your phone

Create a bot with @BotFather, put the token in `TELEGRAM_TOKEN`, run `python main.py --telegram` and message the bot.
It replies with your chat id: put it in `TELEGRAM_ALLOWED_IDS` and restart. Now you can type or send voice notes
from anywhere. `/screen` sends a screenshot, `/status` reports the PC. Approvals are asked in the chat. Only the listed
chat ids are obeyed. Receiving WhatsApp messages needs a public webhook, so use Telegram for control;
`send_whatsapp` (Twilio) can only send.

## Install, launcher, platforms

- `install.ps1`: one-click setup (venv, packages, browser, Desktop shortcut that opens the HUD).
- `build_launcher.ps1`: builds a double-clickable `Jarvis.exe` launcher that sits next to `main.py`. It is a thin
  launcher, not a bundled app: bundling Whisper and Playwright into one exe is unreliable.
- Windows is the main platform. macOS and Linux now have volume, mute, lock, power, active window, autostart and
  terminal launch. On Linux install `xdotool` and `espeak`; on macOS grant Accessibility and Screen Recording
  permission. `UI Automation` tools and the `keyboard` hotkeys are Windows-only.

## Making it faster

1. The model is the biggest delay. An Opus-class route is slow: pick a fast model or combo in OmniRoute
   (Sonnet/Haiku/Flash class) for `JARVIS_OPENAI_MODEL`.
2. `JARVIS_LISTEN_MODE=neural` (or `hotkey`) stops Whisper from transcribing every sound.
3. `JARVIS_WHISPER_MODEL=base.en` is about twice as fast as `small.en`.
4. Vision: `JARVIS_VISION_WIDTH=1024`, and `look_at_screen` with target `window`.

## Dashboard, background agents and coding sessions

`python main.py --dashboard` (add `--headless` for no microphone) opens a local web page with tabs for Chat,
Agents, Coding, Schedule, Memory and Activity. The link includes a random token printed in the terminal, the server
only listens on 127.0.0.1, and other websites cannot drive it.

- **Approvals:** when the dashboard chat or a background agent needs permission, Allow / Always / Deny buttons
  appear at the top of the page. Background agents are denied automatically when no dashboard is running.
- **Background agents:** say "create an agent called researcher that researches topics on the web", then
  "ask researcher to compare the three best local speech models". It works on its own, keeps its own history,
  and Jarvis announces when it finishes. Agents never touch your mouse, keyboard, screen or volume.
- **Routines with agents:** "every weekday at 8:30 have researcher brief me on AI news".
- **Coding sessions:** "start Claude Code in the background on my project and add tests". Watch the live log and stop
  it from the Coding tab. Jarvis announces when it is done.
- **Phone (optional):** `phone_call` and `send_sms` need your own Twilio account (see `.env.example`). The call reads
  a message aloud, it is not a conversation. Each call asks first and can never be set to "always".
- **Faster replies:** answers are spoken sentence by sentence while the model is still writing
  (`JARVIS_STREAM=0` turns it off). Press F8 to cut Jarvis off.

## Safety model

- Every tool is `safe`, `ask` or blocked. Policy lives in `jarvis/safety.py`, and every call is logged to
  `~/.jarvis/audit.jsonl`.
- Shell commands always ask and can't be auto-approved. Disk-wipe, registry-hive and similar patterns are blocked.
- Writes, moves and deletes refuse Windows, Program Files and drive roots.
- Browser clicks on words like buy/pay/send/delete and typing with "submit" ask first.
- With the Anthropic provider, screen-vision tools ask first because a screenshot leaves your PC.
- Web pages, files and screens are treated as untrusted data (prompt-injection guard in the system prompt).
- Mouse failsafe: slam the pointer into the top-left screen corner to abort a click or typing sequence.
- `JARVIS_AUTO_APPROVE=type_text,press_keys` lets you opt out of prompts per tool.

## Tuning

- Mic too sensitive or deaf: `JARVIS_MIC_THRESHOLD`. Slow recognition: `JARVIS_WHISPER_MODEL=base.en`.
- Other languages: `JARVIS_WHISPER_MODEL=small` and `JARVIS_LANGUAGE=hi` (or your language code).
- Coding CLI flags differ between versions. Edit `CODING_CLIS` in `jarvis/config.py`.

## Known limits

Built and logic-tested offline (agent loop, safety, memory, tools registry). Microphone, speech, browser,
screen and MCP parts depend on your hardware and installed packages. Run `--check` first and send me any errors.
No two-way phone conversations, and no multi-pane terminal IDE (use the Coding tab and your own terminal).

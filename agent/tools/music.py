"""Music playback tool using yt-dlp."""

import asyncio
import shutil


async def play_music(query: str) -> str:
    """Search YouTube and play audio of the first result."""
    if not shutil.which("yt-dlp"):
        return "yt-dlp is not installed. Please install it: pip install yt-dlp"

    try:
        # Use yt-dlp with JSON output for reliable parsing, skip URL resolution
        search_cmd = [
            "yt-dlp",
            f"ytsearch1:{query}",
            "--dump-json",
            "--no-download",
            "--no-warnings",
            "--no-playlist",
        ]
        proc = await asyncio.create_subprocess_exec(
            *search_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

        if proc.returncode != 0:
            return f"Search failed: {stderr.decode(errors='replace').strip()}"

        import json
        info = json.loads(stdout.decode(errors='replace'))
        title = info.get("title", "Unknown")
        video_url = info.get("webpage_url", "")

        if not video_url:
            return "No music found for that query."

        # Play with ffplay via yt-dlp piping (more reliable than raw URL)
        if shutil.which("ffplay"):
            play_cmd = [
                "yt-dlp",
                "-f", "bestaudio",
                "-o", "-",
                "--no-warnings",
                video_url,
            ]
            # Pipe yt-dlp output to ffplay
            yt_proc = await asyncio.create_subprocess_exec(
                *play_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.create_subprocess_exec(
                "ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "-i", "pipe:0",
                stdin=yt_proc.stdout,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            return f"Now playing: {title}"
        else:
            return (
                f"Found: {title}\n"
                f"URL: {video_url}\n"
                "Note: ffplay not found. Install ffmpeg to enable audio playback."
            )

    except asyncio.TimeoutError:
        return "Music search timed out. Try a more specific query."
    except Exception as e:
        return f"Music playback error: {e}"

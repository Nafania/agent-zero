"""
Async wrapper over the `npx skills` CLI.

Provides: find, add, remove, check_updates, update.
Caches find results in memory with 1-hour TTL.
"""
from __future__ import annotations

import asyncio
import re
import time
from collections import OrderedDict

CACHE_TTL = 3600  # 1 hour
CACHE_MAX = 50
TIMEOUT_FIND = 30
TIMEOUT_ADD = 60
TIMEOUT_DEFAULT = 30


class SkillsCLIError(Exception):
    pass


_cache: OrderedDict[str, tuple[list[dict[str, str]], float]] = OrderedDict()


async def _run_npx(*args: str, timeout: int = TIMEOUT_DEFAULT) -> str:
    cmd = ["npx", "skills", *args]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        raise SkillsCLIError(
            "Node.js/npx not found. Install Node.js to use Skills marketplace."
        )

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise SkillsCLIError(f"Command timed out after {timeout}s: {' '.join(cmd)}")

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="replace").strip()
        raise SkillsCLIError(err or f"npx skills exited with code {proc.returncode}")

    return stdout.decode("utf-8", errors="replace").strip()


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def parse_find_output(output: str) -> list[dict[str, str]]:
    if not output or not output.strip():
        return []

    clean = _strip_ansi(output)
    results: list[dict[str, str]] = []
    lines = clean.strip().splitlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        m = re.match(r"^(\S+)\s+(\S+\s+installs)\s*$", line)
        if m:
            source = m.group(1)
            installs = m.group(2)
            url = ""
            if i + 1 < len(lines):
                url_line = lines[i + 1].strip()
                url_m = re.match(r"^[└|]?\s*(https?://\S+)", url_line)
                if url_m:
                    url = url_m.group(1)
                    i += 1
            name = source.split("@")[-1] if "@" in source else source.rsplit("/", 1)[-1]
            results.append({
                "name": name,
                "source": source,
                "description": f"{installs}",
                "url": url,
            })
        i += 1

    return results


async def find(query: str) -> list[dict[str, str]]:
    query = (query or "").strip()
    if not query:
        return []

    now = time.monotonic()
    if query in _cache:
        results, ts = _cache[query]
        if now - ts < CACHE_TTL:
            _cache.move_to_end(query)
            return results

    output = await _run_npx("find", query, timeout=TIMEOUT_FIND)
    results = parse_find_output(output)

    _cache[query] = (results, now)
    _cache.move_to_end(query)
    while len(_cache) > CACHE_MAX:
        _cache.popitem(last=False)

    return results


async def _list_repo_skills(owner_repo: str) -> list[str]:
    """Query GitHub API for all skill directories in a repo's skills/ folder."""
    import aiohttp

    url = f"https://api.github.com/repos/{owner_repo}/contents/skills"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return [
                    item["name"]
                    for item in data
                    if isinstance(item, dict) and item.get("type") == "dir"
                ]
    except Exception:
        return []


async def add(source: str) -> str:
    source = (source or "").strip()
    if not source:
        raise SkillsCLIError("source is required")

    has_skill_specifier = "@" in source

    if not has_skill_specifier and "/" in source:
        skill_names = await _list_repo_skills(source)
        if len(skill_names) > 1:
            results = []
            for skill_name in skill_names:
                full_source = f"{source}@{skill_name}"
                try:
                    out = await _run_npx(
                        "add", full_source, "--yes", "--global", timeout=TIMEOUT_ADD
                    )
                    results.append(f"+ {skill_name}")
                except SkillsCLIError as e:
                    results.append(f"x {skill_name}: {e}")
            _cache.clear()
            return f"Installed {len(results)} skills from {source}:\n" + "\n".join(results)

    result = await _run_npx("add", source, "--yes", "--global", timeout=TIMEOUT_ADD)
    _cache.clear()
    return result


async def remove(skill_name: str) -> str:
    skill_name = (skill_name or "").strip()
    if not skill_name:
        raise SkillsCLIError("skill_name is required")

    result = await _run_npx("remove", skill_name, "--yes", "--global", timeout=TIMEOUT_DEFAULT)
    _cache.clear()
    return result


async def check_updates() -> str:
    return await _run_npx("check", timeout=TIMEOUT_DEFAULT)


async def update() -> str:
    result = await _run_npx("update", timeout=TIMEOUT_ADD)
    _cache.clear()
    return result

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
                "description": "",
                "installs": installs,
                "url": url,
            })
        i += 1

    return results


async def find(query: str, enrich: bool = False) -> list[dict[str, str]]:
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

    if enrich and results:
        repos: set[str] = set()
        for r in results:
            src = r.get("source", "")
            if "@" in src:
                repos.add(src.split("@")[0])
            elif "/" in src:
                repos.add(src)

        desc_map: dict[str, dict[str, str]] = {}
        for repo in repos:
            desc_map[repo] = await list_repo_skills(repo)

        for r in results:
            src = r.get("source", "")
            if "@" in src:
                repo, skill = src.split("@", 1)
            elif "/" in src:
                repo, skill = src, src.rsplit("/", 1)[-1]
            else:
                continue
            repo_descs = desc_map.get(repo, {})
            if skill in repo_descs and repo_descs[skill]:
                r["description"] = repo_descs[skill]

    _cache[query] = (results, now)
    _cache.move_to_end(query)
    while len(_cache) > CACHE_MAX:
        _cache.popitem(last=False)

    return results


_CTRL_RE = re.compile(r"\x1b\[\?\d+[hl]|\x1b\[\d*[A-Za-z]|\x1b\].*?\x07|\r")

def _strip_all_ansi(text: str) -> str:
    return _CTRL_RE.sub("", _strip_ansi(text))


def parse_list_output(output: str) -> dict[str, str]:
    """Parse `npx skills add <repo> --list` output into {skill_name: description}."""
    if not output:
        return {}

    clean = _strip_all_ansi(output)
    result: dict[str, str] = {}
    lines = clean.strip().splitlines()

    current_name: str | None = None
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            current_name = None
            continue
        stripped = line.lstrip("│ ").strip()
        if not stripped or stripped.startswith("Tip:") or stripped.startswith("Source:"):
            continue
        if stripped.startswith("Available Skills") or stripped.startswith("Found "):
            continue
        if stripped.startswith("Use --"):
            continue

        if re.match(r"^[a-z0-9][a-z0-9._:-]*$", stripped, re.IGNORECASE):
            current_name = stripped
            result[current_name] = ""
        elif current_name is not None and current_name in result:
            result[current_name] = stripped

    return result


_desc_cache: OrderedDict[str, tuple[dict[str, str], float]] = OrderedDict()


async def list_repo_skills(owner_repo: str) -> dict[str, str]:
    """Run `npx skills add <repo> --list` and return {skill_name: description}."""
    now = time.monotonic()
    if owner_repo in _desc_cache:
        data, ts = _desc_cache[owner_repo]
        if now - ts < CACHE_TTL:
            _desc_cache.move_to_end(owner_repo)
            return data

    try:
        output = await _run_npx("add", owner_repo, "--list", timeout=TIMEOUT_ADD)
    except SkillsCLIError:
        return {}

    data = parse_list_output(output)
    _desc_cache[owner_repo] = (data, now)
    _desc_cache.move_to_end(owner_repo)
    while len(_desc_cache) > CACHE_MAX:
        _desc_cache.popitem(last=False)

    return data


async def add(source: str) -> str:
    source = (source or "").strip()
    if not source:
        raise SkillsCLIError("source is required")

    has_skill_specifier = "@" in source

    if not has_skill_specifier and "/" in source:
        repo_skills = await list_repo_skills(source)
        skill_names = list(repo_skills.keys())
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

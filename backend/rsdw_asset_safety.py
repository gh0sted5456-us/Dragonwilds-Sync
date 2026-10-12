"""Bounded HTTPS downloads and strict staging-only GitHub archive extraction."""
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
import urllib.request
from urllib.parse import urlsplit

HOSTS = {"api.github.com", "codeload.github.com", "raw.githubusercontent.com", "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}
MAX_DOWNLOAD = 1024 * 1024 * 1024


def validate_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in HOSTS or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("RSDW assets require an approved GitHub HTTPS host")


class GitHubRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url, target, timeout=90):
    validate_url(url)
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".rsdw-download-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            request = urllib.request.Request(url, headers={"User-Agent": "DragonwildsSync"})
            with urllib.request.build_opener(GitHubRedirect()).open(request, timeout=timeout) as response:
                validate_url(response.geturl())
                expected = response.headers.get("Content-Length")
                if expected and int(expected) > MAX_DOWNLOAD:
                    raise ValueError("RSDW download exceeds size limit")
                total = 0
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_DOWNLOAD:
                        raise ValueError("RSDW download exceeds size limit")
                    output.write(chunk)
                if not total or (expected and total != int(expected)):
                    raise ValueError("RSDW download is empty or incomplete")
        os.replace(name, target)
    finally:
        Path(name).unlink(missing_ok=True)


def extract_archive(archive, target):
    root = Path(target).resolve()
    seen = set()
    total = 0
    members = archive.infolist()
    if len(members) > 150000:
        raise ValueError("RSDW archive contains too many entries")
    for member in members:
        raw = member.filename
        parts = PurePosixPath(raw).parts
        mode = member.external_attr >> 16
        if not parts or raw.startswith('/') or '\\' in raw or any(p in ('.', '..') or ':' in p or p.endswith((' ', '.')) for p in parts):
            raise ValueError("Unsafe RSDW archive path")
        reserved = {'con', 'prn', 'aux', 'nul', *('com'+str(i) for i in range(1,10)), *('lpt'+str(i) for i in range(1,10))}
        if any(p.split('.')[0].casefold() in reserved for p in parts):
            raise ValueError("RSDW archive contains a reserved Windows filename")
        if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
            raise ValueError("RSDW archive contains a special file")
        destination = (root / Path(*parts)).resolve()
        if not destination.is_relative_to(root) or destination == root:
            raise ValueError("RSDW archive escapes staging")
        key = raw.rstrip('/').casefold()
        if key in seen:
            raise ValueError("RSDW archive contains duplicate paths")
        seen.add(key)
        total += member.file_size
        if total > 4 * MAX_DOWNLOAD or member.file_size > MAX_DOWNLOAD:
            raise ValueError("RSDW archive expands beyond size limit")
    archive.extractall(root)

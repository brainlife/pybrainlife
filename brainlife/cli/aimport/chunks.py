"""The chunk map of reference datasets (an OME-Zarr input that aimport does not copy).

The engine writes only new metadata for such a store under ``bids/``, plus
``<work>/output/bids.chunks.json`` (named by ``chunk_map`` in GET /status), which says where each
array's chunks are::

    {"version": 1, "arrays": {"<array dir under bids/>": {
        "source": {"input": "<input-relative dir>"} | {"url": "<https URL>"},
        "zarr_format": 2|3, "shape": [...], "chunk_grid": [...], "separator": "/"|".",
        "codec_bytes_hint": n, ["key_encoding": "v2"]}}}

At upload each chunk is streamed from its source into the object's tar; nothing is copied to disk.
The key and URL rules follow the engine's ``aimport/micr/reference.py`` and
``aimport/micr/remote.py``. The map holds input paths and URLs: it is never uploaded and its
content is never printed.
"""

import email.utils
import errno
import ipaddress
import itertools
import json
import os
import re
import stat
import time
from urllib.parse import unquote, urljoin, urlsplit

import requests

CHUNK_MAP_VERSION = 1
SEPARATORS = ("/", ".")
MAX_REDIRECTS = 5
# S3 answers 403 for a missing key when listing is not allowed
MISSING_STATUS = (403, 404, 410)
_INDEX = re.compile(r"0|[1-9][0-9]*")
_KEY = re.compile(r"c?[0-9./]*")


class ChunkMapError(ValueError):
    pass


def segments(p):
    """The segments of a plain relative posix path: no absolute path, no '', '.' or '..' (also %2e%2e)."""
    if not isinstance(p, str) or not p or p.startswith("/") or "\\" in p or "\0" in p:
        raise ChunkMapError("not a relative path")
    parts = p.split("/")
    if any(s in ("", ".", "..") or unquote(s) in (".", "..") for s in parts):
        raise ChunkMapError("not a plain relative path")
    return parts


# --- chunk keys --------------------------------------------------------------------------------

def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _counts(meta):
    shape = meta.get("shape") if isinstance(meta, dict) else None
    grid = meta.get("chunk_grid") if isinstance(meta, dict) else None
    if (not isinstance(shape, list) or not isinstance(grid, list) or len(shape) != len(grid)
            or any(not _is_int(s) or s < 0 for s in shape) or any(not _is_int(g) or g <= 0 for g in grid)):
        raise ChunkMapError("the chunk map entry has no valid chunk grid")
    return [-(-s // g) for s, g in zip(shape, grid)]


def _prefixed(meta):
    return meta.get("zarr_format") == 3 and meta.get("key_encoding", "default") == "default"


def _separator(meta):
    sep = meta.get("separator")
    if sep not in SEPARATORS:
        raise ChunkMapError("the chunk map entry has no valid separator")
    return sep


def chunk_keys(meta):
    """Every chunk (or shard) key of an array: Zarr v2 ``0.0`` or ``0/0``, Zarr v3 ``c/0/0``.
    A key with no source object is the fill value."""
    sep, prefixed, counts = _separator(meta), _prefixed(meta), _counts(meta)
    for idx in itertools.product(*(range(n) for n in counts)):
        body = sep.join(str(i) for i in idx)
        if prefixed:
            yield "c" + (sep + body if idx else "")
        else:
            yield body if idx else "0"


def key_count(meta):
    n = 1
    for c in _counts(meta):
        n *= c
    return n


def key_ok(meta, key):
    sep, counts = _separator(meta), _counts(meta)
    if not isinstance(key, str):
        return False
    if _prefixed(meta):
        if not key.startswith("c"):
            return False
        key = key[1:]
        if not counts:
            return key == ""
        if not key.startswith(sep):
            return False
        key = key[1:]
    elif not counts:
        return key == "0"
    parts = key.split(sep)
    return len(parts) == len(counts) and all(
        _INDEX.fullmatch(p) is not None and int(p) < n for p, n in zip(parts, counts))


# --- remote rules ------------------------------------------------------------------------------

def _host_refused(host):
    """IP literals, localhost (and *.localhost) and single-label hosts."""
    if not host or "." not in host:
        return True
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        pass
    last = host.rsplit(".", 1)[-1]
    return not re.search(r"[a-z]", last) or last.startswith("0x")


def normalize_url(url):
    """The canonical https URL of a remote source in the chunk map. The engine has already turned
    s3:// into https, so only https:// is accepted here."""
    if not isinstance(url, str) or any(c.isspace() for c in url):
        raise ChunkMapError("a remote source is not a URL")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise ChunkMapError("a remote source is not a URL")
    if parts.scheme.lower() != "https":
        raise ChunkMapError("remote sources must be https:// URLs")
    if "@" in parts.netloc or parts.username is not None or parts.password is not None:
        raise ChunkMapError("remote URLs must not carry user information")
    if parts.query or parts.fragment or "?" in url or "#" in url:
        raise ChunkMapError("remote URLs must not carry a query or fragment")
    host = (parts.hostname or "").lower().rstrip(".")
    if _host_refused(host):
        raise ChunkMapError("remote host must be a dotted DNS name (not an IP address or localhost)")
    if any(unquote(s) in (".", "..") for s in parts.path.split("/")):
        raise ChunkMapError("a remote URL has a relative or encoded path segment")
    netloc = host if port in (None, 443) else "%s:%d" % (host, port)
    return "https://" + netloc + parts.path.rstrip("/")


def _origin(url):
    p = urlsplit(url)
    host = (p.hostname or "").lower()
    port = p.port
    if port is not None and not ((p.scheme == "https" and port == 443) or (p.scheme == "http" and port == 80)):
        host += ":%d" % port
    return p.scheme.lower(), host


def redirect_allowed(origin_url, location):
    """Same origin as the request, or an https ``*.amazonaws.com`` host."""
    try:
        target = urlsplit(location)
        target.port  # noqa: B018 (raises on a bad port)
        if not target.scheme and not target.netloc:
            return True  # relative: same origin
        absolute = urljoin(origin_url, location)
        if _origin(absolute) == _origin(origin_url):
            return True
        t = urlsplit(absolute)
        host = (t.hostname or "").lower()
        return (t.scheme.lower() == "https" and t.username is None and t.password is None
                and t.port in (None, 443) and host.endswith(".amazonaws.com"))
    except ValueError:
        return False


# --- loading and checking ----------------------------------------------------------------------

def _strictly_inside(root, p):
    return p != root and p.startswith(root + os.sep)


def load_chunk_map(work, bids_dir, input_dir, rel):
    """The chunk map /status names (rel, relative to work), or None when it names none.
    Returns {"bids_dir", "input_dir", "arrays"}."""
    if rel is None or rel == "":
        return None
    work_dir = os.path.abspath(work)
    path = os.path.join(work_dir, *segments(rel))
    if not path.endswith(".chunks.json"):
        raise ChunkMapError("the chunk map is not a .chunks.json file")
    if _strictly_inside(os.path.abspath(bids_dir), path):
        raise ChunkMapError("the chunk map lies inside the output")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        raise ChunkMapError("the chunk map cannot be read; execute the plan again")
    if (not isinstance(data, dict) or data.get("version") != CHUNK_MAP_VERSION
            or not isinstance(data.get("arrays"), dict)):
        raise ChunkMapError("the chunk map has an unknown format; update brainlife or rebuild the engine image")
    return {"bids_dir": os.path.abspath(bids_dir), "input_dir": os.path.abspath(input_dir), "arrays": data["arrays"]}


def zarr_dirs(manifest):
    out = []
    for rels in (manifest or {}).values():
        for r in rels if isinstance(rels, list) else []:
            if isinstance(r, str) and r.endswith(".ome.zarr"):
                out.append(r)
    return out


def walk_input(root, segs):
    """Walk an input-relative path below root; no segment may be a symlink. -> (path, missing)."""
    p = root
    for s in segs:
        p = os.path.join(p, s)
        try:
            st = os.lstat(p)
        except FileNotFoundError:
            return p, True
        except NotADirectoryError:
            return p, True
        if stat.S_ISLNK(st.st_mode):
            raise ChunkMapError("a referenced source goes through a symlink")
    return p, False


def check_chunk_map(output_dir, chunk_map, manifest, input_dir):
    """Every array of the map: strictly inside a written .ome.zarr of the manifest, a valid grid,
    and one source inside the input folder (no symlink) or at an allowed https URL."""
    root = os.path.abspath(output_dir)
    dirs = zarr_dirs(manifest)
    input_real = None
    for prefix, meta in chunk_map["arrays"].items():
        try:
            segs = segments(prefix)
        except ChunkMapError:
            raise ChunkMapError("refusing to upload: the chunk map names an array outside the output")
        norm = "/".join(segs)
        if not any(norm.startswith(d + "/") for d in dirs):
            raise ChunkMapError("refusing to upload: the chunk map names an array outside the written OME-Zarr images")
        full = os.path.join(root, *segs)
        if os.path.islink(full) or not os.path.isdir(full):
            raise ChunkMapError("refusing to upload: a referenced array has no metadata in the output")
        if not isinstance(meta, dict) or meta.get("zarr_format") not in (2, 3) or isinstance(meta.get("zarr_format"), bool):
            raise ChunkMapError("refusing to upload: a chunk map entry has no valid Zarr format")
        try:
            _separator(meta)
            _counts(meta)
        except ChunkMapError as err:
            raise ChunkMapError("refusing to upload: %s" % err)
        source = meta.get("source")
        if not isinstance(source, dict) or len(source) != 1:
            raise ChunkMapError("refusing to upload: a chunk map entry has no valid source")
        if "input" in source:
            if not input_dir:
                raise ChunkMapError("refusing to upload: a referenced source needs the input folder")
            if input_real is None:
                input_real = os.path.realpath(input_dir)
            try:
                path, missing = walk_input(input_real, segments(source["input"]))
            except ChunkMapError as err:
                raise ChunkMapError("refusing to upload: a referenced source leaves the input folder (%s)" % err)
            if missing:
                raise ChunkMapError("refusing to upload: a referenced source folder is missing from the input")
            if not _strictly_inside(input_real, os.path.realpath(path)):
                raise ChunkMapError("refusing to upload: a referenced source lies outside the input folder")
        elif "url" in source:
            try:
                normalize_url(source["url"])
            except ChunkMapError as err:
                raise ChunkMapError("refusing to upload: %s" % err)
        else:
            raise ChunkMapError("refusing to upload: a chunk map entry has no valid source")


# --- opening a chunk ---------------------------------------------------------------------------

class Chunk:
    """One chunk to stream: ``read(n)``, its stored ``size`` and ``mtime``; close() when done."""

    def __init__(self, fileobj, size, mtime, closer=None):
        self.fileobj = fileobj
        self.size = size
        self.mtime = mtime
        self._closer = closer

    def read(self, n=-1):
        return self.fileobj.read(n)

    def close(self):
        try:
            if self._closer:
                self._closer()
            else:
                self.fileobj.close()
        except Exception:
            pass


_session = None


def _default_get(url, headers):
    global _session
    if _session is None:
        _session = requests.Session()
        _session.trust_env = False  # anonymous reads: no netrc credentials, no proxy rewriting
    return _session.get(url, headers=headers, allow_redirects=False, stream=True, timeout=(30, 300))


def open_source(source, key, input_dir=None, http_get=None):
    """The Chunk of key in source, or None when the source has no such object (the fill value).
    http_get(url, headers) -> a requests-like streaming response that does not follow redirects."""
    if not isinstance(source, dict):
        raise ChunkMapError("no valid source")
    if not isinstance(key, str) or not _KEY.fullmatch(key):
        raise ChunkMapError("not a chunk key")
    key_segs = segments(key)
    if "input" in source:
        root = os.path.realpath(input_dir)
        path, missing = walk_input(root, segments(source["input"]) + key_segs)
        if missing:
            return None
        try:
            # O_NOFOLLOW: the last segment cannot become a symlink after the walk
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            return None
        except OSError as err:
            if err.errno == errno.ELOOP:
                raise ChunkMapError("a referenced source goes through a symlink")
            raise
        try:
            if not _strictly_inside(root, os.path.realpath(path)):
                raise ChunkMapError("a referenced source lies outside the input folder")
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                raise ChunkMapError("a referenced chunk is not a regular file")
        except BaseException:
            os.close(fd)
            raise
        return Chunk(os.fdopen(fd, "rb"), st.st_size, st.st_mtime)
    if "url" in source:
        get = http_get or _default_get
        url = normalize_url(source["url"]) + "/" + key
        for _ in range(MAX_REDIRECTS + 1):
            res = get(url, {"Accept-Encoding": "identity"})
            code = res.status_code
            if 300 <= code < 400:
                location = res.headers.get("location") or ""
                res.close()
                if not location or not redirect_allowed(url, location):
                    raise ChunkMapError("redirect to another host refused")
                url = urljoin(url, location)
                continue
            if code in MISSING_STATUS:
                res.close()
                return None

            def drop(msg):
                res.close()
                raise ChunkMapError(msg)

            if code != 200:
                drop("a referenced chunk could not be read (HTTP %d)" % code)
            encoding = (res.headers.get("content-encoding") or "identity").lower()
            if encoding != "identity":
                drop("a referenced chunk was sent encoded (%s)" % encoding)
            length = res.headers.get("content-length")
            if length is None or not re.fullmatch(r"[0-9]+", length):
                drop("a referenced chunk has no Content-Length")
            lm = res.headers.get("last-modified")
            try:
                mtime = email.utils.parsedate_to_datetime(lm).timestamp() if lm else time.time()
            except (TypeError, ValueError):
                mtime = time.time()
            return Chunk(res.raw, int(length), mtime, closer=res.close)
        raise ChunkMapError("too many redirects")
    raise ChunkMapError("no valid source")


# --- what an object streams --------------------------------------------------------------------

def arrays_under(chunk_map, fullpath):
    """The referenced arrays inside a written directory: [(sub, meta)] (sub: the array dir below it)."""
    if not chunk_map:
        return []
    rel = os.path.relpath(os.path.abspath(fullpath), chunk_map["bids_dir"]).replace(os.sep, "/")
    if not rel or rel == "." or rel.startswith(".."):
        return []
    return [(p[len(rel) + 1:], chunk_map["arrays"][p]) for p in sorted(chunk_map["arrays"]) if p.startswith(rel + "/")]


def streamed_bytes(chunk_map, datasets):
    """(bytes, upper_bound, arrays): what these objects stream from their sources. Input chunks are
    stat'ed; remote ones are counted at codec_bytes_hint (an upper bound; nothing is fetched)."""
    total, upper, arrays = 0, False, 0
    if not chunk_map:
        return total, upper, arrays
    input_real = os.path.realpath(chunk_map["input_dir"])
    for item in datasets:
        for full in (item.get("files") or {}).values():
            for _sub, meta in arrays_under(chunk_map, full):
                arrays += 1
                source = meta.get("source") or {}
                if "url" in source:
                    try:
                        hint = int(meta.get("codec_bytes_hint") or 0)
                    except (TypeError, ValueError):
                        hint = 0
                    total += key_count(meta) * hint
                    upper = True
                    continue
                base = os.path.join(input_real, *segments(source["input"]))
                for key in chunk_keys(meta):
                    try:
                        st = os.lstat(os.path.join(base, *key.split("/")))
                        if stat.S_ISREG(st.st_mode):
                            total += st.st_size
                    except OSError:
                        pass  # a missing chunk is the fill value
    return total, upper, arrays

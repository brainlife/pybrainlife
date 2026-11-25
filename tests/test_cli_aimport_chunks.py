"""bl aimport: the chunk map of reference datasets (OME-Zarr inputs aimport does not copy)."""

import json
import os

import pytest

from brainlife.cli.aimport import chunks
from brainlife.cli.aimport.chunks import ChunkMapError
from brainlife.cli.aimport.objects import RefusedError, preflight

from .aimport_support import Stub, write

ZARR = "sub-01/micr/sub-01_sample-01_OCT.ome.zarr"
ARRAY = ZARR + "/0"
MANIFEST = {"m1": [ZARR]}


def meta(source, **extra):
    m = {"source": source, "zarr_format": 3, "shape": [4, 4], "chunk_grid": [2, 2], "separator": "/",
         "codec_bytes_hint": 16}
    m.update(extra)
    return m


@pytest.fixture
def tree(tmp_path):
    root = os.path.realpath(str(tmp_path))
    work = os.path.join(root, "work")
    bids = os.path.join(work, "output", "bids")
    inp = os.path.join(root, "input")
    write(os.path.join(bids, ZARR, "zarr.json"), '{"zarr_format": 3, "node_type": "group"}')
    write(os.path.join(bids, ARRAY, "zarr.json"), '{"zarr_format": 3, "node_type": "array"}')
    for key in ("c/0/0", "c/0/1", "c/1/0"):  # c/1/1 missing: the fill value
        write(os.path.join(inp, "store.zarr", "0", *key.split("/")), "chunk " + key)
    return {"root": root, "work": work, "bids": bids, "input": inp}


def cmap(tree, arrays):
    return {"bids_dir": tree["bids"], "input_dir": tree["input"], "arrays": arrays}


# --- keys ---------------------------------------------------------------------------------------

def test_v3_keys_have_the_c_prefix_and_cover_the_grid():
    assert list(chunks.chunk_keys(meta({}))) == ["c/0/0", "c/0/1", "c/1/0", "c/1/1"]
    assert list(chunks.chunk_keys(meta({}, separator="."))) == ["c.0.0", "c.0.1", "c.1.0", "c.1.1"]


def test_v2_and_v2_encoded_v3_keys_and_partial_edge_chunks():
    assert list(chunks.chunk_keys({"zarr_format": 2, "shape": [3, 2], "chunk_grid": [2, 2], "separator": "."})) == ["0.0", "1.0"]
    assert list(chunks.chunk_keys({"zarr_format": 3, "key_encoding": "v2", "shape": [2], "chunk_grid": [1],
                                   "separator": "/"})) == ["0", "1"]
    assert list(chunks.chunk_keys({"zarr_format": 2, "shape": [], "chunk_grid": [], "separator": "."})) == ["0"]
    assert chunks.key_count(meta({}, shape=[5, 4, 3], chunk_grid=[2, 2, 2])) == 3 * 2 * 2


def test_key_ok_accepts_only_keys_inside_the_grid():
    m = meta({})
    assert chunks.key_ok(m, "c/1/1")
    for bad in ("c/2/0", "c/../0", "0/0", "c/00/0", "c/0", "c/0/0/0", "c/-1/0", None):
        assert not chunks.key_ok(m, bad), bad


def test_a_bad_grid_or_separator_is_refused():
    with pytest.raises(ChunkMapError):
        list(chunks.chunk_keys(meta({}, chunk_grid=[0, 2])))
    with pytest.raises(ChunkMapError):
        list(chunks.chunk_keys(meta({}, separator="\\")))
    with pytest.raises(ChunkMapError):
        list(chunks.chunk_keys(meta({}, shape=[4, True])))


# --- URL rules ----------------------------------------------------------------------------------

def test_normalize_url_keeps_plain_https_and_drops_default_port_and_trailing_slash():
    assert chunks.normalize_url("https://Bucket.S3.amazonaws.com:443/a.zarr/0/") == "https://bucket.s3.amazonaws.com/a.zarr/0"
    assert chunks.normalize_url("https://data.example.org:8443/x") == "https://data.example.org:8443/x"


@pytest.mark.parametrize("url", [
    "http://bucket.s3.amazonaws.com/a.zarr", "file:///etc/a.zarr", "s3://bucket/a.zarr",
    "https://u:p@example.org/a.zarr", "https://example.org/a.zarr?X-Amz-Signature=1", "https://example.org/a#x",
    "https://127.0.0.1/a.zarr", "https://[::1]/a", "https://localhost/a.zarr", "https://x.localhost/a",
    "https://intranet/a", "https://127.1/a", "https://example.org/a/../b.zarr", "https://example.org/a/%2e%2e/b",
    "https://example.org/a b", 42,
])
def test_normalize_url_refuses(url):
    with pytest.raises(ChunkMapError):
        chunks.normalize_url(url)


def test_redirects_are_allowed_to_the_same_origin_and_https_amazonaws_only():
    o = "https://data.example.org/a.zarr/0/c/0/0"
    assert chunks.redirect_allowed(o, "/moved/c/0/0")
    assert chunks.redirect_allowed(o, "https://data.example.org/other")
    assert chunks.redirect_allowed(o, "https://bucket.s3.us-east-1.amazonaws.com/a")
    for bad in ("https://evil.example.net/x", "http://bucket.s3.amazonaws.com/x", "//evil.example.net/x",
                "https://bucket.s3.amazonaws.com:8443/x", "https://u@bucket.s3.amazonaws.com/x",
                "https://amazonaws.com.evil.net/x"):
        assert not chunks.redirect_allowed(o, bad), bad


# --- loading and checking -----------------------------------------------------------------------

def test_load_chunk_map_reads_the_map_the_status_names(tree):
    assert chunks.load_chunk_map(tree["work"], tree["bids"], tree["input"], None) is None
    write(os.path.join(tree["work"], "output", "bids.chunks.json"),
          json.dumps({"version": 1, "arrays": {ARRAY: meta({"input": "store.zarr/0"})}}))
    m = chunks.load_chunk_map(tree["work"], tree["bids"], tree["input"], "output/bids.chunks.json")
    assert list(m["arrays"]) == [ARRAY] and m["input_dir"] == tree["input"]


def test_load_chunk_map_refuses_escapes_maps_in_the_output_and_unknown_versions(tree):
    with pytest.raises(ChunkMapError):
        chunks.load_chunk_map(tree["work"], tree["bids"], tree["input"], "../bids.chunks.json")
    with pytest.raises(ChunkMapError):
        chunks.load_chunk_map(tree["work"], tree["bids"], tree["input"], "output/plan.json")
    write(os.path.join(tree["bids"], "x.chunks.json"), '{"version": 1, "arrays": {}}')
    with pytest.raises(ChunkMapError, match="inside the output"):
        chunks.load_chunk_map(tree["work"], tree["bids"], tree["input"], "output/bids/x.chunks.json")
    write(os.path.join(tree["work"], "output", "bids.chunks.json"), '{"version": 2, "arrays": {}}')
    with pytest.raises(ChunkMapError, match="unknown format"):
        chunks.load_chunk_map(tree["work"], tree["bids"], tree["input"], "output/bids.chunks.json")
    with pytest.raises(ChunkMapError, match="cannot be read"):
        chunks.load_chunk_map(tree["work"], tree["bids"], tree["input"], "output/missing.chunks.json")


def check(tree, arrays):
    preflight(tree["bids"], chunk_map=cmap(tree, arrays), manifest=MANIFEST, input_dir=tree["input"])


def test_preflight_accepts_input_and_https_sources_inside_a_written_store(tree):
    check(tree, {ARRAY: meta({"input": "store.zarr/0"})})
    check(tree, {ARRAY: meta({"url": "https://bucket.s3.amazonaws.com/a.zarr/0"})})


def test_preflight_refuses_arrays_outside_the_written_stores(tree):
    os.makedirs(os.path.join(tree["bids"], "sub-01", "micr", "other", "0"))
    for prefix, msg in (("sub-01/micr/other/0", "outside the written OME-Zarr"), (ZARR, "outside the written OME-Zarr"),
                        (ZARR + "/../../x/0", "outside the output"), ("/" + ARRAY, "outside the output"),
                        (ZARR + "/1", "no metadata in the output")):
        with pytest.raises(ChunkMapError, match=msg):
            check(tree, {prefix: meta({"input": "store.zarr/0"})})


def test_preflight_refuses_sources_that_leave_the_input(tree):
    os.makedirs(os.path.join(tree["root"], "outside"))
    os.symlink(os.path.join(tree["root"], "outside"), os.path.join(tree["input"], "link"))
    for src, msg in (("../outside", "leaves the input"), ("store.zarr/%2e%2e/%2e%2e/outside", "leaves the input"),
                     (os.path.join(tree["root"], "outside"), "leaves the input"), ("link", "symlink"),
                     ("link/0", "symlink"), ("nothere/0", "missing from the input")):
        with pytest.raises(ChunkMapError, match=msg):
            check(tree, {ARRAY: meta({"input": src})})


def test_preflight_refuses_bad_urls_two_sources_and_bad_formats(tree):
    for m in (meta({"url": "http://example.org/a"}), meta({"url": "https://10.0.0.1/a"}),
              meta({"input": "store.zarr/0", "url": "https://example.org/a"}), meta({}),
              meta({"input": "store.zarr/0"}, zarr_format=4), meta({"input": "store.zarr/0"}, separator=":")):
        with pytest.raises(ChunkMapError, match="refusing to upload"):
            check(tree, {ARRAY: m})


def test_preflight_refuses_a_chunk_map_or_symlink_in_the_output(tree):
    write(os.path.join(tree["bids"], "bids.chunks.json"), "{}")
    with pytest.raises(RefusedError, match="chunk maps never leave"):
        preflight(tree["bids"])
    os.remove(os.path.join(tree["bids"], "bids.chunks.json"))
    os.symlink(os.path.join(tree["input"], "store.zarr", "0", "c", "0", "0"), os.path.join(tree["bids"], ARRAY, "c"))
    with pytest.raises(RefusedError, match="symbolic link"):
        check(tree, {ARRAY: meta({"input": "store.zarr/0"})})


# --- opening chunks -----------------------------------------------------------------------------

def test_open_source_reads_input_chunks_and_returns_none_for_missing_ones(tree):
    c = chunks.open_source({"input": "store.zarr/0"}, "c/1/0", input_dir=tree["input"])
    try:
        assert c.size == len("chunk c/1/0") and c.read() == b"chunk c/1/0"
    finally:
        c.close()
    assert chunks.open_source({"input": "store.zarr/0"}, "c/1/1", input_dir=tree["input"]) is None


def test_open_source_takes_chunk_keys_only(tree):
    for bad in ("../x", "zarr.json", "/etc/passwd", "c/../../x", ""):
        with pytest.raises(ChunkMapError):
            chunks.open_source({"input": "store.zarr/0"}, bad, input_dir=tree["input"])


def test_open_source_refuses_a_symlinked_chunk(tree):
    os.makedirs(os.path.join(tree["root"], "outside"))
    write(os.path.join(tree["root"], "outside", "secret"), "secret")
    os.symlink(os.path.join(tree["root"], "outside", "secret"), os.path.join(tree["input"], "store.zarr", "0", "c", "1", "1"))
    with pytest.raises(ChunkMapError, match="symlink"):
        chunks.open_source({"input": "store.zarr/0"}, "c/1/1", input_dir=tree["input"])


def remote(routes):
    """A local server standing in for remote hosts: open_source is given https URLs, the fake
    getter sends them here with the requested host in x-host (the URL rules refuse 127.0.0.1)."""
    import requests
    from urllib.parse import urlsplit

    stub = Stub(lambda req: routes(req["headers"].get("x-host"), req["path"]))
    asked = []

    def get(url, headers):
        u = urlsplit(url)
        assert u.scheme == "https"
        asked.append(u.netloc + u.path)
        return requests.get(stub.base + u.path, headers=dict(headers, **{"x-host": u.netloc}),
                            allow_redirects=False, stream=True)
    return stub, get, asked


def test_remote_404_and_s3_403_are_the_fill_value():
    stub, get, _ = remote(lambda host, p: (200, {}, "abc") if p.endswith("/c/0/0") else
                          (403, {}, "") if p.endswith("/c/0/1") else (404, {}, ""))
    with stub:
        src = {"url": "https://bucket.s3.amazonaws.com/a.zarr/0"}
        c = chunks.open_source(src, "c/0/0", http_get=get)
        assert c.size == 3 and c.read() == b"abc"
        c.close()
        assert chunks.open_source(src, "c/0/1", http_get=get) is None
        assert chunks.open_source(src, "c/1/1", http_get=get) is None


def test_remote_redirects_follow_the_rules():
    def routes(host, p):
        if host == "data.example.org":
            return {"/a.zarr/0/c/0/0": (302, {"Location": "https://evil.example.net/x"}, ""),
                    "/a.zarr/0/c/0/1": (302, {"Location": "/moved/c/0/1"}, ""),
                    "/a.zarr/0/c/1/0": (307, {"Location": "https://bucket.s3.us-east-1.amazonaws.com/a/c/1/0"}, ""),
                    "/a.zarr/0/c/1/1": (302, {"Location": "http://bucket.s3.amazonaws.com/x"}, ""),
                    "/moved/c/0/1": (200, {}, "ok")}.get(p, (500, {}, ""))
        if host == "bucket.s3.us-east-1.amazonaws.com":
            return 200, {}, "s3"
        return 200, {}, "evil"
    stub, get, asked = remote(routes)
    with stub:
        src = {"url": "https://data.example.org/a.zarr/0"}
        for key in ("c/0/0", "c/1/1"):
            with pytest.raises(ChunkMapError, match="redirect to another host refused"):
                chunks.open_source(src, key, http_get=get)
        assert not any(a.startswith("evil") for a in asked)
        assert chunks.open_source(src, "c/0/1", http_get=get).read() == b"ok"
        assert chunks.open_source(src, "c/1/0", http_get=get).read() == b"s3"


def test_remote_chunks_must_be_unencoded_with_a_length():
    stub, get, _ = remote(lambda host, p: (200, {"Content-Encoding": "gzip"}, "zz") if "c/0/0" in p
                          else (500, {}, "") if "c/0/1" in p else (200, {}, "x"))
    with stub:
        src = {"url": "https://data.example.org/a"}
        with pytest.raises(ChunkMapError, match="encoded"):
            chunks.open_source(src, "c/0/0", http_get=get)
        with pytest.raises(ChunkMapError, match="HTTP 500"):
            chunks.open_source(src, "c/0/1", http_get=get)


def test_too_many_redirects_stop():
    stub, get, asked = remote(lambda host, p: (302, {"Location": p + "x"}, ""))
    with stub:
        with pytest.raises(ChunkMapError, match="too many redirects"):
            chunks.open_source({"url": "https://data.example.org/a"}, "c/0/0", http_get=get)
        assert len(asked) == chunks.MAX_REDIRECTS + 1


# --- sizes --------------------------------------------------------------------------------------

def test_streamed_bytes_stats_input_chunks_and_bounds_remote_ones(tree):
    item = {"files": {"data.ome.zarr": os.path.join(tree["bids"], ZARR)}}
    assert chunks.streamed_bytes(cmap(tree, {ARRAY: meta({"input": "store.zarr/0"})}), [item]) == (33, False, 1)
    assert chunks.streamed_bytes(cmap(tree, {ARRAY: meta({"url": "https://example.org/a"})}), [item]) == (64, True, 1)
    assert chunks.streamed_bytes(None, [item]) == (0, False, 0)
    other = {"files": {"t1.nii.gz": os.path.join(tree["bids"], "sub-01", "anat", "x.nii.gz")}}
    assert chunks.streamed_bytes(cmap(tree, {ARRAY: meta({"input": "store.zarr/0"})}), [other]) == (0, False, 0)

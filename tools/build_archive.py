"""Assemble a docker-load image archive without a local Docker daemon.

Downloads digest-verified official Python layers. Adds only app files and config;
no Linux program is executed. This is image packaging, not a container smoke test.
Format: https://github.com/moby/docker-image-spec/blob/main/spec.md
"""
import argparse
import copy
import gzip
import hashlib
import io
import json
import tarfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_INDEX = "sha256:4840d514c583a4d3d8cad3940e68dee6f0f6f3635c12fcd0a3d74c21a5b93a54"
REGISTRY = "https://registry-1.docker.io/v2/library/python/"
ACCEPT = ", ".join(["application/vnd.oci.image.index.v1+json", "application/vnd.oci.image.manifest.v1+json", "application/vnd.docker.distribution.manifest.list.v2+json", "application/vnd.docker.distribution.manifest.v2+json"])


def sha(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def tar_bytes(archive, name, data, mode=0o644, uid=0):
    member = tarfile.TarInfo(name)
    member.size, member.mode, member.uid, member.gid, member.mtime = len(data), mode, uid, uid, 0
    archive.addfile(member, io.BytesIO(data))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", choices=("amd64", "arm64"), default="amd64")
    parser.add_argument("--tag", default="pocket-lab:1.0.0")
    args = parser.parse_args()
    cache, dist = ROOT / ".image-cache", ROOT / "dist"
    cache.mkdir(exist_ok=True)
    dist.mkdir(exist_ok=True)
    with urllib.request.urlopen("https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/python:pull", timeout=30) as response:
        token = json.load(response)["token"]

    def get(kind, digest):
        path = cache / digest.split(":")[1]
        if path.exists() and sha_file(path) == digest:
            return path
        request = urllib.request.Request(REGISTRY + kind + "/" + digest, headers={"Authorization": "Bearer " + token, "Accept": ACCEPT})
        for attempt in range(3):
            try:
                print(f"Downloading {kind} {digest[:23]}…", flush=True)
                with urllib.request.urlopen(request, timeout=45) as response, path.open("wb") as output:
                    for block in iter(lambda: response.read(1024 * 1024), b""):
                        output.write(block)
                if sha_file(path) != digest:
                    raise ValueError("Registry digest mismatch")
                return path
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(1)

    index = json.loads(get("manifests", BASE_INDEX).read_bytes())
    platform = next(x for x in index["manifests"] if x.get("platform", {}).get("architecture") == args.arch and x["platform"].get("os") == "linux")
    manifest = json.loads(get("manifests", platform["digest"]).read_bytes())
    config = json.loads(get("blobs", manifest["config"]["digest"]).read_bytes())
    layer_files = []
    for descriptor, expected_diff in zip(manifest["layers"], config["rootfs"]["diff_ids"]):
        blob = get("blobs", descriptor["digest"])
        layer_path = cache / (expected_diff.split(":")[1] + ".tar")
        if not layer_path.exists() or sha_file(layer_path) != expected_diff:
            with gzip.open(blob, "rb") as source, layer_path.open("wb") as target:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    target.write(block)
            if sha_file(layer_path) != expected_diff:
                raise ValueError("Layer DiffID mismatch")
        layer_files.append((expected_diff, layer_path))
    if len(layer_files) != len(manifest["layers"]):
        raise ValueError("Base layer metadata length mismatch")

    app_layer = cache / "pocket-app-layer.tar"
    source_hashes = {}
    with tarfile.open(app_layer, "w", format=tarfile.PAX_FORMAT) as archive:
        for directory in ("app", "data"):
            member = tarfile.TarInfo(directory)
            member.type, member.mode, member.uid, member.gid, member.mtime = tarfile.DIRTYPE, 0o755, 10001, 10001, 0
            archive.addfile(member)
        for path in sorted((ROOT / "app").rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            relative = path.relative_to(ROOT).as_posix()
            data = path.read_bytes()
            tar_bytes(archive, relative, data, uid=10001)
            source_hashes[relative] = sha(data)
        tar_bytes(archive, "data/.keep", b"", uid=10001)
    diff = sha_file(app_layer)
    layer_files.append((diff, app_layer))
    config = copy.deepcopy(config)
    config["created"] = datetime.now(timezone.utc).isoformat()
    config["rootfs"]["diff_ids"].append(diff)
    run = config["config"]
    new_env = {"PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1", "LAB_HOST": "0.0.0.0", "LAB_PORT": "8080", "LAB_INTERNAL_PORT": "9091", "LAB_DATA_DIR": "/data"}
    run["Env"] = [e for e in run.get("Env", []) if e.split("=", 1)[0] not in new_env] + [f"{k}={v}" for k, v in new_env.items()]
    run.update(User="10001:10001", WorkingDir="/app", Entrypoint=None, Cmd=["python", "/app/app.py"], ExposedPorts={"8080/tcp": {}}, Healthcheck={"Test": ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=3).read()"], "Interval": 15000000000, "Timeout": 4000000000, "StartPeriod": 8000000000, "Retries": 3})
    run["Labels"] = {**run.get("Labels", {}), "org.opencontainers.image.title": "Pocket Lab", "org.opencontainers.image.source": "https://github.com/zpx159847/zpx-", "org.opencontainers.image.version": "1.0.0", "org.opencontainers.image.licenses": "MIT"}
    config.setdefault("history", []).append({"created": config["created"], "created_by": "Pocket Lab archive packager: COPY app and data; set Dockerfile runtime configuration"})
    raw_config = json_bytes(config)
    config_name = sha(raw_config).split(":")[1] + ".json"
    output = dist / f"pocket-lab-1.0.0-linux-{args.arch}.tar.gz"
    saved_manifest = [{"Config": config_name, "RepoTags": [args.tag], "Layers": [digest.split(":")[1] + "/layer.tar" for digest, _ in layer_files]}]
    with tarfile.open(output, "w:gz", compresslevel=6) as archive:
        tar_bytes(archive, config_name, raw_config)
        tar_bytes(archive, "manifest.json", json_bytes(saved_manifest))
        for (digest, path), member_name in zip(layer_files, saved_manifest[0]["Layers"]):
            member = tarfile.TarInfo(member_name)
            member.size, member.mode, member.mtime = path.stat().st_size, 0o644, 0
            with path.open("rb") as stream:
                archive.addfile(member, stream)
    # Read archive back and verify exactly what docker load will see.
    with tarfile.open(output) as archive:
        saved = json.load(archive.extractfile("manifest.json"))[0]
        read_config = archive.extractfile(saved["Config"]).read()
        assert sha(read_config).split(":")[1] + ".json" == saved["Config"]
        parsed = json.loads(read_config)
        for name, expected in zip(saved["Layers"], parsed["rootfs"]["diff_ids"]):
            digest = hashlib.sha256()
            with archive.extractfile(name) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            assert "sha256:" + digest.hexdigest() == expected
    report = {"archive": output.name, "size_bytes": output.stat().st_size, "sha256": sha_file(output), "image_id": sha(raw_config), "platform": "linux/" + args.arch, "tag": args.tag, "base_index": BASE_INDEX, "base_manifest": platform["digest"], "layers_verified": len(layer_files), "source_hashes": source_hashes, "container_runtime_tested": False, "note": "Digest/layer/config/source verification passed. No Docker daemon is installed on the packaging host."}
    (dist / "image-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (dist / "SHA256SUMS.txt").write_text(f"{report['sha256'].split(':')[1]}  {output.name}\n", encoding="ascii")
    print(json.dumps({k: v for k, v in report.items() if k != "source_hashes"}, indent=2), flush=True)


if __name__ == "__main__":
    main()

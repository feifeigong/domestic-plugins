import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]


def verify_plugin(profile):
    source = ROOT / "plugins" / "china-email"
    plugin = profile / "本地 邮箱"
    shutil.copytree(source, plugin)
    settings = profile / ".china-email" / "accounts.json"
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(("CHINA_EMAIL_", "PYTHON")):
            env.pop(key)
    env["USERPROFILE"] = str(profile)
    system_root = Path(os.environ["SystemRoot"])
    env["PATH"] = os.pathsep.join([str(system_root / "System32"), str(system_root)])
    assert not any(shutil.which(command, path=env["PATH"]) for command in ("py.exe", "python.exe", "python3.exe"))

    launcher = plugin / "bin" / "china-email.cmd"
    with subprocess.Popen(
        [str(launcher)], cwd=plugin, env=env, stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, text=True, encoding="utf-8",
    ) as process:
        def rpc(method, params=None):
            request = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
            process.stdin.write(json.dumps(request) + "\n")
            process.stdin.flush()
            response = json.loads(process.stdout.readline())
            assert "error" not in response, response
            return response["result"]

        def tool(name, arguments=None):
            result = rpc("tools/call", {"name": name, "arguments": arguments or {}})
            assert not result.get("isError"), result
            return result["structuredContent"]

        try:
            initialization = rpc("initialize", {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "bundled-runtime-check", "version": "1"},
            })
            assert initialization["serverInfo"]["version"] == "0.2.5"
            names = {entry["name"] for entry in rpc("tools/list")["tools"]}
            assert len(names) == 10 and "china_email_start_setup" in names
            assert tool("china_email_list_accounts")["accounts"] == []

            wizard = tool("china_email_start_setup", {"provider": "163", "open_browser": False})
            assert Path(wizard["config_path"]).resolve() == settings.resolve()
            origin, token = wizard["url"].split("/?token=")
            http = build_opener(ProxyHandler({}))
            with http.open(wizard["url"], timeout=10) as response:
                page = response.read()
            assert b'action="/save"' in page and b'name="password"' in page
            form = urlencode({
                "token": token, "provider": "163", "name": "release-test",
                "email": "release-test@example.invalid", "password": "test-only",
            }).encode("ascii")
            with http.open(Request(origin + "/save", data=form), timeout=10) as response:
                assert response.status == 200
            assert [entry["name"] for entry in tool("china_email_list_accounts")["accounts"]] == ["release-test"]
        finally:
            process.stdin.close()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                raise


if __name__ == "__main__":
    with TemporaryDirectory(prefix="china-email-windows-") as directory:
        verify_plugin(Path(directory))
    print("Bundled Windows runtime loaded 10 MCP tools, served the setup form, and saved a synthetic account without system Python.")

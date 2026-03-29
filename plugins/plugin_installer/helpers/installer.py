import os
import tempfile
import zipfile
import shutil
from helpers import files
from helpers.print_style import PrintStyle


def install_from_zip(zip_path: str) -> str:
    """Extract a ZIP file into usr/plugins/ and return the plugin name."""
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp)

        entries = os.listdir(tmp)
        if len(entries) == 1 and os.path.isdir(os.path.join(tmp, entries[0])):
            plugin_dir = os.path.join(tmp, entries[0])
            plugin_name = entries[0]
        else:
            plugin_name = os.path.splitext(os.path.basename(zip_path))[0]
            plugin_dir = tmp

        meta_file = os.path.join(plugin_dir, "plugin.yaml")
        if not os.path.exists(meta_file):
            raise ValueError(f"No plugin.yaml found in {zip_path}")

        dest = files.get_abs_path(files.USER_DIR, files.PLUGINS_DIR, plugin_name)
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.copytree(plugin_dir, dest)

        PrintStyle.success(f"Plugin '{plugin_name}' installed to {dest}")
        return plugin_name


def install_from_git(repo_url: str, branch: str = "main") -> str:
    """Clone a git repo into usr/plugins/."""
    import subprocess

    plugin_name = repo_url.rstrip("/").split("/")[-1].removesuffix(".git")
    dest = files.get_abs_path(files.USER_DIR, files.PLUGINS_DIR, plugin_name)

    if os.path.exists(dest):
        shutil.rmtree(dest)

    subprocess.run(
        ["git", "clone", "--depth=1", "--branch", branch, repo_url, dest],
        check=True,
        capture_output=True,
    )

    meta_file = os.path.join(dest, "plugin.yaml")
    if not os.path.exists(meta_file):
        shutil.rmtree(dest)
        raise ValueError(f"No plugin.yaml in cloned repo {repo_url}")

    PrintStyle.success(f"Plugin '{plugin_name}' installed from {repo_url}")
    return plugin_name

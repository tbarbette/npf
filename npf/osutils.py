import os
from pathlib import Path
import re
import sys

from npf.globals import experiment_path, get_options
from npf.globals import npf_root_path
from typing import List


def ensure_folder_exists(filename):
    savedir = Path(os.path.dirname(filename))
    if not savedir.exists():
        os.makedirs(savedir.as_posix())

    if not os.path.isabs(filename):
        filename = os.getcwd() + os.sep + filename
    return filename


def get_valid_filename(s):
    s = str(s).strip().replace(' ', '_')
    return re.sub(r'(?u)[^-\w.]', '', s)


def find_local(path, critical: bool = False, suppl: List = None):
    if os.path.exists(path):
        return path

    searched = [npf_root_path(), '.', experiment_path()] + list(get_options().search_path) + (suppl if suppl else [])
    for a in searched:
        p = a + os.sep + path
        if os.path.exists(p):
            return p
    if critical:
        raise FileNotFoundError("Could not find file %s, locations searched :\n%s" %
                (path,
                    "\n".join(searched)))
    return path

def git_sources(path):
    """The files that git tracks in the work tree at path, with their local changes, and those of the submodules: what
    a node needs to build the software itself (--remote-build). The untracked files are left out, even when git does
    not ignore them: often, they are build products that the .gitignore misses (installed libraries, test binaries).
    A new source file must be added to git (git add -N is enough). Absolute paths, or None if path is not a git work
    tree."""
    import subprocess
    if not os.path.exists(os.path.join(path, ".git")):
        return None
    try:
        p = subprocess.run(["git", "-C", path, "ls-files", "-z", "--cached", "--recurse-submodules"],
                           capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if p.returncode != 0:
        return None
    return {os.path.abspath(os.path.join(path, f)) for f in p.stdout.decode(errors="surrogateescape").split("\0") if f}

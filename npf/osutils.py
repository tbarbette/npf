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
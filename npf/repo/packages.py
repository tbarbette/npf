"""System packages that a repository needs, from the packages= line of its .repo file.

NPF checks them on the node that builds the repository, and installs the missing ones with --install-packages.
A name can be prefixed with deb: or rpm: when it differs between Debian-based and Red Hat-based systems, e.g.
packages=deb:libdumbnet-dev,rpm:libdnet-devel. With method=package, the repository is the package itself."""
import re
import shlex
import subprocess

FAMILIES = ("deb", "rpm")


def parse(value):
    """:return: the packages of each family, e.g. "a,deb:b rpm:c" gives {"deb": ["a", "b"], "rpm": ["a", "c"]}"""
    packages = {family: [] for family in FAMILIES}
    for p in re.split(r"[,\s]+", value or ""):
        if not p:
            continue
        family, _, name = p.rpartition(":")
        if family and family not in FAMILIES:
            raise Exception("Unknown kind of package %s in packages=%s: use deb: or rpm:" % (p, value))
        for f in ([family] if family else FAMILIES):
            packages[f].append(name)
    return packages


def check_command(packages):
    """A shell command printing the family of the system (deb, rpm or unknown), then its missing packages"""
    names = {f: " ".join(shlex.quote(p) for p in packages[f]) for f in FAMILIES}
    return ("if command -v dpkg-query >/dev/null 2>&1; then echo deb; for p in %s; do "
            "dpkg-query -W -f='${Status}' \"$p\" 2>/dev/null | grep -q ' installed$' || echo \"$p\"; done; "
            "elif command -v rpm >/dev/null 2>&1; then echo rpm; for p in %s; do "
            "rpm -q \"$p\" >/dev/null 2>&1 || echo \"$p\"; done; "
            "else echo unknown; fi") % (names["deb"], names["rpm"])


def install_command(family, missing):
    names = " ".join(shlex.quote(p) for p in missing)
    if family == "deb":
        return "sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install -y " + names
    return "sudo -n $(command -v dnf || command -v yum) install -y " + names


def _run(cmd, node=None, timeout=60):
    """:return: the output of cmd on node (locally if None), and whether it succeeded"""
    if node is not None:
        _, out, err, ret = node.executor.exec(cmd=cmd, timeout=timeout)
        return out + err, ret == 0
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "Timeout after %d s" % timeout, False
    return p.stdout + p.stderr, p.returncode == 0


def ensure(repo, options, node=None, required=False):
    """Checks that the packages of repo are installed on node (locally if None), and installs the missing ones with
    --install-packages. A package can be missing for the package manager but installed from source: unless required
    (method=package), a missing package is only a warning.
    :return: False if the build cannot go on"""
    if not getattr(repo, "packages", None):
        return True
    where = node.get_name() if node is not None else "localhost"
    out, _ = _run(check_command(parse(repo.packages)), node)
    lines = out.split()
    family = lines[0] if lines else "unknown"
    if family not in FAMILIES:
        print("Warning: cannot check the packages %s of %s on %s, which has neither dpkg nor rpm" %
              (repo.packages, repo.reponame, where))
        return not required
    missing = lines[1:]
    if not missing:
        return True
    install = install_command(family, missing)
    if getattr(options, "install_packages", False):
        print("Installing %s on %s for %s..." % (" ".join(missing), where, repo.reponame))
        out, ok = _run(install, node, timeout=900)
        if ok:
            return True
        print("Could not install them:\n" + out.strip())
        return not required
    print("%s: %s needs the packages %s, which %s does not have. Install them with:\n    %s\nor run NPF with "
          "--install-packages." % ("ERROR" if required else "Warning", repo.reponame, " ".join(missing), where, install))
    return not required

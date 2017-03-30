All repositories are defined in the repo folder. A repo configuration define how
to fetch and install a specific program, using one of the following ways :

  * **git** : Use git to download and compile a branch or specific commit
  * **get** : Download a file and compile/install it if needed
  * **package** : Use the OS package manager (only Red-Hat and Debian based supported for now) (TODO : Still not implemented)

The git method supports the "history" parameter, allowing to go back
in commit history to rebuild the history with older versions (commits).
get and package have a hardcoded version in the repo file.

The default method is git.

When giving a repo name to any tool, the version can be overriden by
suffixing a "-version" to the repo name, eg (TODO) :
```bash
    python3 npf-run.py iperf-3.1.3
```

See the repo folder for examples. Repo can inherit others, as there is only one
configure/make line per repo, you can inherit a repo with a specific
configuration and avoid repeating all other parameters. See click/fastclick/fastclick-nobatch.

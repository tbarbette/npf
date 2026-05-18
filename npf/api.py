import re
from typing import Dict, Iterable, List


def _is_enoslib_host(obj) -> bool:
    try:
        import enoslib as en
        return isinstance(obj, en.Host)
    except ImportError:
        return False


def run(npf_script: str, series: List[str] = [], roles: Dict = {},
        argsv: List[str] = None, extra_vars: Dict[str, str] = {}) -> tuple:
    """Run an NPF test script.

    Args:
        npf_script: Path to the .npf file.
        series:     List of repo strings (same as CLI positional repo arguments).
        roles:      Dict mapping role names to one of:
                      - enoslib Host object (or list)  → ansible/enoslib execution
                      - str "user@hostname:path"        → SSH execution
                      - NPF Node object                 → used as-is
                    Omit or leave empty for local-only execution.
        argsv:      Extra CLI arguments as a list (e.g. ["--no-graph", "--cache"]).
        extra_vars: Ansible extra_vars forwarded to EnoslibExecutor (enoslib path only).

    Returns:
        (series_results, time_series) tuple from the comparator run.
    """
    import logging
    import argparse
    import npf.cmdline as _cmdline
    import npf.globals as _globals
    import npf.parsing as _parsing
    from npf.cluster.node import Node
    from npf.repo.repository import Repository
    from npf.repo.factory import get_default_repository
    from npf.output import generate_outputs
    from npf.tests.test_driver import Comparator
    from npf import build_output_filename

    if argsv is None:
        argsv = []
    logging.getLogger('fontTools.subset').level = logging.WARN

    parser = argparse.ArgumentParser(description='NPF Test runner')
    _cmdline.add_verbosity_options(parser)
    _cmdline.add_building_options(parser)
    _cmdline.add_testing_options(parser, regression=False)
    _cmdline.add_graph_options(parser)
    parser.add_argument('repos', metavar='repo', type=str, nargs='*',
                        help='Repositories to compare. '
                             'Use repo+VAR=VAL:Title to overwrite variables and series names.')
    parser.add_argument('--graph-title', type=str, nargs='?', help='Graph title')

    args = parser.parse_args(["--test", npf_script, *argsv])
    args.repos.extend(series)

    _parsing.initialize(args)

    # Clear stale roles from previous calls (important in Jupyter where cells run multiple times)
    _globals.roles.clear()

    _parsing.create_local()

    for r, role_objs in roles.items():
        if isinstance(role_objs, str) or not isinstance(role_objs, Iterable):
            role_objs = [role_objs]
        for role_obj in role_objs:
            if _is_enoslib_host(role_obj):
                from npf.executor.enoslibexecutor import EnoslibExecutor
                ex = EnoslibExecutor(role_obj, extra_vars=extra_vars)
                node = Node(role_obj.address, executor=ex, tags=args.tags)
                # Make ${role:ip} and ${role:addr} work for inter-node communication
                node.ip = role_obj.address
                node.addr = role_obj.address
            elif isinstance(role_obj, Node):
                node = role_obj
            elif isinstance(role_obj, str):
                m = re.match(
                    r'(?:(?P<user>[^@]+)@)?(?P<addr>[^:]+)(?::(?P<path>.+))?',
                    role_obj)
                user = m.group('user')
                addr = m.group('addr')
                path = m.group('path')
                if addr == 'localhost':
                    node = Node.makeLocal()
                else:
                    node = Node.makeSSH(user=user, addr=addr, path=path)
            else:
                raise ValueError(
                    f"Unsupported role value type {type(role_obj)!r} for role {r!r}. "
                    "Expected an enoslib Host, a 'user@hostname:path' string, or an NPF Node.")

            if r in _globals.roles:
                _globals.roles[r].append(node)
            else:
                _globals.roles[r] = [node]

    repo_list = []
    for repo_name in args.repos:
        repo = Repository.get_instance(repo_name, args)
        repo_list.append(repo)
    if not repo_list:
        repo = get_default_repository(args)
        repo_list.append(repo)

    comparator = Comparator(repo_list)
    results, time_series = comparator.run(
        test_name=args.test_files,
        tags=args.tags,
        options=args,
        do_regress=False,
    )

    filename = build_output_filename(repo_list)
    generate_outputs(filename, series=results, time_series=time_series, options=args)

    return results, time_series

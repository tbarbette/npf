import argparse


from src.variable import *
from src.script import *
from src.regression import *
from src.repository import *

def main():
    parser = argparse.ArgumentParser(description='Click Performance Executor')
    parser.add_argument('--show-full', help='Show full execution results', dest='show_full', action='store_true')

    parser.add_argument('--quiet', help='Quiet mode', dest='quiet', action='store_true')
    parser.add_argument('script', metavar='script', type=str, nargs=1, help='path to script');
    parser.add_argument('repo', metavar='repo', type=str, nargs=1, help='name of the repo/group of builds');
    parser.add_argument('uuid', metavar='uuid', type=str, nargs=1, help='build id');
    parser.add_argument('old_uuids', metavar='old_uuids', type=str, nargs='*', help='old build id to compare against');
    parser.set_defaults(show_full=False)
    parser.set_defaults(quiet=False)
    args = parser.parse_args();

    repo=Repository(args.repo[0])
    uuid=args.uuid[0]
    clickpath=repo.reponame+"/build"
    old_uuids=args.old_uuids

    script = Script(args.script[0],repo,clickpath,quiet=args.quiet)

    regression = Regression(script,show_full=args.show_full)

    print script.info.content.strip()

    returncode = regression.run(uuid, old_uuids);
    sys.exit(returncode)


if __name__ == "__main__":
    main()


import os
from npf.tests.repository import Repository
from npf.tests.test import Test


def get_default_repository(args):
    if os.path.exists(args.test_files) and os.path.isfile(args.test_files):
        tmptest = Test(args.test_files,options=args)
        if "default_repo" in tmptest.config and tmptest.config["default_repo"] is not None:
            repo = Repository.get_instance(tmptest.config["default_repo"], args)
            return repo
        else:
            print("This npf experiment script has no default repository.")
    else:
            print("Please specify a repository to use in the command line or only a single experiment with a default_repo.")
    #    sys.exit(1)
    print(f"Using 'local' repository which will not track version of the software under test. To avoid this message, explicitely define a repository or use the 'local' keyword with a command line like {sys.argv[0]} 'local:My serie' {sys.argv[1] or ''}... ")
    return Repository.get_instance("local")
import os
import sys

options = None
cwd = None
roles = {}

def experiment_path(options = None):
    # Return the path to NPF experiment folder
    if options is None:
        options = sys.modules[__name__].options
    return os.path.join(options.experiment_folder, '')


def npf_root_path():
    # Return the path to NPF root
    return os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


def cwd_path(options=None):
    # Return the path to where NPF was first executed
    if options is None:
        options = sys.modules[__name__].options
    return options.cwd


def get_build_path(options = None):
    if options is None:
        options = sys.modules[__name__].options
    assert(options._build_path)
    return options._build_path


def set_args(args):
    sys.modules[__name__].options = args
    args.cwd = os.getcwd()


def get_options():
    return options
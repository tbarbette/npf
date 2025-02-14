import os

from npf.globals import experiment_path, npf_root_path, get_options
from npf.osutils import get_valid_filename

def npf_writeable_root_path():
    path = npf_root_path()
    if not os.access(path, os.W_OK):
        return experiment_path()
    else:
        return path

def from_experiment_path(path):
    # Returns the path under NPF root if it is not absolute
    if (os.path.isabs(path)):
        return path
    else:
        return (experiment_path() if os.path.isabs(experiment_path()) else os.path.abspath(experiment_path())) + os.sep + path

def splitpath(hint):
    if hint is None:
        hint = "results"
    dirname, c_filename = os.path.split(hint)
    if c_filename == '':
        basename = ''
        ext = ''
    else:
        basename, ext = os.path.splitext(c_filename)
        if not ext and basename.startswith('.'):
            ext = basename
            basename = ''
    return dirname, basename, ext

def build_filename(test, build, hint, variables, def_ext, type_str='', show_serie=False, suffix='', force_ext = False, data_folder = False, prefix=None):
    var_str = get_valid_filename('_'.join(
        ["%s=%s" % (k, (val[1] if type(val) is tuple else val)) for k, val in sorted(variables.items()) if val]))

    if hint is None:
        if data_folder:
            path = build.result_path(test.filename, def_ext, folder = var_str + (('-' if var_str else '') + type_str if type_str else ''), prefix=prefix, suffix = ('-' + suffix if suffix else '') + ('-' + get_valid_filename(build.pretty_name()) if show_serie else ''))
        else:
            path = build.result_path(test.filename, def_ext, suffix=('-' + suffix if suffix else '') + var_str + ('-' + type_str if type_str else '') + ('-' + get_valid_filename(build.pretty_name()) if show_serie else '') , prefix=prefix)
    else:
        dirname, basename, ext = splitpath(hint)

        if ext is None or ext == '' or force_ext:
            ext = '.' + def_ext

        if basename is None or basename == '':
            basename = var_str

        if not data_folder:
            if prefix:
                basename = prefix + basename

            if not dirname or show_serie:
                basename = (get_valid_filename(build.pretty_name()) if show_serie else '') + basename
            path = (dirname + '/' if dirname else '') + basename + (
        ('-' if basename else '') + type_str if type_str else '') + ('' if not suffix else ("-" + suffix)) + ext
        else:
            if not dirname or show_serie:
                dirname = (dirname + "/" if dirname else '') + basename
            path = (dirname + '/' if dirname else '') + (prefix if prefix else '') + (get_valid_filename(build.pretty_name()) if show_serie else '') + (type_str if type_str else '') + ('' if not suffix else ("-" + suffix)) + ext

    folder = os.path.dirname(path)
    if folder and not os.path.exists(folder):
        os.makedirs(folder)
    return path


def build_output_filename(repo_list):
    return get_options().graph_filename or (
        (
            f'compare/{os.path.splitext(os.path.basename(get_options().test_files))[0]}_'
            + '_'.join([f"{repo.reponame}" for repo in repo_list])
        )
        + '.pdf'
    )

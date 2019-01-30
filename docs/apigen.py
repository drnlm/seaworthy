# -*- coding: utf-8 -*-
"""
    apigen
    ~~~~~~

    This is a hacked up and heavily modified copy of sphinx.apidoc, which is
    copyright the Sphinx team.

    Unfortunately, sphinx.apidoc hardcodes most of its output and has an
    opinionated output structure that doesn't match our needs.

    We use a similar mechanism to collect the modules we want to autodocument
    and then we build a single autosummary directive and rely on autosummary
    (with a custom template) to generate the autodoc stubs.
"""
from __future__ import print_function

import optparse
import os
import shutil
import sys
from fnmatch import fnmatch
from os import path
from typing import Dict

from sphinx import __display_version__
from sphinx.application import Sphinx
from sphinx.cmd.quickstart import EXTENSIONS
from sphinx.util import logging
from sphinx.util.osutil import FileAvoidWrite, walk

if sys.version_info[0] >= 3:
    unicode = str

if False:
    # For type annotation
    from typing import Any, List, Tuple  # NOQA

logger = logging.getLogger(__name__)


BASEDIR = path.dirname(__file__)


INITPY = '__init__.py'
PY_SUFFIXES = set(['.py', '.pyx'])


def makename(package, module):
    # type: (unicode, unicode) -> unicode
    """Join package and module with a dot."""
    # Both package and module can be None/empty.
    if package:
        name = package
        if module:
            name += '.' + module
    else:
        name = module
    return name


def create_autosummary_file(modules, opts):
    # type: (List[unicode], Any, unicode) -> None
    """Create the module's index."""
    lines = [
        'API Reference',
        '=============',
        '',
        '.. autosummary::',
        '   :template: api_module.rst',
        '   :toctree: {}'.format(opts.destdir),
        '',
    ]

    modules.sort()
    for module in modules:
        lines.append('   {}'.format(module))
    lines.append('')

    fname = path.join(opts.srcdir, '{}.rst'.format(opts.docname))
    logger.info('[apigen] creating API docs file: {}'.format(fname))
    with FileAvoidWrite(fname) as f:
        f.write('\n'.join(lines))


def shall_skip(module, opts):
    # type: (unicode, Any) -> bool
    """Check if we want to skip this module."""
    # skip if the file doesn't exist and not using implicit namespaces
    if not opts.implicit_namespaces and not path.exists(module):
        return True

    # skip it if there is nothing (or just \n or \r\n) in the file
    if path.exists(module) and path.getsize(module) <= 2:
        return True

    # skip if it has a "private" name and this is selected
    filename = path.basename(module)
    if filename != '__init__.py' and filename.startswith('_') and \
       not opts.includeprivate:
        return True
    return False


def recurse_tree(rootpath, excludes, opts):
    # type: (unicode, List[unicode], Any) -> List[unicode]
    """
    Look for every file in the directory tree and create the corresponding
    ReST files.
    """
    if INITPY in os.listdir(rootpath):
        path_prefix = path.sep.join(rootpath.split(path.sep)[:-1])
    else:
        path_prefix = rootpath

    toplevels = []
    followlinks = getattr(opts, 'followlinks', False)
    includeprivate = getattr(opts, 'includeprivate', False)
    implicit_namespaces = getattr(opts, 'implicit_namespaces', False)
    for root, subs, files in walk(rootpath, followlinks=followlinks):
        # document only Python module files (that aren't excluded)
        py_files = sorted(f for f in files
                          if path.splitext(f)[1] in PY_SUFFIXES and
                          not is_excluded(path.join(root, f), excludes))
        is_pkg = INITPY in py_files
        if is_pkg:
            py_files.remove(INITPY)
            py_files.insert(0, INITPY)
        elif root != rootpath:
            # only accept non-package at toplevel unless using implicit
            # namespaces
            if not implicit_namespaces:
                del subs[:]
                continue
        # remove hidden ('.') and private ('_') directories, as well as
        # excluded dirs
        if includeprivate:
            exclude_prefixes = ('.',)  # type: Tuple[unicode, ...]
        else:
            exclude_prefixes = ('.', '_')
        subs[:] = sorted(sub for sub in subs
                         if not sub.startswith(exclude_prefixes) and
                         not is_excluded(path.join(root, sub), excludes))

        pkg = root[len(path_prefix):].lstrip(path.sep).replace(path.sep, '.')
        for py_file in py_files:
            if not shall_skip(path.join(root, py_file), opts):
                if py_file == INITPY:
                    module = ''
                else:
                    module = path.splitext(py_file)[0]
                toplevels.append(makename(pkg, module))

    return toplevels


def normalize_excludes(rootpath, excludes):
    # type: (unicode, List[unicode]) -> List[unicode]
    """Normalize the excluded directory list."""
    return [path.join(rootpath, exclude) for exclude in excludes]


def is_excluded(root, excludes):
    # type: (unicode, List[unicode]) -> bool
    """Check if the directory is in the exclude list.

    Note: by having trailing slashes, we avoid common prefix issues, like
          e.g. an exlude "foo" also accidentally excluding "foobar".
    """
    for exclude in excludes:
        if fnmatch(root, exclude):
            return True
    return False


def main(argv=sys.argv):
    # type: (List[str]) -> int
    """Parse and check the command line arguments."""
    parser = optparse.OptionParser(
        usage="""\
usage: %prog [options] -o <output_path> <module_path> [exclude_pattern, ...]

Look recursively in <module_path> for Python modules and packages and create
one reST file with automodule directives per package in the <output_path>.

The <exclude_pattern>s can be file and/or directory patterns that will be
excluded from generation.

Note: By default this script will not overwrite already created files.""")

    parser.add_option('-o', '--output-dir', action='store', dest='destdir',
                      help='Directory to place all output', default='api')
    parser.add_option('-s', '--source-dir', action='store', dest='srcdir',
                      help='Documentation source directory', default=BASEDIR)
    parser.add_option('-n', '--docname', action='store', dest='docname',
                      help='Index document name', default='api')
    parser.add_option('-l', '--follow-links', action='store_true',
                      dest='followlinks', default=False,
                      help='Follow symbolic links. Powerful when combined '
                      'with collective.recipe.omelette.')
    parser.add_option('-P', '--private', action='store_true',
                      dest='includeprivate',
                      help='Include "_private" modules')
    parser.add_option('--implicit-namespaces', action='store_true',
                      dest='implicit_namespaces',
                      help='Interpret module paths according to PEP-0420 '
                           'implicit namespaces specification')
    parser.add_option('--version', action='store_true', dest='show_version',
                      help='Show version information and exit')
    parser.add_option('--clean', action='store_true', dest='cleanup',
                      help='Clean up generated files and exit')
    group = parser.add_option_group('Extension options')
    for ext in EXTENSIONS:
        group.add_option('--ext-' + ext, action='store_true',
                         dest='ext_' + ext, default=False,
                         help='enable %s extension' % ext)

    (opts, args) = parser.parse_args(argv[1:])

    # Make this more explicitly the current directory.
    if not opts.srcdir:
        opts.srcdir = '.'

    if opts.show_version:
        print('Sphinx (sphinx-apidoc) %s' % __display_version__)
        return 0

    if opts.cleanup:
        print("Removing generated API docs from '{}'...".format(opts.srcdir))
        return cleanup_api_docs(opts)

    if not args:
        parser.error('A package path is required.')

    opts.rootpath, opts.excludes = args[0], args[1:]
    return generate_api_docs(opts)


def generate_api_docs(opts):
    if not path.isdir(opts.rootpath):
        logger.warning('{} is not a directory. Skipped.'.format(opts.rootpath))
        return 1
    destdir = path.join(opts.srcdir, opts.destdir)
    if not path.isdir(destdir):
        os.makedirs(destdir)
    rootpath = path.abspath(opts.rootpath)
    excludes = normalize_excludes(rootpath, opts.excludes)
    modules = recurse_tree(rootpath, excludes, opts)
    create_autosummary_file(modules, opts)
    return 0


def cleanup_api_docs(opts):
    destdir = path.join(opts.srcdir, opts.destdir)
    if path.exists(destdir):
        shutil.rmtree(destdir)
    fname = path.join(opts.srcdir, '{}.rst'.format(opts.docname))
    if path.exists(fname):
        os.remove(fname)
    return 0


def process_apigen(app):
    generate_api_docs(Opts(app))


class Opts:
    def __init__(self, app):
        self._app = app

    def __getattr__(self, name):
        return getattr(self._app.config, 'apigen_{}'.format(name))

    @property
    def srcdir(self):
        return self._app.srcdir


def setup(app):
    # type: (Sphinx) -> Dict[unicode, Any]
    app.connect('builder-inited', process_apigen)
    app.add_config_value('apigen_docname', 'api', True)
    app.add_config_value('apigen_destdir', 'api', True)
    app.add_config_value('apigen_rootpath', None, True)
    app.add_config_value('apigen_excludes', [], True)
    app.add_config_value('apigen_followlinks', False, True)
    app.add_config_value('apigen_includeprivate', False, True)
    app.add_config_value('apigen_implicit_namespaces', False, True)
    return {'version': '0.1', 'parallel_read_safe': True}


if __name__ == "__main__":
    main()

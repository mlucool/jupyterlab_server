# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
# import os
# import sys
# sys.path.insert(0, os.path.abspath('.'))
import os.path as osp
import shutil

HERE = osp.abspath(osp.dirname(__file__))

# -- Project information -----------------------------------------------------

project = 'JupyterLab Server'
copyright = '2021, Project Jupyter'
author = 'Project Jupyter'

# The full version, including alpha/beta/rc tags
_version_py = osp.join(HERE, '..', '..', 'jupyterlab_server', '_version.py')
version_ns = {}

with open(_version_py, mode='r') as version_file:
    exec(version_file.read(), version_ns)

# The short X.Y version.
version = '%i.%i' % version_ns['version_info'][:2]
# The full version, including alpha/beta/rc tags.
release = version_ns['__version__']


# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    'myst_parser',
    'autodoc_traits',
    'sphinx.ext.autodoc',
    'sphinx.ext.intersphinx',
    'sphinx.ext.mathjax',
    'sphinx_copybutton'
]

myst_enable_extensions = ["html_image"]

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = []


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
#
html_theme = "pydata_sphinx_theme"

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']

# Output for github to be used in links
html_context = {
    "display_github": True,  # Integrate GitHub
    "github_user": "jupyterlab",  # Username
    "github_repo": "jupyterlab_server",  # Repo name
    "github_version": "master",  # Version
    "conf_py_path": "/docs/source/",  # Path in the checkout to the docs root
}


def setup(app):
    dest = osp.join(HERE, 'changelog.md')
    shutil.copy(osp.join(HERE, '..', '..', 'CHANGELOG.md'), dest)

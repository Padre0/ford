#!/usr/bin/env python
# -- coding: utf-8 --
#
#  ford.py
#
#  Copyright 2014 Christopher MacMackin <cmacmackin@gmail.com>
#  This file is part of FORD.
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#
#

from contextlib import contextmanager
from io import StringIO
import sys
import argparse
import markdown
import os
import subprocess
from datetime import date, datetime

import ford.fortran_project
import ford.sourceform
import ford.output
from ford.mdx_math import MathExtension
import ford.utils
import ford.pagetree

try:
    from importlib.metadata import version, PackageNotFoundError
except ModuleNotFoundError:
    from importlib_metadata import version, PackageNotFoundError
try:
    __version__ = version(__name__)
except PackageNotFoundError:
    from setuptools_scm import get_version

    __version__ = get_version(root="..", relative_to=__file__)


__appname__ = "FORD"
__author__ = "Chris MacMackin"
__credits__ = [
    "Balint Aradi",
    "Iain Barrass",
    "Izaak Beekman",
    "Jérémie Burgalat",
    "David Dickinson",
    "Gavin Huttley",
    "Harald Klimach",
    "Nick R. Papior",
    "Marco Restelli",
    "Schildkroete23",
    "Stephen J. Turnbull",
    "Jacob Williams",
    "Stefano Zhagi",
]
__license__ = "GPLv3"
__maintainer__ = "Chris MacMackin"
__status__ = "Production"


@contextmanager
def stdout_redirector(stream):
    old_stdout = sys.stdout
    sys.stdout = stream
    try:
        yield
    finally:
        sys.stdout = old_stdout


LICENSES = {
    "by": (
        '<a rel="license" href="http://creativecommons.org/licenses/by/4.0/">'
        '<img alt="Creative Commons License" style="border-width:0" src="https://i.creativecommons.org/l/by/4.0/80x15.png" /></a>'
    ),
    "by-nd": (
        '<a rel="license" href="http://creativecommons.org/licenses/by-nd/4.0/">'
        '<img alt="Creative Commons License" style="border-width:0" src="https://i.creativecommons.org/l/by-nd/4.0/80x15.png" /></a>'
    ),
    "by-sa": (
        '<a rel="license" href="http://creativecommons.org/licenses/by-sa/4.0/">'
        '<img alt="Creative Commons License" style="border-width:0" src="https://i.creativecommons.org/l/by-sa/4.0/80x15.png" /></a>'
    ),
    "by-nc": (
        '<a rel="license" href="http://creativecommons.org/licenses/by-nc/4.0/">'
        '<img alt="Creative Commons License" style="border-width:0" src="https://i.creativecommons.org/l/by-nc/4.0/80x15.png" /></a>'
    ),
    "by-nc-nd": (
        '<a rel="license" href="http://creativecommons.org/licenses/by-nc-nd/4.0/">'
        '<img alt="Creative Commons License" style="border-width:0" src="https://i.creativecommons.org/l/by-nc-nd/4.0/80x15.png" /></a>'
    ),
    "by-nc-sa": (
        '<a rel="license" href="http://creativecommons.org/licenses/by-nc-sa/4.0/">'
        '<img alt="Creative Commons License" style="border-width:0" src="https://i.creativecommons.org/l/by-nc-sa/4.0/80x15.png" /></a>'
    ),
    "gfdl": '<a rel="license" href="http://www.gnu.org/licenses/old-licenses/fdl-1.2.en.html">GNU Free Documentation License</a>',
    "opl": '<a rel="license" href="http://opencontent.org/openpub/">Open Publication License</a>',
    "pdl": '<a rel="license" href="http://www.openoffice.org/licenses/PDL.html">Public Documentation License</a>',
    "bsd": '<a rel="license" href="http://www.freebsd.org/copyright/freebsd-doc-license.html">FreeBSD Documentation License</a>',
    "isc": '<a rel="license" href="https://opensource.org/licenses/ISC">ISC (Internet Systems Consortium) License</a>',
    "mit": '<a rel="license" href="https://opensource.org/licenses/MIT">MIT</a>',
    "": "",
}


def convert_to_bool(name, option):
    """Convert value 'option' to a bool, with a nice error message on failure"""
    if len(option) > 1:
        raise ValueError(
            f"Could not convert option '{name}' to bool: expected a single value but got a list ({option})"
        )
    try:
        return ford.utils.str_to_bool(option[0])
    except ValueError:
        raise ValueError(
            f"Could not convert option '{name}' to bool: expected 'true'/'false', got: {option[0]}"
        )


def initialize():
    """
    Method to parse and check configurations of FORD, get the project's
    global documentation, and create the Markdown reader.
    """
    try:
        import multiprocessing

        ncpus = "{0}".format(multiprocessing.cpu_count())
    except (ImportError, NotImplementedError):
        ncpus = "0"

    # Setup the command-line options and parse them.
    parser = argparse.ArgumentParser(
        "ford",
        description="Document a program or library written in modern Fortran. Any command-line options over-ride those specified in the project file.",
    )
    parser.add_argument(
        "project_file",
        help="file containing the description and settings for the project",
        type=argparse.FileType("r"),
    )
    parser.add_argument(
        "-d",
        "--src_dir",
        action="append",
        help="directories containing all source files for the project",
    )
    parser.add_argument(
        "-p",
        "--page_dir",
        help="directory containing the optional page tree describing the project",
    )
    parser.add_argument(
        "-o", "--output_dir", help="directory in which to place output files"
    )
    parser.add_argument("-s", "--css", help="custom style-sheet for the output")
    parser.add_argument(
        "-r",
        "--revision",
        dest="revision",
        help="Source code revision the project to document",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        help="any files which should not be included in the documentation",
    )
    parser.add_argument(
        "--exclude_dir",
        action="append",
        help="any directories whose contents should not be included in the documentation",
    )
    parser.add_argument(
        "-e",
        "--extensions",
        action="append",
        help="extensions which should be scanned for documentation (default: f90, f95, f03, f08)",
    )
    parser.add_argument(
        "-m",
        "--macro",
        action="append",
        help="preprocessor macro (and, optionally, its value) to be applied to files in need of preprocessing.",
    )
    parser.add_argument(
        "-w",
        "--warn",
        dest="warn",
        action="store_true",
        default=None,
        help="display warnings for undocumented items",
    )
    parser.add_argument(
        "-f",
        "--force",
        dest="force",
        action="store_true",
        default=None,
        help="continue to read file if fatal errors",
    )
    parser.add_argument(
        "--no-search",
        dest="search",
        action="store_false",
        default=None,
        help="don't process documentation to produce a search feature",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        dest="quiet",
        action="store_true",
        default=None,
        help="do not print any description of progress",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version="%(prog)s version {}".format(__version__),
    )
    parser.add_argument(
        "--debug",
        dest="dbg",
        action="store_true",
        default=None,
        help="display traceback if fatal exception occurs and print faulty line",
    )
    parser.add_argument(
        "-I",
        "--include",
        action="append",
        help="any directories which should be searched for include files",
    )
    parser.add_argument(
        "--externalize",
        action="store_const",
        const="true",
        help="Provide information about Fortran objects in a json database for other FORD projects to refer to.",
    )
    parser.add_argument(
        "-L",
        "--external_links",
        dest="external",
        action="append",
        help=""" External projects to link to.
If an entity is not found in the sources, FORD will try to look it up in
those external projects. If those have documentation generated by FORD with
the externalize option, a link will be placed into the documentation wherever
this entity is referred to.
FORD will look in the provided paths for a modules.json file.
""",
    )
    # Get options from command-line
    args = parser.parse_args()
    # Set up Markdown reader
    md_ext = [
        "markdown.extensions.meta",
        "markdown.extensions.codehilite",
        "markdown.extensions.extra",
        MathExtension(),
        "md_environ.environ",
    ]
    md = markdown.Markdown(
        extensions=md_ext, output_format="html5", extension_configs={}
    )
    # Read in the project-file. This will contain global documentation (which
    # will appear on the homepage) as well as any information about the project
    # and settings for generating the documentation.
    proj_docs = args.project_file.read()
    md.convert(proj_docs)
    # Remake the Markdown object with settings parsed from the project_file
    if "md_base_dir" in md.Meta:
        md_base = md.Meta["md_base_dir"][0]
    else:
        md_base = os.path.dirname(args.project_file.name)
    md_ext.append("markdown_include.include")
    if "md_extensions" in md.Meta:
        md_ext.extend(md.Meta["md_extensions"])
    md = markdown.Markdown(
        extensions=md_ext,
        output_format="html5",
        extension_configs={"markdown_include.include": {"base_path": md_base}},
    )

    # Re-read the project file
    proj_docs = md.reset().convert(proj_docs)
    proj_data = md.Meta

    # Get the default options, and any over-rides, straightened out
    defaults = {
        "css": None,
        "author": None,
        "author_description": None,
        "author_pic": None,
        "summary": None,
        "github": None,
        "gitlab": None,
        "bitbucket": None,
        "facebook": None,
        "twitter": None,
        "google_plus": None,
        "linkedin": None,
        "email": None,
        "website": None,
        "project_github": None,
        "project_gitlab": None,
        "project_bitbucket": None,
        "project_website": None,
        "project_download": None,
        "project_sourceforge": None,
        "version": None,
        "media_dir": None,
        "page_dir": None,
        "privacy_policy_url": None,
        "terms_of_service_url": None,
        "graph_dir": None,
        "gitter_sidecar": None,
        "mathjax_config": None,
        "revision": None,
        "src_dir": ["./src"],
        "extensions": ["f90", "f95", "f03", "f08", "f15"],
        "fpp_extensions": ["F90", "F95", "F03", "F08", "F15", "F", "FOR"],
        "fixed_extensions": ["f", "for", "F", "FOR"],
        "output_dir": "./doc",
        "project": "Fortran Program",
        "project_url": "",
        "display": ["public", "protected"],
        "hide_undoc": False,
        "year": date.today().year,
        "exclude": [],
        "exclude_dir": [],
        "copy_subdir": [],
        "external": [],
        "externalize": False,
        "docmark": "!",
        "docmark_alt": "*",
        "predocmark": ">",
        "predocmark_alt": "|",
        "alias": [],
        "favicon": "default-icon",
        "extra_vartypes": [],
        "incl_src": True,
        "source": False,
        "macro": [],
        "include": [],
        "preprocess": True,
        "preprocessor": "",
        "proc_internals": False,
        "warn": False,
        "force": False,
        "quiet": False,
        "search": True,
        "lower": False,
        "sort": "src",
        "extra_mods": [],
        "dbg": True,
        "graph": False,
        "graph_maxdepth": "10000",
        "graph_maxnodes": "1000000000",
        "license": "",
        "doc_license": "",
        "extra_filetypes": [],
        "creation_date": "%Y-%m-%dT%H:%M:%S.%f%z",
        "print_creation_date": False,
        "coloured_edges": False,
        "parallel": ncpus,
        "fixed_length_limit": True,
        "max_frontpage_items": 10,
        "encoding": "utf-8",
    }

    for option, default in defaults.items():
        if hasattr(args, option) and getattr(args, option) is not None:
            proj_data[option] = getattr(args, option)
        elif option in proj_data:
            # Think if there is a safe  way to evaluate any expressions found in this list
            default_type = defaults.get(option, None)
            if isinstance(default_type, bool):
                proj_data[option] = convert_to_bool(option, proj_data[option])
            elif not isinstance(default_type, list):
                proj_data[option] = "\n".join(proj_data[option])
        else:
            proj_data[option] = default

    # Evaluate paths relative to project file location
    base_dir = os.path.abspath(os.path.dirname(args.project_file.name))
    proj_data["base_dir"] = base_dir
    for var in ["src_dir", "exclude_dir", "include"]:
        if var in proj_data:
            proj_data[var] = [
                os.path.normpath(
                    os.path.join(base_dir, os.path.expanduser(os.path.expandvars(p)))
                )
                for p in proj_data[var]
            ]
    for var in [
        "page_dir",
        "output_dir",
        "graph_dir",
        "media_dir",
        "css",
        "mathjax_config",
    ]:
        if proj_data[var] is not None:
            proj_data[var] = os.path.normpath(
                os.path.join(
                    base_dir, os.path.expanduser(os.path.expandvars(proj_data[var]))
                )
            )
    if proj_data["favicon"].strip() != defaults["favicon"]:
        proj_data["favicon"] = os.path.normpath(
            os.path.join(
                base_dir, os.path.expanduser(os.path.expandvars(proj_data["favicon"]))
            )
        )
    proj_data["display"] = [item.lower() for item in proj_data["display"]]
    proj_data["creation_date"] = datetime.now().strftime(proj_data["creation_date"])
    relative = proj_data["project_url"] == ""
    proj_data["relative"] = relative
    proj_data["extensions"] += [
        ext for ext in proj_data["fpp_extensions"] if ext not in proj_data["extensions"]
    ]
    # Parse file extensions and comment characters for extra filetypes
    extdict = {}
    for ext in proj_data["extra_filetypes"]:
        sp = ext.split()
        if len(sp) < 2:
            continue
        if len(sp) == 2:
            extdict[sp[0]] = sp[1]  # (comment_char) only
        else:
            extdict[sp[0]] = (sp[1], sp[2])  # (comment_char and lexer_str)
    proj_data["extra_filetypes"] = extdict
    # Make sure no src_dir is contained within output_dir
    for projdir in proj_data["src_dir"]:
        proj_path = ford.utils.split_path(projdir)
        out_path = ford.utils.split_path(proj_data["output_dir"])
        for directory in out_path:
            if len(proj_path) == 0:
                break
            if directory == proj_path[0]:
                proj_path.remove(directory)
            else:
                break
        else:
            print(
                "Error: directory containing source-code {} a subdirectory of output directory {}.".format(
                    projdir, proj_data["output_dir"]
                )
            )
            sys.exit(1)
    # Check that none of the docmarks are the same
    if proj_data["docmark"] == proj_data["predocmark"] != "":
        print("Error: docmark and predocmark are the same.")
        sys.exit(1)
    if proj_data["docmark"] == proj_data["docmark_alt"] != "":
        print("Error: docmark and docmark_alt are the same.")
        sys.exit(1)
    if proj_data["docmark"] == proj_data["predocmark_alt"] != "":
        print("Error: docmark and predocmark_alt are the same.")
        sys.exit(1)
    if proj_data["docmark_alt"] == proj_data["predocmark"] != "":
        print("Error: docmark_alt and predocmark are the same.")
        sys.exit(1)
    if proj_data["docmark_alt"] == proj_data["predocmark_alt"] != "":
        print("Error: docmark_alt and predocmark_alt are the same.")
        sys.exit(1)
    if proj_data["predocmark"] == proj_data["predocmark_alt"] != "":
        print("Error: predocmark and predocmark_alt are the same.")
        sys.exit(1)
    # Add gitter sidecar if specified in metadata
    if proj_data["gitter_sidecar"] is not None:
        proj_docs += """
        <script>
            ((window.gitter = {{}}).chat = {{}}).options = {{
            room: '{}'
            }};
        </script>
        <script src="https://sidecar.gitter.im/dist/sidecar.v1.js" async defer></script>
        """.format(
            proj_data["gitter_sidecar"].strip()
        )
    # Handle preprocessor:
    if proj_data["preprocess"]:
        if proj_data["preprocessor"]:
            preprocessor = proj_data["preprocessor"].split()
        else:
            preprocessor = ["cpp", "-traditional-cpp", "-E", "-D__GFORTRAN__"]

        # Check whether preprocessor works (reading nothing from stdin)
        try:
            devnull = open(os.devnull)
            subprocess.Popen(
                preprocessor, stdin=devnull, stdout=devnull, stderr=devnull
            ).communicate()
        except OSError as ex:
            print("Warning: Testing preprocessor failed")
            print("  Preprocessor command: {}".format(preprocessor))
            print("  Exception: {}".format(ex))
            print("  -> Preprocessing turned off")
            proj_data["preprocess"] = "false"
        else:
            proj_data["preprocess"] = "true"
            proj_data["preprocessor"] = preprocessor

    # Get the correct license for project license or use value as a custom license value.
    try:
        proj_data["license"] = LICENSES[proj_data["license"].lower()]
    except KeyError:
        print(
            'Notice: license "{}" is not a recognized value, using the value as a custom license value.'.format(
                proj_data["license"]
            )
        )
    # Get the correct license for doc license(website or doc) or use value as a custom license value.
    try:
        proj_data["doc_license"] = LICENSES[proj_data["doc_license"].lower()]
    except KeyError:
        print(
            'Notice: doc_license "{}" is not a recognized value, using the value as a custom license value.'.format(
                proj_data["doc_license"]
            )
        )

    # Return project data, docs, and the Markdown reader
    md.reset()
    return (proj_data, proj_docs, md)


def main(proj_data, proj_docs, md):
    """
    Main driver of FORD.
    """
    if proj_data["relative"]:
        proj_data["project_url"] = "."
    # Parse the files in your project
    project = ford.fortran_project.Project(proj_data)
    if len(project.files) < 1:
        print(
            "Error: No source files with appropriate extension found in specified directory."
        )
        sys.exit(1)

    # Define core macros:
    ford.utils.register_macro("url = {0}".format(proj_data["project_url"]))
    ford.utils.register_macro(
        "media = {0}".format(os.path.join(proj_data["project_url"], "media"))
    )
    ford.utils.register_macro(
        "page = {0}".format(os.path.join(proj_data["project_url"], "page"))
    )

    # Register the user defined aliases:
    for alias in proj_data["alias"]:
        ford.utils.register_macro(alias)

    # Convert the documentation from Markdown to HTML. Make sure to properly
    # handle LateX and metadata.
    if proj_data["relative"]:
        project.markdown(md, "..")
    else:
        project.markdown(md, proj_data["project_url"])
    project.correlate()
    if proj_data["relative"]:
        project.make_links("..")
    else:
        project.make_links(proj_data["project_url"])

    # Convert summaries and descriptions to HTML
    if proj_data["relative"]:
        ford.sourceform.set_base_url(".")
    if proj_data["summary"] is not None:
        proj_data["summary"] = md.convert(proj_data["summary"])
        proj_data["summary"] = ford.utils.sub_links(
            ford.utils.sub_macros(ford.utils.sub_notes(proj_data["summary"])), project
        )
    if proj_data["author_description"] is not None:
        proj_data["author_description"] = md.convert(proj_data["author_description"])
        proj_data["author_description"] = ford.utils.sub_links(
            ford.utils.sub_macros(
                ford.utils.sub_notes(proj_data["author_description"])
            ),
            project,
        )
    proj_docs_ = ford.utils.sub_links(
        ford.utils.sub_macros(ford.utils.sub_notes(proj_docs)), project
    )
    # Process any pages
    if proj_data["page_dir"] is not None:
        page_tree = ford.pagetree.get_page_tree(
            os.path.normpath(proj_data["page_dir"]), proj_data["copy_subdir"], md
        )
        print()
    else:
        page_tree = None
    proj_data["pages"] = page_tree

    # Produce the documentation using Jinja2. Output it to the desired location
    # and copy any files that are needed (CSS, JS, images, fonts, source files,
    # etc.)

    docs = ford.output.Documentation(proj_data, proj_docs_, project, page_tree)
    docs.writeout()

    if proj_data["externalize"]:
        # save FortranModules to a JSON file which then can be used
        # for external modules
        ford.utils.external(project, make=True, path=proj_data["output_dir"])

    print("")
    return 0


def run():
    proj_data, proj_docs, md = initialize()
    if proj_data["quiet"]:
        f = StringIO()
        with stdout_redirector(f):
            main(proj_data, proj_docs, md)
    else:
        main(proj_data, proj_docs, md)


if __name__ == "__main__":
    run()

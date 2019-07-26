import re
import sys
import os
import tempfile

from .download import download_package
from .format import format_normalized_package_name


def determine_package_dependencies(package_json, url):
    # initially use requires_dist
    if package_json["info"]["requires_dist"]:
        extraInputs = []
        propagatedBuildInputs = []
        for package in package_json["info"]["requires_dist"]:
            if re.search("extra\s*==\s*", package):
                extraInputs.append(package)
            else:
                propagatedBuildInputs.append(package)
        dependencies = {
            "extraInputs": extraInputs,
            "buildInputs": [],
            "checkInputs": [],
            "propagatedBuildInputs": propagatedBuildInputs,
        }
    else:
        # fallover if requires_dist not populated
        dependencies = determine_dependencies_from_package(url)
    return sanitize_dependencies(dependencies)


def determine_dependencies_from_package(url):
    sys.path.append(".")

    with tempfile.TemporaryDirectory() as tempdir:
        download_package(url, tempdir, extract_archive=True)
        try:
            current_directory = os.getcwd()

            os.chdir(tempdir)
            sys.path.insert(0, tempdir)

            with open(os.path.join(tempdir, "setup.py")) as f:
                setup_contents = f.read()

            if re.search("setuptools", setup_contents):
                mock_path = "setuptools.setup"
            else:
                mock_path = "distutils.core.setup"

            with mock.patch(mock_path) as mock_setup:
                exec(setup_contents)

            args, kwargs = mock_setup.call_args
        except Exception as e:
            print(
                "mocking setup.py::setup(...) failed thus dependency information is likely incomplete"
            )
            print(f'mocking error: "{e}"')
            args, kwargs = [], {}
        finally:
            sys.path = sys.path[1:]
            os.chdir(current_directory)

    extraInputs = []
    for k, v in kwargs.get("extras_require", {}).items():
        if isinstance(v, list):
            for p in v:
                extraInputs.append(f"{p} # {k}")
        else:
            extraInputs.append(f"{p} # {k}")

    return {
        "extraInputs": extraInputs,
        "buildInputs": kwargs.get("setup_requires", []),
        "checkInputs": kwargs.get("tests_require", []),
        "propagatedBuildInputs": kwargs.get("install_requires", []),
    }


def sanitize_dependencies(packages):
    def sanitize_dependency(package):
        has_condition = None

        match = re.search("[><=;]", package)
        if match:
            has_condition = True

        match = re.search("^([A-Za-z][A-Za-z\-_0-9]+)", format_normalized_package_name(package))
        return match.group(1), has_condition

    packageConditions = []
    buildInputs = []
    checkInputs = []
    propagatedBuildInputs = []

    for package in packages["buildInputs"]:
        sanitized_name, has_condition = sanitize_dependency(package)
        if has_condition:
            packageConditions.append(package)
        buildInputs.append(sanitized_name)

    for package in packages["checkInputs"]:
        sanitized_name, has_condition = sanitize_dependency(package)
        if has_condition:
            packageConditions.append(package)
        checkInputs.append(sanitized_name)

    for package in packages["propagatedBuildInputs"]:
        sanitized_name, has_condition = sanitize_dependency(package)
        if has_condition:
            packageConditions.append(package)
        propagatedBuildInputs.append(sanitized_name)

    return {
        "packageConditions": packageConditions,
        "extraInputs": packages["extraInputs"],
        "buildInputs": buildInputs,
        "checkInputs": checkInputs,
        "propagatedBuildInputs": propagatedBuildInputs,
    }
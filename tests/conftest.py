import copy
import pathlib
import shutil
from textwrap import dedent
from typing import Optional

import pytest
from django.conf import settings


pytest_plugins = "pytester"

REPOSITORY_ROOT = pathlib.Path(__file__).parent


def pytest_configure(config) -> None:
    config.addinivalue_line(
        "markers", "django_project: options for the django_testdir fixture"
    )


def _marker_apifun(
    extra_settings: str = "",
    create_manage_py: bool = False,
    project_root: Optional[str] = None,
):
    return {
        "extra_settings": extra_settings,
        "create_manage_py": create_manage_py,
        "project_root": project_root,
    }


@pytest.fixture
def testdir(testdir, monkeypatch):
    monkeypatch.delenv("PYTEST_ADDOPTS", raising=False)
    return testdir


@pytest.fixture(scope="function")
def django_testdir(request, testdir, monkeypatch):
    from pytest_django_test.db_helpers import (
        DB_NAME, SECOND_DB_NAME, SECOND_TEST_DB_NAME, TEST_DB_NAME,
    )

    marker = request.node.get_closest_marker("django_project")

    options = _marker_apifun(**(marker.kwargs if marker else {}))

    if hasattr(request.node.cls, "db_settings"):
        db_settings = request.node.cls.db_settings
    else:
        db_settings = copy.deepcopy(settings.DATABASES)
        db_settings["default"]["NAME"] = DB_NAME
        db_settings["default"]["TEST"]["NAME"] = TEST_DB_NAME
        db_settings["second"]["NAME"] = SECOND_DB_NAME
        db_settings["second"].setdefault("TEST", {})["NAME"] = SECOND_TEST_DB_NAME

    test_settings = (
        dedent(
            """
        import django

        # Pypy compatibility
        try:
            from psycopg2cffi import compat
        except ImportError:
            pass
        else:
            compat.register()

        DATABASES = %(db_settings)s
        DATABASE_ROUTERS = ['pytest_django_test.db_router.DbRouter']

        INSTALLED_APPS = [
            'django.contrib.auth',
            'django.contrib.contenttypes',
            'tpkg.app',
        ]
        SECRET_KEY = 'foobar'

        MIDDLEWARE = [
            'django.contrib.sessions.middleware.SessionMiddleware',
            'django.middleware.common.CommonMiddleware',
            'django.middleware.csrf.CsrfViewMiddleware',
            'django.contrib.auth.middleware.AuthenticationMiddleware',
            'django.contrib.messages.middleware.MessageMiddleware',
        ]

        TEMPLATES = [
            {
                'BACKEND': 'django.template.backends.django.DjangoTemplates',
                'DIRS': [],
                'APP_DIRS': True,
                'OPTIONS': {},
            },
        ]

        %(extra_settings)s
    """
        )
        % {
            "db_settings": repr(db_settings),
            "extra_settings": dedent(options["extra_settings"]),
        }
    )

    if options["project_root"]:
        project_root = testdir.mkdir(options["project_root"])
    else:
        project_root = testdir.tmpdir

    tpkg_path = project_root.mkdir("tpkg")

    if options["create_manage_py"]:
        project_root.ensure("manage.py")

    tpkg_path.ensure("__init__.py")

    app_source = REPOSITORY_ROOT / "../pytest_django_test/app"
    test_app_path = tpkg_path.join("app")

    # Copy the test app to make it available in the new test run
    shutil.copytree(str(app_source), str(test_app_path))
    tpkg_path.join("the_settings.py").write(test_settings)

    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "tpkg.the_settings")

    def create_test_module(test_code: str, filename: str = "test_the_test.py"):
        r = tpkg_path.join(filename)
        r.write(dedent(test_code), ensure=True)
        return r

    def create_app_file(code: str, filename: str):
        r = test_app_path.join(filename)
        r.write(dedent(code), ensure=True)
        return r

    testdir.create_test_module = create_test_module
    testdir.create_app_file = create_app_file
    testdir.project_root = project_root

    testdir.makeini(
        """
        [pytest]
        addopts = --strict-markers
        console_output_style=classic
    """
    )

    return testdir


@pytest.fixture
def django_testdir_initial(django_testdir):
    """A django_testdir fixture which provides initial_data."""
    django_testdir.project_root.join("tpkg/app/migrations").remove()
    django_testdir.makefile(
        ".json",
        initial_data="""
        [{
            "pk": 1,
            "model": "app.item",
            "fields": { "name": "mark_initial_data" }
        }]""",
    )

    return django_testdir

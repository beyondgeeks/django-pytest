import copy
import shutil
from textwrap import dedent

import py
import pytest
from django.conf import settings

from .db_helpers import (create_empty_production_database, DB_NAME,
                         get_db_engine)

pytest_plugins = 'pytester'

TESTS_DIR = py.path.local(__file__)


def pytest_configure(config):
    config.addinivalue_line(
        'markers',
        'django_project: options for the django_testdir fixture')


def _marker_apifun(extra_settings='',
                   create_manage_py=False,
                   project_root=None):
    return {
        'extra_settings': extra_settings,
        'create_manage_py': create_manage_py,
        'project_root': project_root,
    }


@pytest.fixture(scope='function')
def django_testdir(request, testdir, monkeypatch):
    marker = request.node.get_marker('django_project')

    options = _marker_apifun(**(marker.kwargs if marker else {}))

    db_engine = get_db_engine()
    if db_engine in ('mysql', 'postgresql_psycopg2') \
            or (db_engine == 'sqlite3' and DB_NAME != ':memory:'):
        # Django requires the production database to exist.
        create_empty_production_database()

    if hasattr(request.node.cls, 'db_settings'):
        db_settings = request.node.cls.db_settings
    else:
        db_settings = copy.deepcopy(settings.DATABASES)
        db_settings['default']['NAME'] = DB_NAME

    test_settings = dedent('''
        # Pypy compatibility
        try:
            from psycopg2ct import compat
        except ImportError:
            pass
        else:
            compat.register()

        DATABASES = %(db_settings)s

        INSTALLED_APPS = [
            'tpkg.app',
        ]
        SECRET_KEY = 'foobar'

        MIDDLEWARE_CLASSES = (
            'django.contrib.sessions.middleware.SessionMiddleware',
            'django.middleware.common.CommonMiddleware',
            'django.middleware.csrf.CsrfViewMiddleware',
            'django.contrib.auth.middleware.AuthenticationMiddleware',
            'django.contrib.messages.middleware.MessageMiddleware',
        )

        %(extra_settings)s
    ''') % {
        'db_settings': repr(db_settings),
        'extra_settings': dedent(options['extra_settings'])}

    if options['project_root']:
        project_root = testdir.mkdir(options['project_root'])
    else:
        project_root = testdir.tmpdir

    tpkg_path = project_root.mkdir('tpkg')

    if options['create_manage_py']:
        project_root.ensure('manage.py')

    tpkg_path.ensure('__init__.py')

    app_source = TESTS_DIR.dirpath('app')
    test_app_path = tpkg_path.join('app')

    # Copy the test app to make it available in the new test run
    shutil.copytree(py.builtin._totext(app_source),
                    py.builtin._totext(test_app_path))
    tpkg_path.join("the_settings.py").write(test_settings)

    monkeypatch.setenv('DJANGO_SETTINGS_MODULE', 'tpkg.the_settings')

    def create_test_module(test_code, filename='test_the_test.py'):
        tpkg_path.join(filename).write(dedent(test_code), ensure=True)

    def create_app_file(code, filename):
        test_app_path.join(filename).write(dedent(code), ensure=True)

    testdir.create_test_module = create_test_module
    testdir.create_app_file = create_app_file
    testdir.project_root = project_root

    return testdir


@pytest.fixture
def django_testdir_initial(django_testdir):
    """A django_testdir fixture which provides initial_data."""
    django_testdir.makefile('.json', initial_data="""
        [{
            "pk": 1,
            "model": "app.item",
            "fields": { "name": "mark_initial_data" }
        }]""")

    return django_testdir

"""
These tests use the ``pytester`` plugin to run tests in a separate process.
Because of this, some Docker state can conflict between the main test process
and these new processes. For this reason, these tests have been separated from
the others. Note that these tests produce no coverage data.
https://docs.pytest.org/en/3.2.1/writing_plugins.html#testing-plugins
"""
from seaworthy.checks import docker_client
from seaworthy.dockerhelper import fetch_images
from seaworthy.pytest.checks import dockertest


IMG = 'nginx:alpine'


def setup_module():
    with docker_client() as client:
        fetch_images(client, [IMG])


@dockertest()
class TestDockerHelperFixture:
    def test_fixture(self, testdir):
        """
        The ``docker_helper`` fixture should automatically be in scope for a
        project that uses this pytest plugin.  When the ``DockerHelper`` is
        passed to a test function using a fixture, it should be possible to
        create, start, stop, and remove a container using the helper.
        """
        testdir.makepyfile("""
            from docker.errors import NotFound
            import pytest

            def test_container_basics(docker_helper):
                container = docker_helper.create_container('test', '{}')
                docker_helper.start_container(container)

                assert container.status == 'running'

                docker_helper.stop_and_remove_container(container)

                with pytest.raises(NotFound):
                    container.reload()
        """.format(IMG))

        result = testdir.runpytest()
        result.assert_outcomes(passed=1)


@dockertest()
class TestImagePullFixtureFunc:
    def test_fixture(self, testdir):
        """
        When the fixture is used in a test, the image passed to the test
        should have the right tag.
        """
        testdir.makeconftest("""
            from seaworthy.pytest.fixtures import image_pull_fixture

            fixture = image_pull_fixture('busybox', name='image')
        """.format(IMG))

        testdir.makepyfile("""
            def test_image_pull(image):
                assert 'busybox:latest' in image.tags
        """)


@dockertest()
class TestContainerFixtureFunc:
    def test_fixture(self, testdir):
        """
        When the fixture is used in a test, the container passed to the test
        function should be running.
        """
        testdir.makeconftest("""
            from seaworthy.containers.base import ContainerBase
            from seaworthy.pytest.fixtures import container_fixture

            fixture = container_fixture(ContainerBase(name='test', image='{}'),
                                        'container')
        """.format(IMG))

        testdir.makepyfile("""
            def test_create_container(container):
                assert container.inner().status == 'running'
        """)

        result = testdir.runpytest()
        result.assert_outcomes(passed=1)


@dockertest()
class TestCleanContainerFixturesFunc:
    def test_fixture(self, testdir):
        """
        When the fixture is used in a test, it should be cleaned when the test
        function is marked to be cleaned. The container passed to the test
        function should be running.
        """
        testdir.makeconftest("""
            from seaworthy.containers.base import ContainerBase
            from seaworthy.pytest.fixtures import clean_container_fixtures


            class CleanableContainer(ContainerBase):
                def __init__(self):
                    super().__init__(name='test', image='{}')
                    self.cleaned = False

                def clean(self):
                    self.cleaned = True

                def was_cleaned(self):
                    cleaned = self.cleaned
                    self.cleaned = False
                    return cleaned


            f1, f2 = clean_container_fixtures(
                CleanableContainer(), 'cleanable')
        """.format(IMG))

        testdir.makepyfile("""
            import pytest


            def test_dirty(cleanable):
                assert not cleanable.was_cleaned()
                assert cleanable.inner().status == 'running'

            @pytest.mark.clean_cleanable
            def test_clean(cleanable):
                assert cleanable.was_cleaned()
                assert cleanable.inner().status == 'running'
        """)

        result = testdir.runpytest()
        result.assert_outcomes(passed=2)
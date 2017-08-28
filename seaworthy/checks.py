"""
This module contains some checks and test decorators for skipping tests
that require docker to be present.
"""

import unittest
from contextlib import contextmanager

import docker
from requests.exceptions import ConnectionError


@contextmanager
def docker_client():
    client = docker.client.from_env()
    yield client
    client.api.close()


def docker_available():
    with docker_client() as client:
        try:
            return client.ping()
        except ConnectionError:  # pragma: no cover
            return False


def dockertest():
    """
    Skip tests that require docker to be available.

    This is a function that returns a decorator so that we don't run arbitrary
    docker client code on import. This implementation only works with tests
    based on ``unittest.TestCase``. If you're using pytest, you probably want
    ``seaworthy.pytest.dockertest`` instead.
    """
    return unittest.skipUnless(docker_available(), 'Docker not available.')

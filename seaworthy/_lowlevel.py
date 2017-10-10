"""
This is a module for horrible low-level things that we really wish we
didn't have to build and maintain ourselves.
"""

import struct
import time
# selectors is a stdlib module, but flake8-import-order doesn't know that.
import selectors


class SocketClosed(Exception):
    """
    Exception used for flow control. :-(
    """


def stream_logs(container, stdout=1, stderr=1, timeout=10.0):
    """
    Stream logs from a docker container within a timeout.

    We can't use docker-py's existing streaming support because that's stuck
    behind a blocking API and we have no (sane) way to enforce a timeout.

    NOTE: This function deliberately doesn't support logs=1 because docker
    sometimes just ignores it and skips all the old logs we asked it to give
    us.
    """
    deadline = time.monotonic() + timeout
    params = {
        'stdout': 1 if stdout else 0,
        'stderr': 1 if stderr else 0,
        'stream': 1,
        'logs': 0,
    }
    fileobj = container.attach_socket(params=params)
    fileobj._sock.setblocking(False)  # Make the socket nonblocking.
    sel = selectors.DefaultSelector()
    sel.register(fileobj, selectors.EVENT_READ)
    try:
        while True:
            try:
                yield read_frame(sel, deadline)
            except SocketClosed:
                return
    finally:
        sel.close()
        # We also need to close the response object our socket comes from to
        # avoid leaking any resources.
        fileobj._response.close()


def read_from_ready(fileobj, n):
    """
    Read up to N bytes from a socket. If there's nothing to read, signal that
    it's closed.
    """
    data = fileobj.read(n)
    if len(data) == 0:
        raise SocketClosed()
    return data


def read_n_bytes(sel, n, deadline):
    """
    Read exactly N bytes from a socket before a timeout deadline. We assume
    that the selector contains exactly one socket.
    """
    buf = b''
    while len(buf) < n:
        if time.monotonic() > deadline:
            raise TimeoutError('Timeout waiting for container logs.')
        for selkey, _ in sel.select(0.01):
            buf += read_from_ready(selkey.fileobj, n - len(buf))
    return buf


def read_frame(sel, deadline):
    """
    Read a docker stream frame before a timeout deadline.
    """
    header = read_n_bytes(sel, 8, deadline)
    _, size = struct.unpack('>BxxxL', header)
    return read_n_bytes(sel, size, deadline)
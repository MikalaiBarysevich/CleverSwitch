import socket

_NETLINK_KOBJECT_UEVENT = 15

# udevd's group: sent after rules ran, so the uaccess ACL is already on the node
_UDEV_GROUP = 2

_RECEIVE_BUFFER = 1 << 20
_MESSAGE_SIZE = 16384


def open_udev_socket() -> socket.socket:
    sock = socket.socket(socket.AF_NETLINK, socket.SOCK_RAW | socket.SOCK_CLOEXEC, _NETLINK_KOBJECT_UEVENT)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, _RECEIVE_BUFFER)
        except OSError:
            pass
        sock.bind((0, _UDEV_GROUP))
    except BaseException:
        sock.close()
        raise
    return sock


# (message, ancillary data carrying the sender's credentials); ENOBUFS means messages were lost.
def receive(sock: socket.socket) -> tuple[bytes, list]:
    data, ancdata, _flags, _address = sock.recvmsg(_MESSAGE_SIZE, socket.CMSG_SPACE(12))
    return data, ancdata

import io
import logging
import selectors
from collections import OrderedDict

import fbtftp.base_handler
import fbtftp.base_server
import fbtftp.constants
import fbtftp.netascii

import tftp.router as router

def none(arg):
    pass


class FileResponseData(fbtftp.base_handler.ResponseData):
    def __init__(self, data: bytes):
        self._size = len(data)
        self._stream = io.BytesIO(data)

    def read(self, num_bytes: int):
        return self._stream.read(num_bytes)

    def size(self):
        return self._size

    def close(self):
        self._stream.close()


class DynamicHandler(fbtftp.base_handler.BaseHandler):
    def __init__(self, server_addr, peer, path, options):
        super().__init__(server_addr, peer, path, options, none)

    def get_response_data(self):
        tftp_router = router.TFTPRouter(address=self._peer[0], port=self._peer[1], file=self._path)
        status, data = tftp_router.return_data
        if not status:
            self._stats.error = {
                "error_code": fbtftp.constants.ERR_FILE_NOT_FOUND,
                "error_message": f"Requested file '{self._path}' for {self._peer[0]}:{self._peer[1]} not found",
            }
            self._transmit_error()
            self._should_stop = True
            return
        logging.info(f"Successfully served file '{self._path}' to {self._peer[0]}:{self._peer[1]}")
        return FileResponseData(data)

    def _parse_options(self):
        """
        Method that deals with parsing/validation options provided by the
        client.

        Custom implementation to remove log messages inside this method
        """
        opts_to_ack = OrderedDict()
        # We remove retries and default_timeout from self._options because
        # we don't need to include them in the OACK response to the client.
        # Their value is already hold in self._retries and self._timeout.
        del self._options["retries"]
        del self._options["default_timeout"]
        self._stats.options_in = self._options
        if "mode" in self._options and self._options["mode"] == "netascii":
            self._response_data = fbtftp.netascii.NetasciiReader(self._response_data)
        elif "mode" in self._options and self._options["mode"] != "octet":
            self._stats.error = {
                "error_code": fbtftp.constants.ERR_ILLEGAL_OPERATION,
                "error_message": "Unknown mode: %r" % self._options["mode"],
            }
            self._transmit_error()
            self._close()
            return  # no way anything else will succeed now
        # Let's ack the options in the same order we got asked for them
        # The RFC mentions that option order is not significant, but it can't
        # hurt. This relies on Python 3.6 dicts to be ordered.
        for k, v in self._options.items():
            if k == "blksize":
                opts_to_ack["blksize"] = v
                self._block_size = int(v)
            if k == "tsize":
                self._tsize = self._response_data.size()
                if self._tsize is not None:
                    opts_to_ack["tsize"] = str(self._tsize)
            if k == "timeout":
                opts_to_ack["timeout"] = v
                self._timeout = int(v)

        self._options = opts_to_ack  # only ACK options we can handle
        self._stats.blksize = self._block_size
        self._stats.options = self._options
        self._stats.options_acked = self._options


class TFTPServer(fbtftp.base_server.BaseServer):
    def __init__(self, address, port, retries, timeout):
        super().__init__(address, port, retries, timeout, none)
        logging.info(f"TFTP server started and listening on {address}:{port}")

    def get_handler(self, server_addr, peer, path, options):
        return DynamicHandler(server_addr, peer, path, options)

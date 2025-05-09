"""Test server asyncio."""
import asyncio
import logging
import ssl
from asyncio import CancelledError
from contextlib import suppress
from unittest import mock

import pytest

from pymodbus import FramerType, ModbusDeviceIdentification
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.datastore import (
    ModbusDeviceContext,
    ModbusSequentialDataBlock,
    ModbusServerContext,
)
from pymodbus.exceptions import NoSuchIdException
from pymodbus.server import ModbusTcpServer, ModbusTlsServer, ModbusUdpServer


_logger = logging.getLogger()

SERV_IP = "127.0.0.1"
SERV_ADDR = ("127.0.0.1", 0)
TEST_DATA = b"\x01\x00\x00\x00\x00\x06\x01\x03\x00\x00\x00\x01"


class BasicClient(asyncio.BaseProtocol):
    """Basic client."""

    connected = None
    data = None
    dataTo = None
    received_data = None
    done = None
    eof = None
    transport = None
    protocol = None

    def connection_made(self, transport):
        """Get Connection made."""
        _logger.debug("TEST Client connected")
        if BasicClient.connected is not None:
            BasicClient.connected.set_result(True)

        self.transport = transport
        if BasicClient.data is not None:
            _logger.debug("TEST Client write data")
            self.transport.write(BasicClient.data)
        if BasicClient.dataTo is not None:
            _logger.debug("TEST Client sendTo data")
            self.transport.sendto(BasicClient.dataTo)

    def data_received(self, data):
        """Get Data received."""
        _logger.debug("TEST Client data received")
        BasicClient.received_data = data
        if BasicClient.done is not None:
            BasicClient.done.set_result(True)

    def datagram_received(self, data, _addr):
        """Get Datagram received."""
        _logger.debug("TEST Client datagram received")
        BasicClient.received_data = data
        if BasicClient.done is not None:
            BasicClient.done.set_result(True)
        self.transport.close()

    def connection_lost(self, exc):
        """EOF received."""
        txt = f"TEST Client stream lost: {exc}"
        _logger.debug(txt)
        if BasicClient.eof:
            BasicClient.eof.set_result(True)

    def eof_received(self):
        """Accept other end terminates connection."""

    @classmethod
    def clear(cls):
        """Prepare for new round."""
        if BasicClient.transport:
            BasicClient.transport.close()
            BasicClient.transport = None
        BasicClient.data = None
        BasicClient.connected = None
        BasicClient.done = None
        BasicClient.received_data = None
        BasicClient.eof = None
        BasicClient.my_protocol = None


class TestAsyncioServer:
    """Unittest for the pymodbus.server.asyncio module.

    The scope of this test is the life-cycle management of the network
    connections and server objects.

    This test suite does not attempt to test any of the underlying protocol details
    """

    server = None
    task = None
    loop = None
    store = None
    context = None
    identity = None

    @pytest.fixture(autouse=True)
    async def _setup_teardown(self):
        """Initialize the test environment by setting up a dummy store and context."""
        self.loop = asyncio.get_running_loop()
        self.store = ModbusDeviceContext(
            di=ModbusSequentialDataBlock(0, [17] * 100),
            co=ModbusSequentialDataBlock(0, [17] * 100),
            hr=ModbusSequentialDataBlock(0, [17] * 100),
            ir=ModbusSequentialDataBlock(0, [17] * 100),
        )
        self.context = ModbusServerContext(devices=self.store, single=True)
        self.identity = ModbusDeviceIdentification(
            info_name={"VendorName": "VendorName"}
        )
        yield

        # teardown
        if self.server is not None:
            await self.server.shutdown()
            self.server = None
        if self.task is not None:
            await asyncio.sleep(0.1)
            if not self.task.cancelled():
                self.task.cancel()
                with suppress(CancelledError):
                    await self.task
                self.task = None
        BasicClient.clear()
        await asyncio.sleep(0.1)

    def handle_task(self, result):
        """Handle task exit."""
        with suppress(CancelledError):
            result = result.result()

    async def start_server(
        self, do_forever=True, do_tls=False, do_udp=False, do_ident=False, serv_addr=SERV_ADDR,
    ):
        """Handle setup and control of tcp server."""
        args = {
            "context": self.context,
            "address": SERV_ADDR,
        }
        if do_ident:
            args["identity"] = self.identity
        if do_tls:
            self.server = ModbusTlsServer(
                self.context,
                framer=FramerType.TLS,
                identity=self.identity,
                address=serv_addr
            )
        elif do_udp:
            self.server = ModbusUdpServer(
                self.context,
                framer=FramerType.SOCKET,
                identity=self.identity,
                address=serv_addr
            )
        else:
            self.server = ModbusTcpServer(
                self.context,
                framer=FramerType.SOCKET,
                identity=self.identity,
                address=serv_addr
            )
        assert self.server
        if do_forever:
            self.task = asyncio.create_task(self.server.serve_forever())
            self.task.set_name("Run server")
            self.task.add_done_callback(self.handle_task)
            assert not self.task.cancelled()
            await asyncio.sleep(0.5)
            # TO BE FIXED await asyncio.wait_for(self.server.serving, timeout=0.1)
            if not do_udp:
                assert self.server.transport
        elif not do_udp:  # pylint: disable=confusing-consecutive-elif
            assert not self.server.transport
        assert self.server.control.Identity.VendorName == "VendorName"
        await asyncio.sleep(0.1)

    async def connect_server(self):
        """Handle connect to server."""
        BasicClient.connected = asyncio.Future()
        BasicClient.done = asyncio.Future()
        BasicClient.eof = asyncio.Future()
        random_port = self.server.transport.sockets[0].getsockname()[
            1
        ]  # get the random server port
        (
            BasicClient.transport,
            BasicClient.my_protocol,
        ) = await self.loop.create_connection(
            BasicClient, host="127.0.0.1", port=random_port
        )
        await asyncio.wait_for(BasicClient.connected, timeout=0.1)
        await asyncio.sleep(0.1)

    async def test_async_start_server_no_loop(self):
        """Test that the modbus tcp asyncio server starts correctly."""
        await self.start_server(do_forever=False)

    async def test_async_start_server(self):
        """Test that the modbus tcp asyncio server starts correctly."""
        await self.start_server()

    async def test_async_tcp_server_serve_forever_twice(self):
        """Call on serve_forever() twice should result in a runtime error."""
        await self.start_server()
        with pytest.raises(RuntimeError):
            await self.server.serve_forever()

    async def test_async_tcp_server_receive_data(self):
        """Test data sent on socket is received by internals - doesn't not process data."""
        BasicClient.data = b"\x01\x00\x00\x00\x00\x06\x01\x03\x00\x00\x00\x19"
        await self.start_server()
        with mock.patch(
            "pymodbus.framer.FramerSocket.processIncomingFrame",
            new_callable=mock.Mock,
        ) as process:
            await self.connect_server()
            process.assert_called_once()
            assert process.call_args[0][0] == BasicClient.data

    async def test_async_tcp_server_roundtrip(self):
        """Test sending and receiving data on tcp socket."""
        expected_response = b"\x01\x00\x00\x00\x00\x05\x01\x03\x02\x00\x11"
        BasicClient.data = TEST_DATA  # device 1, read register
        await self.start_server()
        await self.connect_server()
        await asyncio.wait_for(BasicClient.done, timeout=0.1)
        assert BasicClient.received_data, expected_response

    @pytest.mark.skip
    async def test_async_server_file_descriptors(self):
        """Test sending and receiving data on tcp socket.

        This test takes a long time (minutes) to run, so should only run when needed.
        """
        addr = ("127.0.0.1", 25001)
        await self.start_server(serv_addr=addr)
        for _ in range(2048):
            client = AsyncModbusTcpClient(addr[0], framer=FramerType.SOCKET, port=addr[1])
            await client.connect()
            response = await client.read_coils(31, count=1, device_id=1)
            assert not response.isError()
            client.close()

    async def test_async_tcp_server_connection_lost(self):
        """Test tcp stream interruption."""
        await self.start_server()
        await self.connect_server()

        BasicClient.transport.close()
        await asyncio.sleep(0.2)  # so we have to wait a bit

    async def test_async_tcp_server_shutdown_connection(self):
        """Test server shutdown() while there are active TCP connections."""
        await self.start_server()
        await self.connect_server()

        # On Windows we seem to need to give this an extra chance to finish,
        # otherwise there ends up being an active connection at the assert.
        await asyncio.sleep(0.5)
        await self.server.shutdown()

    async def test_async_tcp_server_no_device(self):
        """Test unknown device exception."""
        self.context = ModbusServerContext(
            devices={0x01: self.store, 0x02: self.store}, single=False
        )
        BasicClient.data = b"\x01\x00\x00\x00\x00\x06\x05\x03\x00\x00\x00\x01"
        await self.start_server()
        await self.connect_server()
        assert not BasicClient.eof.done()
        await self.server.shutdown()
        self.server = None

    async def test_async_tcp_server_modbus_error(self):
        """Test sending garbage data on a TCP socket should drop the connection."""
        BasicClient.data = TEST_DATA
        await self.start_server()
        with mock.patch(
            "pymodbus.pdu.register_message.ReadHoldingRegistersRequest.update_datastore",
            side_effect=NoSuchIdException,
        ):
            await self.connect_server()
            await asyncio.wait_for(BasicClient.done, timeout=0.1)

    # -----------------------------------------------------------------------#
    # Test ModbusTlsProtocol
    # -----------------------------------------------------------------------#
    async def test_async_start_tls_server_no_loop(self):
        """Test that the modbus tls asyncio server starts correctly."""
        with mock.patch.object(ssl.SSLContext, "load_cert_chain"):
            await self.start_server(do_tls=True, do_forever=False, do_ident=True)
            assert self.server.control.Identity.VendorName == "VendorName"

    async def test_async_start_tls_server(self):
        """Test that the modbus tls asyncio server starts correctly."""
        with mock.patch.object(ssl.SSLContext, "load_cert_chain"):
            await self.start_server(do_tls=True, do_ident=True)
            assert self.server.control.Identity.VendorName == "VendorName"

    async def test_async_tls_server_serve_forever_twice(self):
        """Call on serve_forever() twice should result in a runtime error."""
        with mock.patch.object(ssl.SSLContext, "load_cert_chain"):
            await self.start_server(do_tls=True)
            with pytest.raises(RuntimeError):
                await self.server.serve_forever()

    # -----------------------------------------------------------------------#
    # Test ModbusUdpProtocol
    # -----------------------------------------------------------------------#

    async def test_async_start_udp_server_no_loop(self):
        """Test that the modbus udp asyncio server starts correctly."""
        await self.start_server(do_udp=True, do_forever=False, do_ident=True)
        assert self.server.control.Identity.VendorName == "VendorName"
        assert not self.server.transport

    async def test_async_start_udp_server(self):
        """Test that the modbus udp asyncio server starts correctly."""
        await self.start_server(do_udp=True, do_ident=True)
        assert self.server.control.Identity.VendorName == "VendorName"
        assert self.server.transport

    async def test_async_udp_server_serve_forever_close(self):
        """Test StarAsyncUdpServer serve_forever() method."""
        await self.start_server(do_udp=True)
        await self.server.shutdown()
        self.server = None

    async def test_async_udp_server_serve_forever_twice(self):
        """Call on serve_forever() twice should result in a runtime error."""
        await self.start_server(do_udp=True, do_ident=True)
        with pytest.raises(RuntimeError):
            await self.server.serve_forever()

    async def test_async_udp_server_roundtrip(self):
        """Test sending and receiving data on udp socket."""
        expected_response = (
            b"\x01\x00\x00\x00\x00\x05\x01\x03\x02\x00\x11"
        )  # value of 17 as per context
        BasicClient.dataTo = TEST_DATA  # device 1, read register
        BasicClient.done = asyncio.Future()
        await self.start_server(do_udp=True)
        random_port = self.server.transport._sock.getsockname()[1]  # pylint: disable=protected-access
        transport, _ = await self.loop.create_datagram_endpoint(
            BasicClient, remote_addr=("127.0.0.1", random_port)
        )
        await asyncio.wait_for(BasicClient.done, timeout=0.1)
        assert BasicClient.received_data == expected_response
        transport.close()

    async def test_async_udp_server_exception(self):
        """Test sending garbage data on a TCP socket should drop the connection."""
        BasicClient.dataTo = b"\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF"
        BasicClient.connected = asyncio.Future()
        BasicClient.done = asyncio.Future()
        await self.start_server(do_udp=True)
        with mock.patch(
            "pymodbus.framer.FramerSocket.processIncomingFrame",
            new_callable=lambda: mock.Mock(side_effect=Exception),
        ):
            # get the random server port pylint: disable=protected-access
            random_port = self.server.transport._sock.getsockname()[1]
            _, _ = await self.loop.create_datagram_endpoint(
                BasicClient, remote_addr=("127.0.0.1", random_port)
            )
            await asyncio.wait_for(BasicClient.connected, timeout=0.1)
            assert not BasicClient.done.done()

    @pytest.mark.skip
    async def test_async_tcp_server_exception(self):
        """Send garbage data on a TCP socket should drop the connection."""
        BasicClient.data = b"\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF"
        await self.start_server()
        with mock.patch(
            "pymodbus.framer.FramerSocket.processIncomingFrame",
            new_callable=lambda: mock.Mock(side_effect=Exception),
        ):
            await self.connect_server()
            await asyncio.wait_for(BasicClient.eof, timeout=0.1)
            # neither of these should timeout if the test is successful

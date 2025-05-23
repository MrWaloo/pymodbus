#!/usr/bin/env python3
"""Pymodbus Client modbus all calls example.

Please see method **template_call**
for a template on how to make modbus calls and check for different
error conditions.

The handle* functions each handle a set of modbus calls with the
same register type (e.g. coils).

All available modbus calls are present.

If you are performing a request that is not available in the client
mixin, you have to perform the request like this instead::

    from pymodbus.pdu.diag_message import ClearCountersRequest
    from pymodbus.pdu.diag_message import ClearCountersResponse

    request  = ClearCountersRequest()
    response = client.execute(request)
    if isinstance(response, ClearCountersResponse):
        ... do something with the response


This example uses client_async.py and client_sync.py to handle connection,
and have the same options.

The corresponding server must be started before e.g. as:

    ./server_async.py
"""
import logging
import sys

from pymodbus.pdu import FileRecord


try:
    import client_sync  # type: ignore[import-not-found]
except ImportError:
    print("*** ERROR --> THIS EXAMPLE needs the example directory, please see \n\
          https://pymodbus.readthedocs.io/en/latest/source/examples.html\n\
          for more information.")
    sys.exit(-1)



_logger = logging.getLogger(__file__)
_logger.setLevel("DEBUG")


DEVICE_ID = 0x01


# --------------------------------------------------
# Template on how to make modbus calls (sync/async).
# all calls follow the same schema,
# --------------------------------------------------
def template_call(client):
    """Show complete modbus call, sync version."""
    try:
        rr = client.read_coils(32, count=1, device_id=DEVICE_ID)
    except client_sync.ModbusException as exc:
        txt = f"ERROR: exception in pymodbus {exc}"
        _logger.error(txt)
        raise exc
    if rr.isError():
        txt = "ERROR: pymodbus returned an error!"
        _logger.error(txt)
        raise client_sync.ModbusException(txt)

    # Validate data
    txt = f"### Template coils response: {rr.bits!s}"
    _logger.debug(txt)


# ------------------------------------------------------
# Call modbus device (all possible calls are presented).
# ------------------------------------------------------
def handle_coils(client):
    """Read/Write coils."""
    _logger.info("### Reading Coil different number of bits (return 8 bits multiples)")
    rr = client.read_coils(1, count=1, device_id=DEVICE_ID)
    assert not rr.isError()  # test that call was OK
    assert len(rr.bits) == 8

    rr = client.read_coils(1, count=5, device_id=DEVICE_ID)
    assert not rr.isError()  # test that call was OK
    assert len(rr.bits) == 8

    rr = client.read_coils(1, count=12, device_id=DEVICE_ID)
    assert not rr.isError()  # test that call was OK
    assert len(rr.bits) == 16

    rr = client.read_coils(1, count=17, device_id=DEVICE_ID)
    assert not rr.isError()  # test that call was OK
    assert len(rr.bits) == 24

    _logger.info("### Write false/true to coils and read to verify")
    client.write_coil(0, True, device_id=DEVICE_ID)
    rr = client.read_coils(0, count=1, device_id=DEVICE_ID)
    assert not rr.isError()  # test that call was OK
    assert rr.bits[0]  # test the expected value

    client.write_coils(1, [True] * 21, device_id=DEVICE_ID)
    rr = client.read_coils(1, count=21, device_id=DEVICE_ID)
    assert not rr.isError()  # test that call was OK
    resp = [True] * 21
    # If the returned output quantity is not a multiple of eight,
    # the remaining bits in the final data byte will be padded with zeros
    # (toward the high order end of the byte).
    resp.extend([False] * 3)
    assert rr.bits == resp  # test the expected value

    _logger.info("### Write False to address 1-8 coils")
    client.write_coils(1, [False] * 8, device_id=DEVICE_ID)
    rr = client.read_coils(1, count=8, device_id=DEVICE_ID)
    assert not rr.isError()  # test that call was OK
    assert rr.bits == [False] * 8  # test the expected value


def handle_discrete_input(client):
    """Read discrete inputs."""
    _logger.info("### Reading discrete input, Read address:0-7")
    rr = client.read_discrete_inputs(0, count=8, device_id=DEVICE_ID)
    assert not rr.isError()  # test that call was OK
    assert len(rr.bits) == 8


def handle_holding_registers(client):
    """Read/write holding registers."""
    _logger.info("### write holding register and read holding registers")
    client.write_register(1, 10, device_id=DEVICE_ID)
    rr = client.read_holding_registers(1, count=1, device_id=DEVICE_ID)
    assert not rr.isError()  # test that call was OK
    assert rr.registers[0] == 10

    value_int32 = 13211
    registers = client.convert_to_registers(value_int32, client.DATATYPE.INT32)
    client.write_registers(1, registers, device_id=DEVICE_ID)
    rr = client.read_holding_registers(1, count=len(registers), device_id=DEVICE_ID)
    assert not rr.isError()  # test that call was OK
    value = client.convert_from_registers(rr.registers, client.DATATYPE.INT32)
    assert value_int32 == value

    _logger.info("### write read holding registers")
    arguments = {
        "read_address": 1,
        "read_count": 8,
        "write_address": 1,
        "values": [256, 128, 100, 50, 25, 10, 5, 1],
    }
    client.readwrite_registers(device_id=DEVICE_ID, **arguments)
    rr = client.read_holding_registers(1, count=8, device_id=DEVICE_ID)
    assert not rr.isError()  # test that call was OK
    assert rr.registers == arguments["values"]


def handle_input_registers(client):
    """Read input registers."""
    _logger.info("### read input registers")
    rr = client.read_input_registers(1, count=8, device_id=DEVICE_ID)
    assert not rr.isError()  # test that call was OK
    assert len(rr.registers) == 8


def handle_file_records(client):
    """Read/write file records."""
    _logger.info("### Read/write file records")
    record = FileRecord(file_number=14, record_number=12, record_length=64)
    rr = client.read_file_record([record, record], device_id=DEVICE_ID)
    assert not rr.isError()
    assert len(rr.records) == 2
    assert rr.records[0].record_data == b'SERVER DUMMY RECORD.'
    assert rr.records[1].record_data == b'SERVER DUMMY RECORD.'
    record.record_data = b'Pure test '
    record.record_length = len(record.record_data) // 2
    record = FileRecord(file_number=14, record_number=12, record_data=b'Pure test ')
    rr = client.write_file_record([record], device_id=1)
    assert not rr.isError()


def execute_information_requests(client):
    """Execute extended information requests."""
    _logger.info("### Running information requests.")
    rr = client.read_device_information(device_id=DEVICE_ID, read_code=1, object_id=0)
    assert not rr.isError()  # test that call was OK
    assert rr.information[0] == b"Pymodbus"

    rr = client.report_device_id(device_id=DEVICE_ID)
    assert not rr.isError()  # test that call was OK
    assert rr.status

    rr = client.read_exception_status(device_id=DEVICE_ID)
    assert not rr.isError()  # test that call was OK
    assert not rr.status

    rr = client.diag_get_comm_event_counter(device_id=DEVICE_ID)
    assert not rr.isError()  # test that call was OK
    assert rr.status
    assert not rr.count

    rr = client.diag_get_comm_event_log(device_id=DEVICE_ID)
    assert not rr.isError()  # test that call was OK
    assert rr.status
    assert not (rr.event_count + rr.message_count + len(rr.events))


def execute_diagnostic_requests(client):
    """Execute extended diagnostic requests."""
    _logger.info("### Running diagnostic requests.")
    # NOT WORKING: ONLY SYNC
    # message = b"OK"
    # rr = client.diag_query_data(msg=message, device_id=DEVICE_ID)
    # assert not rr.isError()  # test that call was OK
    # assert rr.message == message

    rr = client.diag_restart_communication(True, device_id=DEVICE_ID)
    assert not rr.isError()  # test that call was OK
    rr = client.diag_read_diagnostic_register(device_id=DEVICE_ID)
    assert not rr.isError()  # test that call was OK
    rr = client.diag_change_ascii_input_delimeter(device_id=DEVICE_ID)
    assert not rr.isError()  # test that call was OK
    rr = client.diag_clear_counters()
    assert not rr.isError()  # test that call was OK
    rr = client.diag_read_bus_comm_error_count(device_id=DEVICE_ID)
    assert not rr.isError()  # test that call was OK
    rr = client.diag_read_bus_exception_error_count(device_id=DEVICE_ID)
    assert not rr.isError()  # test that call was OK
    rr = client.diag_read_device_message_count(device_id=DEVICE_ID)
    assert not rr.isError()  # test that call was OK
    rr = client.diag_read_device_no_response_count(device_id=DEVICE_ID)
    assert not rr.isError()  # test that call was OK
    rr = client.diag_read_device_nak_count(device_id=DEVICE_ID)
    assert not rr.isError()  # test that call was OK
    rr = client.diag_read_device_busy_count(device_id=DEVICE_ID)
    assert not rr.isError()  # test that call was OK
    rr = client.diag_read_bus_char_overrun_count(device_id=DEVICE_ID)
    assert not rr.isError()  # test that call was OK
    rr = client.diag_read_iop_overrun_count(device_id=DEVICE_ID)
    assert not rr.isError()  # test that call was OK
    rr = client.diag_clear_overrun_counter(device_id=DEVICE_ID)
    assert not rr.isError()  # test that call was OK
    # NOT WORKING rr = client.diag_getclear_modbus_response(device_id=DEVICE_ID)
    assert not rr.isError()  # test that call was OK
    # NOT WORKING: rr = client.diag_force_listen_only(device_id=DEVICE_ID)
    assert not rr.isError()  # test that call was OK



# ------------------------
# Run the calls in groups.
# ------------------------
def run_sync_calls(client):
    """Demonstrate basic read/write calls."""
    template_call(client)
    handle_coils(client)
    handle_discrete_input(client)
    handle_holding_registers(client)
    handle_input_registers(client)
    handle_file_records(client)
    execute_information_requests(client)
    execute_diagnostic_requests(client)


def main(cmdline=None):
    """Combine setup and run."""
    client = client_sync.setup_sync_client(
        description="Run synchronous client.", cmdline=cmdline
    )
    client_sync.run_sync_client(client, modbus_calls=run_sync_calls)


if __name__ == "__main__":
    main()

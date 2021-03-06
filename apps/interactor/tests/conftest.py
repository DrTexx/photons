from interactor.options import Options
from interactor.server import Server

from photons_app.formatter import MergedOptionStringFormatter
from photons_app import helpers as hp

from photons_control import test_helpers as chp
from photons_transport.fake import FakeDevice
from photons_products import Products

from whirlwind import test_helpers as wthp
from unittest import mock
import tempfile
import logging
import asyncio
import pytest
import shutil
import uuid

log = logging.getLogger("interactor.test_helpers")


class Asserter:
    def assertEqual(s, a, b, msg=None):
        __tracebackhide__ = True
        if msg:
            assert a == b, msg
        else:
            assert a == b

    def assertIs(s, a, b, msg=None):
        __tracebackhide__ = True
        if msg:
            assert a is b, msg
        else:
            assert a is b


@pytest.fixture(scope="session")
def asserter():
    return Asserter()


@pytest.fixture(scope="session")
def temp_dir_maker():
    class Maker:
        def __enter__(s):
            s.dir = tempfile.mkdtemp()
            return s.dir

        def __exit__(s, exc_type, exc, tb):
            if hasattr(s, "dir") and s.dir:
                shutil.rmtree(s.dir)

    return Maker


@pytest.fixture(scope="session")
async def server_wrapper():
    return ServerWrapper


@pytest.fixture(scope="session")
def options_maker():
    return make_options


def make_options(host=None, port=None, database=None, memory=True):
    options = {}
    if database or memory:
        options = {"database": database or {"uri": ":memory:"}}

    if host is not None:
        options["host"] = host

    if port is not None:
        options["port"] = port

    return Options.FieldSpec(formatter=MergedOptionStringFormatter).empty_normalise(**options)


async def make_server_runner(store, target_register=None, **kwargs):
    final_future = hp.create_future(name="server_runner.final_future")

    options = make_options("127.0.0.1", wthp.free_port(), **kwargs)

    targetrunner = chp.MemoryTargetRunner(final_future, fakery.devices)
    await targetrunner.start()

    cleaners = []
    server = Server(final_future, store=store)

    runner = ServerRunner(
        final_future, options.port, server, None, fakery, options, targetrunner.sender, cleaners,
    )
    return runner, server, options


class ServerRunner(wthp.ServerRunner):
    def setup(self, fake, *args, **kwargs):
        self.fake = fake
        self.options = args[0]
        super().setup(*args, **kwargs)

    async def after_close(self, exc_typ, exc, tb):
        if hasattr(self.server.finder.finish, "mock_calls"):
            assert len(self.server.finder.finish.mock_calls) == 0

        for thing in self.server.cleaners:
            try:
                await thing()
            except:
                pass

        # Prevent coroutine not awaited error
        await asyncio.sleep(0.01)

        if hasattr(self.server.finder.finish, "mock_calls"):
            self.server.finder.finish.assert_called_once_with()


class ServerWrapper:
    def __init__(self, store, **kwargs):
        self.store = store
        self.kwargs = kwargs

    async def __aenter__(self):
        return await self.start()

    async def start(self):
        self.runner, self.server, self.options = await make_server_runner(self.store, **self.kwargs)
        await self.runner.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.finish()

    async def finish(self):
        await hp.wait_for_all_futures(hp.async_as_background(self.runner.close(None, None, None)))

    def test_wrap(self):
        class Wrap:
            async def __aenter__(s):
                for device in fakery.devices:
                    await device.reset()

            async def __aexit__(s, exc_typ, exc, tb):
                pass

        return Wrap()

    def ws_stream(self):
        class WSStream(wthp.WSStream):
            async def start(s, command, serial, **other_args):
                s.message_id = str(uuid.uuid1())
                body = {"command": command, "args": {"serial": serial, **other_args}}
                await s.server.ws_write(
                    s.connection,
                    {"path": "/v1/lifx/command", "body": body, "message_id": s.message_id},
                )

        return WSStream(self.runner, Asserter())

    async def assertCommand(
        self, command, status=200, json_output=None, text_output=None, timeout=None
    ):
        return await self.runner.assertPUT(
            Asserter(),
            "/v1/lifx/command",
            command,
            status=status,
            json_output=json_output,
            text_output=text_output,
        )


identifier = lambda: str(uuid.uuid4()).replace("-", "")

group_one_label = "Living Room"
group_one_uuid = identifier()

group_two_label = "Bathroom"
group_two_uuid = identifier()

group_three_label = "desk"
group_three_uuid = identifier()

location_one_label = "Home"
location_one_uuid = identifier()

location_two_label = "Work"
location_two_uuid = identifier()

zones = []
for i in range(16):
    zones.append(chp.Color(i * 10, 1, 1, 2500))


class FakeDevice(FakeDevice):
    def compare_received_set(self, expected, keep_duplicates=False):
        self.received = [m for m in self.received if m.__class__.__name__.startswith("Set")]
        super().compare_received(expected, keep_duplicates=keep_duplicates)

    def expect_no_set_messages(self):
        assert not any([m for m in self.received if m.__class__.__name__.startswith("Set")])


a19_1 = FakeDevice(
    "d073d5000001",
    chp.default_responders(
        Products.LCM2_A19,
        label="kitchen",
        power=0,
        group_label=group_one_label,
        group_uuid=group_one_uuid,
        location_label=location_one_label,
        location_uuid=location_one_uuid,
        color=chp.Color(0, 1, 1, 2500),
        firmware=chp.Firmware(2, 75, 1521690429),
    ),
)

a19_2 = FakeDevice(
    "d073d5000002",
    chp.default_responders(
        Products.LCM2_A19,
        label="bathroom",
        power=65535,
        color=chp.Color(100, 1, 1, 2500),
        group_label=group_two_label,
        group_uuid=group_two_uuid,
        location_label=location_one_label,
        location_uuid=location_one_uuid,
        firmware=chp.Firmware(2, 75, 1521690429),
    ),
)

color1000 = FakeDevice(
    "d073d5000003",
    chp.default_responders(
        Products.LCMV4_A19_COLOR,
        label="lamp",
        power=65535,
        color=chp.Color(100, 0, 1, 2500),
        group_label=group_three_label,
        group_uuid=group_three_uuid,
        location_label=location_two_label,
        location_uuid=location_two_uuid,
        firmware=chp.Firmware(1, 1, 1530327089),
    ),
)

white800 = FakeDevice(
    "d073d5000004",
    chp.default_responders(
        Products.LCMV4_A19_WHITE_LV,
        label="lamp",
        power=65535,
        color=chp.Color(100, 0, 1, 2500),
        group_label=group_three_label,
        group_uuid=group_three_uuid,
        location_label=location_two_label,
        location_uuid=location_two_uuid,
        firmware=chp.Firmware(1, 1, 1530327089),
    ),
)

strip1 = FakeDevice(
    "d073d5000005",
    chp.default_responders(
        Products.LCM2_Z,
        label="desk",
        power=65535,
        zones=zones,
        color=chp.Color(200, 0.5, 0.5, 2500),
        group_label=group_one_label,
        group_uuid=group_one_uuid,
        location_label=location_one_label,
        location_uuid=location_one_uuid,
        firmware=chp.Firmware(2, 75, 1521690429),
    ),
)

strip2 = FakeDevice(
    "d073d5000006",
    chp.default_responders(
        Products.LCM1_Z,
        label="tv",
        power=65535,
        zones=zones,
        color=chp.Color(200, 0.5, 0.5, 2500),
        group_label=group_three_label,
        group_uuid=group_three_uuid,
        location_label=location_two_label,
        location_uuid=location_two_uuid,
        firmware=chp.Firmware(1, 1, 1530327089),
    ),
)

candle = FakeDevice(
    "d073d5000007",
    chp.default_responders(
        Products.LCM3_CANDLE,
        label="pretty",
        power=65535,
        group_label=group_three_label,
        group_uuid=group_three_uuid,
        location_label=location_two_label,
        location_uuid=location_two_uuid,
        firmware=chp.Firmware(3, 50, 1562659776000000000),
    ),
)


class Fakery:
    def __init__(self):
        self.devices = [a19_1, a19_2, color1000, white800, strip1, strip2, candle]

    def for_attribute(self, key, value, expect=1):
        got = []
        for d in self.devices:
            if d.attrs[key] == value:
                got.append(d)
        assert len(got) == expect, f"Expected {expect} devices, got {len(got)}: {got}"
        return got

    def for_serial(self, serial):
        for d in self.devices:
            if d.serial == serial:
                return d
        assert False, f"Expected one device with serial {serial}"


fakery = Fakery()


class Around:
    def __init__(self, val, gap=0.05):
        self.val = val
        self.gap = gap

    def __eq__(self, other):
        return other - self.gap < self.val < other + self.gap

    def __repr__(self):
        return f"<Around {self.val}>"


discovery_response = {
    "d073d5000001": {
        "brightness": 1.0,
        "cap": [
            "color",
            "not_chain",
            "not_ir",
            "not_matrix",
            "not_multizone",
            "variable_color_temp",
        ],
        "firmware_version": "2.75",
        "group_id": mock.ANY,
        "group_name": "Living Room",
        "hue": 0.0,
        "kelvin": 2500,
        "label": "kitchen",
        "location_id": mock.ANY,
        "location_name": "Home",
        "power": "off",
        "product_id": 27,
        "product_identifier": "lifx_a19",
        "saturation": 1.0,
        "serial": "d073d5000001",
    },
    "d073d5000002": {
        "brightness": 1.0,
        "cap": [
            "color",
            "not_chain",
            "not_ir",
            "not_matrix",
            "not_multizone",
            "variable_color_temp",
        ],
        "firmware_version": "2.75",
        "group_id": mock.ANY,
        "group_name": "Bathroom",
        "hue": Around(100),
        "kelvin": 2500,
        "label": "bathroom",
        "location_id": mock.ANY,
        "location_name": "Home",
        "power": "on",
        "product_id": 27,
        "product_identifier": "lifx_a19",
        "saturation": 1.0,
        "serial": "d073d5000002",
    },
    "d073d5000003": {
        "brightness": 1.0,
        "cap": [
            "color",
            "not_chain",
            "not_ir",
            "not_matrix",
            "not_multizone",
            "variable_color_temp",
        ],
        "firmware_version": "1.1",
        "group_id": mock.ANY,
        "group_name": "desk",
        "hue": Around(100),
        "kelvin": 2500,
        "label": "lamp",
        "location_id": mock.ANY,
        "location_name": "Work",
        "power": "on",
        "product_id": 22,
        "product_identifier": "lifx_a19_color",
        "saturation": 0.0,
        "serial": "d073d5000003",
    },
    "d073d5000004": {
        "brightness": 1.0,
        "cap": [
            "not_chain",
            "not_color",
            "not_ir",
            "not_matrix",
            "not_multizone",
            "variable_color_temp",
        ],
        "firmware_version": "1.1",
        "group_id": mock.ANY,
        "group_name": "desk",
        "hue": Around(100),
        "kelvin": 2500,
        "label": "lamp",
        "location_id": mock.ANY,
        "location_name": "Work",
        "power": "on",
        "product_id": 10,
        "product_identifier": "lifx_a19_white",
        "saturation": 0.0,
        "serial": "d073d5000004",
    },
    "d073d5000005": {
        "brightness": Around(0.5),
        "cap": ["color", "multizone", "not_chain", "not_ir", "not_matrix", "variable_color_temp"],
        "firmware_version": "2.75",
        "group_id": mock.ANY,
        "group_name": "Living Room",
        "hue": Around(200),
        "kelvin": 2500,
        "label": "desk",
        "location_id": mock.ANY,
        "location_name": "Home",
        "power": "on",
        "product_id": 32,
        "product_identifier": "lifx_z",
        "saturation": Around(0.5),
        "serial": "d073d5000005",
    },
    "d073d5000006": {
        "brightness": Around(0.5),
        "cap": ["color", "multizone", "not_chain", "not_ir", "not_matrix", "variable_color_temp"],
        "firmware_version": "1.1",
        "group_id": mock.ANY,
        "group_name": "desk",
        "hue": Around(200),
        "kelvin": 2500,
        "label": "tv",
        "location_id": mock.ANY,
        "location_name": "Work",
        "power": "on",
        "product_id": 31,
        "product_identifier": "lifx_z",
        "saturation": Around(0.5),
        "serial": "d073d5000006",
    },
    "d073d5000007": {
        "brightness": 1.0,
        "cap": ["color", "matrix", "not_chain", "not_ir", "not_multizone", "variable_color_temp"],
        "firmware_version": "3.50",
        "group_id": mock.ANY,
        "group_name": "desk",
        "hue": 0.0,
        "kelvin": 3500,
        "label": "pretty",
        "location_id": mock.ANY,
        "location_name": "Work",
        "power": "on",
        "product_id": 57,
        "product_identifier": "lifx_candle",
        "saturation": 1.0,
        "serial": "d073d5000007",
    },
}

light_state_responses = {
    "results": {
        "d073d5000001": {
            "payload": {
                "brightness": 1.0,
                "hue": 0.0,
                "kelvin": 2500,
                "label": "kitchen",
                "power": 0,
                "saturation": 1.0,
            },
            "pkt_name": "LightState",
            "pkt_type": 107,
        },
        "d073d5000002": {
            "payload": {
                "brightness": 1.0,
                "hue": Around(100),
                "kelvin": 2500,
                "label": "bathroom",
                "power": 65535,
                "saturation": 1.0,
            },
            "pkt_name": "LightState",
            "pkt_type": 107,
        },
        "d073d5000003": {
            "payload": {
                "brightness": 1.0,
                "hue": Around(100),
                "kelvin": 2500,
                "label": "lamp",
                "power": 65535,
                "saturation": 0.0,
            },
            "pkt_name": "LightState",
            "pkt_type": 107,
        },
        "d073d5000004": {
            "payload": {
                "brightness": 1.0,
                "hue": Around(100),
                "kelvin": 2500,
                "label": "lamp",
                "power": 65535,
                "saturation": 0.0,
            },
            "pkt_name": "LightState",
            "pkt_type": 107,
        },
        "d073d5000005": {
            "payload": {
                "brightness": Around(0.5),
                "hue": Around(200),
                "kelvin": 2500,
                "label": "desk",
                "power": 65535,
                "saturation": Around(0.5),
            },
            "pkt_name": "LightState",
            "pkt_type": 107,
        },
        "d073d5000006": {
            "payload": {
                "brightness": Around(0.5),
                "hue": Around(200),
                "kelvin": 2500,
                "label": "tv",
                "power": 65535,
                "saturation": Around(0.5),
            },
            "pkt_name": "LightState",
            "pkt_type": 107,
        },
        "d073d5000007": {
            "payload": {
                "brightness": 1.0,
                "hue": 0.0,
                "kelvin": 3500,
                "label": "pretty",
                "power": 65535,
                "saturation": 1.0,
            },
            "pkt_name": "LightState",
            "pkt_type": 107,
        },
    }
}

label_state_responses = {
    "results": {
        "d073d5000001": {"payload": {"label": "kitchen"}, "pkt_name": "StateLabel", "pkt_type": 25},
        "d073d5000002": {
            "payload": {"label": "bathroom"},
            "pkt_name": "StateLabel",
            "pkt_type": 25,
        },
        "d073d5000003": {"payload": {"label": "lamp"}, "pkt_name": "StateLabel", "pkt_type": 25},
        "d073d5000004": {"payload": {"label": "lamp"}, "pkt_name": "StateLabel", "pkt_type": 25},
        "d073d5000005": {"payload": {"label": "desk"}, "pkt_name": "StateLabel", "pkt_type": 25},
        "d073d5000006": {"payload": {"label": "tv"}, "pkt_name": "StateLabel", "pkt_type": 25},
        "d073d5000007": {"payload": {"label": "pretty"}, "pkt_name": "StateLabel", "pkt_type": 25},
    }
}

multizone_state_responses = {
    "results": {
        "d073d5000005": [
            {
                "payload": {
                    "colors": [
                        {"brightness": 1.0, "hue": 0.0, "kelvin": 2500, "saturation": 1.0},
                        {"brightness": 1.0, "hue": Around(10), "kelvin": 2500, "saturation": 1.0},
                        {"brightness": 1.0, "hue": Around(20), "kelvin": 2500, "saturation": 1.0},
                        {"brightness": 1.0, "hue": Around(30), "kelvin": 2500, "saturation": 1.0},
                        {"brightness": 1.0, "hue": Around(40), "kelvin": 2500, "saturation": 1.0},
                        {"brightness": 1.0, "hue": Around(50), "kelvin": 2500, "saturation": 1.0},
                        {"brightness": 1.0, "hue": Around(60), "kelvin": 2500, "saturation": 1.0},
                        {"brightness": 1.0, "hue": Around(70), "kelvin": 2500, "saturation": 1.0},
                    ],
                    "zones_count": 16,
                    "zone_index": 0,
                },
                "pkt_name": "StateMultiZone",
                "pkt_type": 506,
            },
            {
                "payload": {
                    "colors": [
                        {"brightness": 1.0, "hue": Around(80), "kelvin": 2500, "saturation": 1.0},
                        {"brightness": 1.0, "hue": Around(90), "kelvin": 2500, "saturation": 1.0},
                        {"brightness": 1.0, "hue": Around(100), "kelvin": 2500, "saturation": 1.0},
                        {"brightness": 1.0, "hue": Around(110), "kelvin": 2500, "saturation": 1.0},
                        {"brightness": 1.0, "hue": Around(120), "kelvin": 2500, "saturation": 1.0},
                        {"brightness": 1.0, "hue": Around(130), "kelvin": 2500, "saturation": 1.0},
                        {"brightness": 1.0, "hue": Around(140), "kelvin": 2500, "saturation": 1.0},
                        {"brightness": 1.0, "hue": Around(150), "kelvin": 2500, "saturation": 1.0},
                    ],
                    "zones_count": 16,
                    "zone_index": 8,
                },
                "pkt_name": "StateMultiZone",
                "pkt_type": 506,
            },
        ],
        "d073d5000006": [
            {
                "payload": {
                    "colors": [
                        {"brightness": 1.0, "hue": 0.0, "kelvin": 2500, "saturation": 1.0},
                        {"brightness": 1.0, "hue": Around(10), "kelvin": 2500, "saturation": 1.0},
                        {"brightness": 1.0, "hue": Around(20), "kelvin": 2500, "saturation": 1.0},
                        {"brightness": 1.0, "hue": Around(30), "kelvin": 2500, "saturation": 1.0},
                        {"brightness": 1.0, "hue": Around(40), "kelvin": 2500, "saturation": 1.0},
                        {"brightness": 1.0, "hue": Around(50), "kelvin": 2500, "saturation": 1.0},
                        {"brightness": 1.0, "hue": Around(60), "kelvin": 2500, "saturation": 1.0},
                        {"brightness": 1.0, "hue": Around(70), "kelvin": 2500, "saturation": 1.0},
                    ],
                    "zones_count": 16,
                    "zone_index": 0,
                },
                "pkt_name": "StateMultiZone",
                "pkt_type": 506,
            },
            {
                "payload": {
                    "colors": [
                        {"brightness": 1.0, "hue": Around(80), "kelvin": 2500, "saturation": 1.0},
                        {"brightness": 1.0, "hue": Around(90), "kelvin": 2500, "saturation": 1.0},
                        {"brightness": 1.0, "hue": Around(100), "kelvin": 2500, "saturation": 1.0},
                        {"brightness": 1.0, "hue": Around(110), "kelvin": 2500, "saturation": 1.0},
                        {"brightness": 1.0, "hue": Around(120), "kelvin": 2500, "saturation": 1.0},
                        {"brightness": 1.0, "hue": Around(130), "kelvin": 2500, "saturation": 1.0},
                        {"brightness": 1.0, "hue": Around(140), "kelvin": 2500, "saturation": 1.0},
                        {"brightness": 1.0, "hue": Around(150), "kelvin": 2500, "saturation": 1.0},
                    ],
                    "zones_count": 16,
                    "zone_index": 8,
                },
                "pkt_name": "StateMultiZone",
                "pkt_type": 506,
            },
        ],
    }
}


@pytest.fixture(scope="session")
def fake():
    return fakery


@pytest.fixture(scope="session")
def responses():
    class Responses:
        def __init__(s):
            s.discovery_response = discovery_response
            s.light_state_responses = light_state_responses
            s.multizone_state_responses = multizone_state_responses
            s.label_state_responses = label_state_responses

    return Responses()

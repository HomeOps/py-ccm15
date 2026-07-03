import unittest
from unittest.mock import patch, MagicMock

import httpx

from ccm15 import (
    CCM15Device,
    CCM15DeviceState,
    CCM15ReturnCode,
    CCM15SlaveDevice,
    TriState,
)


class TestCCM15(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.ccm = CCM15Device("localhost", 8000)

    @patch("httpx.AsyncClient.get")
    async def test_get_status_async(self, mock_get) -> None:
        """Contiguous active slots starting at 0."""
        mock_response = MagicMock()
        mock_response.text = """
        <response>
            <a0>00000001020304,</a0>
            <a1>00000005060708,</a1>
        </response>
        """
        mock_get.return_value = mock_response

        state = await self.ccm.get_status_async()
        self.assertIsInstance(state, CCM15DeviceState)
        self.assertEqual(set(state.devices.keys()), {0, 1})
        self.assertIsInstance(state.devices[0], CCM15SlaveDevice)
        self.assertIsInstance(state.devices[1], CCM15SlaveDevice)

    @patch("httpx.AsyncClient.get")
    async def test_get_status_async_noncontiguous(self, mock_get) -> None:
        """Empty slots before and between active slots must not truncate parsing."""
        mock_response = MagicMock()
        mock_response.text = """
        <response>
            <a0>-</a0>
            <a1>-</a1>
            <a2>00000001020304,</a2>
            <a3>-</a3>
            <a4>00000005060708,</a4>
        </response>
        """
        mock_get.return_value = mock_response

        state = await self.ccm.get_status_async()
        self.assertEqual(set(state.devices.keys()), {2, 4})

    @patch("httpx.AsyncClient.get")
    async def test_get_status_async_skips_malformed_entries(self, mock_get) -> None:
        """A non-slot key or a non-hex payload is skipped, not fatal."""
        mock_response = MagicMock()
        mock_response.text = """
        <response>
            <a0>00000001020304,</a0>
            <a1>nothexdata</a1>
            <bogus>00000005060708,</bogus>
        </response>
        """
        mock_get.return_value = mock_response

        state = await self.ccm.get_status_async()
        self.assertEqual(set(state.devices.keys()), {0})

    @patch("httpx.AsyncClient.get")
    async def test_empty_response_serves_cached_state(self, mock_get) -> None:
        """A transient all-'-' body returns the last good state, not empty."""
        good = MagicMock()
        good.text = "<response><a0>00000001020304,</a0></response>"
        empty = MagicMock()
        empty.text = "<response><a0>-</a0></response>"
        mock_get.side_effect = [good, empty]

        first = await self.ccm.get_status_async()
        self.assertEqual(set(first.devices.keys()), {0})
        self.assertEqual(first.devices[0].age, 0.0)  # live read
        # Age the last good read deterministically: back-to-back calls can land
        # inside a single time.monotonic() tick (coarse on some platforms), so
        # don't rely on wall-clock elapsing to prove the cached read is stamped.
        self.ccm._slot_seen[0] -= 5
        second = await self.ccm.get_status_async()
        self.assertEqual(set(second.devices.keys()), {0})
        self.assertIs(second.devices[0], first.devices[0])  # same cached device
        self.assertGreaterEqual(second.devices[0].age, 5.0)  # stamped as stale

    @patch("httpx.AsyncClient.get")
    async def test_exception_serves_cached_state(self, mock_get) -> None:
        """A transient fetch error returns the last good state, not a raise."""
        good = MagicMock()
        good.text = "<response><a0>00000001020304,</a0></response>"
        mock_get.side_effect = [good, httpx.ConnectTimeout("boom")]

        first = await self.ccm.get_status_async()
        second = await self.ccm.get_status_async()
        self.assertEqual(set(second.devices.keys()), {0})
        self.assertIs(second.devices[0], first.devices[0])

    @patch("httpx.AsyncClient.get")
    async def test_cache_expires_after_ttl(self, mock_get) -> None:
        """Past the TTL the real failure surfaces (exception propagates)."""
        ccm = CCM15Device("localhost", 8000, state_ttl=300)
        good = MagicMock()
        good.text = "<response><a0>00000001020304,</a0></response>"
        mock_get.side_effect = [good, httpx.ConnectTimeout("boom")]

        await ccm.get_status_async()
        # Backdate the last good read past the TTL window.
        ccm._slot_seen[0] -= 301
        with self.assertRaises(httpx.ConnectTimeout):
            await ccm.get_status_async()

    @patch("httpx.AsyncClient.get")
    async def test_ttl_zero_disables_cache(self, mock_get) -> None:
        """state_ttl=0 opts out: empty responses return empty state."""
        ccm = CCM15Device("localhost", 8000, state_ttl=0)
        good = MagicMock()
        good.text = "<response><a0>00000001020304,</a0></response>"
        empty = MagicMock()
        empty.text = "<response><a0>-</a0></response>"
        mock_get.side_effect = [good, empty, httpx.ConnectTimeout("boom")]

        await ccm.get_status_async()
        second = await ccm.get_status_async()
        self.assertEqual(second.devices, {})
        # With caching off, a fetch error is never masked either.
        with self.assertRaises(httpx.ConnectTimeout):
            await ccm.get_status_async()

    @patch("httpx.AsyncClient.get")
    async def test_single_slot_dropout_backfills_from_cache(self, mock_get) -> None:
        """One slot reported '-' for a poll is served from cache, not dropped."""
        both = MagicMock()
        both.text = (
            "<response><a2>00000001020304,</a2>"
            "<a4>00000005060708,</a4></response>"
        )
        # a4 momentarily drops out while a2 keeps decoding live.
        partial = MagicMock()
        partial.text = "<response><a2>00000001020304,</a2><a4>-</a4></response>"
        mock_get.side_effect = [both, partial]

        first = await self.ccm.get_status_async()
        self.assertEqual(set(first.devices.keys()), {2, 4})
        self.ccm._slot_seen[4] -= 5  # age slot 4's cache deterministically

        second = await self.ccm.get_status_async()
        self.assertEqual(set(second.devices.keys()), {2, 4})  # 4 backfilled
        self.assertEqual(second.devices[2].age, 0.0)  # live
        self.assertIs(second.devices[4], first.devices[4])  # cached object
        self.assertGreaterEqual(second.devices[4].age, 5.0)  # stamped stale

    @patch("httpx.AsyncClient.get")
    async def test_single_slot_dropout_expires_after_ttl(self, mock_get) -> None:
        """A slot missing longer than the TTL is dropped, not kept forever."""
        both = MagicMock()
        both.text = (
            "<response><a2>00000001020304,</a2>"
            "<a4>00000005060708,</a4></response>"
        )
        partial = MagicMock()
        partial.text = "<response><a2>00000001020304,</a2><a4>-</a4></response>"
        mock_get.side_effect = [both, partial]

        await self.ccm.get_status_async()
        self.ccm._slot_seen[4] -= 301  # past the default 300 s TTL

        second = await self.ccm.get_status_async()
        self.assertEqual(set(second.devices.keys()), {2})  # 4 aged out

    @patch("httpx.AsyncClient.get")
    async def test_returning_slot_refreshes_ttl(self, mock_get) -> None:
        """A slot returning live resets its clock so it can't expire mid-backfill."""
        both = MagicMock()
        both.text = (
            "<response><a2>00000001020304,</a2>"
            "<a4>00000005060708,</a4></response>"
        )
        partial = MagicMock()
        partial.text = "<response><a2>00000001020304,</a2><a4>-</a4></response>"
        mock_get.side_effect = [both, both, partial]

        await self.ccm.get_status_async()
        self.ccm._slot_seen[4] -= 299  # nearly stale...
        await self.ccm.get_status_async()  # ...but slot 4 decodes live again
        self.ccm._slot_seen[4] -= 5  # only 5 s old now, well inside the TTL

        third = await self.ccm.get_status_async()
        self.assertEqual(set(third.devices.keys()), {2, 4})

    @patch("httpx.AsyncClient.get")
    async def test_mass_partial_dropout_keeps_all_slots(self, mock_get) -> None:
        """Real repro: 5 of 6 slots blink to '-' at once; all 6 stay available."""
        full = MagicMock()
        full.text = "<response>" + "".join(
            f"<a{i}>0000000{i}020304,</a{i}>" for i in range(6)
        ) + "</response>"
        # Only a0 still decodes; a1-a5 drop to '-' in the same poll.
        degraded = MagicMock()
        degraded.text = (
            "<response><a0>00000000020304,</a0>"
            + "".join(f"<a{i}>-</a{i}>" for i in range(1, 6))
            + "</response>"
        )
        mock_get.side_effect = [full, degraded]

        first = await self.ccm.get_status_async()
        self.assertEqual(set(first.devices.keys()), {0, 1, 2, 3, 4, 5})

        second = await self.ccm.get_status_async()
        # Without the per-slot cache this would be just {0}; now all 6 survive.
        self.assertEqual(set(second.devices.keys()), {0, 1, 2, 3, 4, 5})
        self.assertEqual(second.devices[0].age, 0.0)  # the one live slot
        self.assertGreaterEqual(second.devices[5].age, 0.0)  # back-filled

    @patch("httpx.AsyncClient.get")
    async def test_live_reread_updates_same_instance(self, mock_get) -> None:
        """A slot decoding live again updates its existing object, not a new one.

        Only the first sighting of a slot constructs a CCM15SlaveDevice; every
        later live poll updates that same instance in place, so a consumer that
        holds a reference to a device keeps seeing fresh data through it.
        """
        first_resp = MagicMock()
        first_resp.text = "<response><a0>00000041d2001a,</a0></response>"  # swing on, 26
        second_resp = MagicMock()
        second_resp.text = "<response><a0>00000041d00018,</a0></response>"  # swing off, 24
        mock_get.side_effect = [first_resp, second_resp]

        first = await self.ccm.get_status_async()
        obj = first.devices[0]
        self.assertTrue(obj.is_swing_on)
        self.assertEqual(26, obj.temperature)

        second = await self.ccm.get_status_async()
        self.assertIs(second.devices[0], obj)  # same instance, updated in place
        self.assertFalse(second.devices[0].is_swing_on)  # re-decoded from new bytes
        self.assertEqual(24, second.devices[0].temperature)
        self.assertEqual(0.0, second.devices[0].age)  # live read

    @patch("httpx.AsyncClient.get")
    async def test_async_set_state_low_slot(self, mock_get):
        """Slots 0-31 go into ac0, ac1 is 0."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ""
        mock_get.return_value = mock_response

        data = MagicMock(ac_mode=0, fan_mode=0, temperature_setpoint=24)
        self.assertEqual(
            await self.ccm.async_set_state(4, data), CCM15ReturnCode.OK
        )

        called_url = mock_get.call_args.args[0]
        self.assertIn("ac0=16", called_url)  # 2 ** 4
        self.assertIn("ac1=0", called_url)

    @patch("httpx.AsyncClient.get")
    async def test_async_set_state_high_slot(self, mock_get):
        """Slots 32-63 go into ac1, ac0 is 0."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ""
        mock_get.return_value = mock_response

        data = MagicMock(ac_mode=0, fan_mode=0, temperature_setpoint=24)
        self.assertEqual(
            await self.ccm.async_set_state(40, data), CCM15ReturnCode.OK
        )

        called_url = mock_get.call_args.args[0]
        self.assertIn("ac0=0", called_url)
        self.assertIn("ac1=256", called_url)  # 2 ** (40 - 32)

    @patch("httpx.AsyncClient.get")
    async def test_async_set_state_sends_full_state(self, mock_get):
        """Regression test for #15.

        The CCM15 treats every ctrl.xml write as the complete desired state and
        resets any omitted field to its default (which lands on COOL). So a
        single set must always carry mode, fan AND temp together, using the
        caller's current values. Here the unit is in HEAT (mode=1) with a
        non-default fan; all three must appear in the command, otherwise the
        controller would revert to COOL.
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ""
        mock_get.return_value = mock_response

        data = MagicMock(ac_mode=1, fan_mode=2, temperature_setpoint=26)
        self.assertEqual(
            await self.ccm.async_set_state(0, data), CCM15ReturnCode.OK
        )

        called_url = mock_get.call_args.args[0]
        self.assertIn("mode=1", called_url)  # HEAT preserved, not reset to COOL
        self.assertIn("fan=2", called_url)
        self.assertIn("temp=26", called_url)

    @patch("httpx.AsyncClient.get")
    async def test_async_set_state_active_mode_uses_auto_fan_when_fan_off(
        self, mock_get
    ):
        """An active mode with fan off is sent with auto fan.

        The controller treats each write as the complete desired state. Some
        firmwares do not start an active HVAC mode when the same command also
        carries fan=off, so the library normalizes that wire command to
        fan=auto.
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ""
        mock_get.return_value = mock_response

        data = MagicMock(ac_mode=0, fan_mode=5, temperature_setpoint=26)
        self.assertEqual(
            await self.ccm.async_set_state(0, data), CCM15ReturnCode.OK
        )

        called_url = mock_get.call_args.args[0]
        self.assertIn("mode=0", called_url)
        self.assertIn("fan=0", called_url)
        self.assertIn("temp=26", called_url)
        self.assertEqual(data.fan_mode, 5)

    @patch("httpx.AsyncClient.get")
    async def test_async_set_state_off_mode_preserves_fan_off(self, mock_get):
        """An off command can still carry fan off."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ""
        mock_get.return_value = mock_response

        data = MagicMock(ac_mode=4, fan_mode=5, temperature_setpoint=26)
        self.assertEqual(
            await self.ccm.async_set_state(0, data), CCM15ReturnCode.OK
        )

        called_url = mock_get.call_args.args[0]
        self.assertIn("mode=4", called_url)
        self.assertIn("fan=5", called_url)

    @patch("httpx.AsyncClient.get")
    async def test_set_state_url_obfuscates_password(self, mock_get):
        """The configured password is XOR-obfuscated on the wire, with a nonce.

        The factory default 123456 must go out as pwd=296393
        (0x1E240 ^ 0x56789 = 0x485C9 = 296393), matching the controller's own
        pwdstr(). The user-facing value (123456) must never appear in the URL.
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ""
        mock_get.return_value = mock_response

        device = CCM15Device("localhost", 8000, password="123456")
        data = MagicMock(ac_mode=0, fan_mode=4, temperature_setpoint=22)
        self.assertEqual(
            await device.async_set_state(1, data), CCM15ReturnCode.OK
        )

        called_url = mock_get.call_args.args[0]
        self.assertIn("pwd=296393", called_url)
        self.assertNotIn("pwd=123456", called_url)  # raw value never sent
        self.assertIn("utsxxx=", called_url)  # nonce included
        self.assertIn("ac0=2", called_url)  # 2 ** 1

    @patch("httpx.AsyncClient.get")
    async def test_set_state_url_omits_password_when_unset(self, mock_get):
        """Without a password the URL must not include pwd or utsxxx."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ""
        mock_get.return_value = mock_response

        device = CCM15Device("localhost", 8000)
        data = MagicMock(ac_mode=1, fan_mode=2, temperature_setpoint=18)
        await device.async_set_state(0, data)

        called_url = mock_get.call_args.args[0]
        self.assertNotIn("pwd=", called_url)
        self.assertNotIn("utsxxx=", called_url)

    @patch("httpx.AsyncClient.get")
    async def test_set_state_returns_wrong_password(self, mock_get):
        """A <ret>250</ret> response maps to CCM15ReturnCode.WRONG_PASSWORD."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<response><ret>250</ret></response>"
        mock_get.return_value = mock_response

        device = CCM15Device("localhost", 8000, password="999999")
        data = MagicMock(ac_mode=0, fan_mode=0, temperature_setpoint=24)
        self.assertEqual(
            await device.async_set_state(0, data),
            CCM15ReturnCode.WRONG_PASSWORD,
        )

    @patch("httpx.AsyncClient.get")
    async def test_set_state_returns_connection_error_on_bad_status(self, mock_get):
        """A non-OK HTTP status maps to CCM15ReturnCode.CONNECTION_ERROR."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = ""
        mock_get.return_value = mock_response

        data = MagicMock(ac_mode=0, fan_mode=0, temperature_setpoint=24)
        self.assertEqual(
            await self.ccm.async_set_state(0, data),
            CCM15ReturnCode.CONNECTION_ERROR,
        )

    async def test_uses_injected_client_when_provided(self) -> None:
        """A client passed to the constructor is reused instead of building a new one."""
        injected = MagicMock(spec=httpx.AsyncClient)
        device = CCM15Device("localhost", 8000, client=injected)
        self.assertIs(device._get_client(), injected)

    async def test_builds_client_when_not_provided(self) -> None:
        """Standalone callers can still use the library without an injected client."""
        device = CCM15Device("localhost", 8000)
        client = device._get_client()
        self.assertIsInstance(client, httpx.AsyncClient)
        # Lazy creation is cached for the lifetime of the device.
        self.assertIs(device._get_client(), client)

    async def test_aclose_closes_self_built_client(self) -> None:
        """A client the library built is closed (no leak) on aclose()."""
        device = CCM15Device("localhost", 8000)
        built = device._get_client()
        await device.aclose()
        self.assertTrue(built.is_closed)
        self.assertIsNone(device._client)
        # Idempotent: a second close is a no-op, not an error.
        await device.aclose()

    async def test_aclose_leaves_injected_client_open(self) -> None:
        """An injected client is owned by the caller and must not be closed."""
        injected = httpx.AsyncClient()
        device = CCM15Device("localhost", 8000, client=injected)
        await device.aclose()
        self.assertFalse(injected.is_closed)
        self.assertIs(device._client, injected)
        await injected.aclose()

    async def test_context_manager_closes_self_built_client(self) -> None:
        """`async with CCM15Device(...)` closes a self-built client on exit."""
        async with CCM15Device("localhost", 8000) as device:
            built = device._get_client()
            self.assertFalse(built.is_closed)
        self.assertTrue(built.is_closed)

    @patch("httpx.AsyncClient.get")
    async def test_set_state_omits_swing_by_default(self, mock_get):
        """A freshly decoded device has desired_swing UNSET, so no sw is sent."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ""
        mock_get.return_value = mock_response

        data = CCM15SlaveDevice(bytes.fromhex("00000001020304"))
        self.assertIs(data.desired_swing, TriState.UNSET)
        await self.ccm.async_set_state(0, data)

        called_url = mock_get.call_args.args[0]
        self.assertNotIn("sw=", called_url)

    @patch("httpx.AsyncClient.get")
    async def test_set_state_sends_swing_on_when_desired(self, mock_get):
        """Setting desired_swing=ON emits sw=1."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ""
        mock_get.return_value = mock_response

        data = CCM15SlaveDevice(bytes.fromhex("00000001020304"))
        data.desired_swing = TriState.ON
        await self.ccm.async_set_state(1, data)

        called_url = mock_get.call_args.args[0]
        self.assertIn("sw=1", called_url)

    @patch("httpx.AsyncClient.get")
    async def test_set_state_sends_swing_off_when_desired(self, mock_get):
        """Setting desired_swing=OFF emits sw=0."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ""
        mock_get.return_value = mock_response

        data = CCM15SlaveDevice(bytes.fromhex("00000001020304"))
        data.desired_swing = TriState.OFF
        await self.ccm.async_set_state(0, data)

        called_url = mock_get.call_args.args[0]
        self.assertIn("sw=0", called_url)

    @patch("httpx.AsyncClient.get")
    async def test_set_state_omits_heater_by_default(self, mock_get):
        """A freshly decoded device has desired_heater UNSET, so no ht is sent."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ""
        mock_get.return_value = mock_response

        data = CCM15SlaveDevice(bytes.fromhex("00000001020304"))
        self.assertIs(data.desired_heater, TriState.UNSET)
        await self.ccm.async_set_state(0, data)

        called_url = mock_get.call_args.args[0]
        self.assertNotIn("ht=", called_url)

    @patch("httpx.AsyncClient.get")
    async def test_set_state_sends_heater_on_when_desired(self, mock_get):
        """Setting desired_heater=ON emits ht=1, independent of swing."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ""
        mock_get.return_value = mock_response

        data = CCM15SlaveDevice(bytes.fromhex("00000001020304"))
        data.desired_heater = TriState.ON
        await self.ccm.async_set_state(1, data)

        called_url = mock_get.call_args.args[0]
        self.assertIn("ht=1", called_url)
        self.assertNotIn("sw=", called_url)  # heater is independent of swing

    @patch("httpx.AsyncClient.get")
    async def test_set_state_sends_heater_off_when_desired(self, mock_get):
        """Setting desired_heater=OFF emits ht=0."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ""
        mock_get.return_value = mock_response

        data = CCM15SlaveDevice(bytes.fromhex("00000001020304"))
        data.desired_heater = TriState.OFF
        await self.ccm.async_set_state(0, data)

        called_url = mock_get.call_args.args[0]
        self.assertIn("ht=0", called_url)


class TestHeaterDecode(unittest.TestCase):
    def test_is_heater_on_decoded_from_byte4_bit0(self):
        # byte 4 bit 0 set -> heater on; clear -> off. Other bytes arbitrary.
        on = CCM15SlaveDevice(bytes.fromhex("00000000010000"))
        self.assertTrue(on.is_heater_on)
        off = CCM15SlaveDevice(bytes.fromhex("00000000000000"))
        self.assertFalse(off.is_heater_on)


class TestTriState(unittest.TestCase):
    def test_from_bool(self):
        self.assertIs(TriState.from_bool(None), TriState.UNSET)
        self.assertIs(TriState.from_bool(True), TriState.ON)
        self.assertIs(TriState.from_bool(False), TriState.OFF)

    def test_is_set(self):
        self.assertFalse(TriState.UNSET.is_set)
        self.assertTrue(TriState.ON.is_set)
        self.assertTrue(TriState.OFF.is_set)

    def test_values(self):
        # Wire values: ON -> "1", OFF -> "0".
        self.assertEqual(str(TriState.ON.value), "1")
        self.assertEqual(str(TriState.OFF.value), "0")


if __name__ == "__main__":
    unittest.main()

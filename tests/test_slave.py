import unittest
from ccm15 import CCM15SlaveDevice, TriState

class TestCCM15SlaveDevice(unittest.TestCase):
    def test_swing_mode_on(self) -> None:
        """Test that the swing mode is on."""
        data = bytes.fromhex("00000041d2001a")
        device = CCM15SlaveDevice(data)
        self.assertTrue(device.is_swing_on)

    def test_swing_mode_off(self) -> None:
        """Test that the swing mode is off."""
        data = bytes.fromhex("00000041d0001a")
        device = CCM15SlaveDevice(data)
        self.assertFalse(device.is_swing_on)

    def test_temp_fan_mode(self) -> None:
        """Test that the swing mode is on."""
        data = bytes.fromhex("00000041d2001a")
        device = CCM15SlaveDevice(data)
        self.assertEqual(26, device.temperature)
        self.assertEqual(2, device.fan_mode)
        self.assertEqual(0, device.ac_mode)

    def test_fahrenheit(self) -> None:
        """Test that farenheith bit."""

        data = bytearray.fromhex("81000041d2001a")
        device = CCM15SlaveDevice(data)
        self.assertEqual(False, device.is_celsius)
        self.assertEqual(88, device.temperature_setpoint)
        self.assertEqual(0, device.locked_cool_temperature)
        self.assertEqual(0, device.locked_heat_temperature)

    def test_all_fields_locked_and_negative_temp(self) -> None:
        """Decode every field with locks active and a sub-zero room temp.

        Byte layout (celsius): A8 74 16 8E 8A 78 C8
        b5 = 0x78 keeps the locked cool/heat temps and sets the fan/remote
        locks; b6 = 0xC8 (200) decodes as a signed -56.
        """
        device = CCM15SlaveDevice(bytes.fromhex("a874168e8a78c8"))
        self.assertTrue(device.is_celsius)
        self.assertEqual(21, device.locked_cool_temperature)
        self.assertEqual(20, device.locked_heat_temperature)
        self.assertEqual(3, device.locked_wind)
        self.assertEqual(2, device.locked_ac_mode)
        self.assertEqual(5, device.error_code)
        self.assertEqual(3, device.ac_mode)
        self.assertEqual(4, device.fan_mode)
        self.assertTrue(device.is_ac_mode_locked)
        self.assertEqual(17, device.temperature_setpoint)
        self.assertTrue(device.is_swing_on)
        self.assertTrue(device.fan_locked)
        self.assertTrue(device.is_remote_locked)
        self.assertEqual(-56, device.temperature)

    def test_locked_temps_cleared_when_flags_off(self) -> None:
        """b5 = 0x00 clears the locked cool/heat temps and the lock flags."""
        device = CCM15SlaveDevice(bytes.fromhex("a874168e8a0048"))
        self.assertEqual(0, device.locked_cool_temperature)
        self.assertEqual(0, device.locked_heat_temperature)
        self.assertFalse(device.fan_locked)
        self.assertFalse(device.is_remote_locked)
        self.assertEqual(72, device.temperature)

    def test_update_redecodes_in_place(self) -> None:
        """update() re-decodes new bytes into the same object.

        The result is field-for-field identical to constructing a fresh device
        from those bytes, so reusing an instance is behaviorally identical to
        replacing it -- only the object identity is preserved.
        """
        device = CCM15SlaveDevice(bytes.fromhex("00000041d2001a"))
        self.assertTrue(device.is_swing_on)
        self.assertEqual(26, device.temperature)

        device.update(bytes.fromhex("00000041d00018"))  # swing off, temp 24
        self.assertFalse(device.is_swing_on)  # re-decoded from the new bytes
        self.assertEqual(24, device.temperature)
        fresh = CCM15SlaveDevice(bytes.fromhex("00000041d00018"))
        self.assertEqual(device.__dict__, fresh.__dict__)

    def test_update_resets_age_and_desired(self) -> None:
        """update() resets age and the opt-in desired_* intents.

        Matches a fresh decode so a poll can never leave a stale age or cause
        an opt-in swing/heater command to keep being re-sent.
        """
        device = CCM15SlaveDevice(bytes.fromhex("00000041d2001a"))
        device.age = 42.0
        device.desired_swing = TriState.ON
        device.desired_heater = TriState.OFF

        device.update(bytes.fromhex("00000041d2001a"))
        self.assertEqual(0.0, device.age)
        self.assertIs(TriState.UNSET, device.desired_swing)
        self.assertIs(TriState.UNSET, device.desired_heater)

if __name__ == '__main__':
    unittest.main()

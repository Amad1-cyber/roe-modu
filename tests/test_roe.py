"""Unit tests for ROE MODU (no game client needed). Run: python -m unittest discover -s tests -v"""
import os
import struct
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import roecrypt          # noqa: E402
import roe_store as store  # noqa: E402
import roe_server as srv   # noqa: E402

# A 96-byte login packet captured from the genuine 0.95 client (account "tester", password "testpass1").
CAPTURED_LOGIN = bytes.fromhex(
    'fa30b633ba27da4f9c69a46eeb22ee3dfd2bae62a96bf00b9a18c421dd4b9953844d8c0701fb9d2b5fb3a33e279cf5513fd4f61825d8f35'
    'd3fd1ec2b67faf40711df940d5eda971be9e8138ea5fa49ead4f36f9acbf420d6ceeb33c09da2739f')


class CryptoTests(unittest.TestCase):
    def test_roundtrip_both_directions(self):
        data = bytes(range(256)) * 3
        for key in (roecrypt.KEY_CLIENT_SEND, roecrypt.KEY_SERVER_SEND):
            enc = roecrypt.Stream(key).encrypt(data)
            self.assertNotEqual(enc, data)
            self.assertEqual(roecrypt.Stream(key).decrypt(enc), data)

    def test_decrypts_a_real_client_packet(self):
        plain = roecrypt.Stream(roecrypt.KEY_CLIENT_SEND).decrypt(CAPTURED_LOGIN)
        length, mtype = struct.unpack_from('<hH', plain, 0)
        self.assertEqual((length, mtype), (96, 0x65))
        self.assertEqual(srv.cstr(plain[4:21]), 'tester')
        self.assertEqual(srv.cstr(plain[21:72]), 'testpass1')
        self.assertEqual(struct.unpack_from('<I', plain, 72)[0], 95)      # client version 0.95


class MessageTests(unittest.TestCase):
    def test_frame_has_length_and_type(self):
        pkt = srv.frame(0x66, b'abcd')
        self.assertEqual(struct.unpack('<hH', pkt[:4]), (8, 0x66))

    def test_builder_sizes(self):
        self.assertEqual(len(srv.frame(0xd2, srv.npc_add(1, 1, (0, 0, 0), srv.MODEL_GOBLIN, 'Goblin'))), 360)
        self.assertEqual(len(srv.frame(0xfe, srv.item_add(1, 0, 'Sword', 'sword_longsword'))), 452)
        self.assertEqual(len(srv.frame(0xf3, srv.player_state('Tester', 35, 24, 60, 40))), 700)

    def test_goblin_model_id(self):
        payload = srv.npc_add(7, 1, (1.0, 2.0, 3.0), srv.MODEL_GOBLIN, 'Goblin')
        self.assertEqual(struct.unpack_from('<I', payload, 0)[0], 7)               # uid at message +4
        self.assertEqual(struct.unpack_from('<I', payload, 0x14)[0], 76)           # model id at message +0x18


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        for name in ('ACCOUNTS_FILE', 'CHARACTERS_FILE', 'CONFIG_FILE'):
            setattr(store, name, os.path.join(self.tmp.name, name.lower() + '.json'))

    def tearDown(self):
        self.tmp.cleanup()

    def test_accounts_hash_and_login(self):
        store.create_account('Alice', 'secret1')
        self.assertTrue(store.check_login('alice', 'secret1', False)[0])
        self.assertFalse(store.check_login('alice', 'wrong', False)[0])
        self.assertFalse(store.check_login('bob', 'whatever', False)[0])          # unknown + registration closed
        self.assertTrue(store.check_login('bob', 'whatever', True)[0])            # open registration creates it
        with open(store.ACCOUNTS_FILE, encoding='utf-8') as f:
            self.assertNotIn('secret1', f.read())                                  # never stored in clear

    def test_invalid_account_names_rejected(self):
        with self.assertRaises(ValueError):
            store.create_account('x', 'password')
        with self.assertRaises(ValueError):
            store.create_account('bad name!', 'password')

    def test_characters(self):
        store.add_character('alice', 'Mooka', 'Ahhmeed', '00' * 56)
        self.assertTrue(store.name_taken('mooka', ''))
        self.assertEqual(len(store.characters_of('Alice')), 1)
        store.delete_character('alice', 'Mooka')
        self.assertEqual(store.characters_of('alice'), [])


class SpawnerTests(unittest.TestCase):
    def test_spawn_kill_respawn(self):
        sent = []
        defs = [{'name': 'Goblin', 'model': 76, 'level': 1, 'kind': 1, 'count': 3, 'radius': 500}]
        sp = srv.Spawner(lambda t, p: sent.append((t, p)), defs, 0.25, (0.0, 380.0, 0.0, 0.0))
        sp.spawn_all()
        self.assertEqual(sum(1 for t, _ in sent if t == 0xd2), 3)
        uid = sorted(sp.slots)[0]
        self.assertTrue(sp.on_death(uid))
        self.assertFalse(sp.on_death(uid))                                         # already dead
        self.assertEqual(struct.unpack('<I', [p for t, p in sent if t == 0xd4][0])[0], uid)
        time.sleep(0.6)
        self.assertEqual(sum(1 for t, p in sent if t == 0xd2 and struct.unpack_from('<I', p, 0)[0] == uid), 2)
        sp.stop()

    def test_default_respawn_is_five_minutes(self):
        self.assertEqual(store.DEFAULT_CONFIG['respawn_seconds'], 300)


if __name__ == '__main__':
    unittest.main()

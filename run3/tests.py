import unittest
from unittest import mock
from unittest.mock import patch, call
import socket
import selectors
import client
import Classes
import constants
import struct
import mysql.connector
import queue
import types


class TestDatabaseMethods(unittest.TestCase):

    @classmethod
    def setUpClass(cls): 
        cls.db = Classes.Database("localhost", "c", "c", "262_testing")
        cls.db.drop_all()
        
    def test_login_register(self): 
        self.assertFalse(self.db.is_registered("test"))
        self.db.register("test", "test")
        self.assertTrue(self.db.is_registered("test"))
        self.assertFalse(self.db.is_logged_in("test"))
        self.db.login("test")
        self.assertTrue(self.db.is_logged_in("test"))

    def test_add_message(self): 
        self.assertEqual(self.db.load_old_messages("test"), [])
        self.db.add_message(1111, "test1", "test2", "Hello")
        self.assertEqual(self.db.load_old_messages("username"), [])
        self.assertEqual(self.db.load_old_messages("test1"), [('Hello', 'test1', 'test2')])
        self.assertEqual(self.db.load_old_messages("test2"), [('Hello', 'test1', 'test2')])
    
        
class TestServerMethods(unittest.TestCase):
    @mock.patch("mysql.connector")
    @mock.patch("builtins.print")
    @mock.patch("time.sleep")
    @mock.patch("selectors.DefaultSelector")
    @mock.patch("socket.socket")
    def test_become_primary(self, mock_socket, mock_selector, mock_sleep, mock_print, mock_mysql):
        self.mock_DB = mock.Mock(name="db")
        self.server = Classes.Server(num=1, is_primary=True, database=self.mock_DB)
        mock_socket.return_value.setsockopt.assert_called_once()
        mock_socket.return_value.listen.assert_called_once()
        mock_socket.return_value.setblocking.assert_called_once_with(False)
        mock_selector.return_value.register.assert_called_once_with(mock_socket.return_value, selectors.EVENT_READ, data=None)
        mock_socket.return_value.bind.assert_called_once_with((constants.HOST1, constants.PORT1))
        self.assertEqual(self.server.active_conns, {})
        self.assertEqual(self.server.active_backups, [])

    @mock.patch("mysql.connector")
    @mock.patch("builtins.print")
    @mock.patch("time.sleep")
    @mock.patch("selectors.DefaultSelector")
    @mock.patch("socket.socket")
    def test_connect_to_primary(self, mock_socket, mock_selector, mock_sleep, mock_print, mock_mysql):
        self.mock_DB = mock.Mock(name="db")
        self.server = Classes.Server(num=2, is_primary=False, database=self.mock_DB)
        mock_socket.return_value.setsockopt.assert_called_once()
        mock_socket.return_value.bind.assert_called_once_with((constants.HOST2, constants.PORT2))
        mock_socket.return_value.connect.assert_called_once_with((constants.HOST1, constants.PORT1))
        mock_selector.return_value.register.assert_called_once_with(mock_socket.return_value, selectors.EVENT_READ, data=1)

    @mock.patch("mysql.connector")
    @mock.patch("builtins.print")
    @mock.patch("time.sleep")
    @mock.patch("selectors.DefaultSelector")
    @mock.patch("socket.socket")
    def test_accept_wrapper_secondary_replicas(self, mock_socket, mock_selector, mock_sleep, mock_print, mock_mysql):
        self.mock_DB = mock.Mock(name="db")
        self.server = Classes.Server(num=1, is_primary=True, database=self.mock_DB)
        mock_conn = mock.Mock(name="conn")
        mock_socket.return_value.accept.return_value = (mock_conn, (constants.HOST2, constants.PORT2))
        self.server.accept_wrapper()
        mock_selector.return_value.register.assert_called_with(mock_conn, selectors.EVENT_READ, data=None)
        self.assertEqual(self.server.active_backups, [mock_conn])

    @mock.patch("mysql.connector")
    @mock.patch("builtins.print")
    @mock.patch("time.sleep")
    @mock.patch("selectors.DefaultSelector")
    @mock.patch("socket.socket")
    def test_accept_wrapper_clients(self, mock_socket, mock_selector, mock_sleep, mock_print, mock_mysql):
        self.mock_DB = mock.Mock(name="db")
        self.server = Classes.Server(num=1, is_primary=True, database=self.mock_DB)
        mock_conn = mock.Mock(name="conn")
        mock_socket.return_value.accept.return_value = (mock_conn, ("hostasdf", 1234))
        self.server.accept_wrapper()
        mock_selector.return_value.register.assert_called_with(mock_conn, selectors.EVENT_READ | selectors.EVENT_WRITE, data=types.SimpleNamespace(addr=("hostasdf", 1234), username=""))
        self.assertEqual(self.server.active_backups, [])

    @mock.patch("Classes.Server._recvall")
    @mock.patch("mysql.connector")
    @mock.patch("builtins.print")
    @mock.patch("time.sleep")
    @mock.patch("selectors.DefaultSelector")
    @mock.patch("socket.socket")
    def test_lock_until_backups_respond(self, mock_socket, mock_selector, mock_sleep, mock_print, mock_mysql, mock_recvall):
        self.mock_DB = mock.Mock(name="db")
        self.server = Classes.Server(num=1, is_primary=True, database=self.mock_DB)
        mock_conn1, mock_conn2 = mock.Mock(name="conn1"), mock.Mock(name="conn2")
        mock_key1, mock_key2 = mock.Mock(name="key1"), mock.Mock(name="key2")
        mock_key1.fileobj = mock_conn1
        mock_key2.fileobj = mock_conn2
        self.server.active_backups = [mock_conn1, mock_conn2]
        mock_recvall.return_value = 25
        mock_selector.return_value.select.return_value = [(mock_key1, 1), (mock_key2, 1)]
        self.server.lock_until_backups_respond("asdf")
        mock_conn1.sendall.assert_called_once_with("asdf")
        mock_conn2.sendall.assert_called_once_with("asdf")
        self.assertEqual(self.server.active_backups, [mock_conn1, mock_conn2])

    @mock.patch("mysql.connector")
    @mock.patch("builtins.print")
    @mock.patch("time.sleep")
    @mock.patch("selectors.DefaultSelector")
    @mock.patch("socket.socket")
    def test_recvall(self, mock_socket, mock_selector, mock_sleep, mock_print, mock_mysql):
        self.mock_DB = mock.Mock(name="db")
        self.server = Classes.Server(num=1, is_primary=True, database=self.mock_DB)
        mock_sock = mock.Mock(name="sock")
        mock_sock.recv.side_effect = [b"abcd", b"efgh", b"ij"]
        ans = self.server._recvall(mock_sock, 10)
        self.assertEqual(ans, b"abcdefghij")

    @mock.patch("mysql.connector")
    @mock.patch("builtins.print")
    @mock.patch("time.sleep")
    @mock.patch("selectors.DefaultSelector")
    @mock.patch("socket.socket")
    def test_recvall_dead_client(self, mock_socket, mock_selector, mock_sleep, mock_print, mock_mysql):
        self.mock_DB = mock.Mock(name="db")
        self.server = Classes.Server(num=1, is_primary=True, database=self.mock_DB)
        mock_sock = mock.Mock(name="sock")
        mock_sock.recv.return_value = None
        ans = self.server._recvall(mock_sock, 10)
        self.assertEqual(ans, None)

    @mock.patch("Classes.Server.become_primary")
    @mock.patch("mysql.connector")
    @mock.patch("builtins.print")
    @mock.patch("time.sleep")
    @mock.patch("selectors.DefaultSelector")
    @mock.patch("socket.socket")
    def test_recvall_dead_primary(self, mock_socket, mock_selector, mock_sleep, mock_print, mock_mysql, mock_become_primary):
        self.mock_DB = mock.Mock(name="db")
        self.server = Classes.Server(num=2, is_primary=False, database=self.mock_DB)
        mock_sock = mock.Mock(name="sock")
        mock_sock.recv.return_value = None
        ans = self.server._recvall(mock_sock, 10)
        mock_selector.return_value.unregister.assert_called_once()
        mock_sock.close.assert_called_once()
        mock_become_primary.assert_called_once()
        self.assertEqual(ans, None)

    @mock.patch("struct.unpack")
    @mock.patch("Classes.Server._recvall")
    @mock.patch("mysql.connector")
    @mock.patch("builtins.print")
    @mock.patch("time.sleep")
    @mock.patch("selectors.DefaultSelector")
    @mock.patch("socket.socket")
    def test_recv_n_args(self, mock_socket, mock_selector, mock_sleep, mock_print, mock_mysql, mock_recvall, mock_unpack):
        self.mock_DB = mock.Mock(name="db")
        self.server = Classes.Server(num=1, is_primary=True, database=self.mock_DB)
        mock_sock = mock.Mock(name="sock")
        mock_unpack.side_effect = [(2,), (2,)]
        mock1 = mock.Mock(name="1")
        mock2 = mock.Mock(name="2")
        mock3 = mock.Mock(name="3")
        mock4 = mock.Mock(name="4")
        mock_recvall.side_effect = [mock1, mock2, mock3, mock4]
        ans = self.server._recv_n_args(mock_sock, 2)
        self.assertEqual(ans, [mock2.decode.return_value, mock4.decode.return_value])

    @mock.patch("mysql.connector")
    @mock.patch("builtins.print")
    @mock.patch("time.sleep")
    @mock.patch("selectors.DefaultSelector")
    @mock.patch("socket.socket")
    def test_pack_n_args(self, mock_socket, mock_selector, mock_sleep, mock_print, mock_mysql):
        self.mock_DB = mock.Mock(name="db")
        self.server = Classes.Server(num=1, is_primary=True, database=self.mock_DB)
        ans = self.server._pack_n_args(opcode=1, args=["asdf", "efg"], uuid=123)
        self.assertEqual(ans, struct.pack(">I", 1) + struct.pack(">I", 123) + struct.pack(">I", 4) + "asdf".encode("utf-8") + struct.pack(">I", 3) + "efg".encode("utf-8"))


    @mock.patch("struct.unpack")
    @mock.patch("Classes.Server._pack_n_args")
    @mock.patch("Classes.Server._recv_n_args")
    @mock.patch("Classes.Server._recvall")
    @mock.patch("mysql.connector")
    @mock.patch("time.sleep")
    @mock.patch("selectors.DefaultSelector")
    @mock.patch("socket.socket")
    def test_service_connection_new_primary(self, mock_socket, mock_selector, mock_sleep, mock_mysql, mock_recvall, mock_recv_n_args, mock_pack_n_args, mock_unpack):
        self.server = Classes.Server(num=1, is_primary=True, database=mock.Mock(name="db_initialization"))
        mock_db = mock.Mock(name="db")
        self.server.db = mock_db
        mock_unpack.return_value = (constants.NEW_PRIMARY,)
        mock_key, mock_sock = mock.Mock(name="key"), mock.Mock(name="sock")
        mock_key.fileobj = mock_sock
        mock_recv_n_args.return_value = ("username", "password")
        mock_db.is_registered.return_value = True
        mock_db.is_valid_password.return_value = True
        mock_db.is_logged_in.return_value = True
        
        self.server.service_connection(mock_key, selectors.EVENT_READ)
        mock_recv_n_args.assert_called_once_with(mock_sock, 2)
        mock_db.is_registered.assert_called_once_with("username")
        mock_db.is_valid_password.assert_called_once_with("username", "password")
        mock_db.is_logged_in.assert_called_once_with("username")
        mock_sock.sendall.assert_called_once_with(struct.pack('>I', constants.NEW_PRIMARY_ACK))
        self.assertEqual(self.server.active_conns["username"][0], mock_sock)

    @mock.patch("struct.unpack")
    @mock.patch("Classes.Server._pack_n_args")
    @mock.patch("Classes.Server._recv_n_args")
    @mock.patch("Classes.Server._recvall")
    @mock.patch("mysql.connector")
    @mock.patch("builtins.print")
    @mock.patch("time.sleep")
    @mock.patch("selectors.DefaultSelector")
    @mock.patch("socket.socket")
    def test_service_connection(self, mock_socket, mock_selector, mock_sleep, mock_print, mock_mysql, mock_recvall, mock_recv_n_args, mock_pack_n_args, mock_unpack):
        self.mock_DB = mock.Mock(name="db")
        self.server = Classes.Server(num=1, is_primary=True, database=self.mock_DB)

        mock_key, mock_sock = mock.Mock(name="key"), mock.Mock(name="sock")
        mock_key.fileobj = mock_sock
        self.server.service_connection(mock_key, selectors.EVENT_READ)

class TestUserInputMethods(unittest.TestCase):
    def setUp(self):
        self.mock_client = mock.Mock(name="client")
        self.user_input = client.UserInput(self.mock_client)

    def test_do_login_happy_path(self):
        self.mock_client.logged_in = False
        self.user_input.do_login("username password")
        self.mock_client.write_queue.put.assert_called_once_with(struct.pack('>I', constants.LOGIN) + struct.pack('>I', len("username")) + "username".encode('utf-8') + struct.pack('>I', len("password")) + "password".encode('utf-8'))
        self.assertEqual(self.mock_client.username, "username")
        self.assertEqual(self.mock_client.password, "password")

    @patch("builtins.print")
    def test_do_login_incorrect_args(self, mock_print):
        self.user_input.do_login("username_only")
        mock_print.assert_called_once_with(f"Incorrect arguments: correct form is login [username] [password]. Please try again!")
        self.mock_client.write_queue.put.assert_not_called()

    @patch("builtins.print")
    def test_do_login_special_chars(self, mock_print):
        self.user_input.do_login("username** password")
        mock_print.assert_called_once_with(f"Special characters not allowed in usernames. Please try again!")
        self.mock_client.write_queue.put.assert_not_called()

    @patch("builtins.print")
    def test_do_login_too_long(self, mock_print):
        self.user_input.do_login("u" * (constants.MAX_LENGTH + 1) + "   password")
        mock_print.assert_called_once_with(f"Username or password is too long. Please try again!")
        self.mock_client.write_queue.put.assert_not_called()

    @patch("builtins.print")
    def test_do_login_already_logged_in(self, mock_print):
        self.mock_client.logged_in = True
        self.user_input.do_login("username password")
        mock_print.assert_called_once_with(f"Already logged in as a user!")
        self.mock_client.write_queue.put.assert_not_called()

    def test_do_register_happy_path(self):
        self.mock_client.logged_in = False
        self.user_input.do_register("username password")
        self.mock_client.write_queue.put.assert_called_once_with(struct.pack('>I', constants.REGISTER) + struct.pack('>I', len("username")) + "username".encode('utf-8') + struct.pack('>I', len("password")) + "password".encode('utf-8'))
        self.assertEqual(self.mock_client.username, "username")
        self.assertEqual(self.mock_client.password, "password")

    def test_do_logout_happy_path(self):
        self.mock_client.logged_in = True
        self.mock_client.username = "username"
        self.mock_client.password = "password"
        self.user_input.do_logout(None)
        self.mock_client.write_queue.put.assert_called_once_with(struct.pack('>I', constants.LOGOUT) + struct.pack('>I', len(self.mock_client.username)) + self.mock_client.username.encode('utf-8'))

    @patch("builtins.print")
    def test_do_logout_not_logged_in(self, mock_print):
        self.mock_client.logged_in = False
        self.user_input.do_logout(None)
        mock_print.assert_called_once_with("Please log in first to log out!")
        self.mock_client.write_queue.put.assert_not_called()

    def test_do_delete_happy_path(self):
        self.mock_client.logged_in = True
        self.mock_client.username = "username"
        self.mock_client.password = "password"
        self.user_input.do_delete(None)
        self.mock_client.write_queue.put.assert_called_once_with(struct.pack('>I', constants.DELETE) + struct.pack('>I', len(self.mock_client.username)) + self.mock_client.username.encode('utf-8'))

    @patch("builtins.print")
    def test_do_delete_not_logged_in(self, mock_print):
        self.mock_client.logged_in = False
        self.user_input.do_delete(None)
        mock_print.assert_called_once_with("Please log in first to delete your account!")
        self.mock_client.write_queue.put.assert_not_called()

    def test_do_find_happy_path(self):
        r = "regex.expression.here"
        self.user_input.do_find(r)
        self.mock_client.write_queue.put.assert_called_once_with(struct.pack('>I', constants.FIND) + struct.pack('>I', len(r)) + r.encode('utf-8'))

    @patch("builtins.print")
    def test_do_find_happy_path(self, mock_print):
        r = "regex.expression.here" * (constants.MAX_LENGTH + 1)
        self.user_input.do_find(r)
        self.mock_client.write_queue.put.assert_not_called()
        mock_print.assert_called_once_with("Expression is too long. Please try again!")

    @patch("random.randint")
    def test_do_send_happy_path(self, mock_randint):
        self.mock_client.logged_in = True
        self.mock_client.username = "username"
        mock_randint.return_value = 123
        self.user_input.do_send("send_to msg")
        self.mock_client.write_queue.put.assert_called_once_with(struct.pack('>I', constants.SEND) + struct.pack('>I', 123) + struct.pack('>I', len("send_to")) + "send_to".encode('utf-8') + struct.pack('>I', len(self.mock_client.username)) + self.mock_client.username.encode('utf-8') + struct.pack('>I', len("msg")) + "msg".encode('utf-8'))

    @patch("builtins.print")
    def test_do_send_incorrect_args(self, mock_print):
        self.user_input.do_send("send_to_no_msg")
        mock_print.assert_called_once_with("Incorrect arguments: correct form is send [username] [message]. Please try again!")

    @patch("builtins.print")
    def test_do_send_too_long(self, mock_print):
        self.user_input.do_send("send_to   " + "msg" * constants.MAX_LENGTH)
        mock_print.assert_called_once_with("Username or message is too long. Please try again!")

    @patch("builtins.print")
    def test_do_send_not_logged_in(self, mock_print):
        self.mock_client.logged_in = False
        self.user_input.do_send("send_to msg")
        mock_print.assert_called_once_with("Please log in first to send a message!")


class TestClientMethods(unittest.TestCase):
    @mock.patch("time.sleep")
    @mock.patch("selectors.DefaultSelector")
    @mock.patch("socket.socket")
    def test_initial_connect_to_primary_server(self, mock_socket, mock_selector, mock_sleep):
        client_test = client.Client()
        mock_sleep.assert_called_once()
        mock_selector.return_value.register.assert_has_calls([call(mock_socket.return_value, selectors.EVENT_WRITE), call(mock_socket.return_value, selectors.EVENT_READ)])
        mock_socket.return_value.connect.assert_called_once()
        mock_socket.return_value.setblocking.assert_called_once()
        mock_socket.return_value.settimeout.assert_called_once()

    @mock.patch("time.sleep")
    @mock.patch("selectors.DefaultSelector")
    @mock.patch("socket.socket")
    def test_later_connect_to_primary_server(self, mock_socket, mock_selector, mock_sleep):
        client_test = client.Client()
        client_test.connect_to_primary_server()
        self.assertEqual(mock_sleep.call_count, 2)
        mock_selector.return_value.register.assert_has_calls([call(mock_socket.return_value, selectors.EVENT_WRITE), call(mock_socket.return_value, selectors.EVENT_READ)])
        self.assertEqual(mock_socket.return_value.connect.call_count, 2)
        self.assertEqual(mock_socket.return_value.setblocking.call_count, 2)
        self.assertEqual(mock_socket.return_value.settimeout.call_count, 2)
        self.assertEqual(list(client_test.pending_queue.queue), [])
        self.assertTrue(len(list(client_test.write_queue.queue)) > 1)

    @mock.patch("builtins.print")
    @mock.patch("time.sleep")
    @mock.patch("selectors.DefaultSelector")
    @mock.patch("socket.socket")
    def test_no_double_print(self, mock_socket, mock_selector, mock_sleep, mock_print):
        client_test = client.Client()
        for i in range(1, 11):
            client_test._no_double_print(uuid=i, msg="msg" + str(i))
            mock_print.assert_called_with("msg" + str(i))
            self.assertTrue(i in client_test.prev_msgs)
        self.assertEqual(list(client_test.prev_msgs_queue.queue), list(range(1, 11)))
        client_test._no_double_print(uuid=5, msg="diff_message_same_uuid")
        self.assertTrue(call("diff_message_same_uuid") not in mock_print.mock_calls)
        self.assertEqual(list(client_test.prev_msgs_queue.queue), list(range(1, 11)))
        self.assertEqual(list(client_test.prev_msgs_queue.queue), list(range(1, 11)))
        client_test._no_double_print(uuid=11, msg="new_message_new_uuid")
        mock_print.assert_called_with("new_message_new_uuid")
        self.assertEqual(list(client_test.prev_msgs_queue.queue), list(range(2, 12)))
        self.assertTrue(11 in client_test.prev_msgs)
        self.assertFalse(1 in client_test.prev_msgs)

    @mock.patch("builtins.print")
    @mock.patch("time.sleep")
    @mock.patch("selectors.DefaultSelector")
    @mock.patch("socket.socket")
    def test_recvall(self, mock_socket, mock_selector, mock_sleep, mock_print):
        client_test = client.Client()
        mock_socket.return_value.recv.return_value = None
        client_test._recvall(5)
        self.assertTrue(call("Client detected old primary server is down - reaching out to new primary") in mock_print.mock_calls)
        mock_selector.return_value.unregister.assert_has_calls([call(mock_socket.return_value), call(mock_socket.return_value)])
        mock_socket.return_value.close.assert_called()

    @mock.patch("client.Client._recvall")
    @mock.patch("builtins.print")
    @mock.patch("time.sleep")
    @mock.patch("selectors.DefaultSelector")
    @mock.patch("socket.socket")
    def test_recv_n_args(self, mock_socket, mock_selector, mock_sleep, mock_print, mock_recvall):
        client_test = client.Client()
        mock_recvall.return_value = None
        self.assertIsNone(client_test._recv_n_args(5))

        

if __name__ == '__main__':
    unittest.main()

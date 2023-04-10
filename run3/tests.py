import unittest
from unittest import mock
from unittest.mock import patch, call
import socket
import selectors
import client
import Classes
import constants
import struct

class TestDatabaseMethods(unittest.TestCase):
    pass


class TestServerMethods(unittest.TestCase):
    pass


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
    pass


if __name__ == '__main__':
    unittest.main()

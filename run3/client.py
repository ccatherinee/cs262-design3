from cmd import Cmd 
import queue 
import socket 
import selectors
import struct 
import threading
import sys 
import os
import time
from constants import *
import random 


# takes and parses command-line user input for all different commands
class UserInput(Cmd): 
    # intro message displayed in command-line prompt for client
    intro = "Welcome! Type help or ? to list commands. To see what a particular command does and how to invoke it, type help <command>. \n"

    def __init__(self, client): 
        # give access to all methods and properties of the parent class (Cmd)
        super().__init__()
        # needs to know about client to access client's write queue
        self.client = client

    def do_login(self, login_info): 
        "Description: This command allows users to login once they have an account. \nSynopsis: login [username] [password] \n"
        self._register_or_login(login_info, LOGIN)

    def do_register(self, register_info):
        "Description: This command allows users to create an account. \nSynopsis: register [username] [password] \n"
        self._register_or_login(register_info, REGISTER)

    def do_logout(self, info):
        "Description: This command allows users to logout and subsequently exit the chatbot. \nSynopsis: logout \n"
        self.client.write_queue.put(struct.pack('>I', LOGOUT) + struct.pack('>I', len(self.client.username)) + self.client.username.encode('utf-8')) # send LOGOUT opcode over the wire

    def do_delete(self, info):
        "Description: This command allows users to delete their account and subsequently exit the chatbot. \nSynopsis: delete\n"
        self.client.write_queue.put(struct.pack('>I', DELETE) + struct.pack('>I', len(self.client.username)) + self.client.username.encode('utf-8')) # send DELETE opcode over the wire

    def do_find(self, exp): 
        "Description: This command allows users to find users by a regex expression. \nSynopsis: find [regex]\n"
        if len(exp) > MAX_LENGTH: # only allow expressions under a certain length to be sent over the wire
            print("Expression is too long. Please try again!")
            return
        # send FIND opcode, length of regex expression, and expression itself over the wire
        self.client.write_queue.put(struct.pack('>I', FIND) + struct.pack('>I', len(exp)) + exp.encode('utf-8'))
    
    def do_send(self, info): 
        "Description: This command allows users to send a message. \nSynopsis: send [username] [message] \n"
        # split command line-input into username and everything else as message
        info = info.split(' ', 1)
        if len(info) != 2:
            print("Incorrect arguments: correct form is send [username] [message]. Please try again!")
            return
        send_to, msg = info
        # limit length of username and message that will be sent over the wire
        if len(send_to) > MAX_LENGTH or len(msg) > MAX_LENGTH:
            print("Username or message is too long. Please try again!")
            return
        # send SEND op code, recipient username length and username, and message length and message over the wire
        uuid = random.randint(0, 2 ** 32 - 1)
        self.client.write_queue.put(struct.pack('>I', SEND) + struct.pack('>I', uuid) + struct.pack('>I', len(send_to)) + send_to.encode('utf-8') + struct.pack('>I', len(self.client.username)) + self.client.username.encode('utf-8') + struct.pack('>I', len(msg)) + msg.encode('utf-8'))

    # Helper function that registers or logins user depending on the opcode given
    def _register_or_login(self, info, opcode):
        # split command-line input into exactly username and password
        info = info.split()
        if len(info) != 2:
            print(f"Incorrect arguments: correct form is {'login' if opcode == LOGIN else 'register'} [username] [password]. Please try again!")
            return
        username, password = info
        # prohibit usernames from having any regex special characters within them
        if any(c in ".+*?^$()[]{}|\\" for c in username):
            print("Special characters not allowed in usernames. Please try again!")
            return
        # prohibit usernames or passwords from being too long to send over the wire
        if len(username) > MAX_LENGTH or len(password) > MAX_LENGTH:
            print("Username or password is too long. Please try again!")
            return
        # send LOGIN/REGISTER op code, username length and username, and password length and password over the wire
        self.client.write_queue.put(struct.pack('>I', opcode) + struct.pack('>I', len(username)) + username.encode('utf-8') + struct.pack('>I', len(password)) + password.encode('utf-8'))

        self.client.username, self.client.password = username, password


class Client(): 
    def __init__(self): 
        # selector used by client's write thread to know when socket is writable
        self.sel_write = selectors.DefaultSelector() 
        # selector used by client's read thread to know when socket is readable
        self.sel_read = selectors.DefaultSelector()
        # thread-safe queue for outgoing messages to be sent from client to server
        self.write_queue = queue.Queue() 
        # thread-safe queue for outgoing messages already sent from client to server, waiting for server acks
        self.pending_queue = queue.Queue()

        # store previous 10 uuids of messages displayed, so client doesn't display same message twice even if sent so
        self.prev_msgs = set()
        self.prev_msgs_queue = queue.Queue()

        self.logged_in, self.username, self.password = False, "", ""
        self.connect_to_primary_server()
    
    def connect_to_primary_server(self): 
        time.sleep(1)
        print("Client trying to connect to new primary server")
        for host, port in SERVERS:
            try: 
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setblocking(True)
                sock.connect((host, port))
                self.sock = sock
                self.sel_write.register(self.sock, selectors.EVENT_WRITE)
                self.sel_read.register(self.sock, selectors.EVENT_READ)
                print(f"Client connected to primary server at {(host, port)}")
                # Move pending queue to front of write queue (thus emptying pending queue),#
                # adding a NEW_PRIMARY operation to the front so that client can stay logged in with new primary
                self.temp_queue, self.write_queue = self.write_queue, queue.Queue()
                while not self.temp_queue.empty():
                    self.pending_queue.put(self.temp_queue.get())
                new_primary = struct.pack('>I', NEW_PRIMARY) + struct.pack('>I', len(self.username)) + self.username.encode("utf-8") + struct.pack('>I', len(self.password)) + self.password.encode("utf-8")
                self.pending_queue.queue.insert(0, new_primary)
                self.write_queue, self.pending_queue = self.pending_queue, queue.Queue()
                return 
            except (ConnectionRefusedError, TimeoutError):
                print(f"Primary server is not at {(host, port)}")
                sock.close()

    # De-queues messages in write_queue and sends them over the wire to the server
    def send(self): 
        while True: 
            # once the socket with the server is established, send messages from the write_queue
            for _, _ in self.sel_write.select(timeout=-1): 
                if not self.write_queue.empty(): 
                    rq = self.write_queue.get()
                    self.sock.sendall(rq)
                    self.pending_queue.put(rq)
                
    # Receives messages over the wire from the server
    def receive(self): 
        while True: 
            # once the socket with the server is established and readable
            for _, _ in self.sel_read.select(timeout=None): 
                raw_statuscode = self._recvall(4)
                # if the socket has closed on the server, close likewise on the client and exit
                if not raw_statuscode: continue
                # unpack the status code sent by the server
                statuscode = struct.unpack('>I', raw_statuscode)[0]
                if statuscode == RECEIVE: # display message sent from another client/user
                    raw_uuid = self._recvall(4)
                    if not raw_uuid: continue
                    uuid = struct.unpack('>I', raw_uuid)[0]
                    args = self._recv_n_args(2)
                    if not args: continue 
                    sentfrom, msg = args
                    if uuid not in self.prev_msgs:
                        print(sentfrom, ": ", msg, sep="")
                        self.prev_msgs_queue.put(uuid)
                        self.prev_msgs.add(uuid)
                        if self.prev_msgs_queue.qsize() > 10:
                            self.prev_msgs.remove(self.prev_msgs_queue.get())
                elif statuscode % 4 == 1: # display message sent from the server
                    self.pending_queue.get() 
                    print(statuscode)
                    # TODO: change self.logged_in if receive LOGGED_IN ack; or DELETE/LOGGED_OUT ack

    # Receive exactly n bytes from server, returning None otherwise
    def _recvall(self, n): 
        data = bytearray() 
        while len(data) < n: 
            packet = self.sock.recv(n - len(data))
            if not packet: 
                print("Client detected old primary server is down - reaching out to new primary")
                # close/unregister old socket with old primary and connect to new primary
                self.sel_read.unregister(self.sock)
                self.sel_write.unregister(self.sock)
                self.sock.close()
                self.connect_to_primary_server()
                return None 
            data.extend(packet) 
        return data 

    # Receives n arguments from wire, packaged as len(arg1) + arg1 + len(arg2) + arg2 + ...
    def _recv_n_args(self, n):
        args = []
        for _ in range(n):
            raw_len = self._recvall(4)
            if not raw_len: return None
            arg_len = struct.unpack('>I', raw_len)[0]
            raw_arg = self._recvall(arg_len)
            if not raw_arg: return None 
            temp = raw_arg.decode("utf-8", "strict")
            args.append(temp)
        return args


if __name__ == '__main__':
    try:
        client = Client() 
        # start separate threads for command-line input, sending messages, and receiving messages
        threading.Thread(target=client.receive).start()
        threading.Thread(target=UserInput(client).cmdloop).start()
        threading.Thread(target=client.send).start()
        # main thread stays infinitely in this try block so that Control-C exception can be dealt with
        while True: time.sleep(100)
    except KeyboardInterrupt:
        print("Caught keyboard interrupt exception, client exiting")
        os._exit(1)
    
   
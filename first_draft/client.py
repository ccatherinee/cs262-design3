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
        self.client.write_queue.put(struct.pack('>I', LOGOUT)) # send LOGOUT opcode over the wire

    def do_delete(self, info):
        "Description: This command allows users to delete their account and subsequently exit the chatbot. \nSynopsis: delete\n"
        self.client.write_queue.put(struct.pack('>I', DELETE)) # send DELETE opcode over the wire

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
        uuid = random.randint(0,10000)
        self.client.write_queue.put(struct.pack('>I', SEND) + struct.pack('>I', uuid) + struct.pack('>I', len(send_to)) + send_to.encode('utf-8') + struct.pack('>I', len(msg)) + msg.encode('utf-8'))

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


class Client(): 
    def __init__(self, host, port): 
        # selector used by client's write thread to know when socket is writable
        self.sel_write = selectors.DefaultSelector() 
        # selector used by client's read thread to know when socket is readable
        self.sel_read = selectors.DefaultSelector()
        # initialize blocking socket and connect to server
        # thread-safe queue for outgoing messages to be sent from client to server
        self.write_queue = queue.Queue() 
        self.pending_queue = queue.Queue()
        self.create_connections(host, port)
    
    def create_connections(self, host, port): 
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setblocking(True)
        try: 
            self.sock.connect((host, port))
            self.sel_write.register(self.sock, selectors.EVENT_WRITE)
            self.sel_read.register(self.sock, selectors.EVENT_READ)

            while not self.pending_queue.empty(): 
                req = self.pending_queue.get() 
                self.write_queue.queue.insert(0, req)
            # ! put new primary in the front of the write queue
            return True 
        except ConnectionRefusedError:
            return False

    # Receive exactly n bytes from server, returning None otherwise
    def _recvall(self, n): 
        data = bytearray() 
        while len(data) < n: 
            packet = self.sock.recv(n - len(data))
            if not packet: 
                return None 
            data.extend(packet) 
        return data 

    # Receives n arguments from wire, packaged as len(arg1) + arg1 + len(arg2) + arg2 + ...
    def _recv_n_args(self, n):
        args = []
        for _ in range(n):
            arg_len = struct.unpack('>I', self._recvall(4))[0]
            args.append(self._recvall(arg_len).decode("utf-8", "strict"))
        return args

    # De-queues messages in write_queue and sends them over the wire to the server
    def send(self): 
        while True: 
            # once the socket with the server is established, send messages from the write_queue
            for _, _ in self.sel_write.select(timeout=None): 
                temp = self.write_queue.get()
                self.sock.sendall(temp)
                self.pending_queue.put(temp)
                
    # Receives messages over the wire from the server
    def receive(self): 
        while True: 
            # once the socket with the server is established and readable
            for _, _ in self.sel_read.select(timeout=None): 
                raw_statuscode = self._recvall(4)
                # if the socket has closed on the server, close likewise on the client and exit
                if not raw_statuscode:
                    # make connection with new primary 
                    self.sel_read.unregister(self.sock)
                    self.sel_write.unregister(self.sock)
                    self.sock.close()
                    # ! need to specify which host and which port and what do do when that port isn't the new primary 
                    self.create_connections("", PORT3)
                    return
                # unpack the status code sent by the server
                statuscode = struct.unpack('>I', raw_statuscode)[0]
                if statuscode == RECEIVE: # display message sent from another client/user
                    sentfrom, msg = self._recv_n_args(2)
                    print(sentfrom, ": ", msg, sep="")
                elif statuscode % 4 == 1: # display message sent from the server
                    ack = self.pending_queue.get() 
                    print(ack)


if __name__ == '__main__':
    try:
        # client connects to host and port given as command-line arguments to client.py
        client = Client(sys.argv[1], int(sys.argv[2])) 
        # start separate threads for command-line input, sending messages, and receiving messages
        threading.Thread(target=client.receive).start()
        threading.Thread(target=UserInput(client).cmdloop).start()
        threading.Thread(target=client.send).start()
        # main thread stays infinitely in this try block so that Control-C exception can be dealt with
        while True: time.sleep(100)
    except KeyboardInterrupt:
        print("Caught keyboard interrupt exception, client exiting")
        os._exit(1)
    
   
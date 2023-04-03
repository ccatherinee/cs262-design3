import socket 
import selectors
import types 
import struct 
import queue
import re
from constants import *
import mysql.connector

class Server(): 
    def __init__(self, host, port, logs=True): 
        # initialize listening socket on server that accepts new client connections
        lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lsock.bind((host, port))
        lsock.listen()
        self.logs = logs
        if logs: print(f"Server listening on {(host, port)}")
        lsock.setblocking(False)
        # register read events on listening socket in selector so that server knows when new client is trying to connect
        self.sel = selectors.DefaultSelector() 
        self.sel.register(lsock, selectors.EVENT_READ, data=None)
        self.sock = lsock 
        # stores all users: username maps to password
        self.users = {}
        # stores all online users: username maps to (socket, data)
        self.active_conns = {} 
        # stores all messages needing to be sent to offline users once they log back in:
        # intended (offline) recipient maps to a queue of (sender, message)
        self.messages_queue = {}
        self.db = mysql.connector.connect(
            host="localhost", 
            user="c", 
            password="c", 
            database="design_3", 
            autocommit=True
        )
        self.cursor = self.db.cursor() 
            
    # Receive exactly n bytes from specified socket, returning None otherwise
    def _recvall(self, sock, n): 
        data = bytearray() 
        while len(data) < n: 
            packet = sock.recv(n - len(data))
            if not packet:
                return None 
            data.extend(packet) 
        return data

    # Pack opcode, length of message, and message itself to send through specified socket on the wire
    def _send_msg(self, sock, opcode, msg):
        sock.sendall(struct.pack('>I', opcode) + struct.pack('>I', len(msg)) + msg.encode("utf-8"))

    # Receives n arguments from wire, packaged as len(arg1) + arg1 + len(arg2) + arg2 + ...
    def _recv_n_args(self, sock, n):
        args = []
        for _ in range(n):
            arg_len = struct.unpack('>I', self._recvall(sock, 4))[0]
            args.append(self._recvall(sock, arg_len).decode("utf-8", "strict"))
        return args

    # Accept connection from a new client
    def accept_wrapper(self):
        conn, addr = self.sock.accept() 
        if self.logs: print(f"Accepted connection from {addr}")
        conn.setblocking(False)
        # store with the new connection the address of the client, any bytes the server should
        # send to the new client, and the username of the new client (if logged in)
        data = types.SimpleNamespace(addr=addr, outb=b"", username="")
        # register read/write events on this new connection with the selector, 
        # so that server knows if client sent something to server, or server can write to client
        self.sel.register(conn, selectors.EVENT_READ | selectors.EVENT_WRITE, data=data)

    # Service connection from an existing client
    def service_connection(self, key, mask):
        # obtain socket for connection and data previously stored with connection
        sock, data = key.fileobj, key.data
        if mask & selectors.EVENT_READ: # if the server can read from socket
            raw_opcode = self._recvall(sock, 4)
            if not raw_opcode: # if client socket has closed
                if data.username != "": 
                    del self.active_conns[data.username] # remove user as active
                self.sel.unregister(sock) # unregister socket from selector, so server doesn't track its events anymore
                sock.close() # close corresponding server socket
                if self.logs: print(f"Closed socket with address {data.addr}")
                return
            opcode = struct.unpack('>I', raw_opcode)[0]

        # if connection can be written to and connection represents a logged-in user
        if mask & selectors.EVENT_WRITE and data.username != '': 
            # send previous messages to this user that were sent when they were offline
            if data.username in self.messages_queue and not self.messages_queue[data.username].empty(): 
                while not self.messages_queue[data.username].empty(): 
                    sentfrom, msg = self.messages_queue[data.username].get()
                    sql = "INSERT INTO messages (sent_from, sent_to, msg) VALUES (%s, %s, %s)"
                    val = (sentfrom, data.username, msg)
                    self.cursor.execute(sql, val)
                    # Pack RECEIVE opcode, length of sender, sender, length of message, and message to send over the wire
                    sock.sendall(struct.pack('>I', RECEIVE) + struct.pack('>I', len(sentfrom)) + sentfrom.encode('utf-8') + struct.pack('>I', len(msg)) + msg.encode('utf-8'))    
                self.messages_queue.pop(data.username, None) 
            # send messages to this user that were sent when they were online
            if data.outb: 
                sock.sendall(data.outb)
                data.outb = b""

        if mask & selectors.EVENT_READ: # if the server can read from the socket
            if opcode == LOGIN: # client socket is trying to login
                username, password = self._recv_n_args(sock, 2) # receive username and password from the wire
                # ensure only logged out clients can login
                if data.username:
                    self._send_msg(sock, PRIVILEGE_ERROR, "You need to be logged out to login. Please try again!")
                    return
                # ensure login is allowed only if username and password are verified
                if username in self.users and self.users[username] == password: 
                    # only allow an account to be logged in from one client/socket at a time
                    if username in self.active_conns:
                        self._send_msg(sock, LOGIN_ERROR, "User already logged in in a different location. Please try again!")
                        return
                    # login client by setting socket's data to specified username and adding it to active connections
                    data.username = username
                    self.active_conns[username] = (sock, data)
                    if self.logs: print(f"{username} logged in successfully")
                    # send appropriate login or register confirmation over the wire
                    self._send_msg(sock, LOGIN_CONFIRM, f"Logged in as {username}!")
                    sql = "SELECT * FROM messages WHERE sent_from = '{}' OR sent_to = '{}'".format(username, username)
                    self.cursor.execute(sql)
                    res = self.cursor.fetchall()
                    while res: 
                        sent_from, sent_to, msg = res.pop(0) 
                        # Pack RECEIVE opcode, length of sender, sender, length of message, and message to send over the wire
                        sock.sendall(struct.pack('>I', RECEIVE) + struct.pack('>I', len(sent_from)) + sent_from.encode('utf-8') + struct.pack('>I', len(msg)) + msg.encode('utf-8'))   
                else: 
                    if self.logs: print(f"Unsuccessful login attempt by {username}")
                    self._send_msg(sock, LOGIN_ERROR, "Incorrect username or password. Please try again!")
            elif opcode == REGISTER: # client socket is trying to register
                username, password = self._recv_n_args(sock, 2) # receive username and password from the wire
                # ensure only logged out clients can register
                if data.username:
                    self._send_msg(sock, PRIVILEGE_ERROR, "You need to be logged out to register. Please try again!")
                    return
                 # ensure clients must register unique usernames
                if username in self.users:
                    self._send_msg(sock, REGISTER_ERROR, "Username already exists. Please try again!")
                    return
                # add registration's username and passwords to dictionary of users
                self.users[username] = password
                if self.logs: print(f"{username} successfully registered")
                self._send_msg(sock, REGISTER_CONFIRM, f"{username} successfully registered, please log in!")
            elif opcode == LOGOUT or opcode == DELETE: # client socket is trying to logout or delete account
                # ensure only logged in clients can logout or delete their account
                if not data.username:
                    self._send_msg(sock, PRIVILEGE_ERROR, "You need to be logged in. Please try again!")
                    return
                # drop socket from active connections because logout/delete both cause client shutdown
                self.active_conns.pop(data.username, None)
                if opcode == LOGOUT:
                    self._send_msg(sock, LOGOUT_CONFIRM, "Logged out successfully!")
                    if self.logs: print(f"{data.username} logged out successfully")
                elif opcode == DELETE:
                    # delete user permanently by removing them from users dictionary and self.messages_queue
                    self.messages_queue.pop(data.username, None)
                    self.users.pop(data.username, None)
                    self._send_msg(sock, DELETE_CONFIRM, "Deleted account successfully!")
                    if self.logs: print(f"{data.username} deleted successfully")
                # disassociate current socket from the account
                data.username = ''
            elif opcode == SEND: # client socket is trying to send a message
                sendto, msg = self._recv_n_args(sock, 2) # get command-line arguments from the wire
                # ensure client must be logged in to send a message to another user
                if not data.username:
                    self._send_msg(sock, PRIVILEGE_ERROR, "You need to be logged in to send a message. Please try again!")
                    return
                if sendto not in self.active_conns: # recipient is not online
                    if sendto not in self.users: # recipient does not exist, so send error back to client
                        self._send_msg(sock, SEND_ERROR, "Recipient user does not exist. Please try again!")
                    else: # otherwise, put message in self.messages_queue to be sent when recipient comes back online
                        if sendto not in self.messages_queue: 
                            self.messages_queue[sendto] = queue.Queue()
                        self.messages_queue[sendto].put((data.username, msg))
                else: # recipient is online
                    # attach message to recipient's connection's data, to be sent to recipient's client by server soon
                    self.active_conns[sendto][1].outb += struct.pack('>I', RECEIVE) + struct.pack('>I', len(data.username)) + data.username.encode('utf-8') + struct.pack('>I', len(msg)) + msg.encode('utf-8')
                    sql = "INSERT INTO messages (sent_from, sent_to, msg) VALUES (%s, %s, %s)"
                    val = (data.username, sendto, msg)
                    self.cursor.execute(sql, val)
            elif opcode == FIND: # client socket trying to find users 
                exp = self._recv_n_args(sock, 1)[0] # receive command-line input of regex expression
                regex = re.compile(exp) # compile regex expression
                result = "Users: " + ', '.join(list(filter(regex.match, self.users.keys()))) # compute users that match the regex
                self._send_msg(sock, FIND_RESULT, result) # return the result to the client socket
    
    # main loop that runs server
    def run(self): 
        try: 
            while True: 
                # get events from sockets previously registered with selector
                events = self.sel.select(timeout=None)
                for key, mask in events: 
                    # if no data is stored with connection, then it must be a new connection, so accept it
                    if key.data is None: 
                        self.accept_wrapper()
                    # otherwise, it is an old connection from an already accepted client, so service it
                    else: 
                        self.service_connection(key, mask)
        # catch Control-C keyboard interrupt gracefully by closing selector and socket
        except KeyboardInterrupt: 
            print("Caught keyboard interrupt exception, server exiting")
        finally:
            self.sel.close()
            self.sock.close()
        

if __name__ == '__main__': 
    host, port = "", PORT # empty host string means server is reachable by any address it has
    Server(host, port).run()
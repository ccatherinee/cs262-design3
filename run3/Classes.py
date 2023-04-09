import socket 
import selectors
import types 
import struct 
import copy
import re
from constants import *
from datetime import datetime
import mysql.connector
import time


class Database(): 
    def __init__(self, host, user, password, database, autocommit=True): 
        self.db = mysql.connector.connect(
            host=host,
            user=user, 
            password=password, 
            database=database,
            autocommit=autocommit
        )
        self.cursor = self.db.cursor()
    
    def login(self, username): 
        sql = 'UPDATE Users SET logged_in = True WHERE username = "{un}"'.format(un=username)
        self.cursor.execute(sql)
    
    def logout(self, username): 
        sql = 'UPDATE Users SET logged_in = False WHERE username = "{un}"'.format(un=username)
        self.cursor.execute(sql)

    def delete(self, username): 
        sql = 'DELETE FROM Users WHERE username = "{un}"'.format(un=username)
        self.cursor.execute(sql) 
    
    def register(self, username, password): 
        sql = 'INSERT INTO Users (username, password, logged_in) VALUES ("{un}","{pa}",False)'.format(un=username, pa=password)
        self.cursor.execute(sql)
    
    def add_message(self, uuid, sentto, sentfrom, msg): 
        sql = 'SELECT uuid FROM Messages WHERE uuid = {uu}'.format(uu = uuid)
        self.cursor.execute(sql)
        # Only insert message into database if it isn't already in database
        if self.cursor.fetchone() is not None: return
        sql = 'INSERT INTO Messages (uuid, sentto, sentfrom, msg, timestamp) VALUES ({uu},"{st}","{sf}","{msg}", "{ts}")'.format(uu=uuid, st=sentto, sf=sentfrom, msg=msg, ts=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        self.cursor.execute(sql)

    def is_valid_password(self, username, password): 
        sql = "SELECT password FROM Users WHERE username = '{un}'".format(un=username)
        self.cursor.execute(sql)
        return self.cursor.fetchone()[0] == password 

    def is_registered(self, username): 
        sql = "SELECT username FROM Users WHERE username = '{un}'".format(un=username)
        self.cursor.execute(sql)
        return self.cursor.fetchone() is not None 

    def is_logged_in(self, username): 
        sql = "SELECT logged_in FROM Users WHERE username = '{un}'".format(un=username)
        self.cursor.execute(sql)
        return self.cursor.fetchone()[0]
    
    def load_old_messages(self, username): 
        sql = "SELECT msg, sento, sentfrom FROM Messages WHERE sentto = '{un}' OR sentfrom = '{un_}' ORDER BY timestamp ASC".format(un=username, un_=username)
        self.cursor.execute(sql)
        res = self.cursor.fetchall()
        return res

    
class Server(): 
    def __init__(self, num, is_primary, database): 
        self.num = num
        self.primary = is_primary
        # initialize current server's host/port
        self.host, self.port = SERVERS[num - 1] 
        # store the 2 other servers' hosts/ports
        self.other_servers = copy.deepcopy(SERVERS)
        self.other_servers.remove((self.host, self.port))
        self.db = Database(DB_HOST, DB_USER, DB_PASSWORD, database)
        # used by primary server to register client reads/writes and to initially establish connection
        # with secondary replicas; used by secondary replicas to monitor for messages from the primary server
        self.sel = selectors.DefaultSelector() 
        # used ONLY by primary server to register/read acks from secondary replicas 
        self.backup_read_sel = selectors.DefaultSelector() 
        if self.primary: 
            self.become_primary() # ascend the current server to be the primary server
        else: 
            self.connect_to_primary() # connect the current non-primary server to the primary server

    def become_primary(self): 
        self.primary = True 
        # establish primary server's listening socket that accepts connect requests from clients or secondary replicas
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((self.host, self.port))
        self.sock.listen() # Reminder: only the primary server listens!!
        print(f"Primary server (server {self.num}) listening on {(self.host, self.port)}")
        self.sock.setblocking(False)
        self.sel.register(self.sock, selectors.EVENT_READ, data=None)
        # Reminder: only the primary server stores the following:
        # all online clients: a dictionary mapping username to (socket, data), where data has client address and username, if logged in
        self.active_conns = {}
        # all online secondary replicas: a list of sockets
        self.active_backups = []

    def connect_to_primary(self): 
        time.sleep(1)
        # try each of the other servers to see if it is listening, implying it's the primary server
        for host, port in self.other_servers: 
            print(f"Secondary replica (server {self.num}) trying to connect to possible primary at {(host, port)}")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind((self.host, self.port)) 
            # bind the secondary replica's host/port to the socket so that the primary server
            # can distinguish between requests from clients vs. requests from server replicas
            try: 
                sock.connect((host, port))
                # connection to primary server succeeded, so register messages from primary server
                # to secondary replica's selector so that SR gets notified about updates from primary server
                self.sel.register(sock, selectors.EVENT_READ, data=1)
                print(f"Secondary replica (server {self.num}) connected to primary server at {(host, port)}")
                return True
            except (ConnectionRefusedError, TimeoutError):
                print(f"Primary server is not at {(host, port)}")
        return False

    def accept_wrapper(self):
        # Reminder: only primary servers listen and thus accept new connections!
        conn, addr = self.sock.accept() 
        conn.setblocking(False)
        if addr in self.other_servers: # secondary replica trying to connect to current primary server
            self.backup_read_sel.register(conn, selectors.EVENT_READ, data=None) # register messages from socket for future acks from secondary replica
            self.active_backups.append(conn)
            print(f"Primary server (server {self.num}) accepted secondary replica connection from {addr}") 
        else: # client trying to connect to current primary server
            data = types.SimpleNamespace(addr=addr, username="")
            self.sel.register(conn, selectors.EVENT_READ | selectors.EVENT_WRITE, data=data)
            print(f"Primary server (server {self.num}) accepted client connection from {addr}")

    # Only invoked by primary server: to_backup is a byte array to send to all online secondary replicas
    # containing data for them to replicate. This function locks the primary replica until it receives
    # acks from all secondary replicas or times them out and declares them dead.
    def lock_until_backups_respond(self, to_backup): 
        for sock in self.active_backups: 
            sock.sendall(to_backup)
        not_responded = [sock for sock in self.active_backups]
        t_end = time.time() + 10
        # declare replicas dead if no ack received within 10 seconds
        while time.time() < t_end and len(not_responded) > 0: 
            # primary server is notified of acks by backup read selector
            # timeout = -1 ensures select doesn't block but only gets events that are currently available
            events = self.backup_read_sel.select(timeout=-1)
            for key, _ in events: 
                sock = key.fileobj
                if sock in self.active_backups: 
                    self._recvall(sock, 4) # receive the actual 4-byte ack code
                    not_responded.remove(sock)
        for sock in not_responded: 
            print(f"Primary server (server {self.num}) detected a dead secondary replica")
            sock.close() 
            # dead replicas should be removed and unregistered from primary server's selector
            self.backup_read_sel.unregister(sock)
            self.active_backups.remove(sock)
            
    # Primary server services client connections/requests; secondary replicas service primary server requests
    def service_connection(self, key, mask): 
        sock, data = key.fileobj, key.data 
        
        if mask & selectors.EVENT_READ: 
            raw_opcode = self._recvall(sock, 4) # the bytes forming the opcode
            if not raw_opcode: # TODO: when handling changing recv helper functions in server so that killing backup doesn't kill primary, move this chunk of logic into self._recvall?
                sock.close() 
                self.sel.unregister(sock)
                # if the current server is a secondary replica, then dead socket means the primary server is down!
                if not self.primary: 
                    # New primary replica leadership election between server 2 and server 3
                    # Primary ascension order: server 1 (default), server 2, server 3
                    if self.port == PORT2:
                        self.become_primary() # server 2, if up, always should go for primary
                    elif self.port == PORT3:
                        time.sleep(3)
                        if not self.connect_to_primary():
                            self.become_primary() # server 3 only goes for primary if both servers 1 + 2 are down
                else: # if the current server is the primary server, then a client has gone down
                    if data.username != "":
                        del self.active_conns[data.username] # remove user from online users
                        print(f"Primary server (server {self.num}) detected a dead client")
                return 
            
            opcode = struct.unpack('>I', raw_opcode)[0]
            if opcode == NEW_PRIMARY: # only primary server could end up here
                assert(self.primary) # only clients should be sending NEW_PRIMARY operation requests, and only to the primary server
                print(f"Primary server (server {self.num}) received a new primary request from a client")
                username, password = self._recv_n_args(sock, 2)
                # Add client connection to primary server's active client connections
                if self.db.is_registered(username) and self.db.is_valid_password(username, password) and self.db.is_logged_in(username):
                    data.username = username 
                    self.active_conns[username] = (sock, data)
                sock.sendall(struct.pack('>I', NEW_PRIMARY_ACK))

            elif opcode == LOGIN: # TODO: check permissioning/login status/add LOGIN_ERROR code etc. - checked logged in do on client side! but also need to check if password correct server side, if not, error
                username, password = self._recv_n_args(sock, 2)
                if self.db.is_registered(username) and self.db.is_valid_password(username, password): 
                    self.db.login(username)
                    # primary server is talking directly to client and thus needs to update its in-memory active client connections
                    if self.primary:  
                        data.username = username
                        self.active_conns[username] = (sock, data)
                if self.primary: # primary server tells secondary replicas to replicate this request/login state
                    to_backup = self._pack_n_args(opcode, [username, password])
                    self.lock_until_backups_respond(to_backup)
                sock.sendall(struct.pack('>I', LOGIN_ACK))

            elif opcode == REGISTER: # TODO: check permissioning/add REGISTER_ERROR code etc. - check logged in on client side! but also need to check if username already registered on server side
                username, password = self._recv_n_args(sock, 2)
                if not self.db.is_registered(username): 
                    self.db.register(username, password)
                if self.primary: # primary server tells secondary replicas to replicate this request/registration state
                    to_backup = self._pack_n_args(opcode, [username, password])
                    self.lock_until_backups_respond(to_backup) 
                sock.sendall(struct.pack('>I', REGISTER_ACK))
            
            elif opcode == SEND: # TODO: check permissioning/add SEND_ERROR code etc. - check logged in on client side! but need to check invalid recipient here etc.
                raw_uuid = self._recvall(sock, 4)
                uuid = struct.unpack('>I', raw_uuid)[0]
                sentto, sentfrom, msg = self._recv_n_args(sock, 3)
                if self.primary: 
                    assert(data.username == sentfrom) # only client actually logged in as sender should be sending send requests with that username
                self.db.add_message(uuid, sentto, sentfrom, msg) # add_message only inserts into DB if the uuid isn't already in the DB
                if self.primary:
                    if self.db.is_logged_in(sentto): # primary server actually sends message to recipient over the wire
                        self.active_conns[sentto][0].sendall(self._pack_n_args(RECEIVE, [sentfrom, msg], uuid))
                    to_backup = self._pack_n_args(SEND, [sentto, sentfrom, msg], uuid)
                    self.lock_until_backups_respond(to_backup) # primary server tells secondary replicas to replicate this message
                sock.sendall(struct.pack('>I', SEND_ACK))

            elif opcode == LOGOUT or opcode == DELETE: # TODO: check permissioning/add LOGOUT_ERROR/DELETE_ERROR code etc. - check logged in on client side!
                username = self._recv_n_args(sock, 1)[0]
                if self.primary:
                    assert(username == data.username) # only client actually logged in as the user should be sending logout/delete requests
                if opcode == LOGOUT: 
                    self.db.logout(username)
                if opcode == DELETE: 
                    self.db.delete(username)
                if self.primary: 
                    self.active_conns.pop(data.username, None) # to the primary server, this client is no longer logged-in or active
                    to_backup = self._pack_n_args(opcode, username)
                    self.lock_until_backups_respond(to_backup)  # primary server tells secondary replicas to replicate the users account state
                sock.sendall(struct.pack('>I', DELETE_OR_LOGOUT_ACK))
    
    def run(self): 
        while True: 
            events = self.sel.select(timeout=None)
            for key, mask in events: 
                if key.data is None: 
                    self.accept_wrapper() # Reminder: only primary replicas listen and thus accept new connections!
                else: 
                    # Both primary/secondary replicas service connections: primary server services clients, SRs service the primary server's replication requests
                    self.service_connection(key, mask) 

    def _recvall(self, sock, n): 
        data = bytearray() 
        while len(data) < n: 
            packet = sock.recv(n - len(data))
            if not packet:
                return None 
            data.extend(packet) 
        return data

    # Receives n arguments from wire, packaged as len(arg1) + arg1 + len(arg2) + arg2 + ...
    def _recv_n_args(self, sock, n):
        args = []
        for _ in range(n):
            arg_len = struct.unpack('>I', self._recvall(sock, 4))[0]
            args.append(self._recvall(sock, arg_len).decode("utf-8", "strict"))
        return args
    
    # Pack opcode, length of message, and message itself to send through specified socket on the wire
    def _pack_n_args(self, opcode, args, uuid=None): 
        to_send = struct.pack('>I', opcode)
        if uuid: 
            to_send += struct.pack('>I', uuid)
        for arg in args: 
            to_send += struct.pack('>I', len(arg)) + arg.encode("utf-8")
        return to_send

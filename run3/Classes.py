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

# Database class used to maintain each server's separate class
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
    
    def login(self, username): # login the user with the given username
        sql = 'UPDATE Users SET logged_in = True WHERE username = "{un}"'.format(un=username)
        self.cursor.execute(sql)
    
    def logout(self, username): # logout the user with the given username
        sql = 'UPDATE Users SET logged_in = False WHERE username = "{un}"'.format(un=username)
        self.cursor.execute(sql)

    def delete(self, username): # delete the user with the given username
        sql = 'DELETE FROM Users WHERE username = "{un}"'.format(un=username)
        self.cursor.execute(sql) 
    
    def register(self, username, password): # register the given username with the given password
        sql = 'INSERT INTO Users (username, password, logged_in) VALUES ("{un}","{pa}",False)'.format(un=username, pa=password)
        self.cursor.execute(sql)
    
    def add_message(self, uuid, sentto, sentfrom, msg): # add a message to the chat application history, sent sentfrom -> sentto
        sql = 'SELECT uuid FROM Messages WHERE uuid = {uu}'.format(uu = uuid)
        self.cursor.execute(sql)
        # Only insert message into database if it isn't already in database
        if self.cursor.fetchone() is not None: return
        sql = 'INSERT INTO Messages (uuid, sentto, sentfrom, msg, timestamp) VALUES ({uu},"{st}","{sf}","{msg}", "{ts}")'.format(uu=uuid, st=sentto, sf=sentfrom, msg=msg, ts=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        self.cursor.execute(sql)

    def is_valid_password(self, username, password): # return whether the given password is the correct password for the given user
        sql = "SELECT password FROM Users WHERE username = '{un}'".format(un=username)
        self.cursor.execute(sql)
        return self.cursor.fetchone()[0] == password 

    def is_registered(self, username): # return whether the given user is registered
        sql = "SELECT username FROM Users WHERE username = '{un}'".format(un=username)
        self.cursor.execute(sql)
        return self.cursor.fetchone() is not None 

    def is_logged_in(self, username): # return whether the given user is currently logged into a client somewhere
        sql = "SELECT logged_in FROM Users WHERE username = '{un}'".format(un=username)
        self.cursor.execute(sql)
        return self.cursor.fetchone()[0]
    
    def load_old_messages(self, username): # load message history for the given user, messages they either sent or received
        sql = "SELECT msg, sentto, sentfrom FROM Messages WHERE sentto = '{un}' OR sentfrom = '{un_}' ORDER BY timestamp ASC".format(un=username, un_=username)
        self.cursor.execute(sql)
        return self.cursor.fetchall()
    
    def load_all_users(self): # load all users from the database
        sql = "SELECT username from users"
        self.cursor.execute(sql)
        return self.cursor.fetchall()
    
    def drop_all(self):
        sql = "DELETE FROM users"
        self.cursor.execute(sql)
        sql = "DELETE FROM messages"
        self.cursor.execute(sql)

    
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
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
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
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # bind the secondary replica's host/port to the socket so that the primary server
            # can distinguish between requests from clients vs. requests from server replicas
            try: 
                sock.bind((self.host, self.port)) 
            except OSError: 
                sock.bind((self.host, self.port + 10))
            try: 
                sock.settimeout(0.5)
                sock.connect((host, port))
                # connection to primary server succeeded, so register messages from primary server
                # to secondary replica's selector so that SR gets notified about updates from primary server
                self.sel.register(sock, selectors.EVENT_READ, data=1)
                print(f"Secondary replica (server {self.num}) connected to primary server at {(host, port)}")
                return True
            except (ConnectionRefusedError, TimeoutError, socket.timeout):
                print(f"Primary server is not at {(host, port)}")
                sock.close()
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
            try: 
                sock.sendall(to_backup)
            except OSError: 
                self.active_backups.remove(sock)
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
                    temp = self._recvall(sock, 4) # receive the actual 4-byte ack code
                    if temp: 
                        not_responded.remove(sock)
                    else: 
                        self.backup_read_sel.unregister(sock)
                        sock.close() 
                        # remove the backup and unregister and stuff
        for sock in not_responded: 
            print(f"Primary server (server {self.num}) detected a dead secondary replica")
            # dead replicas should be removed and unregistered from primary server's selector
            self.active_backups.remove(sock)
            
    # Primary server services client connections/requests; secondary replicas service primary server requests
    def service_connection(self, key, mask): 
        sock, data = key.fileobj, key.data 
        
        if mask & selectors.EVENT_READ: 
            raw_opcode = self._recvall(sock, 4) # the bytes forming the opcode
            if not raw_opcode: return 
            opcode = struct.unpack('>I', raw_opcode)[0]
            if opcode == NEW_PRIMARY: # only primary server could end up here
                assert(self.primary) # only clients should be sending NEW_PRIMARY operation requests, and only to the primary server
                print(f"Primary server (server {self.num}) received a new primary request from a client")
                args = self._recv_n_args(sock, 2)
                if not args: return
                username, password = args
                # Add client connection to primary server's active client connections
                if self.db.is_registered(username) and self.db.is_valid_password(username, password) and self.db.is_logged_in(username):
                    data.username = username 
                    self.active_conns[username] = (sock, data)
                sock.sendall(struct.pack('>I', NEW_PRIMARY_ACK))

            elif opcode == LOGIN:
                args = self._recv_n_args(sock, 2)
                if not args: return 
                username, password = args
                if self.db.is_registered(username) and self.db.is_valid_password(username, password): 
                    self.db.login(username)
                    # primary server is talking directly to client and thus needs to update its in-memory active client connections
                    if self.primary:  
                        data.username = username
                        if username in self.active_conns:
                            sock.sendall(struct.pack('>I', LOGIN_ERROR))
                            return
                        self.active_conns[username] = (sock, data)
                        # primary server tells secondary replicas to replicate this request/login state
                        to_backup = self._pack_n_args(opcode, [username, password])
                        self.lock_until_backups_respond(to_backup)
                    sock.sendall(struct.pack('>I', LOGIN_ACK))
                else:
                    sock.sendall(struct.pack('>I', LOGIN_ERROR))

            elif opcode == REGISTER:
                args = self._recv_n_args(sock, 2)
                if not args: return 
                username, password = args
                if not self.db.is_registered(username): 
                    self.db.register(username, password)
                    if self.primary: # primary server tells secondary replicas to replicate this request/registration state
                        to_backup = self._pack_n_args(opcode, [username, password])
                        self.lock_until_backups_respond(to_backup) 
                    sock.sendall(struct.pack('>I', REGISTER_ACK))
                else:
                    sock.sendall(struct.pack('>I', REGISTER_ERROR))

            elif opcode == FETCH_ALL: # only primary server should be receiving these requests from clients
                assert(self.primary)
                username = self._recv_n_args(sock, 1)
                if not username: return 
                username = username[0]
                msgs = "\n".join([f"{sentfrom}->{sentto}: {msg}" for msg, sentto, sentfrom in self.db.load_old_messages(username)])
                msgs = msgs or "No previous messages!"
                sock.sendall(self._pack_n_args(FETCH_ALL_ACK, [msgs], uuid=hash(msgs) % 2 ** 32))

            elif opcode == FIND:
                exp = self._recv_n_args(sock, 1)[0] # receive command-line input of regex expression
                regex = re.compile(exp) # compile regex expression
                result = "Users: " + ', '.join(list(filter(regex.match, [user[0] for user in self.db.load_all_users()]))) # compute users that match the regex
                sock.sendall(self._pack_n_args(FIND_ACK, [result])) # return the result to the client socket
            
            elif opcode == SEND:
                raw_uuid = self._recvall(sock, 4)
                if not raw_uuid: return 
                uuid = struct.unpack('>I', raw_uuid)[0]
                sentto, sentfrom, msg = self._recv_n_args(sock, 3)
                if self.primary: 
                    assert(data.username == sentfrom) # only client actually logged in as sender should be sending send requests with that username
                if self.db.is_registered(sentto):
                    self.db.add_message(uuid, sentto, sentfrom, msg) # add_message only inserts into DB if the uuid isn't already in the DB
                    if self.primary:
                        if self.db.is_logged_in(sentto) and sentto in self.active_conns: # primary server actually sends message to recipient over the wire
                            self.active_conns[sentto][0].sendall(self._pack_n_args(RECEIVE, [sentfrom, msg], uuid))
                        to_backup = self._pack_n_args(SEND, [sentto, sentfrom, msg], uuid)
                        self.lock_until_backups_respond(to_backup) # primary server tells secondary replicas to replicate this message
                    sock.sendall(struct.pack('>I', SEND_ACK))
                else:
                    sock.sendall(struct.pack('>I', SEND_ERROR))

            elif opcode == LOGOUT or opcode == DELETE:
                username = self._recv_n_args(sock, 1)
                if not username: return 
                username = username[0]
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
                sock.sendall(struct.pack('>I', LOGOUT_ACK if opcode == LOGOUT else DELETE_ACK))
    
    def run(self): 
        while True: 
            events = self.sel.select(timeout=None)
            for key, mask in events: 
                if key.data is None: 
                    self.accept_wrapper() # Reminder: only primary replicas listen and thus accept new connections!
                else: 
                    # Both primary/secondary replicas service connections: primary server services clients, SRs service the primary server's replication requests
                    self.service_connection(key, mask) 

    # Receive all n bytes for socket, returning None if the socket closes in the middle of receiving
    def _recvall(self, sock, n): 
        data = bytearray() 
        while len(data) < n: 
            try: 
                packet = sock.recv(n - len(data))
                if not packet:
                    raise Exception("Packet is none.") # raise exception that is caught below
            except (ConnectionResetError, Exception): 
                # LEADERSHIP ELECTION PROTOCOL
                # if this server is a SR and it detects a dead socket, since SRs only talk to
                # the PR, this means the PR is dead, so a new PR/leader must be elected!
                if not self.primary: 
                    self.sel.unregister(sock)
                    sock.close()
                    if self.port == PORT2: # Server 2, if it is up, always becomes the new leader
                        self.become_primary() 
                    elif self.port == PORT3: # Server 3 waits to see if Server 2 is up/becomes the new leader
                        time.sleep(1)
                        if not self.connect_to_primary(): 
                            self.become_primary() # If not, Server 3 becomes the new leader
                return None 
            data.extend(packet) 
        return data

    # Receives n arguments from wire, packaged as len(arg1) + arg1 + len(arg2) + arg2 + ...
    def _recv_n_args(self, sock, n):
        args = []
        for _ in range(n):
            raw_len = self._recvall(sock, 4)
            if not raw_len: return None
            arg_len = struct.unpack('>I', raw_len)[0]
            if arg_len != 0:
                raw_arg = self._recvall(sock, arg_len)
                if not raw_arg: return None
                temp = raw_arg.decode("utf-8", "strict")
                args.append(temp)
        return args
    
    # Pack as bytes the opcode, optional uuid, and args packaged as length + arg 
    def _pack_n_args(self, opcode, args, uuid=None): 
        to_send = struct.pack('>I', opcode)
        if uuid: 
            to_send += struct.pack('>I', uuid)
        for arg in args: 
            to_send += struct.pack('>I', len(arg)) + arg.encode("utf-8")
        return to_send

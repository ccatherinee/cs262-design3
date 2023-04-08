import socket 
import selectors
import types 
import struct 
import queue
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
        sql = "SELECT msg, sento, sentfrom FROM Messages WHERE sentto = '{un}' OR sentfrom = '{un_}' ORDER BY timestamp ASC;".format(un=username, un_=username)
        self.cursor.execute(sql)
        res = self.cursor.fetchall()
        return res

    
class Server(): 
    def __init__(self, host, port, is_primary, database): 
        # initialize listening socket on server that accepts new client connections
        self.port = port 
        self.other_servers = [PORT1, PORT2, PORT3]
        self.other_servers.remove(port) 

        self.primary = is_primary
        self.db = Database(DB_HOST, DB_USER, DB_PASSWORD, database)
        # sel keeps track of clients for primary and is connection with primary for SR
        self.sel = selectors.DefaultSelector() 
        # backup_sel keeps track of read events (PR receives SR from acks)
        self.backup_read_sel = selectors.DefaultSelector() 
        if self.primary: 
            self.become_primary(host, port) 
        else: 
            self.create_connections(host, port)

    # Accept connection from a new client
    def accept_wrapper(self):
        conn, addr = self.sock.accept() 
        conn.setblocking(False)
        # backup server trying to create connection 
        if addr[1] in self.other_servers: 
            self.backup_read_sel.register(conn, selectors.EVENT_READ, data=None)
            self.active_backups.append(conn)
            print(f"Accepted connection from {conn}")
        # client trying to create connection 
        else: 
            data = types.SimpleNamespace(addr=addr, outb=b"", username="")
            self.sel.register(conn, selectors.EVENT_READ | selectors.EVENT_WRITE, data=data)
            print(f"Accepted connection from a client: {conn}")
    
    def _recvall(self, sock, n): 
        data = bytearray() 
        while len(data) < n: 
            packet = sock.recv(n - len(data))
            if not packet:
                return None 
            data.extend(packet) 
        return data

    # Pack opcode, length of message, and message itself to send through specified socket on the wire
    def _pack_n_args(self, opcode, args, uuid=None): 
        to_send = struct.pack('>I', opcode)
        if uuid: 
            to_send += struct.pack('>I', uuid)
        for arg in args: 
            to_send += struct.pack('>I', len(arg)) + arg.encode("utf-8")
        return to_send

    # Receives n arguments from wire, packaged as len(arg1) + arg1 + len(arg2) + arg2 + ...
    def _recv_n_args(self, sock, n):
        args = []
        for _ in range(n):
            arg_len = struct.unpack('>I', self._recvall(sock, 4))[0]
            args.append(self._recvall(sock, arg_len).decode("utf-8", "strict"))
        return args

    def become_primary(self, host, port): 
        self.primary = True 
        
        lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lsock.bind((host, port))
        lsock.listen() 
        print(f"Server listening on {(host, port)}")
        lsock.setblocking(False)
        
        self.sel.register(lsock, selectors.EVENT_READ, data=None)
        self.sock = lsock 

        self.active_conns = {}
        self.active_backups = []

    def create_connections(self, host, port): 
        # try to reach out to both of the other servers, and when it finds the right one register on self.sel selector 
        for port_ in self.other_servers: 
            print(port_, "fabulosa")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind((host, port))
            time.sleep(1)
            try: 
                sock.connect(("", port_))
                # connection with the primary on self.sock
                self.sel.register(sock, selectors.EVENT_READ, data=1)
                return True 
            except (ConnectionRefusedError, TimeoutError) as e:
                print(f"Connection refused from {port_}")
                sock.close()
            

    def lock_until_backups_respond(self, to_backup): 
        for sock in self.active_backups: 
            sock.sendall(to_backup)
        not_responded = [sock for sock in self.active_backups]
        t_end = time.time() + 10
        while time.time() < t_end and len(not_responded) > 0: 
            events = self.backup_read_sel.select(timeout=-1)
            for key, mask in events: 
                sock, data = key.fileobj, key.data
                if sock in self.active_backups: 
                    self._recvall(sock, 4)
                    not_responded.remove(sock)
        for sock in not_responded: 
            print("Server down - please restart.")
            sock.close() 
            self.backup_read_sel.unregister(sock)
            self.active_backups.remove(sock)
            
    # service_connection function is what responds to the self.sel events selector that the main loop runs 
    def service_connection(self, key, mask): 
        sock, data = key.fileobj, key.data 
        
        if mask & selectors.EVENT_READ: 
            raw_opcode = self._recvall(sock, 4)
            if not raw_opcode: 
                if not self.primary: 
                    sock.close() 
                    self.sel.unregister(sock)
                    if self.port == PORT3: 
                        self.become_primary("", self.port)
                    else: 
                        self.create_connections("", self.port)
                    return 
                return 
            opcode = struct.unpack('>I', raw_opcode)[0]
            if opcode == NEW_PRIMARY: 
                # get the username and check if they're logged in - if yes, then create an active connections thing with the socket and data 
                print("Receiving a new primary request.")
                username = self._recv_n_args(sock, 1)[0]
                if self.db.is_registered(username) and self.db.is_logged_in(username):
                    data.username = username 
                    self.active_conns[username] = (sock, data)
                sock.sendall(struct.pack('>I', NEW_PRIMARY_ACK))

            elif opcode == LOGIN: 
                username, password = self._recv_n_args(sock, 2)
                if self.db.is_registered(username) and self.db.is_valid_password(username, password): 
                    self.db.login(username)
                    if self.primary: 
                        data.username = username
                        self.active_conns[username] = (sock, data)
                if self.primary: 
                    to_backup = self._pack_n_args(opcode, [username, password])
                    self.lock_until_backups_respond(to_backup)
                sock.sendall(struct.pack('>I', LOGIN_ACK))

            elif opcode == REGISTER: 
                username, password = self._recv_n_args(sock, 2)
                # check to see if that username already exists 
                if not self.db.is_registered(username): 
                    self.db.register(username, password)
                if self.primary: 
                    to_backup = self._pack_n_args(opcode, [username, password])
                    self.lock_until_backups_respond(to_backup) 
                sock.sendall(struct.pack('>I', REGISTER_ACK))
            
            elif opcode == SEND or opcode == SEND_M: 
                raw_uuid = self._recvall(sock, 4)
                uuid = struct.unpack('>I', raw_uuid)[0]
                if not self.primary: 
                    sentto, sentfrom, msg = self._recv_n_args(sock, 3)
                else: 
                    sentto, msg = self._recv_n_args(sock, 2)
                    sentfrom = data.username
                self.db.add_message(uuid, sentto, sentfrom, msg)
                if self.primary:
                    if self.db.is_logged_in(sentto):
                        self.active_conns[sentto][0].sendall(self._pack_n_args(RECEIVE, [sentfrom, msg], uuid))
                    to_backup = self._pack_n_args(SEND, [sentto, sentfrom, msg], uuid)
                    self.lock_until_backups_respond(to_backup)
                sock.sendall(struct.pack('>I', SEND_ACK))

            elif opcode == LOGOUT or opcode == DELETE: 
                if self.primary: 
                    username = data.username 
                else: 
                    username = self._recv_n_args(sock, 1)[0]
                if opcode == LOGOUT: 
                    self.db.logout(username)
                if opcode == DELETE: 
                    self.db.delete(username)
                if self.primary: 
                    self.active_conns.pop(data.username, None)
                    to_backup = self._pack_n_args(opcode, username)
                    self.lock_until_backups_respond(to_backup)
                sock.sendall(struct.pack('>I', DELETE_OR_LOGOUT_ACK))

    def run(self): 
        while True: 
            events = self.sel.select(timeout=None)
            for key, mask in events: 
                if key.data is None: 
                    self.accept_wrapper() 
                else: 
                    self.service_connection(key, mask)

# opcodes deal w now: LOGIN, REGISTER, SEND, LOGOUT, DELETE
# deal with later: LOGOUT, DELETE, FIND

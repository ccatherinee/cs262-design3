import socket 
import selectors
import types 
import struct 
import queue
import re
from constants import *
import mysql.connector
import time

class Log(): 
    def __init__(self, file): 
        self.fr = open(file, "r")
        self.fa = open(file, "a")
    
    def login(self, username): 
        # writes in the log the sql command for updating the users table 
        self.fa.write('UPDATE Users SET logged_in = True WHERE username = "{un}"'.format(un=username)+'\n')
        self.fa.flush()
            
    def register(self, username, password): 
        # writes in the log the sql comand for updating the users table
        self.fa.write('INSERT INTO Users (username, password, logged_in) VALUES ("{un}","{pa}",False)'.format(un=username, pa=password)+'\n')
        self.fa.flush() 

    def send(self, uuid, sentto, sentfrom, msg): 
        # write in the log the sql command for sending the message 
        self.fa.write('INSERT INTO Messages (uuid, sentto, sentfrom, msg) VALUES ({uu},"{st}","{sf}","{msg}")'.format(uu=uuid, st=sentto, sf=sentfrom, msg=msg)+'\n')
        self.fa.flush()

    def del_from_messages_queue(self, uuid): 
        self.fa.write('DELETE FROM Messages_queue WHERE uuid = {uu}'.format(uu=uuid)+'\n')
        self.fa.flush()

    def put_in_messages_queue(self, uuid, sentto, sentfrom, msg):
        self.fa.write('INSERT INTO Messages_queue (uuid, sentto, sentfrom, msg) VALUES ({uu},"{st}","{sf}","{msg}")'.format(uu=uuid, st=sentto, sf=sentfrom, msg=msg)+'\n')
        self.fa.flush()

class Database(): 
    def __init__(self, host, user, password, database, log, autocommit=True): 
        self.db = mysql.connector.connect(
            host=host,
            user=user, 
            password=password, 
            database=database,
            autocommit=autocommit
        )
        self.cursor = self.db.cursor()
        self.log = log
        
    def update_db(self): 
        print("Updating ...")
        while True: 
            sql = self.log.fr.readline().strip()
            if sql == '': break 
            else: self.cursor.execute(sql)

    def is_valid_password(self, username, password): 
        sql = "SELECT password FROM Users WHERE username = '{}'".format(username)
        self.cursor.execute(sql)
        if self.cursor.fetchone()[0] != password: 
            return False
        return True

    def is_registered(self, username): 
        sql = "SELECT username FROM Users WHERE username = '{}'".format(username)
        self.cursor.execute(sql)
        if not self.cursor.fetchone(): 
            return False 
        return True

    def is_logged_in(self, username): 
        sql = "SELECT logged_in FROM Users WHERE username = '{}'".format(username)
        self.cursor.execute(sql)
        if self.cursor.fetchone()[0]:
            return True
        return False

    def get_from_messages_queue(self, username): 
        sql = "SELECT * FROM Messages_queue WHERE sentto = '{}'".format(username, username)
        self.cursor.execute(sql)
        res = self.cursor.fetchall() 
        return res
    
    """
    def load_old_messages(self): 
        # for each message in the database which has user has sentto or sentfrom: 
        # put in the log file (sql for write it to messages queue table)
    """
    
class Server(): 
    def __init__(self, host, port, is_primary, database, file): 
        # initialize listening socket on server that accepts new client connections
        self.port = port 
        self.other_servers = [PORT1, PORT2, PORT3]
        self.other_servers.remove(port) 
        self.primary = is_primary
        self.log = Log(file)
        self.db = Database(DB_HOST, DB_USER, DB_PASSWORD, database, self.log)

        self.sel = selectors.DefaultSelector() 
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
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(30)
        sock.bind((host, port))
        time.sleep(3)
        # try to reach out to both of the other servers, and when it finds the right one register on self.sel selector 
        for port in self.other_servers: 
            print(port, "fabulosa")
            try: 
                sock.connect(("", port))
                # connection with the primary on self.sock
                self.sel.register(sock, selectors.EVENT_READ, data=1)
                return True 
            except ConnectionRefusedError:
                print("big butts")

    def lock_until_backups_respond(self, to_backup): 
        for sock in self.active_backups: 
            sock.sendall(to_backup)
        not_responded = [sock for sock in self.active_backups]
        print(not_responded, self.active_backups, "quarter")
        t_end = time.time() + 10
        while time.time() < t_end and len(not_responded) > 0: 
            events = self.backup_read_sel.select(timeout=1)
            # print("sour cherry", events)
            for key, mask in events: 
                sock, data = key.fileobj, key.data
                if sock in self.active_backups: 
                    print(sock, "blueberry")
                    self._recvall(sock, 4)
                    not_responded.remove(sock)
        print(not_responded, "sunflower")
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
            opcode = struct.unpack('>I', raw_opcode)[0]

            if opcode == LOGIN: 
                username, password = self._recv_n_args(sock, 2)
                if self.db.is_registered(username) and self.db.is_valid_password(username, password): 
                    self.log.login(username)
                    self.db.update_db()
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
                    self.log.register(username, password)
                    self.db.update_db() 
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
                if opcode == SEND_M:
                    self.log.del_from_messages_queue(uuid)

                if self.db.is_logged_in(sentto): 
                    self.log.send(uuid, sentto, sentfrom, msg)
                    if self.primary: 
                        self.active_conns[sentto][0].sendall(self._pack_n_args(RECEIVE, [sentfrom, msg], uuid))
                else: 
                    self.log.put_in_message_queue(uuid, sentto, sentfrom, msg)
                if self.primary: 
                    to_backup = self._pack_n_args(SEND, [sentto, sentfrom, msg], uuid)
                    self.lock_until_backups_respond(to_backup)
                sock.sendall(struct.pack('>I', SEND_ACK))

        if mask & selectors.EVENT_WRITE and data.username != '':
            res = self.db.get_from_messages_queue(data.username)
            while res: 
                uuid, sentto, sentfrom, msg = res.pop() 
                self.log.del_from_messages_queue(uuid)
                self.log.put_in_message_queue(uuid, sentto, sentfrom, msg)
                self.active_conns[sentto][0].sendall(self._pack_n_args(RECEIVE, [sentfrom, msg], uuid))
            
                to_backup = self._pack_n_args(SEND_M, [sentto, sentfrom, msg], uuid)
                self.lock_until_backups_respond(to_backup)

    def run(self): 
        while True: 
            events = self.sel.select(timeout=None)
            for key, mask in events: 
                if key.data is None: 
                    self.accept_wrapper() 
                else: 
                    self.service_connection(key, mask)

# opcodes deal w now: LOGIN, REGISTER, SEND
# deal with later: LOGOUT, DELETE, FIND


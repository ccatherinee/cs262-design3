# GENERAL CONSTANTS
# For hosts, do NOT use "" or "localhost": explicitly write out IP addresses
HOST1, PORT1 = "10.250.124.104", 12334
HOST2, PORT2 = "10.250.21.115", 12335
HOST3, PORT3 = "10.250.21.115", 12336
SERVERS = [(HOST1, PORT1), (HOST2, PORT2), (HOST3, PORT3)]

MAX_LENGTH = 2 ** 8 - 1 # max argument length in wire protocol (e.g., username, password, message, etc.)

# DATABASE CONSTANTS
DB_HOST = "localhost"
DB_USER = "c"
DB_PASSWORD = "c"

# OP CODES (from client to primary server)
LOGIN = 0
REGISTER = 4
LOGOUT = 8
DELETE = 12
SEND = 16
NEW_PRIMARY = 20
FETCH_ALL = 24
FIND = 28

# OP CODES (from primary server to client)
RECEIVE = SEND # from primary server to intended recipient of message (not sender of message)

# OP ACKS (from primary server to client)
SEND_ACK = SEND + 1 # from primary server to sender of message
REGISTER_ACK = REGISTER + 1
LOGIN_ACK = LOGIN + 1
NEW_PRIMARY_ACK = NEW_PRIMARY + 1
LOGOUT_ACK = LOGOUT + 1
DELETE_ACK = DELETE + 1
FETCH_ALL_ACK = FETCH_ALL + 1
FIND_ACK = FIND + 1

# OP ERRORS (from primary server to client)
SEND_ERROR = SEND + 2
REGISTER_ERROR = REGISTER + 2
LOGIN_ERROR = LOGIN + 2

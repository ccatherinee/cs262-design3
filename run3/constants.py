# GENERAL CONSTANTS
# For hosts, do NOT use "" or "localhost": explicitly write out IP addresses
HOST1, PORT1 = "10.250.124.104", 12331
HOST2, PORT2 = "10.250.21.115", 12332
HOST3, PORT3 = "10.250.21.115", 12333
SERVERS = [(HOST1, PORT1), (HOST2, PORT2), (HOST3, PORT3)]

MAX_LENGTH = 2 ** 8 - 1 # max argument length in wire protocol (e.g., username, password, message, etc.)

# DATABASE CONSTANTS
DB_HOST = "localhost"
DB_USER = "c"
DB_PASSWORD = "c"

# OP CODES (from client to primary server)
LOGIN = 4
REGISTER = 8
LOGOUT = 12
DELETE = 16
SEND = 20
NEW_PRIMARY = 24 # First message that client sends to a new PR (to establish its logged in state/connection details)
FETCH_ALL = 28 # Message that client sends after having logged in, to fetch all old message history, for persistence
FIND = 32

# OP CODES (from primary server to client)
RECEIVE = SEND # from primary server to intended recipient of message (not sender of message)

# OP ACKS (from primary server to client): indicate the operation was performed successfully
SEND_ACK = SEND + 1 # from primary server to sender of message
REGISTER_ACK = REGISTER + 1
LOGIN_ACK = LOGIN + 1
NEW_PRIMARY_ACK = NEW_PRIMARY + 1
LOGOUT_ACK = LOGOUT + 1
DELETE_ACK = DELETE + 1
FETCH_ALL_ACK = FETCH_ALL + 1
FIND_ACK = FIND + 1

# OP ERRORS (from primary server to client): indicate the operation errored
SEND_ERROR = SEND + 2
REGISTER_ERROR = REGISTER + 2
LOGIN_ERROR = LOGIN + 2

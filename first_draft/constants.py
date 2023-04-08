# General constants
PORT1 = 11114
PORT2 = 11115
PORT3 = 11116
MAX_LENGTH = 2 ** 10 # max argument length in wire protocol (e.g., username, password, message, etc.)

DB_HOST = "localhost"
DB_USER = "c"
DB_PASSWORD = "c"

# OP CODES (what client sends to server)
LOGIN = 0
REGISTER = 4
SEND = 16

# FROM SERVER TO CLIENT 
RECEIVE = SEND 

# OPERATION ACK
SEND_ACK = SEND + 1
REGISTER_ACK = REGISTER + 1
LOGIN_ACK = LOGIN + 1
SEND_M = SEND + 2
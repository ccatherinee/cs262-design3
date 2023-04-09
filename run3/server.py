import sys
from Classes import Server

if __name__ == '__main__': 
    server_num, is_primary = int(sys.argv[1]), str(sys.argv[2]).lower() == "true"
    Server(server_num, is_primary, "server_" + str(server_num)).run()
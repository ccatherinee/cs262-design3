from Classes import Database
from Classes import Server 
from constants import * 

if __name__ == '__main__': 
    host, port = "", PORT1
    Server(host, port, True, "server_1").run()
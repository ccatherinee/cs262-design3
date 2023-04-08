from Classes import Database
from Classes import Server 
from constants import * 

if __name__ == '__main__': 
    host, port = "", PORT3
    Server(host, port, False, "server_3").run()
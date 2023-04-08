from Classes import Log 
from Classes import Database
from Classes import Server 
from constants import * 

if __name__ == '__main__': 
    host, port = "", PORT3
    file = "/Users/catherinecui/cs262/design3/run/logs/server3_log.txt"
    Server(host, port, False, "server_3", file).run()
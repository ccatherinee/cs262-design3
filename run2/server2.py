from Classes import Log 
from Classes import Database
from Classes import Server 
from constants import * 

if __name__ == '__main__': 
    host, port = "", PORT2
    file = "/Users/catherinecui/cs262/design3/run2/logs/server2_log.txt"
    Server(host, port, False, "server_2", file).run()
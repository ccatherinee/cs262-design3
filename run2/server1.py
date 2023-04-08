from Classes import Log 
from Classes import Database
from Classes import Server 
from constants import * 

if __name__ == '__main__': 
    host, port = "", PORT1
    file = "/Users/catherinecui/cs262/design3/run2/logs/server1_log.txt"
    Server(host, port, True, "server_1", file).run()
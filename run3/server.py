import sys
from Classes import Server

if __name__ == '__main__': 
    # obtain server number and whether the server is the PR or not from command line args
    server_num, is_primary = int(sys.argv[1]), str(sys.argv[2]).lower() == "true"
    server = Server(server_num, is_primary, "server_" + str(server_num))
    try:
        server.run() # run the server
    except KeyboardInterrupt: # try to close appropriate sockets if/when server is shut down via Control-C
        print(f"Keyboard interrupt detected - server {server.num} shutting down")
        if server.primary:
            for socket, _ in server.active_conns.values():
                socket.close()
            for socket in server.active_backups:
                socket.close()
        sys.exit(1)
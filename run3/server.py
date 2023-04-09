import sys, os
from Classes import Server

if __name__ == '__main__': 
    server_num, is_primary = int(sys.argv[1]), str(sys.argv[2]).lower() == "true"
    server = Server(server_num, is_primary, "server_" + str(server_num))
    try:
        server.run()
    except KeyboardInterrupt:
        print(f"Keyboard interrupt detected - server {server.num} shutting down")
        server.sock.close()
        if server.primary:
            for socket, _ in server.active_conns.values():
                socket.close()
        sys.exit(1)
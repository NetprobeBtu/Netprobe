import socket

def main():
    host = "127.0.0.1"
    port = 9000
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind((host, port))
        print(f"Basic UDP Server listening on {host}:{port}...")
        while True:
            try:
                data, addr = sock.recvfrom(65535)
                print(f"Received {len(data)} bytes from {addr}")
            except KeyboardInterrupt:
                break

if __name__ == "__main__":
    main()

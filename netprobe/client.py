import socket
import time

def main():
    host = "127.0.0.1"
    port = 9000
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        print(f"Sending basic UDP packets to {host}:{port}...")
        message = b"NetProbe V1 Basic Test Message."
        for i in range(10):
            sock.sendto(message, (host, port))
            print(f"Sent packet {i+1} ({len(message)} bytes)")
            time.sleep(0.1)

if __name__ == "__main__":
    main()

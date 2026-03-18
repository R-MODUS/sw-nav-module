import socket
import subprocess

def get_ip_address():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip_address = s.getsockname()[0]
    except Exception:
        ip_address = '127.0.0.1'
    finally:
        s.close()
    return ip_address

def get_available_wifi():
    try:
        result = subprocess.check_output(['nmcli', '-t', '-f', 'SSID,SIGNAL', 'dev', 'wifi'], text=True)
        
        networks = []
        for line in result.splitlines():
            if ":" in line:
                ssid, signal = line.split(":")
                if ssid:
                    networks.append({"ssid": ssid, "signal": signal})
        return networks
    except subprocess.CalledProcessError:
        return []

def get_saved_wifi():
    try:
        result = subprocess.check_output(['nmcli', '-t', '-f', 'NAME,TYPE', 'connection', 'show'], text=True)
        
        saved = []
        for line in result.splitlines():
            if ":802-11-wireless" in line:
                name = line.replace(":802-11-wireless", "")
                saved.append(name)
        return saved
    except subprocess.CalledProcessError:
        return []

if __name__ == "__main__":

    ip = get_ip_address()
    print(f"Moje aktuální IP je: {ip}\n")

    print("Dostupné Wi-Fi sítě:")
    for net in get_available_wifi():
        print(f"Síť: {net['ssid']}, Signál: {net['signal']}%")

    print("Uložené Wi-Fi profily:", get_saved_wifi())
    for i, profile in enumerate(get_saved_wifi()):
        print(f"Profil {i}: {profile}")
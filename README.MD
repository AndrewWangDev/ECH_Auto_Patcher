# Exclave ECH Auto-Patcher

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.8%2B-green)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Linux-orange)]()

**A server-side middleware for automating Encrypted Client Hello (ECH) updates for Exclave and V2Ray/Xray-based clients.**

Project URL: [https://github.com/AndrewWangDev/ECH_Auto_Patcher](https://github.com/AndrewWangDev/ECH_Auto_Patcher)

Related Project URL: [https://github.com/dyhkwong/Exclave](https://github.com/dyhkwong/Exclave)

---

## 1. The Challenge: Privacy vs. Connectivity

Hosting services behind **Cloudflare** offers significant protection. To further harden privacy and prevent censorship, enabling **ECH (Encrypted Client Hello)** is essential. Without ECH, the **SNI (Server Name Indication)** remains in plaintext during the TLS handshake, allowing firewalls (like the GFW) to snoop on and block connections based on the domain name.

![ECH Check](ech.png)

However, implementing ECH reliably on mobile clients (specifically **Exclave**, which utilizes V2Ray/Xray cores) presents a dilemma:

1.  **Key Rotation**: To ensure forward secrecy, Cloudflare rotates its ECH Configs (Public Keys) frequently (often hourly).
2.  **Static Configuration Requirement**: Exclave supports advanced transport protocols (VMess + WebSocket + mTLS + Mux + XUDP). To enable these features simultaneously, the client relies on a rigid binary configuration (Protobuf) or specific JSON structure.
3.  **The Conflict**: Exclave does not natively support "Auto-Fetch ECH" logic when using these complex transport configurations. Users are forced to manually look up the ECH key and hardcode it into the client. When Cloudflare rotates the key an hour later, the connection fails.

## 2. Mainstream Solutions (And Why They Fail)

There are two common methods attempted by the community, both of which are suboptimal for this specific use case.

### Method A: Client-Side DoH (DNS over HTTPS)
The client is configured to resolve the ECH keys dynamically via a DoH server before establishing the connection.

**Why it's problematic:**
1.  **Latency Overhead (The "Cold Start" Problem)**:
    * **Standard TLS 1.3**: TCP Handshake (1 RTT) + TLS Handshake (1 RTT) = **2 RTT**.
    * **With Client-Side DoH**:
        * Connect to DoH Server: TCP (1 RTT) + TLS (1 RTT).
        * DNS Query/Response: 1 RTT.
        * **Total**: **5+ RTTs** before the first byte of real data is sent.
    * *Real-world impact*: On a cellular network with 50ms latency, this adds **250ms+** delay to every new connection. Since DNS TTL for ECH is short, this penalty is paid frequently.
2.  **Availability**: Public DoH endpoints (e.g., 1.1.1.1) are frequently blocked or throttled in restrictive regions (e.g., Mainland China). Self-hosting DoH relays adds unnecessary complexity.

### Method B: Host Mapping + Empty ECH Config
The user provides the destination IP (or domain) but leaves the ECH Config field empty, hoping the core will resolve it automatically.

**Why it's problematic:**
1.  **Core Incompatibility**: Not all V2Ray/Xray implementations support this logic, especially when combined with complex transports (e.g., mTLS + WebSocket).
2.  **Exclave Limitation**: Exclave's import parser often fails to generate a valid configuration when advanced fields are mixed with an empty ECH field, resulting in connection failures or ECH being disabled entirely.

## 3. Our Solution: Server-Side Binary Patching

Instead of relying on the client to fetch keys, we shift the burden to the **Server (VPS)**.

This project runs a lightweight Python daemon that:
1.  **Polls**: Queries Cloudflare's DNS for the fresh ECH Config.
2.  **Patches**: Uses a **Fixed-Length Binary Replacement** technique to inject the new key into your Exclave backup file (Protobuf) directly.
3.  **Serves**: Exposes the always-fresh configuration via a local subscription link.


### Architecture

The following diagram illustrates how the server-side patching mechanism ensures zero-latency connections for the client.

![System Architecture Diagram](arch.png)

## 4. Features & Comparison

| Feature | Client-Side DoH (Method A) | Empty ECH Config (Method B) | **ECH Auto-Patcher (This Project)** |
| :--- | :--- | :--- | :--- |
| **Connection Latency** | High (Requires DNS RTT) | Medium (Core Dependent) | **Zero Overhead** (Key is pre-loaded) |
| **Reliability** | Low (DoH Blocking) | Low (Client Compatibility) | **High** (Fetched by VPS) |
| **mTLS/Mux Support** | Varies | Often Fails | **Full Support** |
| **Client Battery** | Higher Drain | Normal | **Lowest Drain** |
| **Setup** | Complex Routing | Simple | **One-time Server Setup** |

## 5. Usage Guide

### Step 1: Client Preparation (Exclave)
1.  Configure your node in Exclave with all desired settings:
    * Protocol: VMess / VLESS
    * Transport: WebSocket + TLS
    * Security: **mTLS** (Client Certificates), **Mux**, **XUDP**
2.  In the **ECH Config** field, enter a **Placeholder String** consisting of **1000 'a' characters**.
    * *Why?* This reserves physical space in the binary file for the script to inject the variable-length ECH key later.
3.  Export the backup to your clipboard.

### Step 2: Server Deployment
1.  Clone this repository:
    ```bash
    git clone [https://github.com/AndrewWangDev/ECH_Auto_Patcher.git](https://github.com/AndrewWangDev/ECH_Auto_Patcher.git)
    cd ECH_Auto_Patcher
    ```
2.  Install dependencies:
    ```bash
    pip3 install -r requirements.txt
    ```
3.  Edit `secure_sub.py`:
    * `RAW_BACKUP_URI`: Paste your exported Exclave string here.
    * `REAL_DOMAIN`: Replace with your actual domain (e.g., `api.yourdomain.com`).
    * `SECRET_PATH`: Define a unique path for your subscription (e.g., `/sub/my-secret-uuid`).
4.  Run the service:
    ```bash
    nohup python3 secure_sub.py > sub_log.txt 2>&1 &
    ```

### Step 3: Client Subscription
1.  Add the subscription link to Exclave:
    `http://<YOUR_VPS_IP>:25500/sub/<YOUR_SECRET_PATH>`
2.  **Important**: Go to Exclave settings and enable **"Update via Proxy"**.
    * *Security Note*: This ensures the subscription update (which contains your mTLS keys) is transmitted over your existing encrypted proxy tunnel, never via plaintext HTTP.

## 6. Security Recommendation

To prevent unauthorized scanning of your subscription port, it is highly recommended to configure `iptables` on your VPS to only allow access from localhost (for the proxy loopback) and your specific public IP.

```bash
# Only allow local proxy to access the subscription service
iptables -A INPUT -s 127.0.0.1 -p tcp --dport 25500 -j ACCEPT
iptables -A INPUT -p tcp --dport 25500 -j DROP
```

## 7. Contributing

Contributions are welcome! If you have ideas for supporting other clients or improving the patching logic, please open an issue or submit a Pull Request.

## 8. License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
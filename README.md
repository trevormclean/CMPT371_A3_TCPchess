# **CMPT 371 A3 Socket Programming `OnlineChess`**

**Course:** CMPT 371 \- Data Communications & Networking  
**Instructor:** Mirza Zaeem Baig  
**Semester:** Spring 2026  
<span style="color: purple;">***RUBRIC NOTE: As per submission guidelines, only one group member will submit the link to this repository on Canvas.***

## **Group Members**

| Name | Student ID | Email |
| :---- | :---- | :---- |
| Angad Hundal | 301590384 | ash32@sfu.ca |
| John Smith | 301222222 | john.smith@university.edu |

## **1\. Project Overview & Description**

This project is a multiplayer Chess game built using Python's Socket API (TCP) and a `pygame` graphical user interface. It allows two clients to connect to a central server and play against each other in real time.

The server acts as the authoritative source of truth for the match. It validates all incoming moves using the shared chess logic, applies only legal moves, and broadcasts approved updates back to both clients. This helps keep both players synchronized and prevents clients from making unauthorized or illegal moves. The project supports standard chess rules including promotion, castling, en passant, check, checkmate, and stalemate.

## **2\. System Limitations & Edge Cases**

As required by the project specifications, we identified and handled (or explicitly defined) the following limitations and edge cases within our application scope:

* **Handling Two Networked Players:**  
  * <span style="color: green;">*Solution:*</span> The server accepts TCP connections, stores incoming clients in a matchmaking queue, and starts a dedicated game session thread once two players are available. This allows each match to run independently without blocking the main server listener.  
  * <span style="color: red;">*Limitation:*</span> Our design is intended for lightweight class-project use. While multiple sessions are possible, the threading model is not optimized for large-scale deployment.

* **TCP Stream Buffering:**  
  * <span style="color: green;">*Solution:*</span> Because TCP is a byte stream rather than a message-based protocol, our application uses newline-delimited JSON. Each message is sent as one JSON object followed by `\n`, and incoming data is split on that delimiter before parsing.

* **Server-Side Move Validation:**  
  * <span style="color: green;">*Solution:*</span> The server validates each incoming move against the authoritative board state before applying it. Illegal moves are rejected and an error message is sent back to the client. This follows a single-source-of-truth design similar to a real multiplayer game server.

* **Client Synchronization:**  
  * <span style="color: red;">*Limitation:*</span> The server currently broadcasts the latest approved move and game status rather than a full serialized board snapshot every turn. This is sufficient if both clients remain synchronized, but it is less robust than transmitting the full board state each update.

* **New Game / Rematch Support:**  
  * <span style="color: red;">*Limitation:*</span> The original GUI includes a local "New Game" button, but in the networked version a full rematch protocol was not implemented on the server. As a result, restarting a game online is not fully supported unless both clients and the server are reset.

* **Disconnect Handling:**  
  * <span style="color: green;">*Solution:*</span> If one player disconnects during their turn, the server ends the session and awards the win to the other player.

## **3\. Video Demo**

<span style="color: purple;">***RUBRIC NOTE: Include a clickable link.***</span>  
Our 2-minute video demonstration covering connection establishment, data exchange, real-time gameplay, and process termination can be viewed below:  
[**▶️ Watch Project Demo on YouTube**](https://www.youtube.com/watch?v=dQw4w9WgXcQ)

## **4\. Prerequisites (Fresh Environment)**

To run this project, you need:

* **Python 3.10** or higher  
* **pygame** installed  
* The provided chess piece image assets in an `img/` folder next to `gui.py`

Install `pygame` with:

```bash
pip install pygame
```

## **5\. Step-by-Step Run Guide**

<span style="color: purple;">***RUBRIC NOTE: The grader must be able to copy-paste these commands.***</span>


### **Step 1: Start the Server**
Open your terminal and navigate to the project root folder. The server binds to `127.0.0.1` on port `5050`.
```bash
python src/server.py
# Console output: "[STARTING] Chess server listening on 127.0.0.1:5050"
```
 
### **Step 2: Connect Player 1**
Open a **new** terminal window (keep the server running). Launch the GUI client for the first player.
```bash
python src/gui.py
# A pygame window will open for Player 1.
```
 
### **Step 3: Connect Player 2**
Open a **third** terminal window. Launch the GUI client again for the second player.
```bash
python src/gui.py
# A second pygame window will open for Player 2.
```
Once both clients connect, the server terminal will show:
```
[QUEUE] Player added from ('127.0.0.1', PORT). Queue size: 1
[QUEUE] Player added from ('127.0.0.1', PORT). Queue size: 2
[MATCH] 2 players found. Starting chess session.
```
 
### **Step 4: Gameplay**
1. The server assigns one client **White** and the other **Black**.
2. **White moves first** — click a piece, then click its destination square.
3. The client sends the move to the server, which validates it against the authoritative board state.
4. If legal, the server applies the move and broadcasts it to both clients, keeping both boards in sync.
5. The game continues until it ends by **checkmate**, **stalemate**, **resignation**, or **disconnect**.
 
### **Step 5: Closing the Program**
To stop the server, return to the server terminal and press `Ctrl + C`.
```bash
^C
# Shuts down the chess server
```
> **Note:** Closing a client window during an active match is treated as a disconnect and will end the game.

## 6\. Technical Protocol Details (JSON over TCP)
 
We designed a custom application-layer protocol using newline-delimited JSON over TCP.
 
### **Handshake Phase**
 
Client sends:
```json
{"type": "CONNECT"}
```
Server responds:
```json
{"type": "WELCOME", "color": "white"}
```
or
```json
{"type": "WELCOME", "color": "black"}
```
 
### **Gameplay Phase**
 
Client sends a move request:
```json
{"type": "MOVE", "move": {"start": [1, 4], "end": [3, 4], "promotion": null, "en_passant": false, "kside_castle": false, "qside_castle": false}}
```
Server broadcasts updated state:
```json
{"type": "STATE", "turn": "black", "status": "ongoing", "winner": null, "last_move": {"start": [1, 4], "end": [3, 4], "promotion": null, "en_passant": false, "kside_castle": false, "qside_castle": false}}
```
 
### **Other Messages**
 
Resignation:
```json
{"type": "RESIGN"}
```
Illegal move / invalid request:
```json
{"type": "ERROR", "message": "Illegal move"}
```
Game over:
```json
{"type": "GAME_OVER", "status": "checkmate", "winner": "white"}
```
 
---
 
## 7\. **Academic Integrity & References**
 
### **Code Origin**
- The chess board logic and GUI were developed as part of the group project.
- The socket/server-client structure was inspired by the course socket programming examples and adapted to support a multiplayer chess game.
 
### **GenAI Usage**
- ChatGPT was used to help explain networking design decisions, organize message formats, and refine documentation/comments.
 
### **References**
- [CMPT371_A3_Socket_Programming by Miriam Bebawy](https://github.com/mariam-bebawy/CMPT371_A3_Socket_Programming)
 

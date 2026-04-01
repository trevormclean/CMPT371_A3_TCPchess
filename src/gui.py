"""gui.py runs the chess GUI"""
import sys
import os
import pygame
from board import Board, Move, WHITE, BLACK, Pawn, Rook, Bishop, Knight, Queen, King
from network import NetworkClient, dict_to_move, SERVER_TO_LOCAL_COLOR

# constants __________________________________________________________________
SQ = 80 # side length of a square
BOARD_PX = SQ * 8 # board width
SIDEBAR = 160 # sidebar width (new game / surrender buttons)
WIN_W = BOARD_PX + SIDEBAR # window width
WIN_H = BOARD_PX # window height

# colors
LIGHT = (240, 217, 181) # light square
DARK = (181, 136, 99) # dark square
SEL = (247, 247, 105) # selected square
MOVE_COL = (106, 135, 75) # legal-move dot / ring
CHECK = (220, 50, 50) # king-in-check square
OVERLAY = (0, 0, 0, 150) # overlay for piece promotion
PANEL_BG = (30, 30, 30) # background for piece promotion panel
SIDEBAR_BG = (40, 40, 40) # sidebar background
BTN_NORMAL = (70, 70, 70) # default button color
BTN_HOVER = (100, 100, 100) # hover color
BTN_DISABLED = (50, 50, 50) # disabled button color
BTN_TEXT = (220, 220, 220) # default button text color
BTN_TEXT_DISABLED = (100, 100, 100) # disabled button text color

# piece images
_PIECE_DIR = os.path.join(os.path.dirname(__file__), "img")
_PIECE_KEYS: dict[tuple[str, type], str] = {
    (WHITE, Pawn): "wP", (WHITE, Rook): "wR", (WHITE, Bishop): "wB",
    (WHITE, Knight): "wN", (WHITE, Queen): "wQ", (WHITE, King): "wK",
    (BLACK, Pawn): "bP", (BLACK, Rook): "bR", (BLACK, Bishop): "bB",
    (BLACK, Knight): "bN", (BLACK, Queen): "bQ", (BLACK, King): "bK",
}

PROMO_CHOICES = (Queen, Rook, Bishop, Knight)


class Button:
  def __init__(self, label: str, x: int, y: int, w: int, h: int):
    self.label = label
    self.rect = pygame.Rect(x, y, w, h)
    self.enabled = True

  def draw(self, screen: pygame.Surface, font: pygame.font.Font):
    if not self.enabled:
      color = BTN_DISABLED
      text_col = BTN_TEXT_DISABLED
    elif self.rect.collidepoint(pygame.mouse.get_pos()):
      color = BTN_HOVER
      text_col = BTN_TEXT
    else:
      color = BTN_NORMAL
      text_col = BTN_TEXT
    pygame.draw.rect(screen, color, self.rect, border_radius=6)
    surf = font.render(self.label, True, text_col)
    screen.blit(surf, (
      self.rect.centerx - surf.get_width() // 2,
      self.rect.centery - surf.get_height() // 2,
    ))

  def is_clicked(self, pos: tuple[int, int]) -> bool:
    return self.enabled and self.rect.collidepoint(pos)


class ChessGUI:
  def __init__(self):
    pygame.init()
    self.screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Chess")
    self.ui_font = pygame.font.SysFont("arial, helvetica", 22)
    self.piece_imgs = self._load_piece_images()

    self.board = Board()
    
    # Create the client-side network connection and immediately connect to the server.
    # This GUI will receive its assigned color (WHITE or BLACK) after connecting.
    self.network = NetworkClient()
    self.network.connect()
    self.online = True

    # When networking is added, set this to WHITE or BLACK for each client.
    # None means both sides are played locally.
    self.local_color: str | None = None
    self.surrendered: bool = False

    self.selected: tuple[int, int] | None = None # square of the selected piece
    self.legal_moves: list[Move] = [] # legal moves for the selected piece
    self.promo_pending: list[Move] | None = None # stores pawn promotion candidates
    self.status: str = ""

    bx = BOARD_PX + (SIDEBAR - 120) // 2  # horizontally center buttons in sidebar
    self.btn_surrender = Button("Surrender", bx, 40, 120, 40)
    self.btn_new_game  = Button("New Game",  bx, 100, 120, 40)

  def _load_piece_images(self) -> dict[tuple[str, type], pygame.Surface]:
    """Loads piece PNGs from img/ and scales them to SQ x SQ."""
    imgs: dict[tuple[str, type], pygame.Surface] = {}
    for key, name in _PIECE_KEYS.items():
      path = os.path.join(_PIECE_DIR, f"{name}.png")
      if not os.path.exists(path):
        raise FileNotFoundError(
          f"Missing piece image: {path}\n"
          "Place the 12 PNGs (wP.png … bK.png) in an img/ folder next to gui.py."
        )
      imgs[key] = pygame.transform.smoothscale(
        pygame.image.load(path).convert_alpha(), (SQ, SQ)
      )
    return imgs

  def sq_to_px(self, row: int, col: int) -> tuple[int, int]:
    """Given a square, returns the top left pixel's coordinates"""
    if self.local_color == BLACK:
        return (7 - col) * SQ, row * SQ
    return col * SQ, (7 - row) * SQ

  def px_to_sq(self, x: int, y: int) -> tuple[int, int]:
    """Given pixel's coordinates, returns the square"""
    if self.local_color == BLACK:
        return y // SQ, 7 - x // SQ
    return 7 - y // SQ, x // SQ

  def draw_board(self):
    """Draw the chess board, including the legal moves for a selected piece"""
    move_ends = {m.end for m in self.legal_moves}

    check_sq = None
    if self.board.in_check(self.board.turn):
      for r in range(8):
        for c in range(8):
          p = self.board.grid[r][c]
          if isinstance(p, King) and p.color == self.board.turn:
            check_sq = (r, c)
            break

    for row in range(8):
      for col in range(8):
        x, y = self.sq_to_px(row, col)
        color = LIGHT if (row + col) % 2 == 0 else DARK

        if (row, col) == self.selected: color = SEL
        elif (row, col) == check_sq: color = CHECK

        pygame.draw.rect(self.screen, color, (x, y, SQ, SQ))

        if (row, col) in move_ends:
          if self.board.grid[row][col] is not None:
            pygame.draw.rect(self.screen, MOVE_COL, (x, y, SQ, SQ), 5)
          else:
            pygame.draw.circle(self.screen, MOVE_COL, (x + SQ // 2, y + SQ // 2), SQ // 6)

  def draw_pieces(self):
    """Draw the pieces on the board"""
    for row in range(8):
      for col in range(8):
        piece = self.board.grid[row][col]
        if piece is None:
          continue
        x, y = self.sq_to_px(row, col)
        self.screen.blit(self.piece_imgs[(piece.color, type(piece))], (x, y))

  def draw_promo_overlay(self):
    """Dim the board and show promotion options"""
    dim = pygame.Surface((BOARD_PX, BOARD_PX), pygame.SRCALPHA)
    dim.fill(OVERLAY)
    self.screen.blit(dim, (0, 0))

    color = self.board.grid[self.promo_pending[0].start[0]][self.promo_pending[0].start[1]].color

    panel_w = SQ * 4
    px = (BOARD_PX - panel_w) // 2
    py = (BOARD_PX - SQ) // 2

    pygame.draw.rect(self.screen, PANEL_BG, (px - 6, py - 6, panel_w + 12, SQ + 12))

    for i, p in enumerate(PROMO_CHOICES):
      sx = px + i * SQ
      bg = LIGHT if i % 2 == 0 else DARK
      pygame.draw.rect(self.screen, bg, (sx, py, SQ, SQ))
      self.screen.blit(self.piece_imgs[(color, p)], (sx, py))

  def draw_status(self):
    """Draw the game status (check, checkmate, etc.)"""
    if not self.status:
      return
    surf = self.ui_font.render(self.status, True, (255, 255, 255))
    bg = pygame.Surface((surf.get_width() + 20, surf.get_height() + 10), pygame.SRCALPHA)
    bg.fill((0, 0, 0, 170))
    self.screen.blit(bg, (BOARD_PX // 2 - bg.get_width() // 2, 8))
    self.screen.blit(surf, (BOARD_PX // 2 - surf.get_width() // 2, 13))

  def draw_sidebar(self):
    """Draw the sidebar with surrender / new game buttons"""
    pygame.draw.rect(self.screen, SIDEBAR_BG, (BOARD_PX, 0, SIDEBAR, WIN_H))

    game_over = self.board.is_game_over() or self.surrendered
    self.btn_surrender.enabled = not game_over
    self.btn_new_game.enabled  = game_over

    self.btn_surrender.draw(self.screen, self.ui_font)
    self.btn_new_game.draw(self.screen, self.ui_font)

  def draw(self):
    self.draw_board()
    self.draw_pieces()
    if self.promo_pending:
      self.draw_promo_overlay()
    self.draw_status()
    self.draw_sidebar()
    pygame.display.flip()

  # Input handling _______________________________________________________________
  def board_click(self, x: int, y: int):
    # In online mode, do not apply the move locally right away.
    # Send it to the server first; the server will validate it and broadcast
    # the accepted move back to both clients.
    row, col = self.px_to_sq(x, y)
    if not (0 <= row < 8 and 0 <= col < 8):
      return

    if self.selected is None:
      self.select(row, col) # try selecting the piece
      return

    # can't play move if not your turn
    piece = self.board.grid[self.selected[0]][self.selected[1]]
    if piece.color != self.board.turn: 
      self.select(row, col)
      return

    # all possible promotions
    promo_moves = [m for m in self.legal_moves if m.end == (row, col) and m.promotion is not None]

    move = None
    for m in self.legal_moves:
      if m.end == (row, col) and m.promotion is None:
        move = m

    if promo_moves:
      self.promo_pending = promo_moves
      self.selected = None
      self.legal_moves = []
      return

    if move is not None:
      if self.online:
        self.network.send_move(move)
      else:
        self.board.apply_move(move)
        self.update_status()
      self.selected = None
      self.legal_moves = []
      return

    # clicked on a square the selected piece can't move to
    self.select(row, col)
    
  def promo_click(self, x: int, y: int):
    """Handle a click on the promotion panel"""
    panel_w = SQ * 4
    px = (BOARD_PX - panel_w) // 2
    py = (BOARD_PX - SQ) // 2

    # if clicked outside the panel
    if not (px <= x < px + panel_w and py <= y < py + SQ):
      return

    # determine which promotion piece was chosen
    i = (x - px) // SQ
    if not 0 <= i < 4:
      return
    chosen = PROMO_CHOICES[i]

    # apply the promotion move
    move = None
    for m in self.promo_pending:
      if m.promotion == chosen:
        move = m
    self.promo_pending = None
    if self.online:
      self.network.send_move(move)
    else:
      self.board.apply_move(move)
      self.update_status()

  def select(self, row: int, col: int):
    """Tries to select the piece at (row, col)"""
    piece = self.board.grid[row][col]
    if piece is None or (row, col) == self.selected or \
        (self.local_color is None and piece.color != self.board.turn) or \
        (self.local_color is not None and piece.color != self.local_color):
      self.selected = None
      self.legal_moves = []
    else:
      self.selected = (row, col)
      self.legal_moves = self.board.get_legal_moves(row, col)

  def update_status(self):
    """Update the game status (check, checkmate, stalemate)"""
    if self.board.is_checkmate():
      winner = "White" if self.board.turn == BLACK else "Black"
      self.status = f"Checkmate — {winner} wins"
    elif self.board.is_stalemate():
      self.status = "Stalemate — draw"
    elif self.board.in_check(self.board.turn):
      self.status = "Check"
    else:
      self.status = ""

  def process_network_messages(self):
    """Drain and handle any pending network messages.

    Called once per frame from the main loop; processes all queued messages so
    the UI/board state stays in sync with the server.
    """
    while True:
      # Poll until the network queue is empty (non-blocking).
      msg = self.network.poll_message()
      if msg is None:
        break

      if msg["type"] == "WELCOME":
        # Server assigns our side (white/black) when we connect.
        self.local_color = SERVER_TO_LOCAL_COLOR[msg["color"]]

      elif msg["type"] == "STATE":
        # Full/partial state update; apply the last move if provided.
        last = msg.get("last_move")
        if last is not None:
          move = dict_to_move(last)
          self.board.apply_move(move)
        self.update_status()

      elif msg["type"] == "GAME_OVER":
        # Terminal game state (resign, disconnect, checkmate, stalemate).
        status = msg["status"]
        winner = msg.get("winner")
        if status == "resign":
          self.status = f"{winner.capitalize()} wins by resignation"
        elif status == "disconnect":
          self.status = f"{winner.capitalize()} wins by disconnect"
        elif status == "checkmate":
          self.status = f"Checkmate — {winner.capitalize()} wins"
        elif status == "stalemate":
          self.status = "Stalemate — draw"
        self.surrendered = True

      elif msg["type"] == "ERROR":
        # Display server-side validation/connection errors in the status bar.
        self.status = msg["message"]

      elif msg["type"] == "DISCONNECT":
        # Connection dropped unexpectedly; freeze the game.
        self.status = "Disconnected from server"
        self.surrendered = True

  def new_game(self):
    """Resets the board and all GUI state"""
    self.board = Board()
    self.selected = None
    self.legal_moves = []
    self.promo_pending = None
    self.status = ""
    self.surrendered = False

  def surrender(self):
    """Ends the game, awarding the win to the opponent"""
    # In online mode, the server must be told about the resignation so it 
    # can notify both players and officially end the game.
    if self.online:
      self.network.send_resign()
    else:
      winner = "Black" if self.board.turn == WHITE else "White"
      self.status = f"{winner} wins by resignation"
      self.surrendered = True

  # Main loop ___________________________________________________________________
  def run(self):
    """Runs the main game loop"""
    clock = pygame.time.Clock()
    while True:
      # Process any pending messages from the server before handling user input.
      # This keeps the GUI updated with opponent moves and game-over messages.

      self.process_network_messages()
      
      for event in pygame.event.get():
        if event.type == pygame.QUIT:
          pygame.quit()
          sys.exit()

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
          x, y = event.pos

          if self.btn_new_game.is_clicked((x, y)):
            self.new_game()
            continue
          if self.btn_surrender.is_clicked((x, y)):
            self.surrender()
            continue

          game_over = self.board.is_game_over() or self.surrendered
          if x < BOARD_PX and not game_over:
            if self.promo_pending:
              self.promo_click(x, y)
            else:
              self.board_click(x, y)

      self.draw()
      clock.tick(60)

if __name__ == "__main__":
  ChessGUI().run()
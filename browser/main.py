import tkinter
import socket
import ssl

WIDTH, HEIGHT = 800, 600 # キャンバス全体の幅と高さ．
HSTEP, VSTEP = 13, 18 # 画面上の1文字の幅と高さ．
SCROLL_STEP = 100 # 1回の画面スクロールで座標が移動する距離．

class URL:
    def __init__(self, url: str):
        # URL のパース．
        self.scheme, url = url.split("://", 1)
        assert self.scheme in ["http", "https"]

        if self.scheme == "http":
            self.port = 80
        elif self.scheme == "https":
            self.port = 443

        if "/" not in url:
            url = url + "/"

        self.host, url = url.split("/", 1)
        self.path = "/" + url

        if ":" in self.host:
            # http://example.org:8080/ のようなカスタムポートに対応．
            self.host, port = self.host.split(":", 1)
            self.port = int(port)

    def request(self):
        # ソケットの作成．
        s = socket.socket(
            family=socket.AF_INET, # アドレスファミリー（＝ 他のコンピュータを見つける方法）．INET（＝ IPv4 を使用）．
            type=socket.SOCK_STREAM, # ソケットタイプ（＝ 行われる会話の種類）．STREAM（＝ 任意の量のデータを送信できる）．
            proto=socket.IPPROTO_TCP, # プロトコル（＝ 2台のコンピュータが接続を確立する方法）．
        )
        s.connect((self.host, self.port))
        if self.scheme == "https":
            ctx = ssl.create_default_context()
            s = ctx.wrap_socket(s, server_hostname=self.host)

        # リクエストの送信．
        request = "GET {} HTTP/1.0\r\n".format(self.path)
        request += "Host: {}\r\n".format(self.host)
        request += "\r\n"
        s.send(request.encode("utf8"))

        # レスポンスの受信．
        response = s.makefile("r", encoding="utf8", newline="\r\n") # レスポンスのバイトストリームを1つのファイルオブジェクトにまとめて返す．

        # レスポンスのパース（1行目）．
        statusline = response.readline()
        version, status, explanation = statusline.split(" ", 2)

        # レスポンスのパース（ヘッダー）．
        response_headers = {}
        while True:
            line = response.readline()
            if line == "\r\n": break
            header, value = line.split(":", 1)
            response_headers[header.casefold()] = value.strip() # casefold(): 小文字に正規化．strip(): 前後の空白を削除．

        assert "transfer-encoding" not in response_headers
        assert "content-encoding" not in response_headers

        # レスポンスのパース（ボディ）．
        content = response.read()
        s.close()

        return content

class Browser:
    def __init__(self):
        self.window = tkinter.Tk()
        self.canvas = tkinter.Canvas(
            self.window,
            width=WIDTH,
            height=HEIGHT
        )
        self.canvas.pack()
        self.scroll = 0
        self.window.bind("<Down>", self.scrolldown) # 下矢印キーがクリックされたら，scrolldown メソッドが呼ばれる．

    def draw(self):
        """
        テキストの画面座標（ref. layout()）を決定し，画面（キャンバス）に描画する．
        """
        self.canvas.delete("all") # 再描画時のためにまずキャンバスをクリア．
        for x, y, c in self.display_list:
            self.canvas.create_text(x, y - self.scroll, text=c) # 左上が（0,0）右下が（x,y）となる座標系．

    def load(self, url: URL):
        body = url.request()
        text = lex(body)
        self.display_list = layout(text)
        self.draw()

    def scrolldown(self, e):
        self.scroll += SCROLL_STEP
        self.draw() # 再描画

def lex(body):
    text = ""
    in_tag = False
    for c in body:
        if c == "<":
            in_tag = True
        elif c == ">":
            in_tag = False
        elif not in_tag:
            text += c
    return text

def layout(text):
    """
    テキストのページ座標を決定する．

    ページ座標：Webページ全体における位置座標
    画面座標：画面（フレーム）内における位置座標

    e.g. ページ座標(y) 123 ピクセルの位置のテキストが 30 ピクセル下にスクロールされた場合の画面座標(y)は 93 ピクセル．
    """
    display_list = [] # 各文字のページ座標のリスト．
    cursor_x, cursor_y = HSTEP, VSTEP
    for c in text:
        display_list.append((cursor_x, cursor_y, c))
        cursor_x += HSTEP
        if cursor_x >= WIDTH - HSTEP:
            # 折り返し
            cursor_y += VSTEP
            cursor_x = HSTEP
    return display_list

if __name__ == "__main__":
    import sys
    Browser().load(URL(sys.argv[1]))
    tkinter.mainloop()
